"""User profile service for aggregating long-term memory into a structured user model.

This service builds a coherent profile from extracted facts (memory_extractor),
organizing them into sections like personal_info, work, preferences, etc.
The profile is injected into system prompts to provide user-specific context.
"""
import aiosqlite
import asyncio
import logging
import uuid
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Connection pool settings
_DB_BUSY_TIMEOUT_MS = 5000
_DB_POOL_SIZE = 5


# Profile section definitions
PROFILE_SECTIONS = {
    "personal_info": "Personal Information",
    "work": "Work Context",
    "preferences": "Preferences & Habits",
    "schedule_patterns": "Schedule & Routines",
    "interests": "Interests & Hobbies",
    "communication_style": "Communication Style"
}


# Mapping from fact types to profile sections
FACT_TYPE_TO_SECTION = {
    "personal_info": "personal_info",
    "work_context": "work",
    "preference": "preferences",
    "temporal": "schedule_patterns",
    "behavioral_pattern": "communication_style",
}


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

    async def __aexit__(self, _exc_type, _exc_val, _exc_tb):
        if self.conn:
            await self.pool.release(self.conn)
            self.conn = None


class UserProfileService:
    """Service for managing user profile aggregated from long-term memory facts.

    Architecture:
        Long-term Memory Facts → aggregate_from_facts() → Structured Profile
        Profile → get_profile_summary() → System prompt context

    Profile sections:
        - personal_info: Name, location, background, interests
        - work: Company, role, projects, industry
        - preferences: Response style, tool preferences, behavior preferences
        - schedule_patterns: Timezone, working hours, routines
        - interests: Hobbies, topics of interest
        - communication_style: Patterns, preferences
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

        with self._tables_init_lock:
            if self._tables_lock is None:
                self._tables_lock = asyncio.Lock()

        async with self._tables_lock:
            if self._tables_created:
                return

            async with self._get_connection() as db:
                # Profile table stores structured profile entries
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS user_profile (
                        id TEXT PRIMARY KEY,
                        section TEXT NOT NULL,
                        key TEXT NOT NULL,
                        value TEXT NOT NULL,
                        source TEXT,
                        confidence REAL,
                        is_manual_override INTEGER DEFAULT 0,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(section, key)
                    )
                """)

                # Index for efficient section lookups
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_profile_section
                    ON user_profile(section)
                """)

                await db.commit()
            self._tables_created = True

    async def aggregate_from_facts(self, memory_extractor):
        """Aggregate facts from long-term memory into profile sections.

        This method pulls facts from the MemoryExtractorService and organizes
        them into profile sections. It runs periodically or after fact extraction.

        Args:
            memory_extractor: MemoryExtractorService instance
        """
        await self._ensure_initialized()

        # Get all facts from memory extractor
        facts = await memory_extractor.get_all_facts(limit=1000)

        if not facts:
            logger.debug("No facts to aggregate into profile")
            return

        logger.info(f"Aggregating {len(facts)} facts into user profile")

        async with self._get_connection() as db:
            for fact in facts:
                # Map fact type to profile section
                section = FACT_TYPE_TO_SECTION.get(fact.fact_type)

                # If fact type maps to "interests", extract from personal_info
                if not section and fact.fact_type == "personal_info" and "interest" in fact.key.lower():
                    section = "interests"
                elif not section:
                    # Skip facts that don't map to profile sections
                    continue

                # Check if this entry already exists
                cursor = await db.execute(
                    """SELECT id, confidence, is_manual_override
                       FROM user_profile
                       WHERE section = ? AND key = ?""",
                    (section, fact.key)
                )
                existing = await cursor.fetchone()

                now = datetime.now().isoformat()

                if existing:
                    existing_id, existing_confidence, is_manual = existing

                    # Don't override manual entries
                    if is_manual:
                        continue

                    # Update if new fact has higher confidence
                    if fact.confidence >= existing_confidence:
                        await db.execute(
                            """UPDATE user_profile
                               SET value = ?, source = ?, confidence = ?, updated_at = ?
                               WHERE id = ?""",
                            (fact.value, fact.id, fact.confidence, now, existing_id)
                        )
                        logger.debug(
                            f"Updated profile {section}:{fact.key} "
                            f"(confidence {existing_confidence:.2f} -> {fact.confidence:.2f})"
                        )
                else:
                    # Insert new profile entry
                    profile_id = f"profile_{uuid.uuid4().hex[:12]}"
                    await db.execute(
                        """INSERT INTO user_profile
                           (id, section, key, value, source, confidence, is_manual_override, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                        (profile_id, section, fact.key, fact.value, fact.id, fact.confidence, now, now)
                    )
                    logger.debug(f"Added profile {section}:{fact.key}")

            await db.commit()

        logger.info("Profile aggregation complete")

    async def get_profile(self) -> Dict[str, Dict[str, Any]]:
        """Get the complete user profile organized by sections.

        Returns:
            Dict with sections as keys, each containing entries with key->value mappings
            Example:
            {
                "personal_info": {
                    "name": {"value": "Alex", "confidence": 0.95, "source": "fact_123", ...},
                    ...
                },
                "work": {...},
                ...
            }
        """
        await self._ensure_initialized()

        profile = {section: {} for section in PROFILE_SECTIONS.keys()}

        async with self._get_connection() as db:
            cursor = await db.execute(
                """SELECT id, section, key, value, source, confidence, is_manual_override, created_at, updated_at
                   FROM user_profile
                   ORDER BY section, key"""
            )
            rows = await cursor.fetchall()

            for row in rows:
                profile_id, section, key, value, source, confidence, is_manual, created_at, updated_at = row
                profile[section][key] = {
                    "id": profile_id,
                    "value": value,
                    "source": source,
                    "confidence": confidence,
                    "is_manual_override": bool(is_manual),
                    "created_at": created_at,
                    "updated_at": updated_at,
                }

        return profile

    async def get_section(self, section: str) -> Dict[str, Any]:
        """Get a specific profile section.

        Args:
            section: Section name (personal_info, work, preferences, etc.)

        Returns:
            Dict of entries in that section
        """
        if section not in PROFILE_SECTIONS:
            raise ValueError(f"Invalid section: {section}. Must be one of {list(PROFILE_SECTIONS.keys())}")

        await self._ensure_initialized()

        entries = {}

        async with self._get_connection() as db:
            cursor = await db.execute(
                """SELECT id, key, value, source, confidence, is_manual_override, created_at, updated_at
                   FROM user_profile
                   WHERE section = ?
                   ORDER BY key""",
                (section,)
            )
            rows = await cursor.fetchall()

            for row in rows:
                profile_id, key, value, source, confidence, is_manual, created_at, updated_at = row
                entries[key] = {
                    "id": profile_id,
                    "value": value,
                    "source": source,
                    "confidence": confidence,
                    "is_manual_override": bool(is_manual),
                    "created_at": created_at,
                    "updated_at": updated_at,
                }

        return entries

    async def update_section(self, section: str, data: Dict[str, str]) -> Dict[str, Any]:
        """Update a profile section with manual overrides.

        Args:
            section: Section name
            data: Dict of key->value pairs to update

        Returns:
            Dict with updated keys
        """
        if section not in PROFILE_SECTIONS:
            raise ValueError(f"Invalid section: {section}. Must be one of {list(PROFILE_SECTIONS.keys())}")

        await self._ensure_initialized()

        now = datetime.now().isoformat()
        updated_keys = []

        async with self._get_connection() as db:
            for key, value in data.items():
                # Check if entry exists
                cursor = await db.execute(
                    "SELECT id FROM user_profile WHERE section = ? AND key = ?",
                    (section, key)
                )
                existing = await cursor.fetchone()

                if existing:
                    # Update existing
                    await db.execute(
                        """UPDATE user_profile
                           SET value = ?, is_manual_override = 1, updated_at = ?
                           WHERE section = ? AND key = ?""",
                        (value, now, section, key)
                    )
                else:
                    # Insert new
                    profile_id = f"profile_{uuid.uuid4().hex[:12]}"
                    await db.execute(
                        """INSERT INTO user_profile
                           (id, section, key, value, source, confidence, is_manual_override, created_at, updated_at)
                           VALUES (?, ?, ?, ?, 'manual', 1.0, 1, ?, ?)""",
                        (profile_id, section, key, value, now, now)
                    )

                updated_keys.append(key)
                logger.info(f"Manually updated profile {section}:{key}")

            await db.commit()

        return {"updated": updated_keys}

    async def delete_entry(self, section: str, key: str) -> bool:
        """Delete a specific profile entry.

        Args:
            section: Section name
            key: Entry key to delete

        Returns:
            True if deleted, False if not found
        """
        if section not in PROFILE_SECTIONS:
            raise ValueError(f"Invalid section: {section}. Must be one of {list(PROFILE_SECTIONS.keys())}")

        await self._ensure_initialized()

        async with self._get_connection() as db:
            cursor = await db.execute(
                "SELECT 1 FROM user_profile WHERE section = ? AND key = ?",
                (section, key)
            )
            if not await cursor.fetchone():
                return False

            await db.execute(
                "DELETE FROM user_profile WHERE section = ? AND key = ?",
                (section, key)
            )
            await db.commit()
            logger.info(f"Deleted profile {section}:{key}")
            return True

    async def get_profile_summary(self) -> str:
        """Get a compact profile summary for system prompt injection.

        Returns:
            Formatted text suitable for injecting into system prompts
        """
        profile = await self.get_profile()

        # Build compact summary
        lines = []
        has_content = False

        for section, entries in profile.items():
            if not entries:
                continue

            has_content = True
            section_label = PROFILE_SECTIONS[section]
            lines.append(f"**{section_label}:**")

            for _key, entry in entries.items():
                value = entry["value"]
                lines.append(f"- {value}")

            lines.append("")

        if not has_content:
            return ""

        return "## User Profile:\n\n" + "\n".join(lines)

    async def export_profile(self) -> Dict[str, Any]:
        """Export the profile in a portable JSON format.

        Returns:
            Dict with version, metadata, and profile data
        """
        profile = await self.get_profile()

        return {
            "version": "1.0",
            "exported_at": datetime.now().isoformat() + "Z",
            "sections": profile,
        }

    async def import_profile(self, data: Dict[str, Any], mode: str = "merge"):
        """Import profile from exported format.

        Args:
            data: Exported profile data
            mode: "merge" (default, keep existing) or "replace" (clear first)

        Raises:
            ValueError: If format is invalid
        """
        await self._ensure_initialized()

        # Validate format
        if "version" not in data or "sections" not in data:
            raise ValueError("Invalid export format")

        if mode == "replace":
            async with self._get_connection() as db:
                await db.execute("DELETE FROM user_profile")
                await db.commit()

        # Import sections
        now = datetime.now().isoformat()

        async with self._get_connection() as db:
            for section, entries in data["sections"].items():
                if section not in PROFILE_SECTIONS:
                    continue

                for key, entry_data in entries.items():
                    value = entry_data.get("value", "")
                    source = entry_data.get("source", "import")
                    confidence = entry_data.get("confidence", 1.0)
                    is_manual = entry_data.get("is_manual_override", False)

                    # Check if exists
                    cursor = await db.execute(
                        "SELECT id FROM user_profile WHERE section = ? AND key = ?",
                        (section, key)
                    )
                    existing = await cursor.fetchone()

                    if existing and mode == "merge":
                        # Skip in merge mode
                        continue

                    if existing:
                        # Update in replace mode
                        await db.execute(
                            """UPDATE user_profile
                               SET value = ?, source = ?, confidence = ?,
                                   is_manual_override = ?, updated_at = ?
                               WHERE section = ? AND key = ?""",
                            (value, source, confidence, int(is_manual), now, section, key)
                        )
                    else:
                        # Insert new
                        profile_id = f"profile_{uuid.uuid4().hex[:12]}"
                        await db.execute(
                            """INSERT INTO user_profile
                               (id, section, key, value, source, confidence, is_manual_override, created_at, updated_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (profile_id, section, key, value, source, confidence, int(is_manual), now, now)
                        )

            await db.commit()

        logger.info(f"Profile imported in {mode} mode")

    async def clear_profile(self):
        """Clear all profile entries."""
        await self._ensure_initialized()

        async with self._get_connection() as db:
            await db.execute("DELETE FROM user_profile")
            await db.commit()

        logger.info("Profile cleared")


# Global service instance
_service: Optional[UserProfileService] = None


def get_user_profile_service(db_path: Optional[Path] = None) -> UserProfileService:
    """Get the global user profile service instance."""
    global _service
    if _service is None:
        # Use provided path or default to profile database
        if db_path is None:
            import config
            db_path = config.DATABASE_PATH.parent / "profile.db"
        _service = UserProfileService(db_path)
    return _service
