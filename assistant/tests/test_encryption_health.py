"""Tests for encryption health check and management features."""
import pytest
import tempfile
from pathlib import Path

from server.services.encryption import (
    EncryptionService,
    CRYPTOGRAPHY_AVAILABLE
)
from server.services.settings import SettingsService, SENSITIVE_KEYS


# Skip all tests if cryptography is not available
pytestmark = pytest.mark.skipif(
    not CRYPTOGRAPHY_AVAILABLE,
    reason="cryptography library not installed"
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield db_path


@pytest.fixture
def temp_key_file():
    """Create a temporary encryption key file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        key_path = Path(tmpdir) / ".encryption_key_salt"
        yield key_path


@pytest.fixture
async def settings_service(temp_db, temp_key_file):
    """Create a settings service with encryption enabled."""
    enc_service = EncryptionService(key_file_path=temp_key_file)
    service = SettingsService(temp_db, encryption_service=enc_service)
    await service._ensure_initialized()
    return service


class TestEncryptionHealthCheck:
    """Tests for encryption health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check_all_good(self, settings_service):
        """Test health check when all keys are encrypted and decryptable."""
        # Set some encrypted keys
        await settings_service.set("openai_api_key", "sk-test123")
        await settings_service.set("anthropic_api_key", "sk-ant-test456")

        health = await settings_service.check_encryption_health()

        assert health["healthy"] is True
        assert len(health["issues"]) == 0
        assert len(health["warnings"]) == 0

    @pytest.mark.asyncio
    async def test_health_check_plaintext_warning(self, temp_db):
        """Test health check warns about plaintext keys."""
        # Create service without encryption
        service = SettingsService(temp_db, encryption_service=None)
        await service._ensure_initialized()

        # Manually insert plaintext key
        async with service._get_connection() as db:
            await db.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                ("openai_api_key", "sk-plaintext123")
            )
            await db.commit()

        health = await service.check_encryption_health()

        # Should have warnings about plaintext
        assert len(health["warnings"]) > 0
        assert any("plaintext" in w.lower() for w in health["warnings"])

    @pytest.mark.asyncio
    async def test_health_check_undecryptable_issue(self, temp_db, temp_key_file):
        """Test health check detects undecryptable keys."""
        # Create service with encryption
        enc_service = EncryptionService(key_file_path=temp_key_file)
        service = SettingsService(temp_db, encryption_service=enc_service)
        await service._ensure_initialized()

        # Encrypt a key
        await service.set("openai_api_key", "sk-test123")

        # Regenerate encryption key (simulates key loss)
        temp_key_file.unlink()
        new_enc_service = EncryptionService(key_file_path=temp_key_file)
        service._encryption_service = new_enc_service

        # Force update encryption_available flag
        service._encryption_available = True

        health = await service.check_encryption_health()

        # Should detect undecryptable key
        assert health["healthy"] is False
        assert len(health["issues"]) > 0
        assert any("cannot decrypt" in issue.lower() for issue in health["issues"])

    @pytest.mark.asyncio
    async def test_can_decrypt_key_success(self, settings_service):
        """Test _can_decrypt_key returns True for decryptable key."""
        await settings_service.set("openai_api_key", "sk-test123")

        can_decrypt = await settings_service._can_decrypt_key("openai_api_key")

        assert can_decrypt is True

    @pytest.mark.asyncio
    async def test_can_decrypt_key_failure(self, temp_db, temp_key_file):
        """Test _can_decrypt_key returns False when key changed."""
        # Encrypt with one key
        enc_service = EncryptionService(key_file_path=temp_key_file)
        service = SettingsService(temp_db, encryption_service=enc_service)
        await service._ensure_initialized()
        await service.set("openai_api_key", "sk-test123")

        # Change encryption key
        temp_key_file.unlink()
        new_enc_service = EncryptionService(key_file_path=temp_key_file)
        service._encryption_service = new_enc_service

        can_decrypt = await service._can_decrypt_key("openai_api_key")

        assert can_decrypt is False

    @pytest.mark.asyncio
    async def test_can_decrypt_key_not_encrypted(self, temp_db):
        """Test _can_decrypt_key returns True for plaintext."""
        service = SettingsService(temp_db, encryption_service=None)
        await service._ensure_initialized()

        # Insert plaintext key
        async with service._get_connection() as db:
            await db.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                ("openai_api_key", "sk-plaintext123")
            )
            await db.commit()

        can_decrypt = await service._can_decrypt_key("openai_api_key")

        assert can_decrypt is True  # Plaintext is "decryptable"


class TestClearInvalidKeys:
    """Tests for clearing invalid encrypted keys."""

    @pytest.mark.asyncio
    async def test_clear_invalid_keys_success(self, temp_db, temp_key_file):
        """Test clearing keys that cannot be decrypted."""
        # Encrypt with one key
        enc_service = EncryptionService(key_file_path=temp_key_file)
        service = SettingsService(temp_db, encryption_service=enc_service)
        await service._ensure_initialized()
        await service.set("openai_api_key", "sk-test123")
        await service.set("anthropic_api_key", "sk-ant-test456")

        # Change encryption key
        temp_key_file.unlink()
        new_enc_service = EncryptionService(key_file_path=temp_key_file)
        service._encryption_service = new_enc_service

        result = await service.clear_invalid_encrypted_keys()

        assert result["success"] is True
        assert len(result["cleared"]) == 2
        assert "openai_api_key" in result["cleared"]
        assert "anthropic_api_key" in result["cleared"]

        # Verify keys are gone
        assert await service.get("openai_api_key") == ""
        assert await service.get("anthropic_api_key") == ""

    @pytest.mark.asyncio
    async def test_clear_invalid_keeps_decryptable(self, settings_service):
        """Test that decryptable keys are not cleared."""
        await settings_service.set("openai_api_key", "sk-test123")

        result = await settings_service.clear_invalid_encrypted_keys()

        assert result["success"] is True
        assert len(result["cleared"]) == 0
        assert "openai_api_key" in result["skipped"]

        # Verify key is still there
        assert await settings_service.get("openai_api_key") == "sk-test123"

    @pytest.mark.asyncio
    async def test_clear_invalid_skips_plaintext(self, temp_db):
        """Test that plaintext keys are skipped."""
        service = SettingsService(temp_db, encryption_service=None)
        await service._ensure_initialized()

        # Insert plaintext key
        async with service._get_connection() as db:
            await db.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                ("openai_api_key", "sk-plaintext123")
            )
            await db.commit()

        # Enable encryption with a separate key file
        enc_dir = tempfile.mkdtemp()
        enc_service = EncryptionService(key_file_path=Path(enc_dir) / ".key_salt")
        service._encryption_service = enc_service
        service._encryption_available = True

        result = await service.clear_invalid_encrypted_keys()

        assert result["success"] is True
        assert "openai_api_key" in result["skipped"]

    @pytest.mark.asyncio
    async def test_clear_invalid_clears_error_tracking(self, temp_db, temp_key_file):
        """Test that clearing keys removes them from error tracking."""
        # Encrypt with one key
        enc_service = EncryptionService(key_file_path=temp_key_file)
        service = SettingsService(temp_db, encryption_service=enc_service)
        await service._ensure_initialized()
        await service.set("openai_api_key", "sk-test123")

        # Change encryption key and trigger error
        temp_key_file.unlink()
        new_enc_service = EncryptionService(key_file_path=temp_key_file)
        service._encryption_service = new_enc_service

        # Trigger decryption error (adds to tracking)
        await service.get("openai_api_key")
        assert "openai_api_key" in SettingsService._decryption_errors

        # Clear invalid
        await service.clear_invalid_encrypted_keys()

        # Error should be cleared
        assert "openai_api_key" not in SettingsService._decryption_errors


class TestReencryptKeys:
    """Tests for re-encrypting keys with current key."""

    @pytest.mark.asyncio
    async def test_reencrypt_success(self, temp_db, temp_key_file):
        """Test re-encrypting keys with current key."""
        # Encrypt with one key
        enc_service = EncryptionService(key_file_path=temp_key_file)
        service = SettingsService(temp_db, encryption_service=enc_service)
        await service._ensure_initialized()
        await service.set("openai_api_key", "sk-test123")

        # Re-encrypt
        result = await service.reencrypt_with_current_key()

        assert result["success"] is True
        assert "openai_api_key" in result["reencrypted"]
        assert len(result["failed"]) == 0

        # Verify still decryptable
        assert await service.get("openai_api_key") == "sk-test123"

    @pytest.mark.asyncio
    async def test_reencrypt_plaintext_to_encrypted(self, temp_db, temp_key_file):
        """Test re-encrypt converts plaintext to encrypted."""
        # Create service without encryption, insert plaintext
        service = SettingsService(temp_db, encryption_service=None)
        await service._ensure_initialized()
        async with service._get_connection() as db:
            await db.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                ("openai_api_key", "sk-plaintext123")
            )
            await db.commit()

        # Enable encryption and re-encrypt
        enc_service = EncryptionService(key_file_path=temp_key_file)
        service._encryption_service = enc_service
        service._encryption_available = True

        result = await service.reencrypt_with_current_key()

        assert result["success"] is True
        assert "openai_api_key" in result["reencrypted"]

        # Verify now encrypted and decryptable
        decrypted = await service.get("openai_api_key")
        assert decrypted == "sk-plaintext123"

        # Verify it's actually encrypted in DB
        is_enc = await service.is_key_encrypted("openai_api_key")
        assert is_enc is True

    @pytest.mark.asyncio
    async def test_reencrypt_skips_empty_keys(self, settings_service):
        """Test that empty keys are skipped."""
        result = await settings_service.reencrypt_with_current_key()

        assert result["success"] is True
        # All sensitive keys should be skipped (none set)
        assert len(result["skipped"]) == len(SENSITIVE_KEYS)

    @pytest.mark.asyncio
    async def test_reencrypt_clears_error_tracking(self, settings_service):
        """Test that successful re-encrypt clears error tracking."""
        # Set a key
        await settings_service.set("openai_api_key", "sk-test123")

        # Manually add an error to tracking (simulating a previous error)
        SettingsService._decryption_errors["openai_api_key"] = "test_error"

        # Re-encrypt - should clear the error
        result = await settings_service.reencrypt_with_current_key()

        assert result["success"] is True
        # Error should be cleared (either successful reencrypt or failed attempt clears it)
        assert "openai_api_key" not in SettingsService._decryption_errors


class TestDecryptionErrorTracking:
    """Tests for decryption error deduplication."""

    @pytest.mark.asyncio
    async def test_error_logged_once_per_key(self, temp_db, temp_key_file, caplog):
        """Test that decryption errors are only logged once per key."""
        # Encrypt with one key
        enc_service = EncryptionService(key_file_path=temp_key_file)
        service = SettingsService(temp_db, encryption_service=enc_service)
        await service._ensure_initialized()
        await service.set("openai_api_key", "sk-test123")

        # Change key
        temp_key_file.unlink()
        new_enc_service = EncryptionService(key_file_path=temp_key_file)
        service._encryption_service = new_enc_service

        # Clear error tracking to ensure clean state
        SettingsService._decryption_errors.clear()

        # First call - should log
        import logging
        caplog.set_level(logging.ERROR)
        caplog.clear()

        await service.get("openai_api_key")
        error_count_1 = len([r for r in caplog.records if "Decryption failed" in r.message])

        # Second call - should NOT log again
        caplog.clear()
        await service.get("openai_api_key")
        error_count_2 = len([r for r in caplog.records if "Decryption failed" in r.message])

        assert error_count_1 == 1
        assert error_count_2 == 0

    @pytest.mark.asyncio
    async def test_error_tracking_cleared_on_success(self, temp_db, temp_key_file):
        """Test that error tracking is cleared when decryption succeeds."""
        # Encrypt with one key
        enc_service = EncryptionService(key_file_path=temp_key_file)
        service = SettingsService(temp_db, encryption_service=enc_service)
        await service._ensure_initialized()
        await service.set("openai_api_key", "sk-test123")

        # Save the salt
        original_salt = temp_key_file.read_bytes()

        # Change key and trigger error
        temp_key_file.unlink()
        new_enc_service = EncryptionService(key_file_path=temp_key_file)
        service._encryption_service = new_enc_service
        await service.get("openai_api_key")
        assert "openai_api_key" in SettingsService._decryption_errors

        # Restore key and decrypt successfully
        temp_key_file.write_bytes(original_salt)
        restored_enc = EncryptionService(key_file_path=temp_key_file)
        service._encryption_service = restored_enc
        await service.get("openai_api_key")

        # Error should be cleared
        assert "openai_api_key" not in SettingsService._decryption_errors


class TestEncryptionStatusEnhanced:
    """Tests for enhanced encryption status with decryptability."""

    @pytest.mark.asyncio
    async def test_status_includes_decryptability(self, settings_service):
        """Test that status includes can_decrypt field."""
        await settings_service.set("openai_api_key", "sk-test123")

        status = await settings_service.get_encryption_status()

        assert "keys" in status
        assert "openai_api_key" in status["keys"]
        key_info = status["keys"]["openai_api_key"]
        assert "can_decrypt" in key_info
        assert key_info["can_decrypt"] is True

    @pytest.mark.asyncio
    async def test_status_includes_all_decryptable(self, settings_service):
        """Test that status includes all_decryptable field."""
        await settings_service.set("openai_api_key", "sk-test123")

        status = await settings_service.get_encryption_status()

        assert "all_decryptable" in status
        assert status["all_decryptable"] is True

    @pytest.mark.asyncio
    async def test_status_shows_errors(self, temp_db, temp_key_file):
        """Test that status includes decryption errors."""
        # Encrypt and trigger error
        enc_service = EncryptionService(key_file_path=temp_key_file)
        service = SettingsService(temp_db, encryption_service=enc_service)
        await service._ensure_initialized()
        await service.set("openai_api_key", "sk-test123")

        temp_key_file.unlink()
        new_enc_service = EncryptionService(key_file_path=temp_key_file)
        service._encryption_service = new_enc_service
        await service.get("openai_api_key")  # Trigger error

        status = await service.get_encryption_status()

        assert "errors" in status
        assert "openai_api_key" in status["errors"]
