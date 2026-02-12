"""Tests for user profile service and API."""
import pytest
import tempfile
from pathlib import Path
from server.services.user_profile import UserProfileService, PROFILE_SECTIONS, FACT_TYPE_TO_SECTION
from server.services.memory_extractor import MemoryExtractorService, Fact
from datetime import datetime


@pytest.fixture
async def profile_service():
    """Create a temporary profile service for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_profile.db"
        service = UserProfileService(db_path)
        await service._ensure_initialized()
        yield service


@pytest.fixture
async def memory_extractor():
    """Create a temporary memory extractor for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_facts.db"
        service = MemoryExtractorService(db_path)
        await service._ensure_initialized()
        yield service


@pytest.mark.asyncio
async def test_profile_sections_defined():
    """Test that profile sections are properly defined."""
    assert len(PROFILE_SECTIONS) == 6
    assert "personal_info" in PROFILE_SECTIONS
    assert "work" in PROFILE_SECTIONS
    assert "preferences" in PROFILE_SECTIONS
    assert "schedule_patterns" in PROFILE_SECTIONS
    assert "interests" in PROFILE_SECTIONS
    assert "communication_style" in PROFILE_SECTIONS


@pytest.mark.asyncio
async def test_get_empty_profile(profile_service):
    """Test getting an empty profile returns all sections."""
    profile = await profile_service.get_profile()

    assert len(profile) == 6
    for section in PROFILE_SECTIONS.keys():
        assert section in profile
        assert profile[section] == {}


@pytest.mark.asyncio
async def test_update_section(profile_service):
    """Test updating a profile section."""
    result = await profile_service.update_section("personal_info", {
        "name": "Alice",
        "location": "San Francisco"
    })

    assert "updated" in result
    assert len(result["updated"]) == 2
    assert "name" in result["updated"]
    assert "location" in result["updated"]

    # Verify it was stored
    section = await profile_service.get_section("personal_info")
    assert "name" in section
    assert section["name"]["value"] == "Alice"
    assert section["name"]["is_manual_override"] == True
    assert section["location"]["value"] == "San Francisco"


@pytest.mark.asyncio
async def test_update_invalid_section(profile_service):
    """Test that updating an invalid section raises an error."""
    with pytest.raises(ValueError, match="Invalid section"):
        await profile_service.update_section("invalid_section", {"key": "value"})


@pytest.mark.asyncio
async def test_get_section(profile_service):
    """Test getting a specific profile section."""
    await profile_service.update_section("work", {
        "company": "Acme Corp",
        "role": "Engineer"
    })

    section = await profile_service.get_section("work")
    assert len(section) == 2
    assert section["company"]["value"] == "Acme Corp"
    assert section["role"]["value"] == "Engineer"


@pytest.mark.asyncio
async def test_get_invalid_section(profile_service):
    """Test that getting an invalid section raises an error."""
    with pytest.raises(ValueError, match="Invalid section"):
        await profile_service.get_section("invalid_section")


@pytest.mark.asyncio
async def test_delete_entry(profile_service):
    """Test deleting a profile entry."""
    # Add entry
    await profile_service.update_section("preferences", {"theme": "dark"})

    # Delete it
    deleted = await profile_service.delete_entry("preferences", "theme")
    assert deleted == True

    # Verify it's gone
    section = await profile_service.get_section("preferences")
    assert "theme" not in section


@pytest.mark.asyncio
async def test_delete_nonexistent_entry(profile_service):
    """Test deleting a nonexistent entry returns False."""
    deleted = await profile_service.delete_entry("preferences", "nonexistent")
    assert deleted == False


@pytest.mark.asyncio
async def test_aggregate_from_facts(profile_service, memory_extractor):
    """Test aggregating profile from memory facts."""
    # Create some facts
    facts = [
        Fact(
            id="fact1",
            fact_type="personal_info",
            key="name",
            value="Bob",
            source_conversation_id="conv1",
            source_message_id="msg1",
            confidence=0.95,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        ),
        Fact(
            id="fact2",
            fact_type="work_context",
            key="company",
            value="TechCo",
            source_conversation_id="conv1",
            source_message_id="msg2",
            confidence=0.90,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        ),
        Fact(
            id="fact3",
            fact_type="preference",
            key="response_style",
            value="concise",
            source_conversation_id="conv1",
            source_message_id="msg3",
            confidence=0.85,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        ),
    ]

    # Store facts in memory extractor
    await memory_extractor.store_facts(facts)

    # Aggregate into profile
    await profile_service.aggregate_from_facts(memory_extractor)

    # Verify profile was populated
    profile = await profile_service.get_profile()

    # Check personal_info section
    assert "name" in profile["personal_info"]
    assert profile["personal_info"]["name"]["value"] == "Bob"
    assert profile["personal_info"]["name"]["confidence"] == 0.95

    # Check work section
    assert "company" in profile["work"]
    assert profile["work"]["company"]["value"] == "TechCo"

    # Check preferences section
    assert "response_style" in profile["preferences"]
    assert profile["preferences"]["response_style"]["value"] == "concise"


@pytest.mark.asyncio
async def test_aggregate_updates_with_higher_confidence(profile_service, memory_extractor):
    """Test that aggregation updates entries when confidence is higher."""
    # Initial fact
    fact1 = Fact(
        id="fact1",
        fact_type="personal_info",
        key="name",
        value="Alice",
        source_conversation_id="conv1",
        source_message_id="msg1",
        confidence=0.80,
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )
    await memory_extractor.store_facts([fact1])
    await profile_service.aggregate_from_facts(memory_extractor)

    # Higher confidence fact
    fact2 = Fact(
        id="fact2",
        fact_type="personal_info",
        key="name",
        value="Alicia",
        source_conversation_id="conv1",
        source_message_id="msg2",
        confidence=0.95,
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )
    await memory_extractor.store_facts([fact2])
    await profile_service.aggregate_from_facts(memory_extractor)

    # Should be updated to higher confidence value
    section = await profile_service.get_section("personal_info")
    assert section["name"]["value"] == "Alicia"
    assert section["name"]["confidence"] == 0.95


@pytest.mark.asyncio
async def test_aggregate_preserves_manual_overrides(profile_service, memory_extractor):
    """Test that manual overrides are not overwritten by aggregation."""
    # Set manual override
    await profile_service.update_section("personal_info", {"name": "Manual Name"})

    # Try to aggregate a fact with same key
    fact = Fact(
        id="fact1",
        fact_type="personal_info",
        key="name",
        value="Extracted Name",
        source_conversation_id="conv1",
        source_message_id="msg1",
        confidence=1.0,  # Even with max confidence
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )
    await memory_extractor.store_facts([fact])
    await profile_service.aggregate_from_facts(memory_extractor)

    # Manual override should be preserved
    section = await profile_service.get_section("personal_info")
    assert section["name"]["value"] == "Manual Name"
    assert section["name"]["is_manual_override"] == True


@pytest.mark.asyncio
async def test_get_profile_summary_empty(profile_service):
    """Test that empty profile returns empty summary."""
    summary = await profile_service.get_profile_summary()
    assert summary == ""


@pytest.mark.asyncio
async def test_get_profile_summary_with_data(profile_service):
    """Test profile summary generation."""
    await profile_service.update_section("personal_info", {
        "name": "Charlie",
        "location": "NYC"
    })
    await profile_service.update_section("work", {
        "company": "StartupXYZ"
    })

    summary = await profile_service.get_profile_summary()

    assert "## User Profile:" in summary
    assert "**Personal Information:**" in summary
    assert "Charlie" in summary
    assert "NYC" in summary
    assert "**Work Context:**" in summary
    assert "StartupXYZ" in summary


@pytest.mark.asyncio
async def test_export_profile(profile_service):
    """Test exporting profile to JSON."""
    await profile_service.update_section("personal_info", {"name": "Dave"})

    export_data = await profile_service.export_profile()

    assert "version" in export_data
    assert export_data["version"] == "1.0"
    assert "exported_at" in export_data
    assert "sections" in export_data
    assert "personal_info" in export_data["sections"]
    assert "name" in export_data["sections"]["personal_info"]


@pytest.mark.asyncio
async def test_import_profile_merge(profile_service):
    """Test importing profile in merge mode."""
    # Add existing data
    await profile_service.update_section("personal_info", {"name": "Existing"})

    # Import data
    import_data = {
        "version": "1.0",
        "sections": {
            "personal_info": {
                "location": {
                    "value": "Seattle",
                    "source": "import",
                    "confidence": 0.9,
                    "is_manual_override": False
                }
            },
            "work": {
                "company": {
                    "value": "ImportCo",
                    "source": "import",
                    "confidence": 0.8,
                    "is_manual_override": False
                }
            }
        }
    }

    await profile_service.import_profile(import_data, mode="merge")

    # Verify merge: existing preserved, new added
    profile = await profile_service.get_profile()
    assert "name" in profile["personal_info"]
    assert profile["personal_info"]["name"]["value"] == "Existing"
    assert "location" in profile["personal_info"]
    assert profile["personal_info"]["location"]["value"] == "Seattle"
    assert "company" in profile["work"]


@pytest.mark.asyncio
async def test_import_profile_replace(profile_service):
    """Test importing profile in replace mode."""
    # Add existing data
    await profile_service.update_section("personal_info", {"name": "Existing"})

    # Import data in replace mode
    import_data = {
        "version": "1.0",
        "sections": {
            "work": {
                "company": {
                    "value": "NewCo",
                    "source": "import",
                    "confidence": 0.9,
                    "is_manual_override": False
                }
            }
        }
    }

    await profile_service.import_profile(import_data, mode="replace")

    # Verify replace: old data cleared, new data present
    profile = await profile_service.get_profile()
    assert "name" not in profile["personal_info"]
    assert "company" in profile["work"]
    assert profile["work"]["company"]["value"] == "NewCo"


@pytest.mark.asyncio
async def test_clear_profile(profile_service):
    """Test clearing all profile entries."""
    await profile_service.update_section("personal_info", {"name": "Test"})
    await profile_service.update_section("work", {"company": "Test"})

    await profile_service.clear_profile()

    profile = await profile_service.get_profile()
    for section in profile.values():
        assert len(section) == 0


@pytest.mark.asyncio
async def test_fact_type_mapping():
    """Test that fact types are correctly mapped to profile sections."""
    assert FACT_TYPE_TO_SECTION["personal_info"] == "personal_info"
    assert FACT_TYPE_TO_SECTION["work_context"] == "work"
    assert FACT_TYPE_TO_SECTION["preference"] == "preferences"
    assert FACT_TYPE_TO_SECTION["temporal"] == "schedule_patterns"
    assert FACT_TYPE_TO_SECTION["behavioral_pattern"] == "communication_style"


@pytest.mark.asyncio
async def test_confidence_tracked_in_profile(profile_service, memory_extractor):
    """Test that confidence scores are tracked in profile entries."""
    fact = Fact(
        id="fact1",
        fact_type="preference",
        key="language",
        value="Python",
        source_conversation_id="conv1",
        source_message_id="msg1",
        confidence=0.87,
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )

    await memory_extractor.store_facts([fact])
    await profile_service.aggregate_from_facts(memory_extractor)

    section = await profile_service.get_section("preferences")
    assert section["language"]["confidence"] == 0.87


@pytest.mark.asyncio
async def test_profile_source_tracking(profile_service, memory_extractor):
    """Test that profile entries track their source facts."""
    fact = Fact(
        id="fact_source_123",
        fact_type="work_context",
        key="role",
        value="Developer",
        source_conversation_id="conv1",
        source_message_id="msg1",
        confidence=0.9,
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )

    await memory_extractor.store_facts([fact])
    await profile_service.aggregate_from_facts(memory_extractor)

    section = await profile_service.get_section("work")
    assert section["role"]["source"] == "fact_source_123"


@pytest.mark.asyncio
async def test_multiple_sections_populated(profile_service, memory_extractor):
    """Test that multiple profile sections can be populated from facts."""
    facts = [
        Fact(
            id=f"fact{i}",
            fact_type=fact_type,
            key=f"key{i}",
            value=f"value{i}",
            source_conversation_id="conv1",
            source_message_id=f"msg{i}",
            confidence=0.9,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        for i, fact_type in enumerate([
            "personal_info", "work_context", "preference",
            "temporal", "behavioral_pattern"
        ])
    ]

    await memory_extractor.store_facts(facts)
    await profile_service.aggregate_from_facts(memory_extractor)

    profile = await profile_service.get_profile()

    # Verify all sections got populated
    assert len(profile["personal_info"]) > 0
    assert len(profile["work"]) > 0
    assert len(profile["preferences"]) > 0
    assert len(profile["schedule_patterns"]) > 0
    assert len(profile["communication_style"]) > 0
