"""Tests for Repository Analysis Service."""
import os
import tempfile
import pytest
from pathlib import Path

from server.services.repository import (
    RepositoryService,
    get_repository_service,
    FileInfo,
    SearchMatch,
    SENSITIVE_FILE_PATTERNS,
    BINARY_EXTENSIONS,
)


class TestRepositoryService:
    """Test RepositoryService class."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory with test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            test_py = Path(tmpdir) / "test.py"
            test_py.write_text("def hello():\n    print('Hello, World!')\n\nhello()\n")

            test_txt = Path(tmpdir) / "readme.txt"
            test_txt.write_text("This is a readme file.\nLine 2.\nLine 3.\n")

            # Create subdirectory
            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()

            sub_file = subdir / "nested.py"
            sub_file.write_text("# Nested file\nimport os\nprint(os.getcwd())\n")

            # Create hidden file
            hidden = Path(tmpdir) / ".hidden"
            hidden.write_text("secret content")

            yield tmpdir

    @pytest.fixture
    def service(self, temp_dir):
        """Create service for temp directory."""
        return RepositoryService(allowed_paths=[temp_dir])

    # === Path Validation Tests ===

    def test_validate_path_allowed(self, service, temp_dir):
        """Test that allowed paths are validated."""
        is_valid, error, path = service.validate_path(f"{temp_dir}/test.py")
        assert is_valid
        assert error == ""
        assert path is not None

    def test_validate_path_outside_allowed(self, service):
        """Test that paths outside allowed dirs are rejected."""
        is_valid, error, path = service.validate_path("/etc/passwd")
        assert not is_valid
        assert "not in allowed directories" in error
        assert path is None

    def test_validate_path_traversal_attack(self, service, temp_dir):
        """Test that path traversal attacks are blocked."""
        # Try to escape via ../
        is_valid, error, path = service.validate_path(f"{temp_dir}/../../../etc/passwd")
        assert not is_valid
        assert "not in allowed directories" in error

    def test_validate_path_sensitive_file(self, service, temp_dir):
        """Test that sensitive files are blocked."""
        # Create a .env file
        env_file = Path(temp_dir) / ".env"
        env_file.write_text("SECRET=value")

        is_valid, error, path = service.validate_path(str(env_file))
        assert not is_valid
        assert "sensitive file" in error.lower()

    def test_validate_path_credentials_file(self, service, temp_dir):
        """Test that credential files are blocked."""
        creds = Path(temp_dir) / "credentials.json"
        creds.write_text('{"key": "value"}')

        is_valid, error, path = service.validate_path(str(creds))
        assert not is_valid
        assert "sensitive file" in error.lower()

    # === Read File Tests ===

    def test_read_file_success(self, service, temp_dir):
        """Test successful file read."""
        result = service.read_file(f"{temp_dir}/test.py")
        assert result["success"]
        assert "def hello()" in result["content"]
        assert result["lines"] == 4

    def test_read_file_not_found(self, service, temp_dir):
        """Test reading non-existent file."""
        result = service.read_file(f"{temp_dir}/nonexistent.py")
        assert not result["success"]
        assert "not found" in result["error"].lower()

    def test_read_file_line_range(self, service, temp_dir):
        """Test reading specific line range."""
        result = service.read_file(f"{temp_dir}/test.py", start_line=2, end_line=3)
        assert result["success"]
        assert "print" in result["content"]
        assert "def hello" not in result["content"]
        assert result["start_line"] == 2
        assert result["end_line"] == 3

    def test_read_file_max_length(self, service, temp_dir):
        """Test max length truncation."""
        result = service.read_file(f"{temp_dir}/test.py", max_length=10)
        assert result["success"]
        assert len(result["content"]) <= 10
        assert result["truncated"]

    def test_read_file_binary_rejected(self, service, temp_dir):
        """Test that binary files are rejected."""
        # Create a binary file
        binary = Path(temp_dir) / "test.exe"
        binary.write_bytes(b"\x00\x01\x02\x03\x04\x05")

        result = service.read_file(str(binary))
        assert not result["success"]
        assert "binary" in result["error"].lower()

    def test_read_file_outside_allowed(self, service):
        """Test reading file outside allowed paths."""
        result = service.read_file("/etc/passwd")
        assert not result["success"]
        assert "not in allowed" in result["error"].lower()

    def test_read_file_large_file_rejected(self, temp_dir):
        """Test that large files are rejected."""
        # Create service with small max size
        service = RepositoryService(
            allowed_paths=[temp_dir],
            max_file_size=100
        )

        # Create large file
        large = Path(temp_dir) / "large.txt"
        large.write_text("x" * 1000)

        result = service.read_file(str(large))
        assert not result["success"]
        assert "too large" in result["error"].lower()

    # === List Files Tests ===

    def test_list_files_success(self, service, temp_dir):
        """Test listing files in directory."""
        result = service.list_files(temp_dir)
        assert result["success"]
        assert result["total"] >= 2  # test.py, readme.txt, subdir

        names = [f.name for f in result["files"]]
        assert "test.py" in names
        assert "readme.txt" in names

    def test_list_files_pattern_filter(self, service, temp_dir):
        """Test listing files with pattern."""
        result = service.list_files(temp_dir, pattern="*.py")
        assert result["success"]

        for f in result["files"]:
            if f.is_file:
                assert f.extension == ".py"

    def test_list_files_recursive(self, service, temp_dir):
        """Test recursive listing."""
        result = service.list_files(temp_dir, pattern="*.py", recursive=True)
        assert result["success"]

        paths = [f.path for f in result["files"]]
        # Should find nested.py in subdir
        assert any("nested" in p for p in paths)

    def test_list_files_hidden_excluded(self, service, temp_dir):
        """Test that hidden files are excluded by default."""
        result = service.list_files(temp_dir)
        assert result["success"]

        names = [f.name for f in result["files"]]
        assert ".hidden" not in names

    def test_list_files_hidden_included(self, service, temp_dir):
        """Test including hidden files."""
        result = service.list_files(temp_dir, include_hidden=True)
        assert result["success"]

        names = [f.name for f in result["files"]]
        assert ".hidden" in names

    def test_list_files_outside_allowed(self, service):
        """Test listing outside allowed paths."""
        result = service.list_files("/etc")
        assert not result["success"]
        assert "not in allowed" in result["error"].lower()

    def test_list_files_not_directory(self, service, temp_dir):
        """Test listing a file (not directory)."""
        result = service.list_files(f"{temp_dir}/test.py")
        assert not result["success"]
        assert "not a directory" in result["error"].lower()

    # === Search Code Tests ===

    def test_search_code_success(self, service, temp_dir):
        """Test searching for pattern."""
        result = service.search_code("def hello", temp_dir)
        assert result["success"]
        assert result["total"] >= 1
        assert len(result["matches"]) >= 1

        match = result["matches"][0]
        assert "hello" in match.line.lower()

    def test_search_code_regex(self, service, temp_dir):
        """Test regex search."""
        result = service.search_code(r"def\s+\w+", temp_dir, file_pattern="*.py")
        assert result["success"]
        assert result["total"] >= 1

    def test_search_code_case_insensitive(self, service, temp_dir):
        """Test case-insensitive search."""
        result = service.search_code("HELLO", temp_dir, case_sensitive=False)
        assert result["success"]
        assert result["total"] >= 1

    def test_search_code_case_sensitive_no_match(self, service, temp_dir):
        """Test case-sensitive search with no match."""
        result = service.search_code("HELLO", temp_dir, case_sensitive=True)
        assert result["success"]
        assert result["total"] == 0

    def test_search_code_with_context(self, service, temp_dir):
        """Test search with context lines."""
        result = service.search_code("print", temp_dir, context_lines=1)
        assert result["success"]

        if result["matches"]:
            match = result["matches"][0]
            # Should have context lines
            assert isinstance(match.context_before, list)
            assert isinstance(match.context_after, list)

    def test_search_code_file_pattern(self, service, temp_dir):
        """Test search with file pattern filter."""
        result = service.search_code(".", temp_dir, file_pattern="*.txt")
        assert result["success"]
        # All matches should be from .txt files
        for match in result["matches"]:
            assert match.file.endswith(".txt")

    def test_search_code_max_results(self, service, temp_dir):
        """Test max results limit."""
        result = service.search_code(".", temp_dir, max_results=2)
        assert result["success"]
        assert len(result["matches"]) <= 2

    def test_search_code_invalid_regex(self, service, temp_dir):
        """Test invalid regex pattern."""
        result = service.search_code("[invalid(", temp_dir)
        assert not result["success"]
        assert "invalid regex" in result["error"].lower()

    def test_search_code_outside_allowed(self, service):
        """Test searching outside allowed paths."""
        result = service.search_code("test", "/etc")
        assert not result["success"]
        assert "not in allowed" in result["error"].lower()

    # === Get File Info Tests ===

    def test_get_file_info_file(self, service, temp_dir):
        """Test getting file info."""
        result = service.get_file_info(f"{temp_dir}/test.py")
        assert result["success"]
        assert result["is_file"]
        assert not result["is_directory"]
        assert result["extension"] == ".py"
        assert result["size"] > 0
        assert result["can_read"]

    def test_get_file_info_directory(self, service, temp_dir):
        """Test getting directory info."""
        result = service.get_file_info(f"{temp_dir}/subdir")
        assert result["success"]
        assert not result["is_file"]
        assert result["is_directory"]

    def test_get_file_info_binary(self, service, temp_dir):
        """Test getting binary file info."""
        binary = Path(temp_dir) / "test.zip"
        binary.write_bytes(b"\x00\x01\x02")

        result = service.get_file_info(str(binary))
        assert result["success"]
        assert result["is_binary"]
        assert not result["can_read"]

    def test_get_file_info_sensitive(self, service, temp_dir):
        """Test getting sensitive file info."""
        # Create .env but need to test via info since read is blocked
        env = Path(temp_dir) / ".env"
        env.write_text("SECRET=value")

        # get_file_info uses validate_path which blocks sensitive files
        result = service.get_file_info(str(env))
        assert not result["success"]
        assert "sensitive" in result["error"].lower()

    def test_get_file_info_not_found(self, service, temp_dir):
        """Test getting info for non-existent path."""
        result = service.get_file_info(f"{temp_dir}/nonexistent")
        assert not result["success"]
        assert "not found" in result["error"].lower()

    # === Singleton Tests ===

    def test_singleton_creation(self, temp_dir):
        """Test singleton getter."""
        os.environ["REPOSITORY_PATHS"] = temp_dir
        try:
            service = get_repository_service(force_new=True)
            assert service is not None
            assert temp_dir in str(service._allowed_paths[0])
        finally:
            os.environ.pop("REPOSITORY_PATHS", None)

    def test_singleton_reuse(self):
        """Test that singleton is reused."""
        svc1 = get_repository_service(force_new=True)
        svc2 = get_repository_service()
        assert svc1 is svc2


class TestSensitivePatterns:
    """Test sensitive file pattern detection."""

    @pytest.fixture
    def service(self):
        """Create service with temp allowed path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield RepositoryService(allowed_paths=[tmpdir]), tmpdir

    @pytest.mark.parametrize("filename,should_block", [
        (".env", True),
        (".env.local", True),
        (".env.production", True),
        ("config.env", False),  # Not sensitive
        ("id_rsa", True),
        ("id_rsa.pub", True),
        ("id_ed25519", True),
        ("server.key", True),
        ("certificate.pem", True),
        ("credentials.json", True),
        ("my_credentials_file.txt", True),
        ("secrets.yaml", True),
        ("password.txt", True),
        (".npmrc", True),
        (".pypirc", True),
        ("normal.py", False),
        ("test.txt", False),
        ("config.json", False),
    ])
    def test_sensitive_patterns(self, service, filename, should_block):
        """Test various sensitive file patterns."""
        svc, tmpdir = service
        test_file = Path(tmpdir) / filename
        test_file.write_text("test content")

        result = svc._is_sensitive_file(test_file)
        assert result == should_block, f"{filename} should {'be' if should_block else 'not be'} blocked"


class TestBinaryDetection:
    """Test binary file detection."""

    @pytest.fixture
    def service(self):
        """Create service with temp allowed path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield RepositoryService(allowed_paths=[tmpdir]), tmpdir

    @pytest.mark.parametrize("extension,should_be_binary", [
        (".exe", True),
        (".dll", True),
        (".so", True),
        (".zip", True),
        (".tar", True),
        (".png", True),
        (".jpg", True),
        (".pdf", True),
        (".mp3", True),
        (".sqlite", True),
        (".py", False),
        (".js", False),
        (".ts", False),
        (".json", False),
        (".md", False),
        (".txt", False),
        (".html", False),
        (".css", False),
    ])
    def test_binary_by_extension(self, service, extension, should_be_binary):
        """Test binary detection by extension."""
        svc, tmpdir = service
        test_file = Path(tmpdir) / f"test{extension}"
        test_file.write_bytes(b"test content")

        result = svc._is_binary_file(test_file)
        assert result == should_be_binary, f"{extension} should {'be' if should_be_binary else 'not be'} binary"

    def test_binary_by_content(self, service):
        """Test binary detection by null bytes in content."""
        svc, tmpdir = service

        # File with null bytes should be detected as binary
        binary_file = Path(tmpdir) / "unknown_type"
        binary_file.write_bytes(b"text\x00\x00binary\x00content")

        assert svc._is_binary_file(binary_file)

    def test_text_content_not_binary(self, service):
        """Test that text files aren't falsely detected as binary."""
        svc, tmpdir = service

        text_file = Path(tmpdir) / "textfile"
        text_file.write_text("This is regular text content\nwith newlines\n")

        assert not svc._is_binary_file(text_file)


class TestLineFormatting:
    """Test line formatting and truncation."""

    def test_truncate_long_line(self):
        """Test that long lines are truncated."""
        service = RepositoryService(max_line_length=50)

        long_line = "x" * 100
        truncated = service._truncate_line(long_line)

        assert len(truncated) < 100
        assert "truncated" in truncated

    def test_short_line_unchanged(self):
        """Test that short lines aren't modified."""
        service = RepositoryService(max_line_length=50)

        short_line = "x" * 10
        result = service._truncate_line(short_line)

        assert result == short_line


class TestMultipleAllowedPaths:
    """Test service with multiple allowed paths."""

    def test_multiple_paths_allowed(self):
        """Test that multiple paths can be allowed."""
        with tempfile.TemporaryDirectory() as dir1:
            with tempfile.TemporaryDirectory() as dir2:
                service = RepositoryService(allowed_paths=[dir1, dir2])

                # Create test files in both dirs
                Path(dir1, "file1.txt").write_text("content1")
                Path(dir2, "file2.txt").write_text("content2")

                # Both should be accessible
                result1 = service.read_file(f"{dir1}/file1.txt")
                result2 = service.read_file(f"{dir2}/file2.txt")

                assert result1["success"]
                assert result2["success"]

    def test_path_not_in_any_allowed(self):
        """Test that path must be in at least one allowed dir."""
        with tempfile.TemporaryDirectory() as allowed:
            service = RepositoryService(allowed_paths=[allowed])

            with tempfile.TemporaryDirectory() as not_allowed:
                Path(not_allowed, "secret.txt").write_text("secret")
                result = service.read_file(f"{not_allowed}/secret.txt")
                assert not result["success"]
