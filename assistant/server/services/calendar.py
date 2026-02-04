"""Calendar service for CalDAV-based calendar integration.

This module provides calendar access via the CalDAV protocol, which works with:
- Apple iCloud Calendar
- Google Calendar (via CalDAV)
- FastMail, Nextcloud, and other CalDAV servers

Requires SYSTEM permission level as calendar access is sensitive.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path
import uuid
import sys

# Add parent path for core module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.permissions import PermissionLevel

logger = logging.getLogger(__name__)

# Optional caldav import - graceful fallback if not installed
try:
    import caldav
    from caldav.elements import dav, cdav
    CALDAV_AVAILABLE = True
except ImportError:
    CALDAV_AVAILABLE = False
    caldav = None
    logger.warning("caldav library not installed. Calendar features will be unavailable.")


@dataclass
class CalendarEvent:
    """Represents a calendar event."""
    event_id: str
    title: str
    start: datetime
    end: datetime
    location: Optional[str] = None
    notes: Optional[str] = None
    all_day: bool = False
    calendar_name: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "event_id": self.event_id,
            "title": self.title,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "location": self.location,
            "notes": self.notes,
            "all_day": self.all_day,
            "calendar_name": self.calendar_name,
        }


@dataclass
class CalendarConfig:
    """Configuration for calendar connection."""
    caldav_url: str = ""  # e.g., https://caldav.icloud.com or https://www.google.com/calendar/dav/
    username: str = ""
    password: str = ""  # App-specific password for iCloud/Google
    default_calendar: Optional[str] = None  # Calendar name to use by default

    @property
    def is_configured(self) -> bool:
        """Check if calendar is configured."""
        return bool(self.caldav_url and self.username and self.password)


@dataclass
class FreeSlot:
    """Represents a free time slot."""
    start: datetime
    end: datetime
    duration_minutes: int

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "duration_minutes": self.duration_minutes,
        }


class CalendarService:
    """Service for calendar operations via CalDAV.

    Usage:
        config = CalendarConfig(
            caldav_url="https://caldav.icloud.com",
            username="your@email.com",
            password="app-specific-password"
        )
        service = CalendarService(config)

        events = await service.list_events(
            start=datetime.now(),
            end=datetime.now() + timedelta(days=7)
        )
    """

    def __init__(self, config: Optional[CalendarConfig] = None):
        """Initialize calendar service.

        Args:
            config: Calendar configuration. Can be set later via configure().
        """
        self.config = config or CalendarConfig()
        self._client: Optional["caldav.DAVClient"] = None
        self._principal: Optional["caldav.Principal"] = None
        self._calendars: dict[str, "caldav.Calendar"] = {}
        self._connected = False

    @property
    def is_available(self) -> bool:
        """Check if calendar functionality is available."""
        return CALDAV_AVAILABLE

    @property
    def is_configured(self) -> bool:
        """Check if calendar is configured."""
        return self.config.is_configured

    @property
    def is_connected(self) -> bool:
        """Check if connected to calendar server."""
        return self._connected

    def configure(self, config: CalendarConfig) -> None:
        """Update configuration and reset connection."""
        self.config = config
        self._connected = False
        self._client = None
        self._principal = None
        self._calendars = {}

    async def connect(self) -> dict:
        """Connect to CalDAV server.

        Returns:
            Dict with connection status and available calendars.
        """
        if not CALDAV_AVAILABLE:
            return {
                "success": False,
                "error": "caldav library not installed. Run: pip install caldav"
            }

        if not self.config.is_configured:
            return {
                "success": False,
                "error": "Calendar not configured. Set caldav_url, username, and password."
            }

        try:
            # Create CalDAV client
            self._client = caldav.DAVClient(
                url=self.config.caldav_url,
                username=self.config.username,
                password=self.config.password
            )

            # Get principal (user's calendar root)
            self._principal = self._client.principal()

            # Get available calendars
            calendars = self._principal.calendars()
            self._calendars = {}
            calendar_names = []

            for cal in calendars:
                name = cal.name or str(cal.url)
                self._calendars[name] = cal
                calendar_names.append(name)

            self._connected = True
            logger.info(f"Connected to CalDAV server. Found {len(calendars)} calendars.")

            return {
                "success": True,
                "calendars": calendar_names,
                "default_calendar": self.config.default_calendar or (calendar_names[0] if calendar_names else None)
            }

        except Exception as e:
            logger.error(f"CalDAV connection failed: {e}")
            self._connected = False
            return {
                "success": False,
                "error": f"Connection failed: {str(e)}"
            }

    def _get_calendar(self, calendar_name: Optional[str] = None) -> Optional["caldav.Calendar"]:
        """Get a calendar by name, or the default calendar."""
        if not self._connected or not self._calendars:
            return None

        name = calendar_name or self.config.default_calendar
        if name and name in self._calendars:
            return self._calendars[name]

        # Return first calendar if no specific name
        if self._calendars:
            return next(iter(self._calendars.values()))

        return None

    async def list_calendars(self) -> list[str]:
        """List available calendar names."""
        if not self._connected:
            result = await self.connect()
            if not result["success"]:
                return []
        return list(self._calendars.keys())

    async def list_events(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        calendar_name: Optional[str] = None
    ) -> list[CalendarEvent]:
        """List events in a date range.

        Args:
            start: Start of date range (default: now)
            end: End of date range (default: 7 days from start)
            calendar_name: Specific calendar to query (default: all calendars)

        Returns:
            List of CalendarEvent objects.
        """
        if not self._connected:
            result = await self.connect()
            if not result["success"]:
                logger.error(f"Cannot list events: {result.get('error')}")
                return []

        start = start or datetime.now()
        end = end or (start + timedelta(days=7))

        events = []

        # Determine which calendars to search
        if calendar_name:
            calendars_to_search = [self._calendars.get(calendar_name)]
        else:
            calendars_to_search = list(self._calendars.values())

        for cal in calendars_to_search:
            if not cal:
                continue

            try:
                cal_events = cal.date_search(start=start, end=end, expand=True)
                cal_name = cal.name or str(cal.url)

                for event in cal_events:
                    parsed = self._parse_event(event, cal_name)
                    if parsed:
                        events.append(parsed)

            except Exception as e:
                logger.error(f"Error fetching events from calendar: {e}")

        # Sort by start time
        events.sort(key=lambda e: e.start)
        return events

    def _parse_event(self, event, calendar_name: str) -> Optional[CalendarEvent]:
        """Parse a caldav event into CalendarEvent."""
        try:
            vevent = event.vobject_instance.vevent

            # Get event ID
            event_id = str(vevent.uid.value) if hasattr(vevent, 'uid') else str(uuid.uuid4())

            # Get title
            title = str(vevent.summary.value) if hasattr(vevent, 'summary') else "Untitled"

            # Get start/end times
            start_val = vevent.dtstart.value
            end_val = vevent.dtend.value if hasattr(vevent, 'dtend') else start_val

            # Check if all-day event (date without time)
            all_day = not isinstance(start_val, datetime)

            # Convert to datetime if needed
            if all_day:
                start = datetime.combine(start_val, datetime.min.time())
                end = datetime.combine(end_val, datetime.min.time())
            else:
                start = start_val if isinstance(start_val, datetime) else datetime.combine(start_val, datetime.min.time())
                end = end_val if isinstance(end_val, datetime) else datetime.combine(end_val, datetime.min.time())

            # Make timezone naive for consistency
            if hasattr(start, 'tzinfo') and start.tzinfo:
                start = start.replace(tzinfo=None)
            if hasattr(end, 'tzinfo') and end.tzinfo:
                end = end.replace(tzinfo=None)

            # Get optional fields
            location = str(vevent.location.value) if hasattr(vevent, 'location') else None
            notes = str(vevent.description.value) if hasattr(vevent, 'description') else None

            return CalendarEvent(
                event_id=event_id,
                title=title,
                start=start,
                end=end,
                location=location,
                notes=notes,
                all_day=all_day,
                calendar_name=calendar_name
            )

        except Exception as e:
            logger.warning(f"Failed to parse event: {e}")
            return None

    async def create_event(
        self,
        title: str,
        start: datetime,
        end: datetime,
        location: Optional[str] = None,
        notes: Optional[str] = None,
        calendar_name: Optional[str] = None
    ) -> dict:
        """Create a new calendar event.

        Args:
            title: Event title
            start: Event start time
            end: Event end time
            location: Optional location
            notes: Optional description/notes
            calendar_name: Calendar to add event to

        Returns:
            Dict with success status and event_id.
        """
        if not self._connected:
            result = await self.connect()
            if not result["success"]:
                return {"success": False, "error": result.get("error")}

        cal = self._get_calendar(calendar_name)
        if not cal:
            return {"success": False, "error": f"Calendar not found: {calendar_name or 'default'}"}

        # Check for conflicts
        conflicts = await self._check_conflicts(start, end, calendar_name)

        try:
            # Generate unique ID
            event_id = str(uuid.uuid4())

            # Build iCalendar data
            ical_data = self._build_ical(
                event_id=event_id,
                title=title,
                start=start,
                end=end,
                location=location,
                notes=notes
            )

            # Create event
            cal.save_event(ical_data)

            logger.info(f"Created event: {title} at {start}")

            return {
                "success": True,
                "event_id": event_id,
                "conflicts": conflicts
            }

        except Exception as e:
            logger.error(f"Failed to create event: {e}")
            return {"success": False, "error": str(e)}

    def _build_ical(
        self,
        event_id: str,
        title: str,
        start: datetime,
        end: datetime,
        location: Optional[str] = None,
        notes: Optional[str] = None
    ) -> str:
        """Build iCalendar format string for an event."""
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Genesis AI Assistant//EN",
            "BEGIN:VEVENT",
            f"UID:{event_id}",
            f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{title}",
        ]

        if location:
            lines.append(f"LOCATION:{location}")
        if notes:
            # Escape newlines in description
            escaped_notes = notes.replace('\n', '\\n')
            lines.append(f"DESCRIPTION:{escaped_notes}")

        lines.extend([
            "END:VEVENT",
            "END:VCALENDAR"
        ])

        return "\r\n".join(lines)

    async def _check_conflicts(
        self,
        start: datetime,
        end: datetime,
        calendar_name: Optional[str] = None,
        exclude_event_id: Optional[str] = None
    ) -> list[dict]:
        """Check for conflicting events in the time range."""
        events = await self.list_events(start=start, end=end, calendar_name=calendar_name)

        conflicts = []
        for event in events:
            if exclude_event_id and event.event_id == exclude_event_id:
                continue

            # Check if events overlap
            if event.start < end and event.end > start:
                conflicts.append({
                    "event_id": event.event_id,
                    "title": event.title,
                    "start": event.start.isoformat(),
                    "end": event.end.isoformat()
                })

        return conflicts

    async def update_event(
        self,
        event_id: str,
        title: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        location: Optional[str] = None,
        notes: Optional[str] = None,
        calendar_name: Optional[str] = None
    ) -> dict:
        """Update an existing calendar event.

        Args:
            event_id: ID of event to update
            title: New title (optional)
            start: New start time (optional)
            end: New end time (optional)
            location: New location (optional)
            notes: New notes (optional)
            calendar_name: Calendar containing the event

        Returns:
            Dict with success status.
        """
        if not self._connected:
            result = await self.connect()
            if not result["success"]:
                return {"success": False, "error": result.get("error")}

        # Find the event
        event_obj, found_calendar = await self._find_event_by_id(event_id, calendar_name)
        if not event_obj:
            return {"success": False, "error": f"Event not found: {event_id}"}

        try:
            # Get current event data
            vevent = event_obj.vobject_instance.vevent

            # Update fields
            if title is not None:
                vevent.summary.value = title
            if start is not None:
                vevent.dtstart.value = start
            if end is not None:
                vevent.dtend.value = end
            if location is not None:
                if hasattr(vevent, 'location'):
                    vevent.location.value = location
                else:
                    vevent.add('location').value = location
            if notes is not None:
                if hasattr(vevent, 'description'):
                    vevent.description.value = notes
                else:
                    vevent.add('description').value = notes

            # Check for conflicts if time changed
            conflicts = []
            if start is not None or end is not None:
                new_start = start or vevent.dtstart.value
                new_end = end or vevent.dtend.value
                if isinstance(new_start, datetime) and isinstance(new_end, datetime):
                    conflicts = await self._check_conflicts(
                        new_start, new_end, found_calendar, exclude_event_id=event_id
                    )

            # Save changes
            event_obj.save()

            logger.info(f"Updated event: {event_id}")

            return {
                "success": True,
                "event_id": event_id,
                "conflicts": conflicts
            }

        except Exception as e:
            logger.error(f"Failed to update event: {e}")
            return {"success": False, "error": str(e)}

    async def _find_event_by_id(
        self,
        event_id: str,
        calendar_name: Optional[str] = None
    ) -> tuple[Optional["caldav.Event"], Optional[str]]:
        """Find an event by its ID across calendars."""
        if calendar_name:
            calendars_to_search = [(calendar_name, self._calendars.get(calendar_name))]
        else:
            calendars_to_search = list(self._calendars.items())

        for cal_name, cal in calendars_to_search:
            if not cal:
                continue

            try:
                # Search in a wide date range
                events = cal.date_search(
                    start=datetime.now() - timedelta(days=365),
                    end=datetime.now() + timedelta(days=365),
                    expand=False
                )

                for event in events:
                    try:
                        vevent = event.vobject_instance.vevent
                        if hasattr(vevent, 'uid') and str(vevent.uid.value) == event_id:
                            return event, cal_name
                    except:
                        continue

            except Exception as e:
                logger.warning(f"Error searching calendar {cal_name}: {e}")

        return None, None

    async def delete_event(
        self,
        event_id: str,
        calendar_name: Optional[str] = None
    ) -> dict:
        """Delete a calendar event.

        Args:
            event_id: ID of event to delete
            calendar_name: Calendar containing the event

        Returns:
            Dict with success status.
        """
        if not self._connected:
            result = await self.connect()
            if not result["success"]:
                return {"success": False, "error": result.get("error")}

        event_obj, _ = await self._find_event_by_id(event_id, calendar_name)
        if not event_obj:
            return {"success": False, "error": f"Event not found: {event_id}"}

        try:
            event_obj.delete()
            logger.info(f"Deleted event: {event_id}")
            return {"success": True, "event_id": event_id}

        except Exception as e:
            logger.error(f"Failed to delete event: {e}")
            return {"success": False, "error": str(e)}

    async def find_free_time(
        self,
        duration_minutes: int,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        calendar_name: Optional[str] = None,
        work_hours_start: int = 9,
        work_hours_end: int = 17,
        include_weekends: bool = False
    ) -> list[FreeSlot]:
        """Find free time slots of a given duration.

        Args:
            duration_minutes: Minimum duration needed
            start: Start of search range (default: now)
            end: End of search range (default: 7 days from start)
            calendar_name: Calendar to check
            work_hours_start: Start of work hours (0-23)
            work_hours_end: End of work hours (0-23)
            include_weekends: Include Saturday/Sunday

        Returns:
            List of FreeSlot objects.
        """
        start = start or datetime.now()
        end = end or (start + timedelta(days=7))

        # Get all events in range
        events = await self.list_events(start=start, end=end, calendar_name=calendar_name)

        # Build list of busy periods
        busy_periods = [(e.start, e.end) for e in events if not e.all_day]
        busy_periods.sort(key=lambda x: x[0])

        free_slots = []
        current = start

        while current < end:
            # Skip to work hours
            if current.hour < work_hours_start:
                current = current.replace(hour=work_hours_start, minute=0, second=0)
            elif current.hour >= work_hours_end:
                current = (current + timedelta(days=1)).replace(
                    hour=work_hours_start, minute=0, second=0
                )
                continue

            # Skip weekends if configured
            if not include_weekends and current.weekday() >= 5:
                current = (current + timedelta(days=1)).replace(
                    hour=work_hours_start, minute=0, second=0
                )
                continue

            # Find end of current day's work hours
            day_end = current.replace(hour=work_hours_end, minute=0, second=0)

            # Find next busy period
            next_busy_start = day_end
            for busy_start, busy_end in busy_periods:
                if busy_start > current:
                    next_busy_start = min(busy_start, day_end)
                    break

            # Calculate free time
            free_duration = int((next_busy_start - current).total_seconds() / 60)

            if free_duration >= duration_minutes:
                free_slots.append(FreeSlot(
                    start=current,
                    end=current + timedelta(minutes=duration_minutes),
                    duration_minutes=duration_minutes
                ))

            # Move past the busy period
            found_busy = False
            for busy_start, busy_end in busy_periods:
                if busy_start <= current < busy_end:
                    current = busy_end
                    found_busy = True
                    break
                elif busy_start > current:
                    current = busy_end
                    found_busy = True
                    break

            if not found_busy:
                # No more busy periods today, move to next day
                current = (current + timedelta(days=1)).replace(
                    hour=work_hours_start, minute=0, second=0
                )

            # Limit results
            if len(free_slots) >= 10:
                break

        return free_slots


# Singleton instance
_calendar_service: Optional[CalendarService] = None


def get_calendar_service() -> CalendarService:
    """Get the singleton calendar service instance."""
    global _calendar_service
    if _calendar_service is None:
        _calendar_service = CalendarService()
    return _calendar_service


def init_calendar_service(config: CalendarConfig) -> CalendarService:
    """Initialize calendar service with configuration."""
    global _calendar_service
    _calendar_service = CalendarService(config)
    return _calendar_service
