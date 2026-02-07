"""Persona service for managing system prompt templates."""
import aiosqlite
import asyncio
import uuid
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass, asdict
import threading


@dataclass
class PersonaTemplate:
    """A persona template with a custom system prompt."""
    id: str
    name: str
    description: str
    system_prompt: str
    is_builtin: bool
    created_at: str
    updated_at: str


# Built-in persona templates (3 required by issue)
BUILTIN_PERSONAS = [
    PersonaTemplate(
        id="default",
        name="Default Assistant",
        description="A helpful, friendly AI assistant",
        system_prompt="You are a helpful AI assistant. Be concise and helpful.",
        is_builtin=True,
        created_at="2026-02-07T00:00:00Z",
        updated_at="2026-02-07T00:00:00Z",
    ),
    PersonaTemplate(
        id="code-expert",
        name="Code Expert",
        description="Technical, concise, focused on code quality",
        system_prompt=(
            "You are a code expert and technical advisor. "
            "Provide concise, technically accurate responses. "
            "Focus on best practices, code quality, and performance. "
            "Include code examples when relevant. "
            "Be direct and avoid unnecessary explanations."
        ),
        is_builtin=True,
        created_at="2026-02-07T00:00:00Z",
        updated_at="2026-02-07T00:00:00Z",
    ),
    PersonaTemplate(
        id="creative-writer",
        name="Creative Writer",
        description="Expressive, narrative, imaginative",
        system_prompt=(
            "You are a creative writer and storyteller. "
            "Use vivid, expressive language and rich narratives. "
            "Engage the user's imagination with descriptive, evocative responses. "
            "Embrace metaphors, analogies, and creative explanations. "
            "Make your responses engaging and memorable."
        ),
        is_builtin=True,
        created_at="2026-02-07T00:00:00Z",
        updated_at="2026-02-07T00:00:00Z",
    ),
]


class PersonaService:
    """Service for managing persona templates and per-conversation personas.

    Personas are system prompt templates that users can apply to conversations.
    Built-in personas are always available; users can also create custom ones.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._initialized = False
        self._init_lock = threading.Lock()

    async def _ensure_initialized(self):
        """Ensure database tables exist."""
        with self._init_lock:
            if self._initialized:
                return

            async with aiosqlite.connect(self.db_path) as db:
                # Table for custom persona templates
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS persona_templates (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        description TEXT,
                        system_prompt TEXT NOT NULL,
                        is_builtin INTEGER DEFAULT 0,
                        created_at TIMESTAMP,
                        updated_at TIMESTAMP
                    )
                """)

                # Table for per-conversation persona overrides
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS conversation_personas (
                        conversation_id TEXT PRIMARY KEY,
                        persona_id TEXT,
                        custom_system_prompt TEXT,
                        updated_at TIMESTAMP,
                        FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                    )
                """)

                await db.commit()

            self._initialized = True

    async def get_all_personas(self) -> List[PersonaTemplate]:
        """Get all persona templates (built-in + custom).

        Returns:
            List of PersonaTemplate objects sorted by: built-in first, then custom by name
        """
        await self._ensure_initialized()

        personas = list(BUILTIN_PERSONAS)

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """SELECT id, name, description, system_prompt, is_builtin, created_at, updated_at
                   FROM persona_templates
                   WHERE is_builtin = 0
                   ORDER BY name"""
            )
            rows = await cursor.fetchall()
            for row in rows:
                personas.append(PersonaTemplate(
                    id=row[0],
                    name=row[1],
                    description=row[2] or "",
                    system_prompt=row[3],
                    is_builtin=bool(row[4]),
                    created_at=row[5],
                    updated_at=row[6],
                ))

        return personas

    async def get_persona(self, persona_id: str) -> Optional[PersonaTemplate]:
        """Get a persona by ID (checks built-in first, then custom)."""
        await self._ensure_initialized()

        # Check built-in personas first
        for persona in BUILTIN_PERSONAS:
            if persona.id == persona_id:
                return persona

        # Check custom personas
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """SELECT id, name, description, system_prompt, is_builtin, created_at, updated_at
                   FROM persona_templates
                   WHERE id = ?""",
                (persona_id,)
            )
            row = await cursor.fetchone()
            if row:
                return PersonaTemplate(
                    id=row[0],
                    name=row[1],
                    description=row[2] or "",
                    system_prompt=row[3],
                    is_builtin=bool(row[4]),
                    created_at=row[5],
                    updated_at=row[6],
                )

        return None

    async def create_persona(
        self,
        name: str,
        description: str,
        system_prompt: str
    ) -> PersonaTemplate:
        """Create a new custom persona template.

        Args:
            name: Persona name (e.g., "Code Reviewer")
            description: Short description
            system_prompt: The system prompt text (max 4000 chars)

        Returns:
            The created PersonaTemplate

        Raises:
            ValueError: If system_prompt exceeds 4000 characters
        """
        await self._ensure_initialized()

        if len(system_prompt) > 4000:
            raise ValueError("System prompt cannot exceed 4000 characters")

        persona_id = f"persona_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO persona_templates
                   (id, name, description, system_prompt, is_builtin, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 0, ?, ?)""",
                (persona_id, name, description, system_prompt, now, now)
            )
            await db.commit()

        return PersonaTemplate(
            id=persona_id,
            name=name,
            description=description,
            system_prompt=system_prompt,
            is_builtin=False,
            created_at=now,
            updated_at=now,
        )

    async def update_persona(
        self,
        persona_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        system_prompt: Optional[str] = None
    ) -> bool:
        """Update a custom persona template.

        Args:
            persona_id: The persona to update
            name: Optional new name
            description: Optional new description
            system_prompt: Optional new system prompt (max 4000 chars)

        Returns:
            True if updated, False if not found or is built-in

        Raises:
            ValueError: If system_prompt exceeds 4000 characters
        """
        await self._ensure_initialized()

        # Check if it's a built-in (cannot update)
        for builtin in BUILTIN_PERSONAS:
            if builtin.id == persona_id:
                return False

        if system_prompt and len(system_prompt) > 4000:
            raise ValueError("System prompt cannot exceed 4000 characters")

        # Build update query
        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if system_prompt is not None:
            updates.append("system_prompt = ?")
            params.append(system_prompt)

        if not updates:
            return True  # Nothing to update

        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(persona_id)

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                f"""UPDATE persona_templates
                    SET {', '.join(updates)}
                    WHERE id = ? AND is_builtin = 0""",
                params
            )
            await db.commit()
            return cursor.rowcount > 0

    async def delete_persona(self, persona_id: str) -> bool:
        """Delete a custom persona template.

        Args:
            persona_id: The persona to delete

        Returns:
            True if deleted, False if not found or is built-in
        """
        await self._ensure_initialized()

        # Check if it's a built-in (cannot delete)
        for builtin in BUILTIN_PERSONAS:
            if builtin.id == persona_id:
                return False

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM persona_templates WHERE id = ? AND is_builtin = 0",
                (persona_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def set_conversation_persona(
        self,
        conversation_id: str,
        persona_id: Optional[str] = None,
        custom_system_prompt: Optional[str] = None
    ):
        """Set persona for a specific conversation.

        Args:
            conversation_id: The conversation
            persona_id: Optional persona template ID
            custom_system_prompt: Optional custom override (max 4000 chars)

        Raises:
            ValueError: If custom_system_prompt exceeds 4000 characters
        """
        await self._ensure_initialized()

        if custom_system_prompt and len(custom_system_prompt) > 4000:
            raise ValueError("System prompt cannot exceed 4000 characters")

        now = datetime.now().isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO conversation_personas
                   (conversation_id, persona_id, custom_system_prompt, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(conversation_id) DO UPDATE SET
                   persona_id = ?, custom_system_prompt = ?, updated_at = ?""",
                (conversation_id, persona_id, custom_system_prompt, now,
                 persona_id, custom_system_prompt, now)
            )
            await db.commit()

    async def get_conversation_persona(self, conversation_id: str) -> Optional[dict]:
        """Get the persona settings for a conversation.

        Returns:
            Dict with persona_id and custom_system_prompt, or None
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """SELECT persona_id, custom_system_prompt
                   FROM conversation_personas
                   WHERE conversation_id = ?""",
                (conversation_id,)
            )
            row = await cursor.fetchone()
            if row:
                return {
                    "persona_id": row[0],
                    "custom_system_prompt": row[1],
                }
        return None

    async def get_active_system_prompt(
        self,
        conversation_id: str,
        default_system_prompt: str = ""
    ) -> str:
        """Get the effective system prompt for a conversation.

        Priority order:
        1. Conversation-specific custom system prompt
        2. Conversation-assigned persona template
        3. Default system prompt from settings
        4. Fallback default

        Args:
            conversation_id: The conversation
            default_system_prompt: Default from settings

        Returns:
            The effective system prompt
        """
        await self._ensure_initialized()

        # Check for conversation-specific override
        conv_persona = await self.get_conversation_persona(conversation_id)
        if conv_persona:
            # Custom system prompt takes precedence
            if conv_persona.get("custom_system_prompt"):
                return conv_persona["custom_system_prompt"]

            # Otherwise, use assigned persona template
            if conv_persona.get("persona_id"):
                persona = await self.get_persona(conv_persona["persona_id"])
                if persona:
                    return persona.system_prompt

        # Fall back to default system prompt from settings
        if default_system_prompt:
            return default_system_prompt

        # Ultimate fallback
        return "You are a helpful AI assistant. Be concise and helpful."
