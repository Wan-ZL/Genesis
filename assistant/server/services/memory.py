"""Memory service for conversation persistence using SQLite.

Uses a connection pool with WAL mode for concurrency safety.
"""
import aiosqlite
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Callable, TypeVar, Any
import uuid
import threading
import random
import logging
import functools

import config

logger = logging.getLogger(__name__)

T = TypeVar('T')


# Single infinite conversation - all messages go to this conversation
DEFAULT_CONVERSATION_ID = "main"

# Connection pool settings
_DB_BUSY_TIMEOUT_MS = 5000  # 5 seconds - shorter timeout, rely on retries
_DB_POOL_SIZE = 10  # Number of connections in pool (increased for concurrent writes)
_DB_MAX_RETRIES = 5  # Number of retries for database operations
_DB_RETRY_BASE_DELAY = 0.05  # Base delay for exponential backoff (50ms)


def with_db_retry(max_retries: int = _DB_MAX_RETRIES, base_delay: float = _DB_RETRY_BASE_DELAY):
    """Decorator to retry database operations on lock errors.

    Uses exponential backoff with jitter to avoid thundering herd.
    Retries only on OperationalError (database locked).
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_error = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except aiosqlite.OperationalError as e:
                    last_error = e
                    error_msg = str(e).lower()

                    # Only retry on lock-related errors
                    if "locked" not in error_msg and "busy" not in error_msg:
                        raise

                    # Don't retry on last attempt
                    if attempt == max_retries - 1:
                        logger.error(
                            f"Database operation failed after {max_retries} retries: {func.__name__}"
                        )
                        raise

                    # Exponential backoff with jitter
                    delay = base_delay * (2 ** attempt)
                    jitter = random.uniform(0, delay * 0.3)
                    wait_time = delay + jitter

                    logger.warning(
                        f"Database locked in {func.__name__}, "
                        f"retry {attempt + 1}/{max_retries} after {wait_time:.3f}s"
                    )
                    await asyncio.sleep(wait_time)

            # Should not reach here, but just in case
            raise last_error or RuntimeError(f"Retry logic failed for {func.__name__}")

        return wrapper
    return decorator


class ConnectionPool:
    """Simple async connection pool for aiosqlite with WAL mode."""

    def __init__(self, db_path: Path, pool_size: int = _DB_POOL_SIZE):
        self.db_path = db_path
        self.pool_size = pool_size
        self._pool: Optional[asyncio.Queue] = None
        self._initialized = False
        self._lock: Optional[asyncio.Lock] = None
        self._init_lock = threading.Lock()  # Thread-safe lock for initialization
        self._loop = None  # Track which event loop we're bound to

    async def initialize(self):
        """Initialize the connection pool."""
        # Check if we're on a different event loop than we were initialized with
        current_loop = asyncio.get_running_loop()
        if self._loop is not None and self._loop != current_loop:
            # We've switched event loops, need to reinitialize
            await self.close()

        if self._initialized:
            return

        # Create asyncio primitives lazily to avoid event loop attachment issues
        # Use thread lock to prevent race condition in creating async lock
        with self._init_lock:
            if self._lock is None:
                self._loop = current_loop
                self._lock = asyncio.Lock()

        async with self._lock:
            if self._initialized:
                return

            # Create pool queue lazily
            if self._pool is None:
                self._pool = asyncio.Queue(maxsize=self.pool_size)

            # Create pool of connections
            for _ in range(self.pool_size):
                conn = await aiosqlite.connect(
                    self.db_path,
                    timeout=_DB_BUSY_TIMEOUT_MS / 1000  # Convert to seconds
                )
                # Enable WAL mode for better concurrency
                await conn.execute("PRAGMA journal_mode=WAL")
                # Set busy timeout
                await conn.execute(f"PRAGMA busy_timeout={_DB_BUSY_TIMEOUT_MS}")
                # Optimize synchronous mode for WAL
                await conn.execute("PRAGMA synchronous=NORMAL")
                await self._pool.put(conn)

            self._initialized = True

    async def acquire(self) -> aiosqlite.Connection:
        """Get a connection from the pool."""
        await self.initialize()
        if self._pool is None:
            raise RuntimeError("Connection pool not initialized")
        return await self._pool.get()

    async def release(self, conn: aiosqlite.Connection):
        """Return a connection to the pool."""
        if self._pool is None:
            raise RuntimeError("Connection pool not initialized")
        await self._pool.put(conn)

    async def close(self):
        """Close all connections in the pool."""
        if self._pool is not None:
            while not self._pool.empty():
                try:
                    conn = self._pool.get_nowait()
                    await conn.close()
                except asyncio.QueueEmpty:
                    break
        self._initialized = False
        self._pool = None
        self._lock = None


class PooledConnection:
    """Context manager for pooled database connections."""

    def __init__(self, pool: ConnectionPool):
        self.pool = pool
        self.conn: Optional[aiosqlite.Connection] = None

    async def __aenter__(self) -> aiosqlite.Connection:
        self.conn = await self.pool.acquire()
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            await self.pool.release(self.conn)
            self.conn = None


class MemoryService:
    """Service for managing conversation memory in SQLite.

    Uses a connection pool with WAL mode for safe concurrent access.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._pool = ConnectionPool(db_path)
        self._tables_created = False
        self._tables_lock: Optional[asyncio.Lock] = None
        self._tables_init_lock = threading.Lock()

    def _get_connection(self) -> PooledConnection:
        """Get a pooled connection context manager."""
        return PooledConnection(self._pool)

    async def _ensure_initialized(self):
        """Ensure database tables exist."""
        if self._tables_created:
            return

        # Create lock lazily to avoid event loop attachment issues
        with self._tables_init_lock:
            if self._tables_lock is None:
                self._tables_lock = asyncio.Lock()

        async with self._tables_lock:
            if self._tables_created:
                return

            async with self._get_connection() as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS conversations (
                        id TEXT PRIMARY KEY,
                        title TEXT,
                        created_at TIMESTAMP,
                        updated_at TIMESTAMP
                    )
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id TEXT PRIMARY KEY,
                        conversation_id TEXT,
                        role TEXT,
                        content TEXT,
                        created_at TIMESTAMP,
                        FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                    )
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS files (
                        id TEXT PRIMARY KEY,
                        original_filename TEXT,
                        stored_filename TEXT,
                        content_type TEXT,
                        size INTEGER,
                        conversation_id TEXT,
                        uploaded_at TIMESTAMP,
                        FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                    )
                """)
                # Table for storing summaries of old message batches
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS message_summaries (
                        id TEXT PRIMARY KEY,
                        conversation_id TEXT,
                        start_message_id TEXT,
                        end_message_id TEXT,
                        message_count INTEGER,
                        summary TEXT,
                        created_at TIMESTAMP,
                        FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                    )
                """)
                await db.commit()
            self._tables_created = True

    @with_db_retry()
    async def _ensure_default_conversation(self):
        """Ensure the single default conversation exists.

        Uses INSERT OR IGNORE to safely handle concurrent initialization.
        """
        now = datetime.now().isoformat()
        async with self._get_connection() as db:
            # Use INSERT OR IGNORE to avoid race condition
            # If conversation already exists, this is a no-op
            await db.execute(
                "INSERT OR IGNORE INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (DEFAULT_CONVERSATION_ID, "Conversation", now, now)
            )
            await db.commit()

    async def create_conversation(self, title: Optional[str] = None) -> str:
        """Create a new conversation and return its ID."""
        await self._ensure_initialized()

        conversation_id = f"conv_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        async with self._get_connection() as db:
            await db.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (conversation_id, title or "New conversation", now, now)
            )
            await db.commit()

        return conversation_id

    async def conversation_exists(self, conversation_id: str) -> bool:
        """Check if a conversation exists."""
        await self._ensure_initialized()

        async with self._get_connection() as db:
            cursor = await db.execute(
                "SELECT 1 FROM conversations WHERE id = ?",
                (conversation_id,)
            )
            row = await cursor.fetchone()
            return row is not None

    @with_db_retry()
    async def add_message(self, conversation_id: str, role: str, content: str) -> str:
        """Add a message to a conversation.

        Note: For single conversation mode, use conversation_id=DEFAULT_CONVERSATION_ID
        or call the simplified add_to_conversation() method.
        """
        await self._ensure_initialized()

        message_id = f"msg_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        async with self._get_connection() as db:
            await db.execute(
                "INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (message_id, conversation_id, role, content, now)
            )
            await db.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id)
            )
            await db.commit()

        return message_id

    async def add_to_conversation(self, role: str, content: str) -> str:
        """Add a message to the single infinite conversation.

        This is the simplified API for the single-conversation model.
        Messages are added to the default conversation timeline.
        """
        await self._ensure_initialized()
        await self._ensure_default_conversation()
        return await self.add_message(DEFAULT_CONVERSATION_ID, role, content)

    @with_db_retry()
    async def remove_last_message(self, conversation_id: str):
        """Remove the last message from a conversation (for error recovery)."""
        await self._ensure_initialized()

        async with self._get_connection() as db:
            cursor = await db.execute(
                "SELECT id FROM messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT 1",
                (conversation_id,)
            )
            row = await cursor.fetchone()
            if row:
                await db.execute("DELETE FROM messages WHERE id = ?", (row[0],))
                await db.commit()

    async def get_conversation_messages(self, conversation_id: str) -> list[dict]:
        """Get all messages for a conversation in OpenAI format."""
        await self._ensure_initialized()

        messages = [
            {"role": "system", "content": "You are a helpful AI assistant. Be concise and helpful."}
        ]

        async with self._get_connection() as db:
            cursor = await db.execute(
                "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at",
                (conversation_id,)
            )
            rows = await cursor.fetchall()
            for role, content in rows:
                messages.append({"role": role, "content": content})

        return messages

    async def get_messages(self, limit: Optional[int] = None) -> list[dict]:
        """Get messages from the single infinite conversation in OpenAI format.

        This is the simplified API for the single-conversation model.

        Args:
            limit: Optional limit on number of recent messages to return.
                   If None, returns all messages.

        Returns:
            Messages in OpenAI format with system prompt prepended.
        """
        await self._ensure_initialized()
        await self._ensure_default_conversation()

        messages = [
            {"role": "system", "content": "You are a helpful AI assistant. Be concise and helpful."}
        ]

        async with self._get_connection() as db:
            if limit:
                cursor = await db.execute(
                    """SELECT role, content FROM messages
                       WHERE conversation_id = ?
                       ORDER BY created_at DESC LIMIT ?""",
                    (DEFAULT_CONVERSATION_ID, limit)
                )
                rows = await cursor.fetchall()
                # Reverse to get chronological order
                for role, content in reversed(rows):
                    messages.append({"role": role, "content": content})
            else:
                cursor = await db.execute(
                    "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at",
                    (DEFAULT_CONVERSATION_ID,)
                )
                rows = await cursor.fetchall()
                for role, content in rows:
                    messages.append({"role": role, "content": content})

        return messages

    async def remove_last_message_from_conversation(self):
        """Remove the last message from the single conversation (for error recovery)."""
        await self._ensure_initialized()
        await self._ensure_default_conversation()
        await self.remove_last_message(DEFAULT_CONVERSATION_ID)

    async def get_context_for_api(self) -> Tuple[list[dict], dict]:
        """Get messages optimized for LLM context window.

        For long conversations, this method:
        1. Keeps recent messages verbatim
        2. Summarizes older messages to save context space
        3. Original messages are always preserved in DB

        Returns:
            Tuple of (messages_list, metadata) where:
            - messages_list: Messages in OpenAI format with system prompt
            - metadata: Dict with summarization info (total_messages, summarized_count, etc.)
        """
        await self._ensure_initialized()
        await self._ensure_default_conversation()

        # Get total message count
        async with self._get_connection() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                (DEFAULT_CONVERSATION_ID,)
            )
            row = await cursor.fetchone()
            total_messages = row[0] if row else 0

        # If few messages, return all verbatim
        if total_messages <= config.RECENT_MESSAGES_VERBATIM:
            messages = await self.get_messages()
            return messages, {
                "total_messages": total_messages,
                "summarized_count": 0,
                "verbatim_count": total_messages,
                "summaries_used": 0
            }

        # Need to summarize older messages
        verbatim_count = config.RECENT_MESSAGES_VERBATIM
        messages_to_summarize = total_messages - verbatim_count

        # Start with system prompt
        messages = [
            {"role": "system", "content": "You are a helpful AI assistant. Be concise and helpful."}
        ]

        # Get or create summaries for older messages
        async with self._get_connection() as db:
            # Get all messages ordered by time
            cursor = await db.execute(
                """SELECT id, role, content, created_at FROM messages
                   WHERE conversation_id = ?
                   ORDER BY created_at""",
                (DEFAULT_CONVERSATION_ID,)
            )
            all_messages = await cursor.fetchall()

            # Split into old (to summarize) and recent (verbatim)
            old_messages = all_messages[:messages_to_summarize]
            recent_messages = all_messages[messages_to_summarize:]

            # Check for existing summaries
            cursor = await db.execute(
                """SELECT start_message_id, end_message_id, summary
                   FROM message_summaries
                   WHERE conversation_id = ?
                   ORDER BY created_at""",
                (DEFAULT_CONVERSATION_ID,)
            )
            existing_summaries = await cursor.fetchall()

        # Determine which messages need new summaries
        summarized_message_ids = set()
        summaries_to_add = []

        for start_id, end_id, summary in existing_summaries:
            # Find range of summarized messages
            in_range = False
            for msg_id, _, _, _ in old_messages:
                if msg_id == start_id:
                    in_range = True
                if in_range:
                    summarized_message_ids.add(msg_id)
                if msg_id == end_id:
                    break
            summaries_to_add.append(summary)

        # Create summaries for unsummarized old messages
        unsummarized = [(m[0], m[1], m[2], m[3]) for m in old_messages if m[0] not in summarized_message_ids]

        if unsummarized:
            # Group into batches and create summaries
            batch_size = config.MESSAGES_PER_SUMMARY_BATCH
            for i in range(0, len(unsummarized), batch_size):
                batch = unsummarized[i:i + batch_size]
                if batch:
                    summary = _create_text_summary(batch, config.MAX_SUMMARY_LENGTH)
                    summaries_to_add.append(summary)

                    # Store the summary with retry logic
                    await self._store_summary(
                        batch[0][0], batch[-1][0], len(batch), summary
                    )

        # Add summaries as context
        if summaries_to_add:
            combined_summary = "\n---\n".join(summaries_to_add)
            messages.append({
                "role": "system",
                "content": f"[Previous conversation summary ({messages_to_summarize} messages):\n{combined_summary}]"
            })

        # Add recent messages verbatim
        for _, role, content, _ in recent_messages:
            messages.append({"role": role, "content": content})

        return messages, {
            "total_messages": total_messages,
            "summarized_count": messages_to_summarize,
            "verbatim_count": verbatim_count,
            "summaries_used": len(summaries_to_add)
        }

    @with_db_retry()
    async def _store_summary(
        self, start_msg_id: str, end_msg_id: str, msg_count: int, summary: str
    ):
        """Store a message summary with retry logic.

        Helper method for get_context_for_api() to handle database writes
        with automatic retries on lock errors.
        """
        summary_id = f"sum_{uuid.uuid4().hex[:12]}"
        async with self._get_connection() as db:
            await db.execute(
                """INSERT INTO message_summaries
                   (id, conversation_id, start_message_id, end_message_id,
                    message_count, summary, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (summary_id, DEFAULT_CONVERSATION_ID,
                 start_msg_id, end_msg_id,
                 msg_count, summary, datetime.now().isoformat())
            )
            await db.commit()

    async def get_summaries(self) -> list[dict]:
        """Get all stored summaries for the conversation.

        Returns:
            List of summary records with metadata
        """
        await self._ensure_initialized()

        async with self._get_connection() as db:
            cursor = await db.execute(
                """SELECT id, start_message_id, end_message_id, message_count, summary, created_at
                   FROM message_summaries
                   WHERE conversation_id = ?
                   ORDER BY created_at""",
                (DEFAULT_CONVERSATION_ID,)
            )
            rows = await cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "start_message_id": row[1],
                    "end_message_id": row[2],
                    "message_count": row[3],
                    "summary": row[4],
                    "created_at": row[5]
                }
                for row in rows
            ]

    async def clear_summaries(self):
        """Clear all stored summaries (useful for testing or reset)."""
        await self._ensure_initialized()

        async with self._get_connection() as db:
            await db.execute(
                "DELETE FROM message_summaries WHERE conversation_id = ?",
                (DEFAULT_CONVERSATION_ID,)
            )
            await db.commit()

    async def list_conversations(self) -> list[dict]:
        """List all conversations with metadata, sorted by most recently active.

        Includes the last user message as a preview snippet.
        """
        await self._ensure_initialized()

        async with self._get_connection() as db:
            cursor = await db.execute(
                """SELECT c.id, c.title, c.created_at, c.updated_at,
                          COUNT(m.id) as message_count,
                          (SELECT content FROM messages
                           WHERE conversation_id = c.id AND role = 'user'
                           ORDER BY created_at DESC LIMIT 1) as last_preview
                   FROM conversations c LEFT JOIN messages m ON c.id = m.conversation_id
                   GROUP BY c.id ORDER BY c.updated_at DESC"""
            )
            rows = await cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "title": row[1],
                    "created_at": row[2],
                    "updated_at": row[3],
                    "message_count": row[4],
                    "preview": (row[5][:80] + "...") if row[5] and len(row[5]) > 80 else (row[5] or "")
                }
                for row in rows
            ]

    async def get_conversation(self, conversation_id: str) -> Optional[dict]:
        """Get a conversation with all its messages."""
        await self._ensure_initialized()

        async with self._get_connection() as db:
            cursor = await db.execute(
                "SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?",
                (conversation_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None

            conversation = {
                "id": row[0],
                "title": row[1],
                "created_at": row[2],
                "updated_at": row[3],
                "messages": []
            }

            cursor = await db.execute(
                "SELECT id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at",
                (conversation_id,)
            )
            messages = await cursor.fetchall()
            conversation["messages"] = [
                {"id": m[0], "role": m[1], "content": m[2], "created_at": m[3]}
                for m in messages
            ]

            return conversation

    async def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation and all its messages.

        Args:
            conversation_id: The conversation to delete

        Returns:
            True if the conversation was deleted, False if it didn't exist
        """
        await self._ensure_initialized()

        async with self._get_connection() as db:
            # Check if conversation exists
            cursor = await db.execute(
                "SELECT 1 FROM conversations WHERE id = ?",
                (conversation_id,)
            )
            if not await cursor.fetchone():
                return False

            # Delete messages first (foreign key)
            await db.execute(
                "DELETE FROM messages WHERE conversation_id = ?",
                (conversation_id,)
            )
            # Delete summaries
            await db.execute(
                "DELETE FROM message_summaries WHERE conversation_id = ?",
                (conversation_id,)
            )
            # Delete conversation
            await db.execute(
                "DELETE FROM conversations WHERE id = ?",
                (conversation_id,)
            )
            await db.commit()
            return True

    async def rename_conversation(self, conversation_id: str, title: str) -> bool:
        """Rename a conversation.

        Args:
            conversation_id: The conversation to rename
            title: The new title

        Returns:
            True if the conversation was renamed, False if it didn't exist
        """
        await self._ensure_initialized()

        async with self._get_connection() as db:
            cursor = await db.execute(
                "SELECT 1 FROM conversations WHERE id = ?",
                (conversation_id,)
            )
            if not await cursor.fetchone():
                return False

            await db.execute(
                "UPDATE conversations SET title = ? WHERE id = ?",
                (title, conversation_id)
            )
            await db.commit()
            return True

    async def auto_title_conversation(self, conversation_id: str, first_message: str):
        """Auto-generate a conversation title from the first user message.

        Takes the first ~50 characters of the first user message.

        Args:
            conversation_id: The conversation to title
            first_message: The first user message content
        """
        if not first_message:
            return

        # Take first 50 chars, trim to last word boundary if possible
        title = first_message[:50].strip()
        if len(first_message) > 50:
            # Try to trim to last word boundary
            last_space = title.rfind(' ')
            if last_space > 20:
                title = title[:last_space]
            title += "..."

        await self.rename_conversation(conversation_id, title)

    async def save_file_metadata(self, metadata: dict):
        """Save file metadata to database."""
        await self._ensure_initialized()

        async with self._get_connection() as db:
            await db.execute(
                """INSERT INTO files
                   (id, original_filename, stored_filename, content_type, size, conversation_id, uploaded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    metadata["id"],
                    metadata["original_filename"],
                    metadata["stored_filename"],
                    metadata["content_type"],
                    metadata["size"],
                    metadata.get("conversation_id"),
                    metadata["uploaded_at"]
                )
            )
            await db.commit()

    async def list_files(self, conversation_id: Optional[str] = None) -> list:
        """List files, optionally filtered by conversation."""
        await self._ensure_initialized()

        async with self._get_connection() as db:
            if conversation_id:
                cursor = await db.execute(
                    "SELECT id, original_filename, content_type, size, conversation_id, uploaded_at "
                    "FROM files WHERE conversation_id = ? ORDER BY uploaded_at DESC",
                    (conversation_id,)
                )
            else:
                cursor = await db.execute(
                    "SELECT id, original_filename, content_type, size, conversation_id, uploaded_at "
                    "FROM files ORDER BY uploaded_at DESC"
                )
            rows = await cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "filename": row[1],
                    "content_type": row[2],
                    "size": row[3],
                    "conversation_id": row[4],
                    "uploaded_at": row[5]
                }
                for row in rows
            ]

    async def get_file_metadata(self, file_id: str) -> Optional[dict]:
        """Get file metadata by ID."""
        await self._ensure_initialized()

        async with self._get_connection() as db:
            cursor = await db.execute(
                "SELECT id, original_filename, stored_filename, content_type, size, conversation_id, uploaded_at "
                "FROM files WHERE id = ?",
                (file_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "filename": row[1],
                "stored_filename": row[2],
                "content_type": row[3],
                "size": row[4],
                "conversation_id": row[5],
                "uploaded_at": row[6]
            }

    async def search_messages(
        self,
        query: str,
        conversation_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> list[dict]:
        """Search messages by keyword across all conversations or a specific one.

        Args:
            query: Search keyword (case-insensitive)
            conversation_id: Optional filter to search within a specific conversation
            limit: Maximum results to return (default 50)
            offset: Pagination offset (default 0)

        Returns:
            List of matching messages with conversation context
        """
        await self._ensure_initialized()

        async with self._get_connection() as db:
            # Use LIKE for simple keyword search (case-insensitive in SQLite by default for ASCII)
            search_pattern = f"%{query}%"

            if conversation_id:
                cursor = await db.execute(
                    """SELECT m.id, m.conversation_id, m.role, m.content, m.created_at,
                              c.title as conversation_title
                       FROM messages m
                       JOIN conversations c ON m.conversation_id = c.id
                       WHERE m.conversation_id = ? AND m.content LIKE ?
                       ORDER BY m.created_at DESC
                       LIMIT ? OFFSET ?""",
                    (conversation_id, search_pattern, limit, offset)
                )
            else:
                cursor = await db.execute(
                    """SELECT m.id, m.conversation_id, m.role, m.content, m.created_at,
                              c.title as conversation_title
                       FROM messages m
                       JOIN conversations c ON m.conversation_id = c.id
                       WHERE m.content LIKE ?
                       ORDER BY m.created_at DESC
                       LIMIT ? OFFSET ?""",
                    (search_pattern, limit, offset)
                )

            rows = await cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "conversation_id": row[1],
                    "role": row[2],
                    "content": row[3],
                    "created_at": row[4],
                    "conversation_title": row[5],
                    # Include a snippet with context around the match
                    "snippet": _extract_snippet(row[3], query)
                }
                for row in rows
            ]

    async def get_message_count(self) -> int:
        """Get total message count across all conversations."""
        await self._ensure_initialized()

        async with self._get_connection() as db:
            cursor = await db.execute("SELECT COUNT(*) FROM messages")
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def export_conversation(self) -> dict:
        """Export the single conversation in a portable format.

        Returns:
            Dict with version, metadata, and messages array
        """
        await self._ensure_initialized()
        await self._ensure_default_conversation()

        async with self._get_connection() as db:
            # Get all messages with their timestamps
            cursor = await db.execute(
                """SELECT id, role, content, created_at
                   FROM messages WHERE conversation_id = ?
                   ORDER BY created_at""",
                (DEFAULT_CONVERSATION_ID,)
            )
            messages_rows = await cursor.fetchall()

            # Get file references for messages (if any)
            cursor = await db.execute(
                """SELECT id, original_filename, content_type, size, uploaded_at
                   FROM files WHERE conversation_id = ?""",
                (DEFAULT_CONVERSATION_ID,)
            )
            files_rows = await cursor.fetchall()

        # Build messages list
        messages = []
        for msg_id, role, content, created_at in messages_rows:
            messages.append({
                "id": msg_id,
                "role": role,
                "content": content,
                "timestamp": created_at,
                "file_ids": []  # File association tracking not implemented yet
            })

        # Build files list (references only, not content)
        files = []
        for file_id, filename, content_type, size, uploaded_at in files_rows:
            files.append({
                "id": file_id,
                "filename": filename,
                "content_type": content_type,
                "size": size,
                "uploaded_at": uploaded_at
            })

        return {
            "version": "1.0",
            "exported_at": datetime.now().isoformat() + "Z",
            "message_count": len(messages),
            "messages": messages,
            "files": files
        }

    async def import_conversation(
        self,
        data: dict,
        mode: str = "merge"
    ) -> dict:
        """Import conversation from exported format.

        Args:
            data: Exported conversation data dict
            mode: "merge" (skip duplicates) or "replace" (clear existing first)

        Returns:
            Dict with import statistics
        """
        await self._ensure_initialized()
        await self._ensure_default_conversation()

        # Validate format
        if "version" not in data:
            raise ValueError("Invalid export format: missing version")
        if "messages" not in data:
            raise ValueError("Invalid export format: missing messages")

        version = data.get("version", "1.0")
        if version not in ["1.0"]:
            raise ValueError(f"Unsupported export version: {version}")

        messages = data.get("messages", [])

        # Get existing message timestamps for deduplication
        existing_timestamps = set()
        if mode == "merge":
            async with self._get_connection() as db:
                cursor = await db.execute(
                    "SELECT created_at FROM messages WHERE conversation_id = ?",
                    (DEFAULT_CONVERSATION_ID,)
                )
                rows = await cursor.fetchall()
                existing_timestamps = {row[0] for row in rows}
        elif mode == "replace":
            # Clear existing messages and summaries
            async with self._get_connection() as db:
                await db.execute(
                    "DELETE FROM messages WHERE conversation_id = ?",
                    (DEFAULT_CONVERSATION_ID,)
                )
                await db.execute(
                    "DELETE FROM message_summaries WHERE conversation_id = ?",
                    (DEFAULT_CONVERSATION_ID,)
                )
                await db.commit()

        # Import messages
        imported_count = 0
        skipped_count = 0

        async with self._get_connection() as db:
            for msg in messages:
                # Validate required fields
                if "role" not in msg or "content" not in msg:
                    skipped_count += 1
                    continue

                timestamp = msg.get("timestamp")
                if not timestamp:
                    # Generate timestamp if missing
                    timestamp = datetime.now().isoformat()

                # Skip duplicates in merge mode
                if mode == "merge" and timestamp in existing_timestamps:
                    skipped_count += 1
                    continue

                # Use existing ID or generate new one
                msg_id = msg.get("id") or f"msg_{uuid.uuid4().hex[:12]}"

                await db.execute(
                    """INSERT INTO messages (id, conversation_id, role, content, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (msg_id, DEFAULT_CONVERSATION_ID, msg["role"], msg["content"], timestamp)
                )
                imported_count += 1

            await db.commit()

        return {
            "imported_count": imported_count,
            "skipped_count": skipped_count,
            "total_in_file": len(messages),
            "mode": mode
        }

    @with_db_retry()
    async def delete_message(self, conversation_id: str, message_id: str) -> bool:
        """Delete a single message from a conversation.

        Args:
            conversation_id: The conversation containing the message
            message_id: The message to delete

        Returns:
            True if the message was deleted, False if it didn't exist
        """
        await self._ensure_initialized()

        async with self._get_connection() as db:
            # Check if message exists
            cursor = await db.execute(
                "SELECT 1 FROM messages WHERE id = ? AND conversation_id = ?",
                (message_id, conversation_id)
            )
            if not await cursor.fetchone():
                return False

            # Delete the message
            await db.execute(
                "DELETE FROM messages WHERE id = ? AND conversation_id = ?",
                (message_id, conversation_id)
            )
            await db.commit()
            return True


def _create_text_summary(messages: list, max_length: int = 500) -> str:
    """Create a text-based summary of a batch of messages.

    This is a simple text summarization that truncates long messages
    and combines them. For better quality, this could be replaced
    with LLM-based summarization in the future.

    Args:
        messages: List of (id, role, content, created_at) tuples
        max_length: Maximum characters for the summary

    Returns:
        A condensed summary of the messages
    """
    if not messages:
        return ""

    # Build summary by extracting key parts from each message
    summary_parts = []
    chars_per_msg = max_length // max(len(messages), 1)

    for _, role, content, _ in messages:
        # Truncate long messages
        if len(content) > chars_per_msg:
            truncated = content[:chars_per_msg - 3] + "..."
        else:
            truncated = content

        # Use shorter role labels
        role_label = "U" if role == "user" else "A"
        summary_parts.append(f"{role_label}: {truncated}")

    # Combine and final truncation if needed
    summary = " | ".join(summary_parts)
    if len(summary) > max_length:
        summary = summary[:max_length - 3] + "..."

    return summary


def _extract_snippet(content: str, query: str, context_chars: int = 50) -> str:
    """Extract a snippet from content with context around the first match.

    Args:
        content: Full message content
        query: Search query
        context_chars: Characters of context on each side

    Returns:
        Snippet with "..." for truncation
    """
    content_lower = content.lower()
    query_lower = query.lower()
    pos = content_lower.find(query_lower)

    if pos == -1:
        # No match found, return beginning of content
        if len(content) <= context_chars * 2:
            return content
        return content[:context_chars * 2] + "..."

    # Calculate start and end positions with context
    start = max(0, pos - context_chars)
    end = min(len(content), pos + len(query) + context_chars)

    snippet = content[start:end]

    # Add ellipsis if truncated
    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."

    return snippet
