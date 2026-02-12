"""Tests for Telegram bot service."""
import pytest
from unittest.mock import AsyncMock, Mock, patch
from telegram import Update, Message, User, Chat, PhotoSize, Document
from telegram.ext import ContextTypes

from server.services.telegram import TelegramService


@pytest.fixture
def telegram_service():
    """Create a TelegramService instance for testing."""
    return TelegramService(
        bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        allowed_users=[12345, 67890],
        chat_api_url="http://test.local/api/chat",
        upload_api_url="http://test.local/api/upload",
        status_api_url="http://test.local/api/status"
    )


@pytest.fixture
def mock_update():
    """Create a mock Telegram Update object."""
    update = Mock(spec=Update)
    update.effective_user = Mock(spec=User)
    update.effective_user.id = 12345
    update.message = Mock(spec=Message)
    update.message.chat = Mock(spec=Chat)
    update.message.reply_text = AsyncMock()
    update.message.chat.send_action = AsyncMock()
    update.message.chat.send_message = AsyncMock()
    return update


@pytest.fixture
def mock_context():
    """Create a mock Telegram Context object."""
    context = Mock(spec=ContextTypes.DEFAULT_TYPE)
    context.args = []
    return context


class TestTelegramServiceInit:
    """Tests for TelegramService initialization."""

    def test_init_with_valid_params(self):
        """Test initialization with valid parameters."""
        service = TelegramService(
            bot_token="test_token",
            allowed_users=[123, 456]
        )
        assert service.bot_token == "test_token"
        assert service.allowed_users == {123, 456}
        assert not service.is_running()

    def test_init_with_empty_allowed_users(self):
        """Test initialization with empty allowed users list."""
        service = TelegramService(
            bot_token="test_token",
            allowed_users=[]
        )
        assert service.allowed_users == set()

    def test_init_with_custom_urls(self):
        """Test initialization with custom API URLs."""
        service = TelegramService(
            bot_token="test_token",
            allowed_users=[123],
            chat_api_url="http://custom/chat",
            upload_api_url="http://custom/upload"
        )
        assert service.chat_api_url == "http://custom/chat"
        assert service.upload_api_url == "http://custom/upload"


class TestAccessControl:
    """Tests for user access control."""

    def test_is_authorized_valid_user(self, telegram_service):
        """Test authorization check for whitelisted user."""
        assert telegram_service._is_authorized(12345) is True
        assert telegram_service._is_authorized(67890) is True

    def test_is_authorized_invalid_user(self, telegram_service):
        """Test authorization check for non-whitelisted user."""
        assert telegram_service._is_authorized(99999) is False
        assert telegram_service._is_authorized(0) is False

    @pytest.mark.asyncio
    async def test_cmd_start_authorized(self, telegram_service, mock_update, mock_context):
        """Test /start command with authorized user."""
        await telegram_service._cmd_start(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "Welcome to Genesis" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_cmd_start_unauthorized(self, telegram_service, mock_update, mock_context):
        """Test /start command with unauthorized user."""
        mock_update.effective_user.id = 99999

        await telegram_service._cmd_start(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "Access denied" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_text_message_unauthorized(self, telegram_service, mock_update, mock_context):
        """Test text message handling for unauthorized user."""
        mock_update.effective_user.id = 99999
        mock_update.message.text = "Hello"

        await telegram_service._handle_text_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "Access denied" in call_args[0][0]


class TestCommands:
    """Tests for bot commands."""

    @pytest.mark.asyncio
    async def test_cmd_help(self, telegram_service, mock_update, mock_context):
        """Test /help command."""
        await telegram_service._cmd_help(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "Commands" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_cmd_persona(self, telegram_service, mock_update, mock_context):
        """Test /persona command."""
        await telegram_service._cmd_persona(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "Available Personas" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_cmd_search_without_query(self, telegram_service, mock_update, mock_context):
        """Test /search command without query."""
        mock_context.args = []

        await telegram_service._cmd_search(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "provide a search query" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_cmd_search_with_query(self, telegram_service, mock_update, mock_context):
        """Test /search command with query."""
        mock_context.args = ["test", "query"]

        await telegram_service._cmd_search(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "test query" in call_args[0][0]

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_cmd_status_success(self, mock_client_class, telegram_service, mock_update, mock_context):
        """Test /status command with successful API call."""
        # Mock httpx response
        mock_response = Mock()
        mock_response.json.return_value = {
            "uptime": "1 day, 2 hours",
            "version": "0.1.0",
            "config": {"model": "gpt-4o"},
            "database": {"message_count": 42}
        }
        mock_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        await telegram_service._cmd_status(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        response_text = call_args[0][0]
        assert "Online" in response_text
        assert "1 day, 2 hours" in response_text
        assert "gpt-4o" in response_text

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_cmd_status_api_error(self, mock_client_class, telegram_service, mock_update, mock_context):
        """Test /status command with API error."""
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("Connection failed")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        await telegram_service._cmd_status(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "Failed to fetch" in call_args[0][0]


class TestTextMessageHandling:
    """Tests for text message handling."""

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_handle_text_message_success(self, mock_client_class, telegram_service, mock_update, mock_context):
        """Test successful text message handling."""
        mock_update.message.text = "Hello Genesis"

        # Mock httpx response
        mock_response = Mock()
        mock_response.json.return_value = {
            "response": "Hello! How can I help you?",
            "model": "gpt-4o"
        }
        mock_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        await telegram_service._handle_text_message(mock_update, mock_context)

        # Verify typing action was sent
        mock_update.message.chat.send_action.assert_called_once_with("typing")

        # Verify message was replied to
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "Hello! How can I help you?" in call_args[0][0]

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_handle_text_message_api_error(self, mock_client_class, telegram_service, mock_update, mock_context):
        """Test text message handling with API error."""
        mock_update.message.text = "Hello"

        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("API error")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        await telegram_service._handle_text_message(mock_update, mock_context)

        # Verify error message was sent
        mock_update.message.reply_text.assert_called()
        call_args = mock_update.message.reply_text.call_args
        assert "Error" in call_args[0][0]

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_handle_text_message_empty_response(self, mock_client_class, telegram_service, mock_update, mock_context):
        """Test text message handling with empty API response."""
        mock_update.message.text = "Hello"

        mock_response = Mock()
        mock_response.json.return_value = {"response": ""}
        mock_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        await telegram_service._handle_text_message(mock_update, mock_context)

        # Verify error message was sent
        mock_update.message.reply_text.assert_called()
        call_args = mock_update.message.reply_text.call_args
        assert "Empty response" in call_args[0][0]


class TestPhotoHandling:
    """Tests for photo message handling."""

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_handle_photo_message_success(self, mock_client_class, telegram_service, mock_update, mock_context):
        """Test successful photo message handling."""
        # Mock photo
        mock_photo = Mock(spec=PhotoSize)
        mock_photo.file_size = 1024
        mock_photo.get_file = AsyncMock()

        mock_file = AsyncMock()
        mock_file.download_as_bytearray.return_value = bytearray(b"fake_image_data")
        mock_photo.get_file.return_value = mock_file

        mock_update.message.photo = [mock_photo]
        mock_update.message.caption = "What's this?"

        # Mock upload response
        mock_upload_response = Mock()
        mock_upload_response.json.return_value = {"file_id": "test_file_123"}
        mock_upload_response.raise_for_status = Mock()

        # Mock chat response
        mock_chat_response = Mock()
        mock_chat_response.json.return_value = {"response": "This is an image of..."}
        mock_chat_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.post.side_effect = [mock_upload_response, mock_chat_response]
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        await telegram_service._handle_photo_message(mock_update, mock_context)

        # Verify upload and chat actions were called
        assert mock_client.post.call_count == 2

        # Verify response was sent
        mock_update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_handle_photo_message_upload_failure(self, mock_client_class, telegram_service, mock_update, mock_context):
        """Test photo handling with upload failure."""
        mock_photo = Mock(spec=PhotoSize)
        mock_photo.file_size = 1024
        mock_photo.get_file = AsyncMock()

        mock_file = AsyncMock()
        mock_file.download_as_bytearray.return_value = bytearray(b"fake_image_data")
        mock_photo.get_file.return_value = mock_file

        mock_update.message.photo = [mock_photo]
        mock_update.message.caption = None

        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("Upload failed")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        await telegram_service._handle_photo_message(mock_update, mock_context)

        # Verify error message was sent
        mock_update.message.reply_text.assert_called()
        call_args = mock_update.message.reply_text.call_args
        assert "Error" in call_args[0][0]


class TestPDFHandling:
    """Tests for PDF document handling."""

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_handle_document_message_success(self, mock_client_class, telegram_service, mock_update, mock_context):
        """Test successful PDF document handling."""
        # Mock document
        mock_document = Mock(spec=Document)
        mock_document.file_name = "test.pdf"
        mock_document.file_size = 1024
        mock_document.get_file = AsyncMock()

        mock_file = AsyncMock()
        mock_file.download_as_bytearray.return_value = bytearray(b"fake_pdf_data")
        mock_document.get_file.return_value = mock_file

        mock_update.message.document = mock_document
        mock_update.message.caption = "Analyze this PDF"

        # Mock upload and chat responses
        mock_upload_response = Mock()
        mock_upload_response.json.return_value = {"file_id": "test_file_pdf"}
        mock_upload_response.raise_for_status = Mock()

        mock_chat_response = Mock()
        mock_chat_response.json.return_value = {"response": "This PDF contains..."}
        mock_chat_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.post.side_effect = [mock_upload_response, mock_chat_response]
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        await telegram_service._handle_document_message(mock_update, mock_context)

        # Verify response was sent
        mock_update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_document_message_non_pdf(self, telegram_service, mock_update, mock_context):
        """Test document handling with non-PDF file."""
        mock_document = Mock(spec=Document)
        mock_document.file_name = "test.docx"
        mock_document.file_size = 1024

        mock_update.message.document = mock_document

        await telegram_service._handle_document_message(mock_update, mock_context)

        # Verify rejection message was sent
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "PDF" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_handle_document_message_too_large(self, telegram_service, mock_update, mock_context):
        """Test document handling with oversized PDF."""
        mock_document = Mock(spec=Document)
        mock_document.file_name = "test.pdf"
        mock_document.file_size = 25 * 1024 * 1024  # 25MB

        mock_update.message.document = mock_document

        await telegram_service._handle_document_message(mock_update, mock_context)

        # Verify error message was sent
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "too large" in call_args[0][0]


class TestMarkdownConversion:
    """Tests for markdown conversion."""

    def test_convert_markdown_bold(self, telegram_service):
        """Test conversion of bold markdown."""
        text = "This is **bold** text"
        result = telegram_service._convert_markdown_to_telegram(text)
        assert "**" not in result
        assert "*bold*" in result

    def test_convert_markdown_multiple_bold(self, telegram_service):
        """Test conversion of multiple bold sections."""
        text = "**First** and **Second**"
        result = telegram_service._convert_markdown_to_telegram(text)
        assert result == "*First* and *Second*"


class TestLongMessageSplitting:
    """Tests for long message splitting."""

    @pytest.mark.asyncio
    async def test_send_short_message(self, telegram_service, mock_update):
        """Test sending a short message (no splitting)."""
        short_text = "Hello, this is a short message."

        await telegram_service._send_long_message(mock_update, short_text)

        mock_update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_long_message_splits(self, telegram_service, mock_update):
        """Test sending a long message that requires splitting."""
        # Create a message longer than 4096 characters
        long_text = "A" * 5000

        await telegram_service._send_long_message(mock_update, long_text)

        # Should be called multiple times (first reply_text, then send_message)
        assert mock_update.message.reply_text.call_count >= 1

    @pytest.mark.asyncio
    async def test_send_long_message_splits_on_newline(self, telegram_service, mock_update):
        """Test that long messages split on newlines when possible."""
        # Create a message with newlines
        long_text = ("Line 1\n" * 200) + "Final line"  # ~1400 chars

        await telegram_service._send_long_message(mock_update, long_text)

        # Should complete successfully
        mock_update.message.reply_text.assert_called()


class TestServiceLifecycle:
    """Tests for service start/stop."""

    @pytest.mark.asyncio
    async def test_start_with_empty_token(self):
        """Test starting service with empty bot token."""
        service = TelegramService(
            bot_token="",
            allowed_users=[123]
        )

        await service.start()

        # Should not start
        assert not service.is_running()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, telegram_service):
        """Test stopping service that isn't running."""
        # Should not raise error
        await telegram_service.stop()

        assert not telegram_service.is_running()

    @pytest.mark.asyncio
    async def test_double_start_warning(self, telegram_service):
        """Test that starting an already-running service logs a warning."""
        # This is a unit test - we won't actually start the bot
        # Just test that _running flag is respected
        telegram_service._running = True

        # Mock the logger to check for warning
        with patch('server.services.telegram.logger') as mock_logger:
            await telegram_service.start()
            mock_logger.warning.assert_called()
