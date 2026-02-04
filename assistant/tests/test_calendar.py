"""Tests for the Calendar Service."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
import sys
from pathlib import Path

# Ensure server module is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.services.calendar import (
    CalendarService,
    CalendarConfig,
    CalendarEvent,
    FreeSlot,
    CALDAV_AVAILABLE,
    get_calendar_service,
    init_calendar_service,
)


class TestCalendarEvent:
    """Tests for CalendarEvent dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        event = CalendarEvent(
            event_id="test-123",
            title="Test Meeting",
            start=datetime(2026, 2, 5, 14, 0),
            end=datetime(2026, 2, 5, 15, 0),
            location="Conference Room A",
            notes="Discuss project",
            all_day=False,
            calendar_name="Work"
        )

        result = event.to_dict()

        assert result["event_id"] == "test-123"
        assert result["title"] == "Test Meeting"
        assert result["start"] == "2026-02-05T14:00:00"
        assert result["end"] == "2026-02-05T15:00:00"
        assert result["location"] == "Conference Room A"
        assert result["notes"] == "Discuss project"
        assert result["all_day"] is False
        assert result["calendar_name"] == "Work"

    def test_to_dict_minimal(self):
        """Test conversion with minimal fields."""
        event = CalendarEvent(
            event_id="min-123",
            title="Quick Event",
            start=datetime(2026, 2, 5, 10, 0),
            end=datetime(2026, 2, 5, 10, 30),
        )

        result = event.to_dict()

        assert result["event_id"] == "min-123"
        assert result["title"] == "Quick Event"
        assert result["location"] is None
        assert result["notes"] is None


class TestCalendarConfig:
    """Tests for CalendarConfig dataclass."""

    def test_is_configured_true(self):
        """Test is_configured when all fields set."""
        config = CalendarConfig(
            caldav_url="https://caldav.example.com",
            username="user@example.com",
            password="secret123"
        )
        assert config.is_configured is True

    def test_is_configured_false_missing_url(self):
        """Test is_configured with missing URL."""
        config = CalendarConfig(
            caldav_url="",
            username="user@example.com",
            password="secret123"
        )
        assert config.is_configured is False

    def test_is_configured_false_missing_username(self):
        """Test is_configured with missing username."""
        config = CalendarConfig(
            caldav_url="https://caldav.example.com",
            username="",
            password="secret123"
        )
        assert config.is_configured is False

    def test_is_configured_false_missing_password(self):
        """Test is_configured with missing password."""
        config = CalendarConfig(
            caldav_url="https://caldav.example.com",
            username="user@example.com",
            password=""
        )
        assert config.is_configured is False


class TestFreeSlot:
    """Tests for FreeSlot dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        slot = FreeSlot(
            start=datetime(2026, 2, 5, 14, 0),
            end=datetime(2026, 2, 5, 15, 0),
            duration_minutes=60
        )

        result = slot.to_dict()

        assert result["start"] == "2026-02-05T14:00:00"
        assert result["end"] == "2026-02-05T15:00:00"
        assert result["duration_minutes"] == 60


class TestCalendarService:
    """Tests for CalendarService class."""

    def test_init_default(self):
        """Test initialization with defaults."""
        service = CalendarService()

        assert service.is_configured is False
        assert service.is_connected is False
        assert service.is_available == CALDAV_AVAILABLE

    def test_init_with_config(self):
        """Test initialization with config."""
        config = CalendarConfig(
            caldav_url="https://caldav.example.com",
            username="user",
            password="pass"
        )
        service = CalendarService(config)

        assert service.is_configured is True
        assert service.is_connected is False

    def test_configure(self):
        """Test configure method."""
        service = CalendarService()
        assert service.is_configured is False

        config = CalendarConfig(
            caldav_url="https://caldav.example.com",
            username="user",
            password="pass"
        )
        service.configure(config)

        assert service.is_configured is True
        assert service.config.caldav_url == "https://caldav.example.com"


class TestCalendarServiceConnection:
    """Tests for CalendarService connection logic."""

    @pytest.mark.asyncio
    async def test_connect_not_configured(self):
        """Test connect when not configured."""
        service = CalendarService()

        result = await service.connect()

        assert result["success"] is False
        # Error could be about configuration or about caldav not being installed
        assert "not configured" in result["error"].lower() or "caldav" in result["error"].lower()

    @pytest.mark.asyncio
    @pytest.mark.skipif(not CALDAV_AVAILABLE, reason="caldav not installed")
    async def test_connect_with_mock(self):
        """Test connect with mocked caldav."""
        config = CalendarConfig(
            caldav_url="https://caldav.example.com",
            username="user",
            password="pass"
        )
        service = CalendarService(config)

        # Mock caldav client
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        mock_calendar.name = "Test Calendar"

        mock_principal.calendars.return_value = [mock_calendar]
        mock_client.principal.return_value = mock_principal

        with patch("server.services.calendar.caldav.DAVClient", return_value=mock_client):
            result = await service.connect()

        assert result["success"] is True
        assert "Test Calendar" in result["calendars"]
        assert service.is_connected is True


class TestCalendarServiceEvents:
    """Tests for CalendarService event operations."""

    @pytest.mark.asyncio
    async def test_list_events_not_connected(self):
        """Test list_events when not connected."""
        service = CalendarService()

        # Without config, connect will fail
        events = await service.list_events()

        assert events == []

    @pytest.mark.asyncio
    async def test_list_calendars_not_connected(self):
        """Test list_calendars when not connected."""
        service = CalendarService()

        calendars = await service.list_calendars()

        assert calendars == []

    def test_build_ical_basic(self):
        """Test iCalendar generation."""
        service = CalendarService()

        ical = service._build_ical(
            event_id="test-123",
            title="Test Event",
            start=datetime(2026, 2, 5, 14, 0),
            end=datetime(2026, 2, 5, 15, 0)
        )

        assert "BEGIN:VCALENDAR" in ical
        assert "BEGIN:VEVENT" in ical
        assert "UID:test-123" in ical
        assert "SUMMARY:Test Event" in ical
        assert "DTSTART:20260205T140000" in ical
        assert "DTEND:20260205T150000" in ical
        assert "END:VEVENT" in ical
        assert "END:VCALENDAR" in ical

    def test_build_ical_with_location_and_notes(self):
        """Test iCalendar generation with optional fields."""
        service = CalendarService()

        ical = service._build_ical(
            event_id="test-456",
            title="Meeting",
            start=datetime(2026, 2, 6, 10, 0),
            end=datetime(2026, 2, 6, 11, 0),
            location="Room 101",
            notes="Important meeting"
        )

        assert "LOCATION:Room 101" in ical
        assert "DESCRIPTION:Important meeting" in ical


class TestCalendarServiceFreeTime:
    """Tests for find_free_time functionality."""

    @pytest.mark.asyncio
    async def test_find_free_time_basic(self):
        """Test find_free_time returns valid slots."""
        service = CalendarService()

        # When not connected, list_events returns empty, so all slots are "free"
        # This is correct behavior - no events means all time is available
        slots = await service.find_free_time(
            duration_minutes=60,
            start=datetime(2026, 2, 5, 9, 0),
            end=datetime(2026, 2, 5, 17, 0)
        )

        # Should return some free slots (since calendar is empty)
        # Each slot should have the requested duration
        for slot in slots:
            assert slot.duration_minutes == 60
            assert isinstance(slot.start, datetime)
            assert isinstance(slot.end, datetime)


class TestCalendarToolIntegration:
    """Tests for calendar tool integration."""

    def test_tools_registered(self):
        """Test that calendar tools are registered."""
        from server.services.tools import registry

        tool_names = registry.list_tools()

        assert "list_events" in tool_names
        assert "create_event" in tool_names
        assert "update_event" in tool_names
        assert "delete_event" in tool_names
        assert "find_free_time" in tool_names

    def test_list_events_tool_spec(self):
        """Test list_events tool specification."""
        from server.services.tools import registry, PermissionLevel

        tool = registry.get_tool("list_events")

        assert tool is not None
        assert tool.name == "list_events"
        assert "calendar events" in tool.description.lower()
        assert tool.required_permission == PermissionLevel.SYSTEM

        param_names = [p.name for p in tool.parameters]
        assert "start_date" in param_names
        assert "end_date" in param_names
        assert "calendar_name" in param_names

    def test_create_event_tool_spec(self):
        """Test create_event tool specification."""
        from server.services.tools import registry, PermissionLevel

        tool = registry.get_tool("create_event")

        assert tool is not None
        assert tool.required_permission == PermissionLevel.SYSTEM

        param_names = [p.name for p in tool.parameters]
        assert "title" in param_names
        assert "start" in param_names
        assert "end" in param_names
        assert "location" in param_names
        assert "notes" in param_names

    def test_update_event_tool_spec(self):
        """Test update_event tool specification."""
        from server.services.tools import registry, PermissionLevel

        tool = registry.get_tool("update_event")

        assert tool is not None
        assert tool.required_permission == PermissionLevel.SYSTEM

        # event_id should be required
        event_id_param = next(p for p in tool.parameters if p.name == "event_id")
        assert event_id_param.required is True

    def test_delete_event_tool_spec(self):
        """Test delete_event tool specification."""
        from server.services.tools import registry, PermissionLevel

        tool = registry.get_tool("delete_event")

        assert tool is not None
        assert tool.required_permission == PermissionLevel.SYSTEM

        event_id_param = next(p for p in tool.parameters if p.name == "event_id")
        assert event_id_param.required is True

    def test_find_free_time_tool_spec(self):
        """Test find_free_time tool specification."""
        from server.services.tools import registry, PermissionLevel

        tool = registry.get_tool("find_free_time")

        assert tool is not None
        assert tool.required_permission == PermissionLevel.SYSTEM

        param_names = [p.name for p in tool.parameters]
        assert "duration_minutes" in param_names
        assert "work_hours_start" in param_names
        assert "work_hours_end" in param_names
        assert "include_weekends" in param_names


class TestCalendarSettings:
    """Tests for calendar settings integration."""

    def test_calendar_settings_defaults(self):
        """Test that calendar settings are in defaults."""
        from server.services.settings import SettingsService

        assert "calendar_caldav_url" in SettingsService.DEFAULTS
        assert "calendar_username" in SettingsService.DEFAULTS
        assert "calendar_password" in SettingsService.DEFAULTS
        assert "calendar_default" in SettingsService.DEFAULTS
        assert "calendar_enabled" in SettingsService.DEFAULTS

    def test_calendar_password_is_sensitive(self):
        """Test that calendar password is marked as sensitive."""
        from server.services.settings import SENSITIVE_KEYS

        assert "calendar_password" in SENSITIVE_KEYS


class TestSingletonService:
    """Tests for singleton service pattern."""

    def test_get_calendar_service(self):
        """Test getting singleton service."""
        service1 = get_calendar_service()
        service2 = get_calendar_service()

        assert service1 is service2

    def test_init_calendar_service(self):
        """Test initializing service with config."""
        config = CalendarConfig(
            caldav_url="https://caldav.example.com",
            username="user",
            password="pass"
        )

        service = init_calendar_service(config)

        assert service.config.caldav_url == "https://caldav.example.com"
        assert get_calendar_service() is service


class TestToolExecutionWithoutConfig:
    """Tests for tool execution without calendar configuration."""

    def test_list_events_not_configured(self):
        """Test list_events when calendar not configured."""
        from server.services.tools import _list_events_impl

        # Reset singleton to unconfigured state
        from server.services import calendar
        calendar._calendar_service = CalendarService()

        result = _list_events_impl()

        assert "not configured" in result.lower() or "not available" in result.lower()

    def test_create_event_not_configured(self):
        """Test create_event when calendar not configured."""
        from server.services.tools import _create_event_impl

        # Reset singleton
        from server.services import calendar
        calendar._calendar_service = CalendarService()

        result = _create_event_impl(
            title="Test",
            start="2026-02-05T14:00:00",
            end="2026-02-05T15:00:00"
        )

        assert "not configured" in result.lower() or "not available" in result.lower()

    def test_find_free_time_not_configured(self):
        """Test find_free_time when calendar not configured."""
        from server.services.tools import _find_free_time_impl

        # Reset singleton
        from server.services import calendar
        calendar._calendar_service = CalendarService()

        result = _find_free_time_impl(duration_minutes=60)

        assert "not configured" in result.lower() or "not available" in result.lower()


class TestOpenAIClaudeToolFormat:
    """Tests for tool format conversion."""

    def test_calendar_tools_in_openai_format(self):
        """Test calendar tools convert to OpenAI format."""
        from server.services.tools import registry

        tools = registry.to_openai_tools()
        tool_names = [t["function"]["name"] for t in tools]

        assert "list_events" in tool_names
        assert "create_event" in tool_names
        assert "find_free_time" in tool_names

    def test_calendar_tools_in_claude_format(self):
        """Test calendar tools convert to Claude format."""
        from server.services.tools import registry

        tools = registry.to_claude_tools()
        tool_names = [t["name"] for t in tools]

        assert "list_events" in tool_names
        assert "create_event" in tool_names
        assert "find_free_time" in tool_names

        # Check input_schema exists
        create_event = next(t for t in tools if t["name"] == "create_event")
        assert "input_schema" in create_event
        assert create_event["input_schema"]["type"] == "object"
        assert "title" in create_event["input_schema"]["properties"]
