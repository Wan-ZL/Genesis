"""Tests for persona service and API."""
import pytest
from pathlib import Path
import tempfile
import os

from server.services.persona import PersonaService, BUILTIN_PERSONAS
from server.routes.persona import router
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        os.unlink(db_path)


@pytest.fixture
def persona_service(temp_db):
    """Create a PersonaService instance with temp database."""
    return PersonaService(temp_db)


@pytest.fixture
def app():
    """Create a FastAPI test app with persona router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


# ============================================================================
# PersonaService Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_all_personas_includes_builtins(persona_service):
    """Built-in personas should always be available."""
    personas = await persona_service.get_all_personas()

    # Should have at least the 3 built-in personas
    assert len(personas) >= 3

    # Check that all built-ins are present
    persona_ids = {p.id for p in personas}
    assert "default" in persona_ids
    assert "code-expert" in persona_ids
    assert "creative-writer" in persona_ids


@pytest.mark.asyncio
async def test_get_builtin_persona(persona_service):
    """Should be able to retrieve built-in personas by ID."""
    persona = await persona_service.get_persona("default")

    assert persona is not None
    assert persona.id == "default"
    assert persona.name == "Default Assistant"
    assert persona.is_builtin is True
    assert len(persona.system_prompt) > 0


@pytest.mark.asyncio
async def test_create_custom_persona(persona_service):
    """Should be able to create custom personas."""
    persona = await persona_service.create_persona(
        name="Test Persona",
        description="A test persona",
        system_prompt="You are a test assistant."
    )

    assert persona.id.startswith("persona_")
    assert persona.name == "Test Persona"
    assert persona.description == "A test persona"
    assert persona.system_prompt == "You are a test assistant."
    assert persona.is_builtin is False


@pytest.mark.asyncio
async def test_create_persona_with_long_prompt(persona_service):
    """System prompts can be up to 4000 characters."""
    long_prompt = "A" * 4000
    persona = await persona_service.create_persona(
        name="Long Prompt",
        description="Test",
        system_prompt=long_prompt
    )

    assert len(persona.system_prompt) == 4000


@pytest.mark.asyncio
async def test_create_persona_exceeds_limit(persona_service):
    """System prompts cannot exceed 4000 characters."""
    too_long = "A" * 4001

    with pytest.raises(ValueError, match="4000 characters"):
        await persona_service.create_persona(
            name="Too Long",
            description="Test",
            system_prompt=too_long
        )


@pytest.mark.asyncio
async def test_get_all_personas_includes_custom(persona_service):
    """Custom personas should appear in get_all_personas."""
    # Create a custom persona
    await persona_service.create_persona(
        name="Custom",
        description="Test",
        system_prompt="Custom prompt"
    )

    personas = await persona_service.get_all_personas()
    custom_personas = [p for p in personas if not p.is_builtin]

    assert len(custom_personas) == 1
    assert custom_personas[0].name == "Custom"


@pytest.mark.asyncio
async def test_update_custom_persona(persona_service):
    """Should be able to update custom personas."""
    # Create a custom persona
    persona = await persona_service.create_persona(
        name="Original",
        description="Original desc",
        system_prompt="Original prompt"
    )

    # Update it
    success = await persona_service.update_persona(
        persona_id=persona.id,
        name="Updated",
        description="Updated desc"
    )

    assert success is True

    # Verify update
    updated = await persona_service.get_persona(persona.id)
    assert updated.name == "Updated"
    assert updated.description == "Updated desc"
    assert updated.system_prompt == "Original prompt"  # Unchanged


@pytest.mark.asyncio
async def test_update_persona_system_prompt(persona_service):
    """Should be able to update system prompt."""
    persona = await persona_service.create_persona(
        name="Test",
        description="Test",
        system_prompt="Original"
    )

    success = await persona_service.update_persona(
        persona_id=persona.id,
        system_prompt="Updated prompt"
    )

    assert success is True

    updated = await persona_service.get_persona(persona.id)
    assert updated.system_prompt == "Updated prompt"


@pytest.mark.asyncio
async def test_update_builtin_persona_fails(persona_service):
    """Cannot update built-in personas."""
    success = await persona_service.update_persona(
        persona_id="default",
        name="Modified"
    )

    assert success is False


@pytest.mark.asyncio
async def test_update_persona_exceeds_limit(persona_service):
    """Cannot update to a prompt exceeding 4000 characters."""
    persona = await persona_service.create_persona(
        name="Test",
        description="Test",
        system_prompt="Original"
    )

    too_long = "A" * 4001

    with pytest.raises(ValueError, match="4000 characters"):
        await persona_service.update_persona(
            persona_id=persona.id,
            system_prompt=too_long
        )


@pytest.mark.asyncio
async def test_delete_custom_persona(persona_service):
    """Should be able to delete custom personas."""
    persona = await persona_service.create_persona(
        name="To Delete",
        description="Test",
        system_prompt="Test"
    )

    success = await persona_service.delete_persona(persona.id)
    assert success is True

    # Verify deletion
    deleted = await persona_service.get_persona(persona.id)
    assert deleted is None


@pytest.mark.asyncio
async def test_delete_builtin_persona_fails(persona_service):
    """Cannot delete built-in personas."""
    success = await persona_service.delete_persona("default")
    assert success is False

    # Verify it still exists
    persona = await persona_service.get_persona("default")
    assert persona is not None


@pytest.mark.asyncio
async def test_set_conversation_persona(persona_service):
    """Should be able to set persona for a conversation."""
    await persona_service.set_conversation_persona(
        conversation_id="conv_123",
        persona_id="code-expert"
    )

    settings = await persona_service.get_conversation_persona("conv_123")
    assert settings is not None
    assert settings["persona_id"] == "code-expert"
    assert settings["custom_system_prompt"] is None


@pytest.mark.asyncio
async def test_set_conversation_custom_prompt(persona_service):
    """Should be able to set custom system prompt for a conversation."""
    await persona_service.set_conversation_persona(
        conversation_id="conv_123",
        custom_system_prompt="Custom prompt for this conversation"
    )

    settings = await persona_service.get_conversation_persona("conv_123")
    assert settings is not None
    assert settings["custom_system_prompt"] == "Custom prompt for this conversation"


@pytest.mark.asyncio
async def test_set_conversation_both_persona_and_custom(persona_service):
    """Can set both persona_id and custom_system_prompt."""
    await persona_service.set_conversation_persona(
        conversation_id="conv_123",
        persona_id="code-expert",
        custom_system_prompt="Override prompt"
    )

    settings = await persona_service.get_conversation_persona("conv_123")
    assert settings["persona_id"] == "code-expert"
    assert settings["custom_system_prompt"] == "Override prompt"


@pytest.mark.asyncio
async def test_set_conversation_custom_prompt_exceeds_limit(persona_service):
    """Custom conversation prompts cannot exceed 4000 characters."""
    too_long = "A" * 4001

    with pytest.raises(ValueError, match="4000 characters"):
        await persona_service.set_conversation_persona(
            conversation_id="conv_123",
            custom_system_prompt=too_long
        )


@pytest.mark.asyncio
async def test_get_active_system_prompt_default(persona_service):
    """With no overrides, should use default system prompt."""
    prompt = await persona_service.get_active_system_prompt(
        conversation_id="conv_no_override",
        default_system_prompt="Default from settings"
    )

    assert prompt == "Default from settings"


@pytest.mark.asyncio
async def test_get_active_system_prompt_persona(persona_service):
    """Should use persona template if assigned."""
    await persona_service.set_conversation_persona(
        conversation_id="conv_123",
        persona_id="code-expert"
    )

    prompt = await persona_service.get_active_system_prompt(
        conversation_id="conv_123",
        default_system_prompt="Default from settings"
    )

    # Should match the code-expert persona prompt
    code_expert = await persona_service.get_persona("code-expert")
    assert prompt == code_expert.system_prompt


@pytest.mark.asyncio
async def test_get_active_system_prompt_custom_override(persona_service):
    """Custom system prompt should take precedence over persona."""
    await persona_service.set_conversation_persona(
        conversation_id="conv_123",
        persona_id="code-expert",
        custom_system_prompt="Custom override"
    )

    prompt = await persona_service.get_active_system_prompt(
        conversation_id="conv_123",
        default_system_prompt="Default from settings"
    )

    assert prompt == "Custom override"


@pytest.mark.asyncio
async def test_get_active_system_prompt_fallback(persona_service):
    """Should fall back to hardcoded default if nothing is set."""
    prompt = await persona_service.get_active_system_prompt(
        conversation_id="conv_no_settings",
        default_system_prompt=""
    )

    assert prompt == "You are a helpful AI assistant. Be concise and helpful."


# ============================================================================
# API Endpoint Tests (Synchronous - using TestClient)
# ============================================================================


def test_api_list_personas(client, temp_db):
    """GET /personas should list all personas."""
    import config
    config.DATABASE_PATH = temp_db

    response = client.get("/personas")
    assert response.status_code == 200

    data = response.json()
    assert "personas" in data
    assert len(data["personas"]) >= 3  # At least the 3 built-ins


def test_api_get_persona(client, temp_db):
    """GET /personas/{id} should return a persona."""
    import config
    config.DATABASE_PATH = temp_db

    response = client.get("/personas/default")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == "default"
    assert data["is_builtin"] is True


def test_api_get_nonexistent_persona(client, temp_db):
    """GET /personas/{id} should 404 for nonexistent persona."""
    import config
    config.DATABASE_PATH = temp_db

    response = client.get("/personas/nonexistent")
    assert response.status_code == 404


def test_api_create_persona(client, temp_db):
    """POST /personas should create a new persona."""
    import config
    config.DATABASE_PATH = temp_db

    response = client.post("/personas", json={
        "name": "API Test",
        "description": "Created via API",
        "system_prompt": "You are an API test."
    })

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "API Test"
    assert data["is_builtin"] is False


def test_api_create_persona_too_long(client, temp_db):
    """POST /personas should reject prompts exceeding 4000 chars."""
    import config
    config.DATABASE_PATH = temp_db

    response = client.post("/personas", json={
        "name": "Too Long",
        "description": "Test",
        "system_prompt": "A" * 4001
    })

    assert response.status_code == 400


def test_api_update_persona(client, temp_db):
    """PUT /personas/{id} should update a custom persona."""
    import config
    config.DATABASE_PATH = temp_db

    # Create a persona first
    create_response = client.post("/personas", json={
        "name": "Original",
        "description": "Original",
        "system_prompt": "Original"
    })
    persona_id = create_response.json()["id"]

    # Update it
    response = client.put(f"/personas/{persona_id}", json={
        "name": "Updated"
    })

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated"


def test_api_update_builtin_persona(client, temp_db):
    """PUT /personas/{id} should reject updates to built-in personas."""
    import config
    config.DATABASE_PATH = temp_db

    response = client.put("/personas/default", json={
        "name": "Modified"
    })

    assert response.status_code == 400


def test_api_delete_persona(client, temp_db):
    """DELETE /personas/{id} should delete a custom persona."""
    import config
    config.DATABASE_PATH = temp_db

    # Create a persona first
    create_response = client.post("/personas", json={
        "name": "To Delete",
        "description": "Test",
        "system_prompt": "Test"
    })
    persona_id = create_response.json()["id"]

    # Delete it
    response = client.delete(f"/personas/{persona_id}")
    assert response.status_code == 200


def test_api_delete_builtin_persona(client, temp_db):
    """DELETE /personas/{id} should reject deletion of built-in personas."""
    import config
    config.DATABASE_PATH = temp_db

    response = client.delete("/personas/default")
    assert response.status_code == 400


def test_api_set_conversation_persona(client, temp_db):
    """PUT /conversations/{id}/persona should set persona for conversation."""
    import config
    config.DATABASE_PATH = temp_db

    response = client.put("/conversations/conv_123/persona", json={
        "persona_id": "code-expert"
    })

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["persona_id"] == "code-expert"


def test_api_get_conversation_persona(client, temp_db):
    """GET /conversations/{id}/persona should return persona settings."""
    import config
    config.DATABASE_PATH = temp_db

    # Set a persona first
    client.put("/conversations/conv_123/persona", json={
        "persona_id": "code-expert"
    })

    # Get it back
    response = client.get("/conversations/conv_123/persona")
    assert response.status_code == 200

    data = response.json()
    assert data["persona_id"] == "code-expert"


def test_api_get_conversation_persona_not_set(client, temp_db):
    """GET /conversations/{id}/persona should return nulls if not set."""
    import config
    config.DATABASE_PATH = temp_db

    response = client.get("/conversations/conv_nonexistent/persona")
    assert response.status_code == 200

    data = response.json()
    assert data["persona_id"] is None
    assert data["custom_system_prompt"] is None
