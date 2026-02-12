"""Security service for input/output sanitization and validation.

Provides protection against:
- Command injection
- Path traversal
- SSRF (Server-Side Request Forgery)
- Prompt injection attacks
"""

import re
import logging
from pathlib import Path
from typing import Tuple, Optional
from urllib.parse import urlparse
import ipaddress

logger = logging.getLogger(__name__)


class SecurityService:
    """Handles input sanitization and output validation."""

    # Dangerous shell characters and patterns
    SHELL_DANGEROUS_CHARS = r'[;&|`$<>()\[\]{}*?~]'

    # Prompt injection patterns (case-insensitive)
    PROMPT_INJECTION_PATTERNS = [
        r'ignore\s+(previous|all|above)\s+instructions?',
        r'disregard\s+(previous|all|above)',
        r'system\s+prompt',
        r'you\s+are\s+now',
        r'new\s+instructions?:',
        r'act\s+as',
        r'pretend\s+to\s+be',
        r'roleplay',
        r'forget\s+(everything|all|previous)',
        r'<\|.*?\|>',  # Special tokens
        r'\[INST\]',    # Instruction markers
        r'\[/INST\]',
        r'<s>',         # Special tokens
        r'</s>',
    ]

    # Private IP ranges for SSRF protection
    PRIVATE_IP_RANGES = [
        ipaddress.IPv4Network('127.0.0.0/8'),      # Loopback
        ipaddress.IPv4Network('10.0.0.0/8'),       # Private
        ipaddress.IPv4Network('172.16.0.0/12'),    # Private
        ipaddress.IPv4Network('192.168.0.0/16'),   # Private
        ipaddress.IPv4Network('169.254.0.0/16'),   # Link-local
    ]

    def __init__(self):
        # Compile regex patterns once for performance
        self._prompt_injection_regex = re.compile(
            '|'.join(self.PROMPT_INJECTION_PATTERNS),
            re.IGNORECASE
        )

    def sanitize_shell_input(self, command: str) -> Tuple[str, bool]:
        """Sanitize shell command input.

        Args:
            command: Shell command to sanitize

        Returns:
            Tuple of (sanitized_command, is_safe)
        """
        # Check for dangerous patterns
        if re.search(self.SHELL_DANGEROUS_CHARS, command):
            logger.warning(f"Shell command contains dangerous characters: {command[:100]}")
            return command, False

        # Block extremely dangerous commands
        dangerous_keywords = [
            'rm -rf /',
            'rm -rf ~',
            ':(){:|:&};:',  # fork bomb
            'mkfs',
            'dd if=/dev/zero',
            '> /dev/sd',
            'chmod 777 /',
            'chown root /',
        ]

        cmd_lower = command.lower()
        for keyword in dangerous_keywords:
            if keyword in cmd_lower:
                logger.error(f"Blocked dangerous command: {command[:100]}")
                return command, False

        return command, True

    def validate_file_path(
        self,
        file_path: str,
        allowed_dirs: Optional[list[Path]] = None
    ) -> Tuple[Path, bool, Optional[str]]:
        """Validate file path to prevent path traversal.

        Args:
            file_path: File path to validate
            allowed_dirs: List of allowed base directories

        Returns:
            Tuple of (resolved_path, is_safe, error_message)
        """
        try:
            # Resolve path (follows symlinks)
            path = Path(file_path).resolve()

            # Check if path exists
            if not path.exists():
                return path, False, "Path does not exist"

            # Check against allowed directories
            if allowed_dirs:
                is_allowed = any(
                    path.is_relative_to(allowed_dir)
                    for allowed_dir in allowed_dirs
                )
                if not is_allowed:
                    logger.warning(f"Path outside allowed directories: {path}")
                    return path, False, "Path outside allowed directories"

            # Check for sensitive files
            sensitive_patterns = [
                '.env',
                'secrets',
                'credentials',
                'private_key',
                'id_rsa',
                '.ssh',
                'password',
            ]

            path_str = str(path).lower()
            for pattern in sensitive_patterns:
                if pattern in path_str:
                    logger.warning(f"Attempted access to sensitive file: {path}")
                    return path, False, "Access to sensitive file denied"

            return path, True, None

        except Exception as e:
            logger.error(f"Path validation error: {e}")
            return Path(file_path), False, str(e)

    def validate_url(self, url: str) -> Tuple[bool, Optional[str]]:
        """Validate URL to prevent SSRF attacks.

        Args:
            url: URL to validate

        Returns:
            Tuple of (is_safe, error_message)
        """
        try:
            parsed = urlparse(url)

            # Check scheme
            if parsed.scheme not in ('http', 'https'):
                return False, f"Invalid URL scheme: {parsed.scheme}"

            # Check for missing domain
            if not parsed.netloc:
                return False, "Missing domain in URL"

            # Extract hostname (remove port if present)
            hostname = parsed.netloc.split(':')[0]

            # Block localhost variants
            localhost_variants = [
                'localhost',
                '127.0.0.1',
                '::1',
                '0.0.0.0',
            ]
            if hostname.lower() in localhost_variants:
                logger.warning(f"Blocked localhost URL: {url}")
                return False, "Access to localhost is blocked"

            # Try to resolve IP address
            try:
                # Check if hostname is already an IP
                ip = ipaddress.IPv4Address(hostname)

                # Check against private IP ranges
                for private_range in self.PRIVATE_IP_RANGES:
                    if ip in private_range:
                        logger.warning(f"Blocked private IP: {url}")
                        return False, f"Access to private IP range {private_range} is blocked"

            except ValueError:
                # Not an IP address, that's fine (could be a domain name)
                pass

            return True, None

        except Exception as e:
            logger.error(f"URL validation error: {e}")
            return False, str(e)

    def sanitize_tool_args(
        self,
        tool_name: str,
        args: dict
    ) -> Tuple[dict, bool, Optional[str]]:
        """Sanitize tool arguments based on tool type.

        Args:
            tool_name: Name of the tool
            args: Tool arguments

        Returns:
            Tuple of (sanitized_args, is_safe, error_message)
        """
        # Shell command tools need special handling
        if 'shell' in tool_name.lower() or 'command' in tool_name.lower():
            if 'command' in args:
                sanitized, is_safe = self.sanitize_shell_input(args['command'])
                if not is_safe:
                    return args, False, "Command contains unsafe patterns"
                args['command'] = sanitized

        # Web fetch tools need URL validation
        if 'web' in tool_name.lower() or 'fetch' in tool_name.lower():
            if 'url' in args:
                is_safe, error = self.validate_url(args['url'])
                if not is_safe:
                    return args, False, error

        # File operation tools need path validation
        if any(kw in tool_name.lower() for kw in ['read', 'write', 'file', 'list']):
            if 'file_path' in args:
                _, is_safe, error = self.validate_file_path(args['file_path'])
                if not is_safe:
                    return args, False, error
            if 'path' in args:
                _, is_safe, error = self.validate_file_path(args['path'])
                if not is_safe:
                    return args, False, error

        return args, True, None

    def detect_prompt_injection(self, text: str) -> Tuple[str, bool, list[str]]:
        """Detect and sanitize prompt injection attempts.

        Args:
            text: Text to check for prompt injection

        Returns:
            Tuple of (sanitized_text, injection_detected, matched_patterns)
        """
        matched_patterns = []

        # Check for injection patterns
        for pattern in self.PROMPT_INJECTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                matched_patterns.append(pattern)

        if matched_patterns:
            logger.warning(
                f"Prompt injection detected: {len(matched_patterns)} patterns matched in "
                f"{len(text)} chars of text"
            )

            # Sanitize by replacing matched patterns
            sanitized = text
            for pattern in matched_patterns:
                sanitized = re.sub(pattern, '[REDACTED]', sanitized, flags=re.IGNORECASE)

            return sanitized, True, matched_patterns

        return text, False, []

    def sanitize_output(self, text: str, max_length: int = 10000) -> str:
        """Sanitize tool output before returning to LLM.

        Args:
            text: Output text to sanitize
            max_length: Maximum length of output

        Returns:
            Sanitized text
        """
        # Detect and sanitize prompt injection
        sanitized, injection_detected, patterns = self.detect_prompt_injection(text)

        if injection_detected:
            # Prepend warning
            warning = (
                f"[SECURITY WARNING: Potential prompt injection detected and sanitized. "
                f"Matched {len(patterns)} pattern(s)]\n\n"
            )
            sanitized = warning + sanitized

        # Truncate if too long
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length] + f"\n\n[Truncated at {max_length} characters]"

        return sanitized


# Global instance
_security_service: Optional[SecurityService] = None


def get_security_service() -> SecurityService:
    """Get or create the global security service instance."""
    global _security_service
    if _security_service is None:
        _security_service = SecurityService()
    return _security_service
