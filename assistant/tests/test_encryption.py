"""Tests for encryption service."""
import base64
import os
import pytest
import secrets
import tempfile
from pathlib import Path

from server.services.encryption import (
    EncryptionService,
    EncryptedValue,
    is_encrypted,
    get_encryption_service,
    init_encryption_service,
    ENCRYPTED_PREFIX,
    KEY_SIZE,
    NONCE_SIZE,
    SALT_SIZE,
    ENCRYPTION_VERSION,
    CRYPTOGRAPHY_AVAILABLE
)


# Skip all tests if cryptography is not available
pytestmark = pytest.mark.skipif(
    not CRYPTOGRAPHY_AVAILABLE,
    reason="cryptography library not installed"
)


class TestEncryptedValue:
    """Tests for EncryptedValue serialization."""

    def test_to_string_format(self):
        """Test that to_string produces correct format."""
        salt = secrets.token_bytes(SALT_SIZE)
        nonce = secrets.token_bytes(NONCE_SIZE)
        ciphertext = b"encrypted data here"

        ev = EncryptedValue(
            version=ENCRYPTION_VERSION,
            salt=salt,
            nonce=nonce,
            ciphertext=ciphertext
        )

        result = ev.to_string()

        assert result.startswith(ENCRYPTED_PREFIX)
        parts = result[len(ENCRYPTED_PREFIX):].split(":")
        assert len(parts) == 3

        # Verify base64 encoding
        assert base64.b64decode(parts[0]) == salt
        assert base64.b64decode(parts[1]) == nonce
        assert base64.b64decode(parts[2]) == ciphertext

    def test_from_string_roundtrip(self):
        """Test that from_string reverses to_string."""
        salt = secrets.token_bytes(SALT_SIZE)
        nonce = secrets.token_bytes(NONCE_SIZE)
        ciphertext = b"test data"

        original = EncryptedValue(
            version=ENCRYPTION_VERSION,
            salt=salt,
            nonce=nonce,
            ciphertext=ciphertext
        )

        serialized = original.to_string()
        parsed = EncryptedValue.from_string(serialized)

        assert parsed.version == original.version
        assert parsed.salt == original.salt
        assert parsed.nonce == original.nonce
        assert parsed.ciphertext == original.ciphertext

    def test_from_string_invalid_prefix(self):
        """Test that from_string rejects invalid prefix."""
        with pytest.raises(ValueError, match="Invalid encrypted value format"):
            EncryptedValue.from_string("INVALID:v1:abc:def:ghi")

    def test_from_string_invalid_parts(self):
        """Test that from_string rejects wrong number of parts."""
        with pytest.raises(ValueError, match="Invalid encrypted value format"):
            EncryptedValue.from_string(f"{ENCRYPTED_PREFIX}only:two")


class TestIsEncrypted:
    """Tests for is_encrypted helper."""

    def test_encrypted_value(self):
        """Test that encrypted values are detected."""
        encrypted = f"{ENCRYPTED_PREFIX}abc:def:ghi"
        assert is_encrypted(encrypted) is True

    def test_plaintext_value(self):
        """Test that plaintext values are not detected as encrypted."""
        assert is_encrypted("sk-1234567890abcdef") is False
        assert is_encrypted("regular text") is False

    def test_empty_value(self):
        """Test that empty values return False."""
        assert is_encrypted("") is False
        assert is_encrypted(None) is False


class TestEncryptionService:
    """Tests for EncryptionService."""

    @pytest.fixture
    def temp_key_file(self):
        """Create a temporary key file path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / ".encryption_key_salt"

    @pytest.fixture
    def encryption_service(self, temp_key_file):
        """Create an encryption service with temporary key file."""
        return EncryptionService(key_file_path=temp_key_file)

    def test_encrypt_returns_encrypted_format(self, encryption_service):
        """Test that encrypt returns properly formatted string."""
        plaintext = "test-api-key-12345"
        result = encryption_service.encrypt(plaintext)

        assert is_encrypted(result)
        assert result.startswith(ENCRYPTED_PREFIX)

    def test_encrypt_decrypt_roundtrip(self, encryption_service):
        """Test that decrypt reverses encrypt."""
        plaintext = "sk-1234567890abcdefghijklmnop"
        encrypted = encryption_service.encrypt(plaintext)
        decrypted = encryption_service.decrypt(encrypted)

        assert decrypted == plaintext

    def test_encrypt_empty_string(self, encryption_service):
        """Test that empty strings are returned as-is."""
        assert encryption_service.encrypt("") == ""

    def test_decrypt_empty_string(self, encryption_service):
        """Test that empty strings are returned as-is."""
        assert encryption_service.decrypt("") == ""

    def test_encrypt_already_encrypted(self, encryption_service):
        """Test that already encrypted values are returned as-is."""
        plaintext = "test-key"
        encrypted = encryption_service.encrypt(plaintext)
        double_encrypted = encryption_service.encrypt(encrypted)

        assert encrypted == double_encrypted

    def test_decrypt_plaintext(self, encryption_service):
        """Test that plaintext values are returned as-is (for migration)."""
        plaintext = "sk-plaintext-key"
        result = encryption_service.decrypt(plaintext)
        assert result == plaintext

    def test_each_encryption_unique(self, encryption_service):
        """Test that encrypting same value twice produces different ciphertext."""
        plaintext = "same-api-key"
        encrypted1 = encryption_service.encrypt(plaintext)
        encrypted2 = encryption_service.encrypt(plaintext)

        # Both should decrypt to same value
        assert encryption_service.decrypt(encrypted1) == plaintext
        assert encryption_service.decrypt(encrypted2) == plaintext

        # But ciphertext should be different (due to random nonce/salt)
        assert encrypted1 != encrypted2

    def test_unicode_support(self, encryption_service):
        """Test encryption of unicode strings."""
        plaintext = "api-key-with-unicode-\u4e2d\u6587-\u00e9\u00e0\u00fc"
        encrypted = encryption_service.encrypt(plaintext)
        decrypted = encryption_service.decrypt(encrypted)

        assert decrypted == plaintext

    def test_long_value_support(self, encryption_service):
        """Test encryption of long values."""
        plaintext = "x" * 10000  # 10KB of data
        encrypted = encryption_service.encrypt(plaintext)
        decrypted = encryption_service.decrypt(encrypted)

        assert decrypted == plaintext

    def test_key_file_persistence(self, temp_key_file):
        """Test that key file is created and persists."""
        # Create first service
        service1 = EncryptionService(key_file_path=temp_key_file)
        encrypted = service1.encrypt("test-key")

        # Verify key file was created
        assert temp_key_file.exists()
        assert len(temp_key_file.read_bytes()) == SALT_SIZE

        # Create second service with same key file
        service2 = EncryptionService(key_file_path=temp_key_file)
        decrypted = service2.decrypt(encrypted)

        assert decrypted == "test-key"

    def test_different_key_files_incompatible(self, temp_key_file):
        """Test that different key files produce different keys."""
        service1 = EncryptionService(key_file_path=temp_key_file)
        encrypted = service1.encrypt("test-key")

        # Create another service with different key file
        with tempfile.TemporaryDirectory() as tmpdir2:
            other_key_file = Path(tmpdir2) / ".other_key"
            service2 = EncryptionService(key_file_path=other_key_file)

            # Decryption should fail with wrong key
            with pytest.raises(Exception):  # cryptography raises InvalidTag
                service2.decrypt(encrypted)


class TestEncryptionServiceFromPassphrase:
    """Tests for passphrase-based encryption."""

    def test_from_passphrase_basic(self):
        """Test basic passphrase encryption."""
        passphrase = "my-secret-passphrase"
        salt = secrets.token_bytes(SALT_SIZE)

        service = EncryptionService.from_passphrase(passphrase, salt)
        encrypted = service.encrypt("test-data")
        decrypted = service.decrypt(encrypted)

        assert decrypted == "test-data"

    def test_from_passphrase_reproducible(self):
        """Test that same passphrase and salt produce same key."""
        passphrase = "reproducible-pass"
        salt = secrets.token_bytes(SALT_SIZE)

        service1 = EncryptionService.from_passphrase(passphrase, salt)
        encrypted = service1.encrypt("test-data")

        service2 = EncryptionService.from_passphrase(passphrase, salt)
        decrypted = service2.decrypt(encrypted)

        assert decrypted == "test-data"

    def test_from_passphrase_different_salts(self):
        """Test that different salts produce different keys."""
        passphrase = "same-pass"
        salt1 = secrets.token_bytes(SALT_SIZE)
        salt2 = secrets.token_bytes(SALT_SIZE)

        service1 = EncryptionService.from_passphrase(passphrase, salt1)
        encrypted = service1.encrypt("test-data")

        service2 = EncryptionService.from_passphrase(passphrase, salt2)

        # Decryption should fail with different salt
        with pytest.raises(Exception):
            service2.decrypt(encrypted)


class TestEncryptionServiceFromEnvironment:
    """Tests for environment-based encryption."""

    def test_from_environment_valid(self):
        """Test with valid environment key."""
        key = secrets.token_bytes(KEY_SIZE)
        env_var = "TEST_ENCRYPTION_KEY"

        try:
            os.environ[env_var] = base64.b64encode(key).decode()
            service = EncryptionService.from_environment(env_var)

            encrypted = service.encrypt("test")
            assert service.decrypt(encrypted) == "test"
        finally:
            os.environ.pop(env_var, None)

    def test_from_environment_not_set(self):
        """Test with unset environment variable."""
        with pytest.raises(ValueError, match="not set"):
            EncryptionService.from_environment("NONEXISTENT_VAR_12345")

    def test_from_environment_invalid_base64(self):
        """Test with invalid base64 in environment."""
        env_var = "TEST_BAD_KEY"
        try:
            os.environ[env_var] = "not-valid-base64!!!"
            with pytest.raises(ValueError, match="Invalid encryption key"):
                EncryptionService.from_environment(env_var)
        finally:
            os.environ.pop(env_var, None)

    def test_from_environment_wrong_size(self):
        """Test with wrong key size."""
        env_var = "TEST_SHORT_KEY"
        try:
            os.environ[env_var] = base64.b64encode(b"short").decode()
            with pytest.raises(ValueError, match="32 bytes"):
                EncryptionService.from_environment(env_var)
        finally:
            os.environ.pop(env_var, None)


class TestKeyRotation:
    """Tests for key rotation."""

    @pytest.fixture
    def temp_key_file(self):
        """Create a temporary key file path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / ".encryption_key_salt"

    def test_rotate_key(self, temp_key_file):
        """Test key rotation with new master key."""
        # Create original service
        old_service = EncryptionService(key_file_path=temp_key_file)

        # Encrypt some values
        values = {
            "key1": old_service.encrypt("value1"),
            "key2": old_service.encrypt("value2"),
            "key3": old_service.encrypt("value3"),
        }

        # Create new master key
        new_master_key = secrets.token_bytes(KEY_SIZE)

        # Rotate keys
        rotated = old_service.rotate_key(values, new_master_key)

        # Verify with new service
        new_service = EncryptionService(master_key=new_master_key)

        assert new_service.decrypt(rotated["key1"]) == "value1"
        assert new_service.decrypt(rotated["key2"]) == "value2"
        assert new_service.decrypt(rotated["key3"]) == "value3"

    def test_rotate_key_empty_dict(self, temp_key_file):
        """Test key rotation with empty dict."""
        service = EncryptionService(key_file_path=temp_key_file)
        new_key = secrets.token_bytes(KEY_SIZE)

        rotated = service.rotate_key({}, new_key)
        assert rotated == {}


class TestSingleton:
    """Tests for singleton pattern."""

    @pytest.fixture
    def temp_key_file(self):
        """Create a temporary key file path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / ".encryption_key_salt"

    def test_init_encryption_service(self, temp_key_file):
        """Test singleton initialization."""
        # Reset singleton
        import server.services.encryption as enc_module
        enc_module._encryption_service = None

        service = init_encryption_service(temp_key_file)
        assert service is not None

        # Get should return same instance
        same_service = get_encryption_service()
        assert same_service is service

        # Reset for other tests
        enc_module._encryption_service = None


class TestEncryptionServiceMachineKey:
    """Tests for machine-specific key derivation."""

    @pytest.fixture
    def temp_key_file(self):
        """Create a temporary key file path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / ".encryption_key_salt"

    def test_machine_key_consistency(self, temp_key_file):
        """Test that machine key remains consistent across instantiations."""
        # Create first service and encrypt
        service1 = EncryptionService(key_file_path=temp_key_file)
        encrypted = service1.encrypt("test-value")

        # Create second service (should use same machine key)
        service2 = EncryptionService(key_file_path=temp_key_file)
        decrypted = service2.decrypt(encrypted)

        assert decrypted == "test-value"

    def test_machine_identifier_not_empty(self, temp_key_file):
        """Test that machine identifier produces non-empty result."""
        service = EncryptionService(key_file_path=temp_key_file)
        machine_id = service._get_machine_identifier()

        assert machine_id is not None
        assert len(machine_id) > 0
