# Telegram Bot Setup Guide

This guide explains how to set up and use the Genesis Telegram bot for multi-channel messaging.

## Overview

The Telegram bot provides a mobile-friendly interface to Genesis AI Assistant. It forwards messages between Telegram and the Genesis Chat API, allowing you to chat with Genesis from your phone.

**Architecture:**
```
Telegram App (mobile/desktop)
        ↓
Telegram Cloud Servers
        ↓ (long-polling)
TelegramService
        ↓ (HTTP POST)
Genesis Chat API (localhost:8080)
        ↓
Response → Telegram
```

## Features

- **Text messaging**: Normal chat conversations
- **Image support**: Send images for visual analysis
- **PDF support**: Send PDFs for document analysis
- **Bot commands**: `/start`, `/status`, `/persona`, `/search`, `/help`
- **Access control**: Only whitelisted user IDs can interact
- **Markdown formatting**: Responses formatted with Telegram markdown
- **Long message splitting**: Automatically splits messages over 4096 characters
- **Secure**: Bot token encrypted at rest, user whitelist required

## Prerequisites

1. Genesis AI Assistant installed and running
2. A Telegram account
3. Access to Telegram (mobile app or desktop)

## Step 1: Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` to start the bot creation process
3. Follow the instructions:
   - Choose a name for your bot (e.g., "Genesis Assistant")
   - Choose a username (must end in "bot", e.g., "genesis_ai_bot")
4. Copy the **bot token** (looks like: `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`)
5. Keep this token secret - it's like a password for your bot

## Step 2: Get Your Telegram User ID

1. Search for **@userinfobot** in Telegram
2. Send `/start` to the bot
3. Copy your **user ID** (a number like: `123456789`)
4. Anyone you want to access the bot will need to provide their user ID

## Step 3: Configure Genesis

### Option A: Interactive CLI Setup (Recommended)

```bash
cd /Volumes/Storage/Server/Startup/Genesis/assistant
python -m cli telegram setup
```

This will guide you through:
1. Entering your bot token
2. Entering allowed user IDs (comma-separated for multiple users)
3. Enabling the bot

### Option B: Manual Configuration

1. Open the Genesis Settings UI (http://127.0.0.1:8080)
2. Navigate to Settings
3. Add the following:
   - **Telegram Bot Token**: Paste your bot token
   - **Telegram Allowed Users**: Enter user IDs (comma-separated: `123456789,987654321`)
   - **Telegram Enabled**: Check the box
4. Save settings

## Step 4: Restart Genesis

For the bot to start, restart the Genesis server:

```bash
supervisorctl restart assistant
```

Or if not using Supervisor:

```bash
# Stop the server (Ctrl+C if running in terminal)
# Then start it again
cd /Volumes/Storage/Server/Startup/Genesis/assistant
python -m server.main
```

## Step 5: Start Chatting

1. Open Telegram
2. Search for your bot by username (e.g., `@genesis_ai_bot`)
3. Click **Start** or send `/start`
4. You should see a welcome message
5. Start chatting!

## Usage

### Commands

- `/start` - Welcome message and feature overview
- `/help` - Show all available commands
- `/status` - Show Genesis system status (uptime, version, model)
- `/persona <name>` - Switch AI persona (coming soon)
- `/search <query>` - Search conversations (coming soon)

### Text Messages

Just send a message like you would in any chat. Genesis will respond using the configured AI model.

### Images

Send an image with or without a caption. Genesis will analyze the image and respond.

### PDFs

Send a PDF file (up to 20MB). Genesis will analyze the document and respond.

## Security

### Access Control

Only Telegram user IDs in the whitelist can interact with the bot. Anyone else will receive an "Access denied" message with their user ID (so they can request access).

### Bot Token Security

- The bot token is **encrypted at rest** in the Genesis database
- Never share your bot token publicly
- If compromised, revoke the token via @BotFather and create a new bot

### User Whitelist

Add user IDs carefully. Anyone on the whitelist can:
- Send messages to Genesis
- Upload images and PDFs
- Access all bot features

## Troubleshooting

### Bot doesn't respond

1. Check bot status:
   ```bash
   python -m cli telegram status
   ```

2. Check Genesis logs:
   ```bash
   python -m cli logs tail
   ```

3. Verify bot is running:
   - Check Genesis server logs for "Telegram bot started"

### "Access denied" message

Your Telegram user ID is not in the whitelist. Either:
1. Add your user ID via `python -m cli telegram setup`
2. Or update the whitelist in Settings UI

### Bot token error

If you see "Telegram bot token not configured":
1. Run `python -m cli telegram setup`
2. Enter a valid bot token from @BotFather
3. Restart Genesis

### Network issues

The bot uses long-polling, which requires outbound internet access to Telegram servers. If you're behind a firewall:
- Ensure Genesis can reach `api.telegram.org`
- Check firewall rules

## Architecture Details

### Long-Polling Mode

The bot uses **long-polling** instead of webhooks:
- **Advantage**: No public URL or SSL certificate required
- **How it works**: Bot polls Telegram servers every few seconds for new messages
- **Latency**: Typically < 1 second

### Message Flow

1. User sends message in Telegram app
2. Message routed through Telegram cloud
3. TelegramService polls and receives message
4. TelegramService forwards to Genesis Chat API (localhost)
5. Chat API processes with configured AI model
6. Response sent back to TelegramService
7. TelegramService sends response to Telegram
8. User sees response in Telegram app

### File Handling

Images and PDFs:
1. Downloaded from Telegram (up to 20MB)
2. Uploaded to Genesis via Upload API
3. File ID included in chat request
4. AI model analyzes file content
5. Response sent back via Telegram

## Advanced Configuration

### Multiple Users

To allow multiple users:
```
telegram_allowed_users: 123456789,987654321,456789123
```

### Disabling the Bot

Via CLI:
```bash
python -m cli telegram setup
# Answer 'n' when asked "Enable Telegram bot?"
```

Via Settings UI:
- Uncheck "Telegram Enabled"
- Save settings
- Restart Genesis

### Changing Bot Token

If you need to rotate the bot token:
1. Create a new bot with @BotFather or revoke/regenerate token
2. Run `python -m cli telegram setup`
3. Enter new token
4. Restart Genesis

## Limitations

- **File size**: Max 20MB for uploads (Telegram limit)
- **Message length**: Messages over 4096 characters are split
- **Rate limits**: Telegram limits 30 messages/second per chat
- **No voice/video**: Only text, images, and PDFs supported currently

## Future Enhancements

Planned features:
- Persona switching via `/persona` command
- Conversation search via `/search` command
- Voice message support
- Inline mode for quick queries
- Conversation management (new, switch, delete)

## Support

For issues or questions:
1. Check the Genesis logs: `python -m cli logs tail`
2. Review this documentation
3. Check Telegram bot status: `python -m cli telegram status`
4. Create a GitHub issue with error details
