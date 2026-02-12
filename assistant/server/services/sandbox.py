"""Sandbox executor for safe shell command execution.

Provides sandboxed execution environment for shell commands with:
- Restricted environment variables
- Resource limits (timeout, output size)
- Working directory restrictions
- macOS sandbox-exec support (when available)
"""

import subprocess
import logging
import platform
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SandboxConfig:
    """Configuration for sandbox execution."""
    # Maximum execution time in seconds
    timeout: int = 30
    # Maximum output size in bytes
    max_output_size: int = 1024 * 1024  # 1MB
    # Allowed working directory
    working_directory: Optional[Path] = None
    # Allowed environment variables (whitelist)
    allowed_env_vars: set = None
    # Use macOS sandbox-exec (if available)
    use_macos_sandbox: bool = True

    def __post_init__(self):
        if self.allowed_env_vars is None:
            # Default safe environment variables
            self.allowed_env_vars = {
                'PATH', 'HOME', 'USER', 'LANG', 'LC_ALL',
                'TERM', 'SHELL', 'PWD', 'TMPDIR'
            }


class SandboxExecutor:
    """Executes shell commands in a sandboxed environment."""

    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self._is_macos = platform.system() == 'Darwin'
        self._sandbox_exec_available = self._check_sandbox_exec()

    def _check_sandbox_exec(self) -> bool:
        """Check if macOS sandbox-exec is available."""
        if not self._is_macos:
            return False

        try:
            result = subprocess.run(
                ['which', 'sandbox-exec'],
                capture_output=True,
                timeout=5
            )
            available = result.returncode == 0
            if available:
                logger.info("macOS sandbox-exec is available")
            return available
        except Exception as e:
            logger.debug(f"sandbox-exec check failed: {e}")
            return False

    def _get_sandbox_profile(self) -> str:
        """Generate macOS sandbox profile for command execution."""
        return """
(version 1)
(deny default)
(allow process-exec*)
(allow file-read*)
(allow file-write*
    (subpath "/tmp")
    (subpath "/var/tmp"))
(deny network*)
(deny system-socket)
(deny ipc-posix*)
(deny mach-lookup)
"""

    def _build_restricted_env(self) -> Dict[str, str]:
        """Build restricted environment variable dict."""
        import os
        restricted_env = {}

        for key in self.config.allowed_env_vars:
            if key in os.environ:
                restricted_env[key] = os.environ[key]

        # Set safe PATH
        restricted_env['PATH'] = '/usr/bin:/bin:/usr/sbin:/sbin'

        return restricted_env

    def execute(self, command: str) -> Dict[str, Any]:
        """Execute a shell command in sandbox."""
        try:
            # Determine working directory
            cwd = self.config.working_directory
            if cwd is None:
                # Default to Genesis project root
                cwd = Path(__file__).parent.parent.parent.parent

            # Build restricted environment
            env = self._build_restricted_env()

            # Prepare command
            if self._is_macos and self._sandbox_exec_available and self.config.use_macos_sandbox:
                # Use macOS sandbox-exec
                sandbox_profile = self._get_sandbox_profile()
                full_command = [
                    'sandbox-exec',
                    '-p', sandbox_profile,
                    '/bin/sh', '-c', command
                ]
                sandboxed = True
                logger.info(f"Executing command with sandbox-exec: {command[:100]}")
            else:
                # Fallback: run with restricted environment only
                full_command = ['/bin/sh', '-c', command]
                sandboxed = False
                logger.info(f"Executing command without sandbox: {command[:100]}")

            # Execute command
            result = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
                cwd=str(cwd),
                env=env
            )

            # Check output size
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            total_output = len(stdout) + len(stderr)
            truncated = False

            if total_output > self.config.max_output_size:
                # Truncate outputs proportionally
                ratio = self.config.max_output_size / total_output
                stdout_limit = int(len(stdout) * ratio)
                stderr_limit = int(len(stderr) * ratio)

                stdout = stdout[:stdout_limit] + "\n[stdout truncated]"
                stderr = stderr[:stderr_limit] + "\n[stderr truncated]"
                truncated = True
                logger.warning(f"Command output truncated: {total_output} -> {self.config.max_output_size}")

            return {
                'success': True,
                'stdout': stdout,
                'stderr': stderr,
                'exit_code': result.returncode,
                'truncated': truncated,
                'sandboxed': sandboxed,
            }

        except subprocess.TimeoutExpired:
            logger.warning(f"Command timed out after {self.config.timeout}s: {command[:100]}")
            return {
                'success': False,
                'error': f"Command timed out after {self.config.timeout} seconds",
                'sandboxed': sandboxed if 'sandboxed' in locals() else False,
            }

        except Exception as e:
            logger.error(f"Sandbox execution error: {e}")
            return {
                'success': False,
                'error': str(e),
                'sandboxed': False,
            }


# Global instance
_sandbox_executor: Optional[SandboxExecutor] = None


def get_sandbox_executor(config: Optional[SandboxConfig] = None) -> SandboxExecutor:
    """Get or create the global sandbox executor instance."""
    global _sandbox_executor
    if _sandbox_executor is None:
        _sandbox_executor = SandboxExecutor(config)
    return _sandbox_executor
