"""Long-term memory extraction and recall service.

This service analyzes conversations to extract structured facts about the user
(preferences, personal info, work context, etc.) and stores them for future recall.

Architecture:
- Extraction: Runs async after each assistant response
- Storage: SQLite with FTS5 for keyword search
- Recall: Retrieves relevant facts before each response
- Deduplication: Updates existing facts rather than duplicating

Fact types:
- preference: User preferences (response style, tools, behavior)
- personal_info: Personal details (name, location, background)
- work_context: Work-related info (company, projects, role)
- behavioral_pattern: Communication patterns and habits
- temporal: Schedule-related facts (timezone, working hours, routines)
"""
import aiosqlite
import asyncio
import json
import logging
import re
import uuid
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

import config

logger = logging.getLogger(__name__)

# Connection pool settings (similar to memory.py)
_DB_BUSY_TIMEOUT_MS = 5000
_DB_POOL_SIZE = 5


class Fact(BaseModel):
    """Structured fact extracted from conversation."""
    id: str
    fact_type: str  # preference, personal_info, work_context, behavioral_pattern, temporal
    key: str  # Short identifier (e.g., "response_style", "company")
    value: str  # The actual fact value
    source_conversation_id: str
    source_message_id: str
    confidence: float  # 0.0 to 1.0
    created_at: str
    updated_at: str


class ConnectionPool:
    """Simple async connection pool for aiosqlite with WAL mode."""

    def __init__(self, db_path: Path, pool_size: int = _DB_POOL_SIZE):
        self.db_path = db_path
        self.pool_size = pool_size
        self._pool: Optional[asyncio.Queue] = None
        self._initialized = False
        self._lock: Optional[asyncio.Lock] = None
        self._init_lock = threading.Lock()
        self._loop = None

    async def initialize(self):
        """Initialize the connection pool."""
        current_loop = asyncio.get_running_loop()
        if self._loop is not None and self._loop != current_loop:
            await self.close()

        if self._initialized:
            return

        with self._init_lock:
            if self._lock is None:
                self._loop = current_loop
                self._lock = asyncio.Lock()

        async with self._lock:
            if self._initialized:
                return

            if self._pool is None:
                self._pool = asyncio.Queue(maxsize=self.pool_size)

            for _ in range(self.pool_size):
                conn = await aiosqlite.connect(
                    self.db_path,
                    timeout=_DB_BUSY_TIMEOUT_MS / 1000
                )
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute(f"PRAGMA busy_timeout={_DB_BUSY_TIMEOUT_MS}")
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


class MemoryExtractorService:
    """Service for extracting and managing long-term memory facts."""

    # Extraction prompt for LLM
    EXTRACTION_PROMPT = """Analyze the following conversation turn and extract any facts about the user.

Extract facts in these categories:
- preference: User preferences (response style, tool preferences, behavior preferences)
- personal_info: Personal details (name, location, background, interests)
- work_context: Work-related info (company, projects, role, industry)
- behavioral_pattern: Communication patterns (prefers examples, asks follow-ups, etc.)
- temporal: Schedule-related facts (timezone, working hours, routines)

Conversation turn:
User: {user_message}
Assistant: {assistant_message}

Extract 0-5 facts. For each fact, provide:
1. fact_type (one of the above categories)
2. key (short identifier like "response_style", "company", "name")
3. value (the actual fact, keep it concise but complete)
4. confidence (0.0 to 1.0, how confident are you this is a real fact?)

Return ONLY valid JSON with this structure:
{{"facts": [{{"fact_type": "preference", "key": "response_style", "value": "concise answers", "confidence": 0.95}}]}}

If no facts can be extracted, return: {{"facts": []}}"""

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

        with self._tables_init_lock:
            if self._tables_lock is None:
                self._tables_lock = asyncio.Lock()

        async with self._tables_lock:
            if self._tables_created:
                return

            async with self._get_connection() as db:
                # Create facts table
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS facts (
                        id TEXT PRIMARY KEY,
                        fact_type TEXT NOT NULL,
                        key TEXT NOT NULL,
                        value TEXT NOT NULL,
                        source_conversation_id TEXT NOT NULL,
                        source_message_id TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)

                # Create FTS5 virtual table for full-text search on facts
                await db.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
                        id UNINDEXED,
                        key,
                        value,
                        content='facts',
                        content_rowid='rowid'
                    )
                """)

                # Create triggers to keep FTS5 in sync
                await db.execute("""
                    CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
                        INSERT INTO facts_fts(rowid, id, key, value)
                        VALUES (new.rowid, new.id, new.key, new.value);
                    END
                """)

                await db.execute("""
                    CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
                        DELETE FROM facts_fts WHERE rowid = old.rowid;
                    END
                """)

                await db.execute("""
                    CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
                        UPDATE facts_fts SET key = new.key, value = new.value
                        WHERE rowid = old.rowid;
                    END
                """)

                # Index for efficient lookups
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_facts_type_key
                    ON facts(fact_type, key)
                """)

                await db.commit()
            self._tables_created = True

    async def extract_facts_from_turn(
        self,
        user_message: str,
        assistant_message: str,
        conversation_id: str,
        message_id: str,
        use_lightweight_model: bool = True
    ) -> List[Fact]:
        """Extract facts from a conversation turn using LLM.

        Args:
            user_message: The user's message
            assistant_message: The assistant's response
            conversation_id: ID of the conversation
            message_id: ID of the assistant message
            use_lightweight_model: Use a cheaper/faster model for extraction

        Returns:
            List of extracted facts
        """
        # Build extraction prompt
        prompt = self.EXTRACTION_PROMPT.format(
            user_message=user_message,
            assistant_message=assistant_message
        )

        # Call LLM with JSON mode for structured extraction
        try:
            extraction_result = await self._call_extraction_llm(
                prompt, use_lightweight_model
            )

            facts = []
            for fact_data in extraction_result.get("facts", []):
                # Validate fact data
                if not all(k in fact_data for k in ["fact_type", "key", "value", "confidence"]):
                    logger.warning(f"Skipping incomplete fact: {fact_data}")
                    continue

                # Filter by confidence threshold
                if fact_data["confidence"] < 0.5:
                    logger.debug(f"Skipping low-confidence fact: {fact_data}")
                    continue

                fact = Fact(
                    id=f"fact_{uuid.uuid4().hex[:12]}",
                    fact_type=fact_data["fact_type"],
                    key=fact_data["key"],
                    value=fact_data["value"],
                    source_conversation_id=conversation_id,
                    source_message_id=message_id,
                    confidence=fact_data["confidence"],
                    created_at=datetime.now().isoformat(),
                    updated_at=datetime.now().isoformat()
                )
                facts.append(fact)

            logger.info(f"Extracted {len(facts)} facts from conversation turn")
            return facts

        except Exception as e:
            logger.error(f"Fact extraction failed: {e}")
            return []

    async def _call_extraction_llm(
        self, prompt: str, use_lightweight_model: bool
    ) -> Dict[str, Any]:
        """Call LLM to extract facts from conversation turn.

        Uses JSON mode for structured output.
        """
        # Use a lightweight model for extraction to reduce cost/latency
        if use_lightweight_model and config.OPENAI_API_KEY:
            # Use GPT-4o-mini or GPT-4o for extraction
            from openai import OpenAI
            client = OpenAI(api_key=config.OPENAI_API_KEY)

            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    max_tokens=500,
                    temperature=0.0  # Deterministic extraction
                )
                content = response.choices[0].message.content
                if content is None:
                    return {"facts": []}
                return json.loads(content)
            except Exception as e:
                logger.warning(f"Lightweight model extraction failed: {e}, falling back")

        # Fallback to configured model
        if config.ANTHROPIC_API_KEY:
            from anthropic import Anthropic
            client = Anthropic(api_key=config.ANTHROPIC_API_KEY)

            response = client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0
            )

            # Extract text from response content
            content = ""
            for block in response.content:
                block_text = getattr(block, "text", None)
                if block_text:
                    content = block_text
                    break
            if not content:
                return {"facts": []}
            # Find JSON in response
            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(content[start:end])
            return {"facts": []}

        elif config.OPENAI_API_KEY:
            from openai import OpenAI
            client = OpenAI(api_key=config.OPENAI_API_KEY)

            response = client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                max_tokens=500,
                temperature=0.0
            )
            content = response.choices[0].message.content
            if content is None:
                return {"facts": []}
            return json.loads(content)

        else:
            logger.error("No API key available for fact extraction")
            return {"facts": []}

    async def store_facts(self, facts: List[Fact], deduplicate: bool = True):
        """Store facts in the database with deduplication.

        Args:
            facts: List of facts to store
            deduplicate: If True, update existing facts with same type+key
        """
        await self._ensure_initialized()

        async with self._get_connection() as db:
            for fact in facts:
                if deduplicate:
                    # Check for existing fact with same type and key
                    cursor = await db.execute(
                        "SELECT id, confidence FROM facts WHERE fact_type = ? AND key = ?",
                        (fact.fact_type, fact.key)
                    )
                    existing = await cursor.fetchone()

                    if existing:
                        existing_id, existing_confidence = existing
                        # Update if new fact has higher or equal confidence
                        if fact.confidence >= existing_confidence:
                            await db.execute(
                                """UPDATE facts
                                   SET value = ?, confidence = ?, updated_at = ?,
                                       source_conversation_id = ?, source_message_id = ?
                                   WHERE id = ?""",
                                (fact.value, fact.confidence, fact.updated_at,
                                 fact.source_conversation_id, fact.source_message_id,
                                 existing_id)
                            )
                            logger.info(
                                f"Updated fact {fact.fact_type}:{fact.key} "
                                f"(confidence {existing_confidence:.2f} -> {fact.confidence:.2f})"
                            )
                        else:
                            logger.debug(
                                f"Skipping fact update {fact.fact_type}:{fact.key} "
                                f"(lower confidence {fact.confidence:.2f} < {existing_confidence:.2f})"
                            )
                        continue

                # Insert new fact
                await db.execute(
                    """INSERT INTO facts
                       (id, fact_type, key, value, source_conversation_id,
                        source_message_id, confidence, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (fact.id, fact.fact_type, fact.key, fact.value,
                     fact.source_conversation_id, fact.source_message_id,
                     fact.confidence, fact.created_at, fact.updated_at)
                )
                logger.info(f"Stored new fact {fact.fact_type}:{fact.key}")

            await db.commit()

    async def recall_facts(
        self,
        query: Optional[str] = None,
        fact_types: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[Fact]:
        """Recall relevant facts for injecting into system prompt.

        Args:
            query: Optional search query (uses FTS5 if provided)
            fact_types: Optional list of fact types to filter
            limit: Maximum number of facts to return

        Returns:
            List of relevant facts, ordered by relevance/confidence
        """
        await self._ensure_initialized()

        async with self._get_connection() as db:
            words: List[str] = []
            if query:
                # Sanitize query for FTS5 (strip special chars like ?, *, +, etc.)
                sanitized = re.sub(r'[^\w\s]', ' ', query).strip()
                # Extract words and join with OR for broad matching
                words = sanitized.split()
                if not words:
                    # No usable search terms after sanitization, fall through to non-query path
                    query = None

            if query and words:
                fts_query = " OR ".join(f'"{w}"' for w in words)
                # Use FTS5 for keyword search
                sql = """
                    SELECT f.id, f.fact_type, f.key, f.value,
                           f.source_conversation_id, f.source_message_id,
                           f.confidence, f.created_at, f.updated_at
                    FROM facts f
                    JOIN facts_fts fts ON f.rowid = fts.rowid
                    WHERE facts_fts MATCH ?
                """
                params: List[Any] = [fts_query]

                if fact_types:
                    sql += " AND f.fact_type IN ({})".format(
                        ",".join("?" * len(fact_types))
                    )
                    params.extend(fact_types)

                sql += " ORDER BY f.confidence DESC LIMIT ?"
                params.append(limit)

                cursor = await db.execute(sql, params)
            else:
                # Return most confident facts
                sql = """
                    SELECT id, fact_type, key, value,
                           source_conversation_id, source_message_id,
                           confidence, created_at, updated_at
                    FROM facts
                """
                params: List[Any] = []

                if fact_types:
                    sql += " WHERE fact_type IN ({})".format(
                        ",".join("?" * len(fact_types))
                    )
                    params.extend(fact_types)

                sql += " ORDER BY confidence DESC LIMIT ?"
                params.append(limit)

                cursor = await db.execute(sql, params)

            rows = await cursor.fetchall()
            facts = []
            for row in rows:
                fact = Fact(
                    id=row[0],
                    fact_type=row[1],
                    key=row[2],
                    value=row[3],
                    source_conversation_id=row[4],
                    source_message_id=row[5],
                    confidence=row[6],
                    created_at=row[7],
                    updated_at=row[8]
                )
                facts.append(fact)

            return facts

    async def get_all_facts(
        self,
        limit: int = 100,
        offset: int = 0,
        fact_type: Optional[str] = None
    ) -> List[Fact]:
        """Get all stored facts with pagination.

        Args:
            limit: Maximum number of facts to return
            offset: Pagination offset
            fact_type: Optional filter by fact type

        Returns:
            List of facts
        """
        await self._ensure_initialized()

        async with self._get_connection() as db:
            if fact_type:
                cursor = await db.execute(
                    """SELECT id, fact_type, key, value,
                              source_conversation_id, source_message_id,
                              confidence, created_at, updated_at
                       FROM facts
                       WHERE fact_type = ?
                       ORDER BY updated_at DESC
                       LIMIT ? OFFSET ?""",
                    (fact_type, limit, offset)
                )
            else:
                cursor = await db.execute(
                    """SELECT id, fact_type, key, value,
                              source_conversation_id, source_message_id,
                              confidence, created_at, updated_at
                       FROM facts
                       ORDER BY updated_at DESC
                       LIMIT ? OFFSET ?""",
                    (limit, offset)
                )

            rows = await cursor.fetchall()
            facts = []
            for row in rows:
                fact = Fact(
                    id=row[0],
                    fact_type=row[1],
                    key=row[2],
                    value=row[3],
                    source_conversation_id=row[4],
                    source_message_id=row[5],
                    confidence=row[6],
                    created_at=row[7],
                    updated_at=row[8]
                )
                facts.append(fact)

            return facts

    async def get_fact(self, fact_id: str) -> Optional[Fact]:
        """Get a specific fact by ID."""
        await self._ensure_initialized()

        async with self._get_connection() as db:
            cursor = await db.execute(
                """SELECT id, fact_type, key, value,
                          source_conversation_id, source_message_id,
                          confidence, created_at, updated_at
                   FROM facts WHERE id = ?""",
                (fact_id,)
            )
            row = await cursor.fetchone()

            if not row:
                return None

            return Fact(
                id=row[0],
                fact_type=row[1],
                key=row[2],
                value=row[3],
                source_conversation_id=row[4],
                source_message_id=row[5],
                confidence=row[6],
                created_at=row[7],
                updated_at=row[8]
            )

    async def delete_fact(self, fact_id: str) -> bool:
        """Delete a specific fact by ID.

        Returns:
            True if the fact was deleted, False if it didn't exist
        """
        await self._ensure_initialized()

        async with self._get_connection() as db:
            cursor = await db.execute("SELECT 1 FROM facts WHERE id = ?", (fact_id,))
            if not await cursor.fetchone():
                return False

            await db.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
            await db.commit()
            logger.info(f"Deleted fact {fact_id}")
            return True

    async def delete_all_facts(self) -> int:
        """Delete all facts.

        Returns:
            Number of facts deleted
        """
        await self._ensure_initialized()

        async with self._get_connection() as db:
            cursor = await db.execute("SELECT COUNT(*) FROM facts")
            row = await cursor.fetchone()
            count = row[0] if row else 0

            await db.execute("DELETE FROM facts")
            await db.commit()
            logger.info(f"Deleted all {count} facts")
            return count

    def format_facts_for_system_prompt(self, facts: List[Fact]) -> str:
        """Format facts for injection into system prompt.

        Args:
            facts: List of facts to format

        Returns:
            Formatted text for system prompt injection
        """
        if not facts:
            return ""

        # Group facts by type
        facts_by_type: Dict[str, List[Fact]] = {}
        for fact in facts:
            if fact.fact_type not in facts_by_type:
                facts_by_type[fact.fact_type] = []
            facts_by_type[fact.fact_type].append(fact)

        # Build formatted output
        lines = ["## What I know about you:"]
        lines.append("")

        type_labels = {
            "preference": "Preferences",
            "personal_info": "Personal Info",
            "work_context": "Work Context",
            "behavioral_pattern": "Communication Style",
            "temporal": "Schedule"
        }

        for fact_type, type_facts in facts_by_type.items():
            label = type_labels.get(fact_type, fact_type.replace("_", " ").title())
            lines.append(f"**{label}:**")
            for fact in type_facts:
                lines.append(f"- {fact.value}")
            lines.append("")

        return "\n".join(lines)


# Global service instance
_service: Optional[MemoryExtractorService] = None


def get_memory_extractor() -> MemoryExtractorService:
    """Get the global memory extractor service instance."""
    global _service
    if _service is None:
        # Use a separate database for facts to avoid conflicts
        facts_db = config.DATABASE_PATH.parent / "facts.db"
        _service = MemoryExtractorService(facts_db)
    return _service
