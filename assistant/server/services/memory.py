"""Memory service for conversation persistence using SQLite."""
import aiosqlite
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
import uuid

import config


# Single infinite conversation - all messages go to this conversation
DEFAULT_CONVERSATION_ID = "main"


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
        self._initialized = True

    async def _ensure_default_conversation(self):
        """Ensure the single default conversation exists."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM conversations WHERE id = ?",
                (DEFAULT_CONVERSATION_ID,)
            )
            row = await cursor.fetchone()
            if not row:
                now = datetime.now().isoformat()
                await db.execute(
                    "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (DEFAULT_CONVERSATION_ID, "Conversation", now, now)
                )
                await db.commit()

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
        """Add a message to a conversation.

        Note: For single conversation mode, use conversation_id=DEFAULT_CONVERSATION_ID
        or call the simplified add_to_conversation() method.
        """
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

    async def add_to_conversation(self, role: str, content: str) -> str:
        """Add a message to the single infinite conversation.

        This is the simplified API for the single-conversation model.
        Messages are added to the default conversation timeline.
        """
        await self._ensure_initialized()
        await self._ensure_default_conversation()
        return await self.add_message(DEFAULT_CONVERSATION_ID, role, content)

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

        async with aiosqlite.connect(self.db_path) as db:
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
        async with aiosqlite.connect(self.db_path) as db:
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
        async with aiosqlite.connect(self.db_path) as db:
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

                    # Store the summary
                    summary_id = f"sum_{uuid.uuid4().hex[:12]}"
                    async with aiosqlite.connect(self.db_path) as db:
                        await db.execute(
                            """INSERT INTO message_summaries
                               (id, conversation_id, start_message_id, end_message_id,
                                message_count, summary, created_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            (summary_id, DEFAULT_CONVERSATION_ID,
                             batch[0][0], batch[-1][0],
                             len(batch), summary, datetime.now().isoformat())
                        )
                        await db.commit()

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

    async def get_summaries(self) -> list[dict]:
        """Get all stored summaries for the conversation.

        Returns:
            List of summary records with metadata
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
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

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM message_summaries WHERE conversation_id = ?",
                (DEFAULT_CONVERSATION_ID,)
            )
            await db.commit()

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
