"""Repository Analysis Service.

Provides secure file system access for code analysis capabilities.
Supports reading files, listing directories, and searching code.

Security:
- Path validation prevents directory traversal attacks
- Configurable allowed directories (REPOSITORY_PATHS)
- Binary file detection
- Size limits prevent reading huge files
- Sensitive file filtering (.env, credentials, etc.)

Requires LOCAL or higher permission level.
"""

import os
import re
import fnmatch
import logging
import mimetypes
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Patterns for sensitive files that should never be read
SENSITIVE_FILE_PATTERNS = [
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.crt",
    "*credentials*",
    "*secrets*",
    "*password*",
    "*.sqlite*",  # May contain sensitive data
    ".git/config",  # May contain credentials
    ".npmrc",  # May contain tokens
    ".pypirc",  # May contain tokens
    "id_rsa*",
    "id_dsa*",
    "id_ed25519*",
]

# File extensions typically considered binary
BINARY_EXTENSIONS = {
    ".exe", ".dll", ".so", ".dylib", ".o", ".a",
    ".pyc", ".pyo", ".class", ".jar",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".mp3", ".mp4", ".avi", ".mov", ".mkv", ".webm", ".wav", ".flac",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".db", ".sqlite", ".sqlite3",
}


@dataclass
class FileInfo:
    """Information about a file."""
    path: str
    name: str
    is_file: bool
    is_directory: bool
    size: int
    extension: str


@dataclass
class SearchMatch:
    """A code search match."""
    file: str
    line_number: int
    line: str
    context_before: list[str]
    context_after: list[str]


class RepositoryService:
    """Service for repository analysis operations.

    All operations validate paths against allowed directories
    and check for sensitive files.
    """

    # Default configuration
    DEFAULT_MAX_FILE_SIZE = 1024 * 1024  # 1 MB
    DEFAULT_MAX_LINE_LENGTH = 2000  # Truncate long lines
    DEFAULT_MAX_SEARCH_RESULTS = 100
    DEFAULT_MAX_LIST_DEPTH = 10

    def __init__(
        self,
        allowed_paths: Optional[list[str]] = None,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
        max_line_length: int = DEFAULT_MAX_LINE_LENGTH,
    ):
        """Initialize repository service.

        Args:
            allowed_paths: List of directories that can be accessed.
                          If None, defaults to Genesis project root.
            max_file_size: Maximum file size to read (bytes)
            max_line_length: Maximum line length before truncation
        """
        self.max_file_size = max_file_size
        self.max_line_length = max_line_length

        if allowed_paths:
            self._allowed_paths = [Path(p).resolve() for p in allowed_paths]
        else:
            # Default to Genesis project root
            genesis_root = Path(__file__).parent.parent.parent.parent.resolve()
            self._allowed_paths = [genesis_root]

        logger.info(f"RepositoryService initialized with allowed paths: {self._allowed_paths}")

    def _is_path_allowed(self, path: Path) -> bool:
        """Check if a path is within allowed directories.

        Uses resolve() to handle symlinks and ../ traversal attempts.
        """
        resolved = path.resolve()
        return any(
            resolved == allowed or self._is_subpath(resolved, allowed)
            for allowed in self._allowed_paths
        )

    def _is_subpath(self, path: Path, parent: Path) -> bool:
        """Check if path is a subpath of parent (safely)."""
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False

    def _is_sensitive_file(self, path: Path) -> bool:
        """Check if file matches sensitive file patterns."""
        name = path.name.lower()
        path_str = str(path).lower()

        for pattern in SENSITIVE_FILE_PATTERNS:
            if fnmatch.fnmatch(name, pattern.lower()):
                return True
            # Also check if pattern appears in path (for .git/config etc)
            if "/" in pattern and pattern.lower() in path_str:
                return True

        return False

    def _is_binary_file(self, path: Path) -> bool:
        """Check if file is likely binary based on extension or content."""
        # Check extension first (fast)
        if path.suffix.lower() in BINARY_EXTENSIONS:
            return True

        # Extensions that are definitely text (override MIME type)
        TEXT_EXTENSIONS = {
            ".ts", ".tsx", ".jsx", ".mjs", ".cjs",  # TypeScript/modern JS
            ".vue", ".svelte",  # Frontend frameworks
            ".yaml", ".yml", ".toml",  # Config formats
            ".rs", ".go", ".rb", ".php", ".java", ".kt", ".swift",  # Languages
            ".c", ".cpp", ".h", ".hpp", ".cc",  # C/C++
            ".sh", ".bash", ".zsh", ".fish",  # Shell scripts
            ".sql", ".graphql", ".proto",  # Query/schema languages
            ".env.example", ".env.template",  # Example env files (not sensitive)
            ".gitignore", ".dockerignore", ".editorconfig",  # Config files
            ".lock",  # Lock files (often large but text)
        }
        if path.suffix.lower() in TEXT_EXTENSIONS:
            return False

        # Check MIME type
        mime_type, _ = mimetypes.guess_type(str(path))
        if mime_type:
            if not mime_type.startswith("text/") and mime_type not in [
                "application/json",
                "application/javascript",
                "application/xml",
                "application/x-sh",
                "application/x-python",
                "application/yaml",
            ]:
                return True

        # Sample file content for null bytes (slow but accurate)
        try:
            with open(path, "rb") as f:
                sample = f.read(8192)
                if b"\x00" in sample:
                    return True
        except (IOError, OSError):
            pass

        return False

    def _truncate_line(self, line: str) -> str:
        """Truncate line if too long."""
        if len(line) > self.max_line_length:
            return line[:self.max_line_length] + f"... [truncated, {len(line)} chars total]"
        return line

    def validate_path(self, file_path: str) -> tuple[bool, str, Optional[Path]]:
        """Validate a file path for safety.

        Returns:
            Tuple of (is_valid, error_message, resolved_path)
        """
        try:
            path = Path(file_path).resolve()
        except Exception as e:
            return False, f"Invalid path: {e}", None

        if not self._is_path_allowed(path):
            return False, f"Path not in allowed directories: {file_path}", None

        if self._is_sensitive_file(path):
            return False, f"Access denied: sensitive file pattern: {path.name}", None

        return True, "", path

    def read_file(
        self,
        file_path: str,
        max_length: Optional[int] = None,
        start_line: int = 1,
        end_line: Optional[int] = None,
    ) -> dict:
        """Read contents of a file.

        Args:
            file_path: Path to file (absolute or relative to allowed path)
            max_length: Maximum characters to return (None = no limit up to max_file_size)
            start_line: First line to read (1-indexed)
            end_line: Last line to read (None = to end)

        Returns:
            Dict with:
            - success: bool
            - content: str (if success)
            - path: str - resolved path
            - lines: int - total line count
            - truncated: bool - whether content was truncated
            - error: str (if not success)
        """
        # Validate path
        is_valid, error, path = self.validate_path(file_path)
        if not is_valid:
            logger.warning(f"read_file denied: {error}")
            return {"success": False, "error": error}

        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        if not path.is_file():
            return {"success": False, "error": f"Not a file: {file_path}"}

        # Check file size
        file_size = path.stat().st_size
        if file_size > self.max_file_size:
            return {
                "success": False,
                "error": f"File too large: {file_size:,} bytes (max: {self.max_file_size:,})"
            }

        # Check if binary
        if self._is_binary_file(path):
            return {
                "success": False,
                "error": f"Binary file: {path.suffix or 'unknown type'}. Use appropriate tools for binary files."
            }

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)

            # Handle line range
            start_idx = max(0, start_line - 1)  # Convert to 0-indexed
            end_idx = end_line if end_line else total_lines

            selected_lines = lines[start_idx:end_idx]
            content = "".join(selected_lines)

            # Apply truncation
            truncated = False
            effective_max = max_length or self.max_file_size
            if len(content) > effective_max:
                content = content[:effective_max]
                truncated = True

            # Truncate individual long lines
            content_lines = content.split("\n")
            content_lines = [self._truncate_line(line) for line in content_lines]
            content = "\n".join(content_lines)

            logger.info(f"read_file: {path}, {total_lines} lines, {len(content)} chars")

            return {
                "success": True,
                "content": content,
                "path": str(path),
                "lines": total_lines,
                "truncated": truncated,
                "start_line": start_line,
                "end_line": min(end_line or total_lines, total_lines),
            }

        except UnicodeDecodeError:
            return {"success": False, "error": "File encoding error: not valid UTF-8"}
        except Exception as e:
            logger.error(f"read_file error: {e}")
            return {"success": False, "error": f"Error reading file: {e}"}

    def list_files(
        self,
        directory: str,
        pattern: str = "*",
        recursive: bool = False,
        max_depth: Optional[int] = None,
        include_hidden: bool = False,
    ) -> dict:
        """List files in a directory.

        Args:
            directory: Directory path to list
            pattern: Glob pattern (e.g., "*.py", "**/*.ts")
            recursive: Whether to search subdirectories
            max_depth: Maximum directory depth (None = no limit)
            include_hidden: Include hidden files/directories (starting with .)

        Returns:
            Dict with:
            - success: bool
            - files: list[FileInfo] (if success)
            - total: int - number of results
            - truncated: bool - if results were truncated
            - error: str (if not success)
        """
        # Validate path
        is_valid, error, dir_path = self.validate_path(directory)
        if not is_valid:
            logger.warning(f"list_files denied: {error}")
            return {"success": False, "error": error}

        if not dir_path.exists():
            return {"success": False, "error": f"Directory not found: {directory}"}

        if not dir_path.is_dir():
            return {"success": False, "error": f"Not a directory: {directory}"}

        try:
            files = []
            max_results = 1000  # Prevent huge listings
            effective_depth = max_depth or self.DEFAULT_MAX_LIST_DEPTH

            def process_path(p: Path, current_depth: int):
                """Process a path and add to results."""
                if len(files) >= max_results:
                    return

                # Skip hidden unless requested
                if not include_hidden and p.name.startswith("."):
                    return

                # Skip sensitive files
                if p.is_file() and self._is_sensitive_file(p):
                    return

                # Check if matches pattern
                if pattern != "*" and not fnmatch.fnmatch(p.name, pattern):
                    if not (p.is_dir() and recursive):  # Still process dirs for recursion
                        return

                # Add matching files
                if fnmatch.fnmatch(p.name, pattern) or pattern == "*":
                    try:
                        stat = p.stat()
                        files.append(FileInfo(
                            path=str(p.relative_to(dir_path)),
                            name=p.name,
                            is_file=p.is_file(),
                            is_directory=p.is_dir(),
                            size=stat.st_size if p.is_file() else 0,
                            extension=p.suffix.lower() if p.is_file() else "",
                        ))
                    except OSError:
                        pass

                # Recurse into directories
                if p.is_dir() and recursive and current_depth < effective_depth:
                    try:
                        for child in sorted(p.iterdir()):
                            process_path(child, current_depth + 1)
                    except PermissionError:
                        pass

            # Start processing
            for item in sorted(dir_path.iterdir()):
                process_path(item, 0)

            truncated = len(files) >= max_results

            logger.info(f"list_files: {dir_path}, pattern={pattern}, found {len(files)}")

            return {
                "success": True,
                "files": files,
                "total": len(files),
                "truncated": truncated,
                "directory": str(dir_path),
            }

        except Exception as e:
            logger.error(f"list_files error: {e}")
            return {"success": False, "error": f"Error listing directory: {e}"}

    def search_code(
        self,
        pattern: str,
        directory: str = ".",
        file_pattern: str = "*",
        context_lines: int = 2,
        max_results: int = DEFAULT_MAX_SEARCH_RESULTS,
        case_sensitive: bool = True,
        regex: bool = True,
    ) -> dict:
        """Search for code patterns in files.

        Args:
            pattern: Search pattern (regex by default)
            directory: Directory to search
            file_pattern: Glob pattern for file names (e.g., "*.py")
            context_lines: Lines of context before/after match
            max_results: Maximum matches to return
            case_sensitive: Whether search is case-sensitive
            regex: Whether pattern is a regex (if False, literal match)

        Returns:
            Dict with:
            - success: bool
            - matches: list[SearchMatch] (if success)
            - total: int - total matches found
            - files_searched: int
            - truncated: bool
            - error: str (if not success)
        """
        # Validate path
        is_valid, error, dir_path = self.validate_path(directory)
        if not is_valid:
            logger.warning(f"search_code denied: {error}")
            return {"success": False, "error": error}

        if not dir_path.exists():
            return {"success": False, "error": f"Directory not found: {directory}"}

        # Compile pattern
        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            if regex:
                search_re = re.compile(pattern, flags)
            else:
                search_re = re.compile(re.escape(pattern), flags)
        except re.error as e:
            return {"success": False, "error": f"Invalid regex pattern: {e}"}

        matches = []
        files_searched = 0
        total_matches = 0

        try:
            # Find all matching files
            if "**" in file_pattern:
                file_paths = list(dir_path.glob(file_pattern))
            else:
                file_paths = list(dir_path.rglob(file_pattern))

            for file_path in file_paths:
                if not file_path.is_file():
                    continue

                # Skip sensitive and binary
                if self._is_sensitive_file(file_path):
                    continue
                if self._is_binary_file(file_path):
                    continue

                # Check path is allowed
                if not self._is_path_allowed(file_path):
                    continue

                # Search file
                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()

                    files_searched += 1

                    for line_num, line in enumerate(lines, 1):
                        if search_re.search(line):
                            total_matches += 1

                            if len(matches) < max_results:
                                # Get context
                                start = max(0, line_num - 1 - context_lines)
                                end = min(len(lines), line_num + context_lines)

                                context_before = [
                                    self._truncate_line(lines[i].rstrip())
                                    for i in range(start, line_num - 1)
                                ]
                                context_after = [
                                    self._truncate_line(lines[i].rstrip())
                                    for i in range(line_num, end)
                                ]

                                matches.append(SearchMatch(
                                    file=str(file_path.relative_to(dir_path)),
                                    line_number=line_num,
                                    line=self._truncate_line(line.rstrip()),
                                    context_before=context_before,
                                    context_after=context_after,
                                ))

                except (IOError, UnicodeDecodeError):
                    continue

            truncated = total_matches > max_results

            logger.info(f"search_code: pattern={pattern}, searched {files_searched} files, {total_matches} matches")

            return {
                "success": True,
                "matches": matches,
                "total": total_matches,
                "files_searched": files_searched,
                "truncated": truncated,
            }

        except Exception as e:
            logger.error(f"search_code error: {e}")
            return {"success": False, "error": f"Error searching: {e}"}

    def get_file_info(self, file_path: str) -> dict:
        """Get information about a file without reading contents.

        Returns metadata including size, type, and whether it can be read.
        """
        is_valid, error, path = self.validate_path(file_path)
        if not is_valid:
            return {"success": False, "error": error}

        if not path.exists():
            return {"success": False, "error": f"Path not found: {file_path}"}

        try:
            stat = path.stat()
            is_binary = self._is_binary_file(path) if path.is_file() else False
            is_sensitive = self._is_sensitive_file(path)

            return {
                "success": True,
                "path": str(path),
                "name": path.name,
                "is_file": path.is_file(),
                "is_directory": path.is_dir(),
                "size": stat.st_size,
                "extension": path.suffix.lower() if path.is_file() else "",
                "is_binary": is_binary,
                "is_sensitive": is_sensitive,
                "can_read": path.is_file() and not is_binary and not is_sensitive,
            }
        except Exception as e:
            return {"success": False, "error": f"Error getting file info: {e}"}


# Singleton instance
_repository_service: Optional[RepositoryService] = None


def get_repository_service(
    allowed_paths: Optional[list[str]] = None,
    force_new: bool = False,
) -> RepositoryService:
    """Get or create the repository service singleton.

    Args:
        allowed_paths: Override allowed paths (only used if creating new)
        force_new: Force creation of new instance

    Returns:
        RepositoryService instance
    """
    global _repository_service

    if _repository_service is None or force_new:
        # Check environment for allowed paths
        env_paths = os.environ.get("REPOSITORY_PATHS")
        if env_paths and not allowed_paths:
            allowed_paths = [p.strip() for p in env_paths.split(":") if p.strip()]

        _repository_service = RepositoryService(allowed_paths=allowed_paths)

    return _repository_service
