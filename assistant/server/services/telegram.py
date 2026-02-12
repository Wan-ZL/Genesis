"""Telegram Bot Gateway for multi-channel messaging.

This service provides a thin adapter layer that forwards messages between
Telegram and the Genesis Chat API. It uses python-telegram-bot with long-polling
to avoid needing a public URL.

Architecture:
    Telegram App → Telegram Cloud → TelegramService (long-polling)
                                         ↓
                                    Chat API (localhost:8080)
                                         ↓
                                    Response → Telegram
"""
import logging
import asyncio
import json
from typing import Optional, List
from pathlib import Path
import httpx
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from telegram.constants import ParseMode

import config

logger = logging.getLogger(__name__)


class TelegramService:
    """Telegram bot service that forwards messages to Genesis Chat API.

    Features:
    - Long-polling mode (no webhook, no public URL needed)
    - Access control via user whitelist
    - Text and file (image/PDF) support
    - Bot commands: /start, /status, /persona, /search, /help
    - Graceful error handling
    - Markdown formatting support
    """

    def __init__(
        self,
        bot_token: str,
        allowed_users: List[int],
        chat_api_url: str = "http://127.0.0.1:8080/api/chat",
        upload_api_url: str = "http://127.0.0.1:8080/api/upload",
        status_api_url: str = "http://127.0.0.1:8080/api/status"
    ):
        """Initialize Telegram service.

        Args:
            bot_token: Telegram bot token from BotFather
            allowed_users: List of allowed Telegram user IDs
            chat_api_url: URL of Genesis chat API endpoint
            upload_api_url: URL of Genesis upload API endpoint
            status_api_url: URL of Genesis status API endpoint
        """
        self.bot_token = bot_token
        self.allowed_users = set(allowed_users)
        self.chat_api_url = chat_api_url
        self.upload_api_url = upload_api_url
        self.status_api_url = status_api_url

        self.application: Optional[Application] = None
        self._running = False

    async def start(self):
        """Start the Telegram bot with long-polling."""
        if self._running:
            logger.warning("Telegram service already running")
            return

        if not self.bot_token:
            logger.warning("Telegram bot token not configured, skipping start")
            return

        if not self.allowed_users:
            logger.warning("No Telegram users whitelisted, bot will reject all messages")

        try:
            # Create application with bot token
            self.application = (
                Application.builder()
                .token(self.bot_token)
                .build()
            )

            # Register command handlers
            self.application.add_handler(CommandHandler("start", self._cmd_start))
            self.application.add_handler(CommandHandler("help", self._cmd_help))
            self.application.add_handler(CommandHandler("status", self._cmd_status))
            self.application.add_handler(CommandHandler("persona", self._cmd_persona))
            self.application.add_handler(CommandHandler("search", self._cmd_search))

            # Register message handlers
            self.application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text_message)
            )
            self.application.add_handler(
                MessageHandler(filters.PHOTO, self._handle_photo_message)
            )
            self.application.add_handler(
                MessageHandler(filters.Document.PDF, self._handle_document_message)
            )

            # Start polling (non-blocking)
            await self.application.initialize()
            await self.application.start()
            if self.application.updater:
                await self.application.updater.start_polling()

            self._running = True
            logger.info(f"Telegram bot started with {len(self.allowed_users)} whitelisted users")

        except Exception as e:
            logger.error(f"Failed to start Telegram bot: {e}", exc_info=True)
            raise

    async def stop(self):
        """Stop the Telegram bot gracefully."""
        if not self._running:
            return

        try:
            if self.application:
                if self.application.updater:
                    await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()

            self._running = False
            logger.info("Telegram bot stopped")

        except Exception as e:
            logger.error(f"Error stopping Telegram bot: {e}", exc_info=True)

    def is_running(self) -> bool:
        """Check if the bot is running."""
        return self._running

    def _is_authorized(self, user_id: int) -> bool:
        """Check if a user is authorized to use the bot."""
        return user_id in self.allowed_users

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        if not update.message or not update.effective_user:
            return
        user_id = update.effective_user.id

        if not self._is_authorized(user_id):
            await update.message.reply_text(
                "🚫 Access denied. Your user ID is not whitelisted.\n\n"
                f"User ID: `{user_id}`\n\n"
                "Contact the administrator to request access.",
                parse_mode=ParseMode.MARKDOWN
            )
            logger.warning(f"Unauthorized access attempt from user {user_id}")
            return

        await update.message.reply_text(
            "👋 *Welcome to Genesis AI Assistant*\n\n"
            "I'm your 24/7 AI assistant. Send me a message and I'll help you.\n\n"
            "*Commands:*\n"
            "/help - Show all available commands\n"
            "/status - Show system status\n"
            "/persona - Switch AI persona\n"
            "/search - Search conversations\n\n"
            "*File Support:*\n"
            "Send images or PDFs and I'll analyze them.",
            parse_mode=ParseMode.MARKDOWN
        )

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        if not update.message or not update.effective_user:
            return
        user_id = update.effective_user.id
        if not self._is_authorized(user_id):
            await update.message.reply_text("🚫 Access denied.")
            return

        await update.message.reply_text(
            "*Genesis Bot Commands*\n\n"
            "/start - Welcome message\n"
            "/help - Show this help\n"
            "/status - System status and uptime\n"
            "/persona <name> - Switch AI persona (e.g., /persona code_expert)\n"
            "/search <query> - Search conversations\n\n"
            "*Usage:*\n"
            "• Send text messages for normal chat\n"
            "• Send images for visual analysis\n"
            "• Send PDFs for document analysis\n\n"
            "*Features:*\n"
            "• Multi-modal support (text, images, PDFs)\n"
            "• Persistent conversation history\n"
            "• Custom personas for different use cases",
            parse_mode=ParseMode.MARKDOWN
        )

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command - show system status."""
        if not update.message or not update.effective_user:
            return
        user_id = update.effective_user.id
        if not self._is_authorized(user_id):
            await update.message.reply_text("🚫 Access denied.")
            return

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.status_api_url, timeout=10.0)
                response.raise_for_status()
                status = response.json()

            # Format status information
            uptime = status.get("uptime", "Unknown")
            version = status.get("version", "Unknown")
            model = status.get("config", {}).get("model", "Unknown")
            message_count = status.get("database", {}).get("message_count", 0)

            status_text = (
                f"*Genesis System Status*\n\n"
                f"✅ *Online*\n"
                f"⏱ Uptime: {uptime}\n"
                f"🔢 Version: {version}\n"
                f"🤖 Model: {model}\n"
                f"💬 Messages: {message_count}\n"
            )

            await update.message.reply_text(status_text, parse_mode=ParseMode.MARKDOWN)

        except Exception as e:
            logger.error(f"Failed to fetch status: {e}")
            await update.message.reply_text(
                "❌ Failed to fetch system status. The service may be offline."
            )

    async def _cmd_persona(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /persona command - switch AI persona."""
        if not update.message or not update.effective_user:
            return
        user_id = update.effective_user.id
        if not self._is_authorized(user_id):
            await update.message.reply_text("🚫 Access denied.")
            return

        # TODO: Implement persona switching via API when ready
        # For now, show available personas
        await update.message.reply_text(
            "*Available Personas*\n\n"
            "• default - General-purpose assistant\n"
            "• code_expert - Programming and technical help\n"
            "• creative_writer - Creative writing assistance\n\n"
            "Usage: /persona <name>\n"
            "Example: /persona code_expert\n\n"
            "Note: Persona switching API coming soon.",
            parse_mode=ParseMode.MARKDOWN
        )

    async def _cmd_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /search command - search conversations."""
        if not update.message or not update.effective_user:
            return
        user_id = update.effective_user.id
        if not self._is_authorized(user_id):
            await update.message.reply_text("🚫 Access denied.")
            return

        # Extract search query from command
        query = " ".join(context.args) if context.args else ""

        if not query:
            await update.message.reply_text(
                "Please provide a search query.\n"
                "Example: /search kubernetes deployment"
            )
            return

        # TODO: Implement search API integration
        await update.message.reply_text(
            f"🔍 Searching for: _{query}_\n\n"
            "Search API integration coming soon.",
            parse_mode=ParseMode.MARKDOWN
        )

    async def _handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming text messages."""
        if not update.message or not update.effective_user:
            return
        user_id = update.effective_user.id

        if not self._is_authorized(user_id):
            await update.message.reply_text("🚫 Access denied.")
            return

        user_message = update.message.text
        logger.info(f"Received message from user {user_id}: {user_message[:50]}...")

        # Send typing indicator
        await update.message.chat.send_action("typing")

        try:
            # Forward to Chat API
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.chat_api_url,
                    json={"message": user_message},
                    timeout=120.0  # 2 minutes for LLM response
                )
                response.raise_for_status()
                data = response.json()

            # Extract response
            ai_response = data.get("response", "")
            model = data.get("model", "Unknown")

            if not ai_response:
                await update.message.reply_text("❌ Empty response from API")
                return

            # Convert to Telegram-compatible markdown
            telegram_response = self._convert_markdown_to_telegram(ai_response)

            # Send response (split if too long)
            await self._send_long_message(update, telegram_response)

            logger.info(f"Sent response to user {user_id} using model {model}")

        except httpx.HTTPError as e:
            logger.error(f"Chat API error: {e}")
            await update.message.reply_text(
                f"❌ API Error: {str(e)}\n\n"
                "The Genesis service may be experiencing issues."
            )
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            await update.message.reply_text(
                f"❌ Error: {str(e)}\n\n"
                "An unexpected error occurred."
            )

    async def _handle_photo_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming photo messages."""
        if not update.message or not update.effective_user:
            return
        user_id = update.effective_user.id

        if not self._is_authorized(user_id):
            await update.message.reply_text("🚫 Access denied.")
            return

        # Get the highest resolution photo
        photo = update.message.photo[-1]
        caption = update.message.caption or ""

        logger.info(f"Received photo from user {user_id}, size: {photo.file_size} bytes")

        await update.message.chat.send_action("upload_photo")

        try:
            # Download photo
            file = await photo.get_file()
            photo_bytes = await file.download_as_bytearray()

            # Upload to Genesis
            async with httpx.AsyncClient() as client:
                files = {"file": ("image.jpg", bytes(photo_bytes), "image/jpeg")}
                upload_response = await client.post(
                    self.upload_api_url,
                    files=files,
                    timeout=30.0
                )
                upload_response.raise_for_status()
                upload_data = upload_response.json()

            file_id = upload_data.get("file_id")

            if not file_id:
                await update.message.reply_text("❌ Failed to upload image")
                return

            # Forward to Chat API with file_id
            await update.message.chat.send_action("typing")

            async with httpx.AsyncClient() as client:
                chat_response = await client.post(
                    self.chat_api_url,
                    json={
                        "message": caption or "What's in this image?",
                        "file_ids": [file_id]
                    },
                    timeout=120.0
                )
                chat_response.raise_for_status()
                data = chat_response.json()

            ai_response = data.get("response", "")
            telegram_response = self._convert_markdown_to_telegram(ai_response)

            await self._send_long_message(update, telegram_response)
            logger.info(f"Sent image analysis to user {user_id}")

        except Exception as e:
            logger.error(f"Error handling photo: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error processing image: {str(e)}")

    async def _handle_document_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming PDF document messages."""
        if not update.message or not update.effective_user:
            return
        user_id = update.effective_user.id

        if not self._is_authorized(user_id):
            await update.message.reply_text("🚫 Access denied.")
            return

        document = update.message.document
        caption = update.message.caption or ""

        # Validate it's a PDF
        if not document.file_name.lower().endswith('.pdf'):
            await update.message.reply_text("Only PDF documents are supported.")
            return

        # Check size (Telegram limit is 20MB)
        if document.file_size > 20 * 1024 * 1024:
            await update.message.reply_text("PDF too large. Maximum size: 20MB")
            return

        logger.info(f"Received PDF from user {user_id}: {document.file_name}, {document.file_size} bytes")

        await update.message.chat.send_action("upload_document")

        try:
            # Download PDF
            file = await document.get_file()
            pdf_bytes = await file.download_as_bytearray()

            # Upload to Genesis
            async with httpx.AsyncClient() as client:
                files = {"file": (document.file_name, bytes(pdf_bytes), "application/pdf")}
                upload_response = await client.post(
                    self.upload_api_url,
                    files=files,
                    timeout=30.0
                )
                upload_response.raise_for_status()
                upload_data = upload_response.json()

            file_id = upload_data.get("file_id")

            if not file_id:
                await update.message.reply_text("❌ Failed to upload PDF")
                return

            # Forward to Chat API with file_id
            await update.message.chat.send_action("typing")

            async with httpx.AsyncClient() as client:
                chat_response = await client.post(
                    self.chat_api_url,
                    json={
                        "message": caption or "What's in this PDF?",
                        "file_ids": [file_id]
                    },
                    timeout=120.0
                )
                chat_response.raise_for_status()
                data = chat_response.json()

            ai_response = data.get("response", "")
            telegram_response = self._convert_markdown_to_telegram(ai_response)

            await self._send_long_message(update, telegram_response)
            logger.info(f"Sent PDF analysis to user {user_id}")

        except Exception as e:
            logger.error(f"Error handling PDF: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error processing PDF: {str(e)}")

    def _convert_markdown_to_telegram(self, text: str) -> str:
        """Convert standard markdown to Telegram-compatible markdown.

        Telegram supports a limited subset of markdown:
        - *bold* (not **bold**)
        - _italic_ (not _italic_)
        - `code`
        - ```code blocks```
        - [link](url)

        This is a basic converter. For production, consider using a proper parser.
        """
        # Convert **bold** to *bold*
        text = text.replace("**", "*")

        # Telegram doesn't like certain characters in markdown mode
        # Escape special characters that might break parsing
        # (this is simplistic; a real implementation would be more sophisticated)

        return text

    async def _send_long_message(self, update: Update, text: str):
        """Send a message, splitting if it exceeds Telegram's length limit.

        Telegram has a 4096 character limit per message.
        """
        MAX_LENGTH = 4096

        if len(text) <= MAX_LENGTH:
            try:
                await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
            except Exception:
                # Fallback to plain text if markdown fails
                await update.message.reply_text(text)
            return

        # Split into chunks
        chunks = []
        while text:
            if len(text) <= MAX_LENGTH:
                chunks.append(text)
                break

            # Find a good split point (prefer newline)
            split_point = text.rfind('\n', 0, MAX_LENGTH)
            if split_point == -1:
                split_point = MAX_LENGTH

            chunks.append(text[:split_point])
            text = text[split_point:].lstrip()

        # Send chunks
        for i, chunk in enumerate(chunks):
            try:
                if i == 0:
                    await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
                else:
                    # Subsequent chunks sent without reply to avoid nesting
                    await update.message.chat.send_message(chunk, parse_mode=ParseMode.MARKDOWN)
            except Exception:
                # Fallback to plain text
                if i == 0:
                    await update.message.reply_text(chunk)
                else:
                    await update.message.chat.send_message(chunk)


# Global singleton instance
_telegram_service: Optional[TelegramService] = None


async def get_telegram_service() -> Optional[TelegramService]:
    """Get or create the Telegram service singleton.

    Returns None if Telegram is not configured.
    """
    global _telegram_service

    if _telegram_service is not None:
        return _telegram_service

    # Load settings from database
    from server.services.settings import SettingsService
    settings_service = SettingsService(config.DATABASE_PATH)
    settings = await settings_service.get_all()

    bot_token = settings.get("telegram_bot_token", "")
    allowed_users_str = settings.get("telegram_allowed_users", "")

    if not bot_token:
        logger.info("Telegram bot token not configured")
        return None

    # Parse allowed users (comma-separated list of user IDs)
    allowed_users = []
    if allowed_users_str:
        try:
            allowed_users = [
                int(uid.strip())
                for uid in allowed_users_str.split(",")
                if uid.strip()
            ]
        except ValueError:
            logger.error("Invalid telegram_allowed_users format, expected comma-separated integers")
            return None

    if not allowed_users:
        logger.warning("No Telegram users whitelisted")

    _telegram_service = TelegramService(
        bot_token=bot_token,
        allowed_users=allowed_users
    )

    return _telegram_service
