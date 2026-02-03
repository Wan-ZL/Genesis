"""Permission system for AI Assistant.

Defines permission levels and decorators for enforcing access control.
"""
import os
import functools
from enum import IntEnum
from typing import Callable, TypeVar, Any

F = TypeVar('F', bound=Callable[..., Any])


class PermissionLevel(IntEnum):
    """Permission levels for AI Assistant operations.

    SANDBOX (0): Only access assistant/memory/ directory
    LOCAL (1): Access entire Genesis project
    SYSTEM (2): Execute system commands (restricted)
    FULL (3): Complete computer access (user's choice)
    """
    SANDBOX = 0
    LOCAL = 1
    SYSTEM = 2
    FULL = 3


def get_permission_level() -> PermissionLevel:
    """Get current permission level from environment or settings."""
    level = int(os.getenv("ASSISTANT_PERMISSION_LEVEL", "1"))
    return PermissionLevel(level)


# Global permission level (loaded on import, can be updated at runtime)
PERMISSION_LEVEL = get_permission_level()


def require_permission(level: PermissionLevel) -> Callable[[F], F]:
    """Decorator to enforce minimum permission level for a function.

    Usage:
        @require_permission(PermissionLevel.SYSTEM)
        def run_shell_command(cmd: str) -> str:
            ...

    Raises:
        PermissionError: If current permission level is insufficient.
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            current = get_permission_level()
            if current < level:
                raise PermissionError(
                    f"Operation requires {level.name} permission (current: {current.name}). "
                    f"Set ASSISTANT_PERMISSION_LEVEL={level.value} or grant via settings."
                )
            return func(*args, **kwargs)
        return wrapper  # type: ignore
    return decorator


def set_permission_level(level: PermissionLevel) -> None:
    """Update the global permission level (for runtime changes).

    Also updates the environment variable for child processes.
    """
    global PERMISSION_LEVEL
    PERMISSION_LEVEL = level
    os.environ["ASSISTANT_PERMISSION_LEVEL"] = str(level.value)


def can_access(level: PermissionLevel) -> bool:
    """Check if current permission level allows the specified access.

    Usage:
        if can_access(PermissionLevel.SYSTEM):
            run_shell_command("ls")
        else:
            return "Need SYSTEM permission to run commands"
    """
    return get_permission_level() >= level
