# Calendar Integration Setup

Genesis AI Assistant can integrate with your calendar via the CalDAV protocol, enabling natural language scheduling, event management, and free time discovery.

## Supported Calendar Services

The assistant supports any CalDAV-compatible calendar:

| Service | CalDAV URL | Notes |
|---------|-----------|-------|
| Apple iCloud | `https://caldav.icloud.com` | Requires app-specific password |
| Google Calendar | `https://apidata.googleusercontent.com/caldav/v2/` | Requires OAuth or app password |
| Fastmail | `https://caldav.fastmail.com/dav/` | Standard username/password |
| Nextcloud | `https://your-server.com/remote.php/dav/` | Standard username/password |
| Synology | `https://your-nas:5001/caldav/` | Standard username/password |

## Prerequisites

1. **Install caldav library** (if not already installed):
   ```bash
   cd $GENESIS_DIR/assistant
   pip install caldav
   ```

2. **Set SYSTEM permission** - Calendar access requires elevated permissions:
   ```bash
   export ASSISTANT_PERMISSION_LEVEL=2
   ```
   Or set `permission_level: 2` in settings.

## Configuration

### Option 1: Via Settings API

```bash
# Set calendar credentials
curl -X POST http://127.0.0.1:8080/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "calendar_caldav_url": "https://caldav.icloud.com",
    "calendar_username": "your@email.com",
    "calendar_password": "your-app-specific-password",
    "calendar_default": "Personal",
    "calendar_enabled": true
  }'
```

### Option 2: Via Web UI

1. Open Settings (gear icon)
2. Scroll to "Calendar Integration"
3. Enter your CalDAV URL, username, and app password
4. Select default calendar
5. Enable calendar integration

## iCloud Calendar Setup

Apple iCloud requires an **app-specific password** (not your regular password):

1. Go to [appleid.apple.com](https://appleid.apple.com)
2. Sign in with your Apple ID
3. Go to **Sign-In and Security** > **App-Specific Passwords**
4. Click **Generate an app-specific password**
5. Name it "Genesis Assistant"
6. Copy the generated password
7. Use this password in calendar settings

**CalDAV URL for iCloud**: `https://caldav.icloud.com`

## Google Calendar Setup

Google Calendar requires OAuth or app-specific password:

### Method 1: App Password (simpler)
1. Enable 2FA on your Google account
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Generate an app password for "Other (Custom name)"
4. Use this password in calendar settings

**CalDAV URL for Google**: `https://apidata.googleusercontent.com/caldav/v2/your@email.com/events`

## Available Calendar Tools

Once configured, the assistant has access to these tools:

### list_events
List calendar events in a date range.

**Example prompts:**
- "What's on my calendar today?"
- "Show me my meetings for this week"
- "What do I have scheduled tomorrow?"

### create_event
Create new calendar events.

**Example prompts:**
- "Schedule a meeting tomorrow at 2pm for 1 hour"
- "Create an event called 'Dentist' on Friday at 3pm"
- "Add a lunch meeting with John at noon"

### update_event
Modify existing events.

**Example prompts:**
- "Move my 2pm meeting to 3pm"
- "Change the location of tomorrow's meeting to Room 202"
- "Update the meeting title to 'Team Standup'"

### delete_event
Remove events from calendar.

**Example prompts:**
- "Cancel my 3pm appointment"
- "Delete the meeting with Jane"
- "Remove tomorrow's dentist appointment"

### find_free_time
Find available time slots.

**Example prompts:**
- "When am I free for a 30-minute meeting this week?"
- "Find me an hour slot tomorrow afternoon"
- "What time slots are available on Friday?"

## Permission Requirements

All calendar tools require **SYSTEM permission** (level 2) because calendar access is sensitive. The assistant will:

1. Request permission escalation if not already at SYSTEM level
2. Show a prompt explaining what calendar access allows
3. Wait for user approval before proceeding

## Conflict Detection

When creating or updating events, the assistant automatically checks for conflicts:

```
Creating event "Team Meeting" at 2pm...
Warning: Conflicts with 1 existing event:
- "1:1 with Manager" (1:30pm - 2:30pm)

Event created anyway. Would you like to reschedule?
```

## Work Hours & Weekends

The `find_free_time` tool respects work hours by default:

- Default work hours: 9am - 5pm
- Weekends excluded by default
- Configurable via tool parameters

Example: "Find me a free hour this week, including weekends"

## Troubleshooting

### "Calendar not configured"
Set your calendar credentials in settings.

### "caldav library not installed"
Run: `pip install caldav`

### "Connection failed"
- Verify your CalDAV URL is correct
- Check username (usually your email)
- Ensure app-specific password is correct
- Check network connectivity

### "Permission denied"
Set `ASSISTANT_PERMISSION_LEVEL=2` or update permission in settings.

### Events not showing
- Verify the correct calendar is selected
- Check date range parameters
- Some calendars may need time to sync

## Testing Calendar Integration

```bash
# Start the server
cd $GENESIS_DIR/assistant
python3 -m server.main &

# Test connection (requires curl + jq)
curl http://127.0.0.1:8080/api/settings | jq '.calendar_enabled'

# Via chat (with calendar configured)
curl -X POST http://127.0.0.1:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is on my calendar today?"}'
```

## Security Notes

- Calendar passwords are **encrypted at rest** using AES-256-GCM
- Credentials are never logged or exposed in API responses
- SYSTEM permission required for all calendar operations
- All calendar actions are logged for audit purposes

## Known Limitations

- No support for recurring event patterns (v1)
- No attendee/invitation management (v1)
- No Google Calendar OAuth flow (requires app password)
- Single calendar account (multiple accounts planned)
