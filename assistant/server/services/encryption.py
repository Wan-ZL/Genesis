"""Encryption service for securing sensitive data at rest.

Uses AES-256-GCM for authenticated encryption with machine-derived keys.
"""
import base64
import hashlib
import os
import platform
import secrets
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

# Use cryptography library for AES-GCM
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False


# Constants
KEY_SIZE = 32  # 256 bits for AES-256
NONCE_SIZE = 12  # 96 bits recommended for GCM
SALT_SIZE = 16  # 128 bits for salt
PBKDF2_ITERATIONS = 480000  # OWASP 2023 recommendation for SHA256

# Encryption format version for future compatibility
ENCRYPTION_VERSION = 1

# Prefix to identify encrypted values
ENCRYPTED_PREFIX = "ENC:v1:"


@dataclass
class EncryptedValue:
    """Container for encrypted data with metadata."""
    version: int
    salt: bytes
    nonce: bytes
    ciphertext: bytes

    def to_string(self) -> str:
        """Serialize to a storable string format."""
        # Format: ENC:v1:base64(salt):base64(nonce):base64(ciphertext)
        return (
            f"{ENCRYPTED_PREFIX}"
            f"{base64.b64encode(self.salt).decode()}:"
            f"{base64.b64encode(self.nonce).decode()}:"
            f"{base64.b64encode(self.ciphertext).decode()}"
        )

    @classmethod
    def from_string(cls, value: str) -> "EncryptedValue":
        """Parse from stored string format."""
        if not value.startswith(ENCRYPTED_PREFIX):
            raise ValueError("Invalid encrypted value format")

        parts = value[len(ENCRYPTED_PREFIX):].split(":")
        if len(parts) != 3:
            raise ValueError("Invalid encrypted value format")

        return cls(
            version=ENCRYPTION_VERSION,
            salt=base64.b64decode(parts[0]),
            nonce=base64.b64decode(parts[1]),
            ciphertext=base64.b64decode(parts[2])
        )


def is_encrypted(value: str) -> bool:
    """Check if a value is already encrypted."""
    return value.startswith(ENCRYPTED_PREFIX) if value else False


class EncryptionService:
    """Service for encrypting and decrypting sensitive data.

    Uses AES-256-GCM with PBKDF2 key derivation from a master key.
    The master key can be derived from:
    1. Machine-specific identifiers (default, for single-machine deployment)
    2. A user-provided passphrase (for portable backups)
    3. An environment variable (for containerized deployments)
    """

    def __init__(
        self,
        master_key: Optional[bytes] = None,
        key_file_path: Optional[Path] = None
    ):
        """Initialize encryption service.

        Args:
            master_key: Optional pre-derived master key (32 bytes).
                       If not provided, derives from machine identifier.
            key_file_path: Optional path to store/load the machine key salt.
        """
        if not CRYPTOGRAPHY_AVAILABLE:
            raise ImportError(
                "cryptography library required for encryption. "
                "Install with: pip install cryptography"
            )

        self._key_file_path = key_file_path
        self._master_key = master_key or self._derive_machine_key()

    def _get_machine_identifier(self) -> str:
        """Get a stable machine-specific identifier.

        Combines multiple sources for stability across reboots:
        - Platform node (hostname + network)
        - Machine UUID (if available)
        """
        parts = []

        # Hostname
        parts.append(platform.node())

        # Try to get machine UUID
        try:
            if platform.system() == "Darwin":
                # macOS: use hardware UUID
                import subprocess
                result = subprocess.run(
                    ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                    capture_output=True,
                    text=True
                )
                for line in result.stdout.split("\n"):
                    if "IOPlatformUUID" in line:
                        parts.append(line.split('"')[-2])
                        break
            elif platform.system() == "Linux":
                # Linux: try machine-id
                machine_id_path = Path("/etc/machine-id")
                if machine_id_path.exists():
                    parts.append(machine_id_path.read_text().strip())
        except Exception:
            pass

        # Fallback to uuid.getnode() which uses MAC address
        parts.append(str(uuid.getnode()))

        return ":".join(parts)

    def _derive_machine_key(self) -> bytes:
        """Derive a master key from machine-specific identifiers.

        Uses a salt stored in the key file to ensure consistency.
        """
        # Get or create machine salt
        machine_salt = self._get_or_create_machine_salt()

        # Derive key from machine identifier
        machine_id = self._get_machine_identifier().encode()

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=KEY_SIZE,
            salt=machine_salt,
            iterations=PBKDF2_ITERATIONS,
        )

        return kdf.derive(machine_id)

    def _get_or_create_machine_salt(self) -> bytes:
        """Get existing machine salt or create a new one.

        The salt is stored in a file to ensure the same key is derived
        across restarts. If the file is lost, encrypted data cannot
        be recovered unless a backup was made.
        """
        if self._key_file_path and self._key_file_path.exists():
            return self._key_file_path.read_bytes()

        # Generate new salt
        salt = secrets.token_bytes(SALT_SIZE)

        # Store it if path is provided
        if self._key_file_path:
            self._key_file_path.parent.mkdir(parents=True, exist_ok=True)
            self._key_file_path.write_bytes(salt)

        return salt

    def _derive_encryption_key(self, salt: bytes) -> bytes:
        """Derive an encryption key from master key using the given salt.

        Each encrypted value uses a unique salt for key derivation,
        providing additional security.
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=KEY_SIZE,
            salt=salt,
            iterations=PBKDF2_ITERATIONS,
        )
        return kdf.derive(self._master_key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string.

        Args:
            plaintext: The string to encrypt.

        Returns:
            Encrypted value as a string suitable for storage.
        """
        if not plaintext:
            return plaintext

        # Already encrypted? Return as-is
        if is_encrypted(plaintext):
            return plaintext

        # Generate random salt and nonce
        salt = secrets.token_bytes(SALT_SIZE)
        nonce = secrets.token_bytes(NONCE_SIZE)

        # Derive encryption key
        key = self._derive_encryption_key(salt)

        # Encrypt using AES-256-GCM
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

        # Package and return
        encrypted = EncryptedValue(
            version=ENCRYPTION_VERSION,
            salt=salt,
            nonce=nonce,
            ciphertext=ciphertext
        )
        return encrypted.to_string()

    def decrypt(self, encrypted_value: str) -> str:
        """Decrypt an encrypted string.

        Args:
            encrypted_value: The encrypted string from encrypt().

        Returns:
            Original plaintext string.

        Raises:
            ValueError: If the value is not properly encrypted.
            Exception: If decryption fails (wrong key, tampered data).
        """
        if not encrypted_value:
            return encrypted_value

        # Not encrypted? Return as-is (for migration compatibility)
        if not is_encrypted(encrypted_value):
            return encrypted_value

        # Parse encrypted value
        encrypted = EncryptedValue.from_string(encrypted_value)

        # Derive the same encryption key
        key = self._derive_encryption_key(encrypted.salt)

        # Decrypt using AES-256-GCM
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(
            encrypted.nonce,
            encrypted.ciphertext,
            None
        )

        return plaintext.decode("utf-8")

    def rotate_key(
        self,
        encrypted_values: dict[str, str],
        new_master_key: bytes
    ) -> dict[str, str]:
        """Re-encrypt values with a new master key.

        Args:
            encrypted_values: Dict of key -> encrypted_value
            new_master_key: The new master key to use

        Returns:
            Dict of key -> newly_encrypted_value
        """
        result = {}
        new_service = EncryptionService(master_key=new_master_key)

        for key, encrypted_value in encrypted_values.items():
            # Decrypt with old key
            plaintext = self.decrypt(encrypted_value)
            # Re-encrypt with new key
            result[key] = new_service.encrypt(plaintext)

        return result

    @classmethod
    def from_passphrase(cls, passphrase: str, salt: Optional[bytes] = None) -> "EncryptionService":
        """Create an encryption service from a user passphrase.

        Useful for creating portable encrypted backups that can be
        decrypted on any machine.

        Args:
            passphrase: User-provided passphrase
            salt: Optional salt (generates random if not provided)

        Returns:
            EncryptionService configured with passphrase-derived key
        """
        if salt is None:
            salt = secrets.token_bytes(SALT_SIZE)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=KEY_SIZE,
            salt=salt,
            iterations=PBKDF2_ITERATIONS,
        )

        master_key = kdf.derive(passphrase.encode("utf-8"))
        return cls(master_key=master_key)

    @classmethod
    def from_environment(cls, env_var: str = "ASSISTANT_ENCRYPTION_KEY") -> "EncryptionService":
        """Create an encryption service from an environment variable.

        Useful for containerized deployments where keys are managed
        externally (e.g., Kubernetes secrets).

        Args:
            env_var: Name of environment variable containing base64-encoded key

        Returns:
            EncryptionService configured with the key from environment

        Raises:
            ValueError: If environment variable is not set or invalid
        """
        key_b64 = os.environ.get(env_var)
        if not key_b64:
            raise ValueError(f"Environment variable {env_var} not set")

        try:
            key = base64.b64decode(key_b64)
            if len(key) != KEY_SIZE:
                raise ValueError(f"Key must be {KEY_SIZE} bytes")
            return cls(master_key=key)
        except Exception as e:
            raise ValueError(f"Invalid encryption key in {env_var}: {e}")


# Singleton instance for use throughout the application
_encryption_service: Optional[EncryptionService] = None


def get_encryption_service(key_file_path: Optional[Path] = None) -> EncryptionService:
    """Get or create the singleton encryption service.

    Args:
        key_file_path: Path to store machine key salt.
                      Only used on first call to initialize.

    Returns:
        The encryption service instance.
    """
    global _encryption_service

    if _encryption_service is None:
        if not CRYPTOGRAPHY_AVAILABLE:
            raise ImportError(
                "cryptography library required for encryption. "
                "Install with: pip install cryptography"
            )
        _encryption_service = EncryptionService(key_file_path=key_file_path)

    return _encryption_service


def init_encryption_service(key_file_path: Path) -> EncryptionService:
    """Initialize the encryption service with a key file path.

    Args:
        key_file_path: Path to store machine key salt.

    Returns:
        The initialized encryption service.
    """
    global _encryption_service
    _encryption_service = EncryptionService(key_file_path=key_file_path)
    return _encryption_service
