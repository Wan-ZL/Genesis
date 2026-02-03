"""Memory service for conversation persistence using SQLite."""
import aiosqlite
from datetime import datetime
from pathlib import Path
from typing import Optional
import uuid


class MemoryService:
    """Service for managing conversation memory in SQLite."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._initialized = False

    async def _ensure_initialized(self):
        """Ensure database tables exist."""
        if self._initialized:
            return

        async with aiosqlite.connect(self.db_path) as db:
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
            await db.commit()
        self._initialized = True

    async def create_conversation(self, title: Optional[str] = None) -> str:
        """Create a new conversation and return its ID."""
        await self._ensure_initialized()

        conversation_id = f"conv_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (conversation_id, title or "New conversation", now, now)
            )
            await db.commit()

        return conversation_id

    async def conversation_exists(self, conversation_id: str) -> bool:
        """Check if a conversation exists."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM conversations WHERE id = ?",
                (conversation_id,)
            )
            row = await cursor.fetchone()
            return row is not None

    async def add_message(self, conversation_id: str, role: str, content: str) -> str:
        """Add a message to a conversation."""
        await self._ensure_initialized()

        message_id = f"msg_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        async with aiosqlite.connect(self.db_path) as db:
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

    async def remove_last_message(self, conversation_id: str):
        """Remove the last message from a conversation (for error recovery)."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
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

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at",
                (conversation_id,)
            )
            rows = await cursor.fetchall()
            for role, content in rows:
                messages.append({"role": role, "content": content})

        return messages

    async def list_conversations(self) -> list[dict]:
        """List all conversations with metadata."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT c.id, c.title, c.created_at, c.updated_at, COUNT(m.id) as message_count "
                "FROM conversations c LEFT JOIN messages m ON c.id = m.conversation_id "
                "GROUP BY c.id ORDER BY c.updated_at DESC"
            )
            rows = await cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "title": row[1],
                    "created_at": row[2],
                    "updated_at": row[3],
                    "message_count": row[4]
                }
                for row in rows
            ]

    async def get_conversation(self, conversation_id: str) -> Optional[dict]:
        """Get a conversation with all its messages."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
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

    async def save_file_metadata(self, metadata: dict):
        """Save file metadata to database."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
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

        async with aiosqlite.connect(self.db_path) as db:
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

        async with aiosqlite.connect(self.db_path) as db:
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

        async with aiosqlite.connect(self.db_path) as db:
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

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM messages")
            row = await cursor.fetchone()
            return row[0] if row else 0


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
