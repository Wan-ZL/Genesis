"""Tests for the permission system."""
import os
import pytest
from unittest.mock import patch

from core.permissions import (
    PermissionLevel,
    get_permission_level,
    set_permission_level,
    require_permission,
    can_access,
    PERMISSION_LEVEL,
)


class TestPermissionLevel:
    """Tests for PermissionLevel enum."""

    def test_permission_levels_ordered(self):
        """Permission levels should be ordered SANDBOX < LOCAL < SYSTEM < FULL."""
        assert PermissionLevel.SANDBOX < PermissionLevel.LOCAL
        assert PermissionLevel.LOCAL < PermissionLevel.SYSTEM
        assert PermissionLevel.SYSTEM < PermissionLevel.FULL

    def test_permission_level_values(self):
        """Permission levels should have correct integer values."""
        assert PermissionLevel.SANDBOX == 0
        assert PermissionLevel.LOCAL == 1
        assert PermissionLevel.SYSTEM == 2
        assert PermissionLevel.FULL == 3

    def test_permission_level_names(self):
        """Permission levels should have correct names."""
        assert PermissionLevel.SANDBOX.name == "SANDBOX"
        assert PermissionLevel.LOCAL.name == "LOCAL"
        assert PermissionLevel.SYSTEM.name == "SYSTEM"
        assert PermissionLevel.FULL.name == "FULL"


class TestGetPermissionLevel:
    """Tests for get_permission_level function."""

    def test_default_is_local(self):
        """Default permission level should be LOCAL (1)."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove the env var if it exists
            os.environ.pop("ASSISTANT_PERMISSION_LEVEL", None)
            level = get_permission_level()
            assert level == PermissionLevel.LOCAL

    def test_reads_from_env(self):
        """Should read permission level from environment variable."""
        with patch.dict(os.environ, {"ASSISTANT_PERMISSION_LEVEL": "2"}):
            level = get_permission_level()
            assert level == PermissionLevel.SYSTEM

    def test_sandbox_level(self):
        """Should correctly parse SANDBOX level."""
        with patch.dict(os.environ, {"ASSISTANT_PERMISSION_LEVEL": "0"}):
            level = get_permission_level()
            assert level == PermissionLevel.SANDBOX

    def test_full_level(self):
        """Should correctly parse FULL level."""
        with patch.dict(os.environ, {"ASSISTANT_PERMISSION_LEVEL": "3"}):
            level = get_permission_level()
            assert level == PermissionLevel.FULL


class TestSetPermissionLevel:
    """Tests for set_permission_level function."""

    def test_sets_global_and_env(self):
        """Should update global and environment variable."""
        original_env = os.environ.get("ASSISTANT_PERMISSION_LEVEL")
        try:
            set_permission_level(PermissionLevel.SYSTEM)

            # Check environment variable was updated
            assert os.environ["ASSISTANT_PERMISSION_LEVEL"] == "2"

            # Check get_permission_level returns new value
            assert get_permission_level() == PermissionLevel.SYSTEM
        finally:
            # Restore original
            if original_env:
                os.environ["ASSISTANT_PERMISSION_LEVEL"] = original_env
            else:
                os.environ.pop("ASSISTANT_PERMISSION_LEVEL", None)


class TestRequirePermission:
    """Tests for require_permission decorator."""

    def test_allows_sufficient_permission(self):
        """Should allow execution with sufficient permission."""
        with patch.dict(os.environ, {"ASSISTANT_PERMISSION_LEVEL": "2"}):
            @require_permission(PermissionLevel.LOCAL)
            def test_func():
                return "success"

            assert test_func() == "success"

    def test_allows_exact_permission(self):
        """Should allow execution with exact permission level."""
        with patch.dict(os.environ, {"ASSISTANT_PERMISSION_LEVEL": "1"}):
            @require_permission(PermissionLevel.LOCAL)
            def test_func():
                return "success"

            assert test_func() == "success"

    def test_blocks_insufficient_permission(self):
        """Should block execution with insufficient permission."""
        with patch.dict(os.environ, {"ASSISTANT_PERMISSION_LEVEL": "0"}):
            @require_permission(PermissionLevel.LOCAL)
            def test_func():
                return "success"

            with pytest.raises(PermissionError) as exc_info:
                test_func()

            assert "LOCAL permission" in str(exc_info.value)
            assert "SANDBOX" in str(exc_info.value)

    def test_preserves_function_metadata(self):
        """Decorator should preserve function name and docstring."""
        @require_permission(PermissionLevel.SANDBOX)
        def documented_func():
            """This is documentation."""
            pass

        assert documented_func.__name__ == "documented_func"
        assert documented_func.__doc__ == "This is documentation."

    def test_passes_args_and_kwargs(self):
        """Decorator should pass arguments correctly."""
        with patch.dict(os.environ, {"ASSISTANT_PERMISSION_LEVEL": "3"}):
            @require_permission(PermissionLevel.FULL)
            def add(a, b, c=0):
                return a + b + c

            assert add(1, 2) == 3
            assert add(1, 2, c=3) == 6


class TestCanAccess:
    """Tests for can_access function."""

    def test_can_access_lower_level(self):
        """Should return True for lower permission level."""
        with patch.dict(os.environ, {"ASSISTANT_PERMISSION_LEVEL": "2"}):
            assert can_access(PermissionLevel.SANDBOX) is True
            assert can_access(PermissionLevel.LOCAL) is True

    def test_can_access_same_level(self):
        """Should return True for same permission level."""
        with patch.dict(os.environ, {"ASSISTANT_PERMISSION_LEVEL": "1"}):
            assert can_access(PermissionLevel.LOCAL) is True

    def test_cannot_access_higher_level(self):
        """Should return False for higher permission level."""
        with patch.dict(os.environ, {"ASSISTANT_PERMISSION_LEVEL": "1"}):
            assert can_access(PermissionLevel.SYSTEM) is False
            assert can_access(PermissionLevel.FULL) is False
