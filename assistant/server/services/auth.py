"""Authentication service for JWT-based session management."""
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple

import aiosqlite
import bcrypt
import jwt

import config


class AuthConfig:
    """Authentication configuration from environment variables.

    All config values are read dynamically from environment variables
    to support runtime changes (especially important for testing).
    """

    # JWT settings (constant)
    ALGORITHM = "HS256"

    @staticmethod
    def is_enabled() -> bool:
        """Check if authentication is enabled (reads env var each time)."""
        return os.getenv("ASSISTANT_AUTH_ENABLED", "false").lower() == "true"

    @staticmethod
    def get_username() -> str:
        """Get auth username from environment."""
        return os.getenv("ASSISTANT_AUTH_USERNAME", "admin")

    @staticmethod
    def get_password_hash() -> str:
        """Get password hash from environment."""
        return os.getenv("ASSISTANT_AUTH_PASSWORD_HASH", "")

    @staticmethod
    def get_secret_key() -> str:
        """Get JWT secret key from environment."""
        return os.getenv("ASSISTANT_JWT_SECRET", "")

    @staticmethod
    def get_token_expire_minutes() -> int:
        """Get token expiration time in minutes."""
        return int(os.getenv("ASSISTANT_TOKEN_EXPIRE_MINUTES", "60"))

    @staticmethod
    def get_refresh_token_expire_days() -> int:
        """Get refresh token expiration time in days."""
        return int(os.getenv("ASSISTANT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))

    @staticmethod
    def get_max_login_attempts() -> int:
        """Get maximum login attempts before lockout."""
        return int(os.getenv("ASSISTANT_MAX_LOGIN_ATTEMPTS", "5"))

    @staticmethod
    def get_lockout_minutes() -> int:
        """Get lockout duration in minutes."""
        return int(os.getenv("ASSISTANT_LOGIN_LOCKOUT_MINUTES", "15"))

    # Aliases for backward compatibility (read once at access time)
    # These are properties that delegate to the static methods
    ENABLED = property(lambda self: AuthConfig.is_enabled())
    USERNAME = property(lambda self: AuthConfig.get_username())
    PASSWORD_HASH = property(lambda self: AuthConfig.get_password_hash())
    SECRET_KEY = property(lambda self: AuthConfig.get_secret_key())
    TOKEN_EXPIRE_MINUTES = property(lambda self: AuthConfig.get_token_expire_minutes())
    REFRESH_TOKEN_EXPIRE_DAYS = property(lambda self: AuthConfig.get_refresh_token_expire_days())
    MAX_LOGIN_ATTEMPTS = property(lambda self: AuthConfig.get_max_login_attempts())
    LOGIN_LOCKOUT_MINUTES = property(lambda self: AuthConfig.get_lockout_minutes())

    @classmethod
    def generate_secret_key(cls) -> str:
        """Generate a secure random secret key."""
        return secrets.token_urlsafe(32)

    @classmethod
    def hash_password(cls, password: str) -> str:
        """Hash a password using bcrypt."""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    @classmethod
    def verify_password(cls, password: str, hashed: str) -> bool:
        """Verify a password against its hash."""
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


class AuthService:
    """Service for authentication and session management."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or config.DATABASE_PATH
        self._initialized = False
        self._jwt_secret: Optional[str] = None

    async def _ensure_initialized(self):
        """Ensure database tables exist."""
        if self._initialized:
            return

        async with aiosqlite.connect(self.db_path) as db:
            # Table for storing auth configuration
            await db.execute("""
                CREATE TABLE IF NOT EXISTS auth_config (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP
                )
            """)

            # Table for login attempts (rate limiting)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS login_attempts (
                    ip_address TEXT,
                    timestamp TIMESTAMP,
                    success INTEGER
                )
            """)

            # Table for active sessions (for logout/revocation)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS active_sessions (
                    token_id TEXT PRIMARY KEY,
                    user TEXT,
                    created_at TIMESTAMP,
                    expires_at TIMESTAMP,
                    ip_address TEXT,
                    user_agent TEXT,
                    revoked INTEGER DEFAULT 0
                )
            """)

            # Create indexes
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_login_attempts_ip
                ON login_attempts(ip_address, timestamp)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_expires
                ON active_sessions(expires_at)
            """)

            await db.commit()

        self._initialized = True

    async def _get_jwt_secret(self) -> str:
        """Get or generate JWT secret key."""
        if self._jwt_secret:
            return self._jwt_secret

        # First check environment
        env_secret = AuthConfig.get_secret_key()
        if env_secret:
            self._jwt_secret = env_secret
            return self._jwt_secret

        # Then check database
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT value FROM auth_config WHERE key = 'jwt_secret'"
            )
            row = await cursor.fetchone()
            if row:
                self._jwt_secret = row[0]
                return self._jwt_secret

        # Generate new secret and store it
        self._jwt_secret = AuthConfig.generate_secret_key()
        await self._set_auth_config("jwt_secret", self._jwt_secret)
        return self._jwt_secret

    async def _set_auth_config(self, key: str, value: str):
        """Set auth configuration in database."""
        await self._ensure_initialized()
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO auth_config (key, value, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?""",
                (key, value, now, value, now)
            )
            await db.commit()

    async def _get_auth_config(self, key: str) -> Optional[str]:
        """Get auth configuration from database."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT value FROM auth_config WHERE key = ?", (key,)
            )
            row = await cursor.fetchone()
            return row[0] if row else None

    def is_auth_enabled(self) -> bool:
        """Check if authentication is enabled."""
        return AuthConfig.is_enabled()

    async def get_password_hash(self) -> Optional[str]:
        """Get the stored password hash."""
        # First check environment
        env_hash = AuthConfig.get_password_hash()
        if env_hash:
            return env_hash

        # Then check database
        return await self._get_auth_config("password_hash")

    async def set_password(self, password: str):
        """Set the password (stores hash only)."""
        password_hash = AuthConfig.hash_password(password)
        await self._set_auth_config("password_hash", password_hash)

    async def check_rate_limit(self, ip_address: str) -> Tuple[bool, int]:
        """Check if IP is rate limited. Returns (allowed, seconds_remaining)."""
        await self._ensure_initialized()

        cutoff_time = datetime.now(timezone.utc) - timedelta(
            minutes=AuthConfig.get_lockout_minutes()
        )

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """SELECT COUNT(*) FROM login_attempts
                   WHERE ip_address = ?
                   AND timestamp > ?
                   AND success = 0""",
                (ip_address, cutoff_time.isoformat())
            )
            row = await cursor.fetchone()
            failed_attempts = row[0] if row else 0

            if failed_attempts >= AuthConfig.get_max_login_attempts():
                # Calculate remaining lockout time
                cursor = await db.execute(
                    """SELECT MAX(timestamp) FROM login_attempts
                       WHERE ip_address = ? AND success = 0""",
                    (ip_address,)
                )
                row = await cursor.fetchone()
                if row and row[0]:
                    last_attempt = datetime.fromisoformat(row[0])
                    if last_attempt.tzinfo is None:
                        last_attempt = last_attempt.replace(tzinfo=timezone.utc)
                    unlock_time = last_attempt + timedelta(
                        minutes=AuthConfig.get_lockout_minutes()
                    )
                    remaining = (unlock_time - datetime.now(timezone.utc)).total_seconds()
                    return False, max(0, int(remaining))
                return False, AuthConfig.get_lockout_minutes() * 60

        return True, 0

    async def record_login_attempt(self, ip_address: str, success: bool):
        """Record a login attempt for rate limiting."""
        await self._ensure_initialized()
        now = datetime.now(timezone.utc).isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO login_attempts (ip_address, timestamp, success)
                   VALUES (?, ?, ?)""",
                (ip_address, now, 1 if success else 0)
            )

            # Clean up old attempts (older than lockout period * 2)
            cleanup_time = datetime.now(timezone.utc) - timedelta(
                minutes=AuthConfig.get_lockout_minutes() * 2
            )
            await db.execute(
                "DELETE FROM login_attempts WHERE timestamp < ?",
                (cleanup_time.isoformat(),)
            )

            await db.commit()

    async def authenticate(
        self,
        username: str,
        password: str,
        ip_address: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Authenticate user credentials.
        Returns (success, error_message).
        """
        # Check rate limit first
        allowed, wait_seconds = await self.check_rate_limit(ip_address)
        if not allowed:
            return False, f"Too many failed attempts. Try again in {wait_seconds} seconds."

        # Check username
        if username != AuthConfig.get_username():
            await self.record_login_attempt(ip_address, False)
            return False, "Invalid credentials"

        # Get password hash
        password_hash = await self.get_password_hash()
        if not password_hash:
            # No password set - need to configure
            return False, "Authentication not configured. Set ASSISTANT_AUTH_PASSWORD_HASH."

        # Verify password
        if not AuthConfig.verify_password(password, password_hash):
            await self.record_login_attempt(ip_address, False)
            return False, "Invalid credentials"

        # Success
        await self.record_login_attempt(ip_address, True)
        return True, None

    async def create_access_token(
        self,
        username: str,
        ip_address: str = "",
        user_agent: str = ""
    ) -> str:
        """Create a new JWT access token."""
        secret = await self._get_jwt_secret()
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=AuthConfig.get_token_expire_minutes())

        # Generate unique token ID for revocation tracking
        token_id = secrets.token_urlsafe(16)

        payload = {
            "sub": username,
            "jti": token_id,
            "iat": now,
            "exp": expires,
            "type": "access"
        }

        token = jwt.encode(payload, secret, algorithm=AuthConfig.ALGORITHM)

        # Store session for revocation support
        await self._store_session(
            token_id, username, now, expires, ip_address, user_agent
        )

        return token

    async def create_refresh_token(
        self,
        username: str,
        ip_address: str = "",
        user_agent: str = ""
    ) -> str:
        """Create a new JWT refresh token."""
        secret = await self._get_jwt_secret()
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=AuthConfig.get_refresh_token_expire_days())

        token_id = secrets.token_urlsafe(16)

        payload = {
            "sub": username,
            "jti": token_id,
            "iat": now,
            "exp": expires,
            "type": "refresh"
        }

        token = jwt.encode(payload, secret, algorithm=AuthConfig.ALGORITHM)

        # Store session
        await self._store_session(
            token_id, username, now, expires, ip_address, user_agent
        )

        return token

    async def _store_session(
        self,
        token_id: str,
        username: str,
        created_at: datetime,
        expires_at: datetime,
        ip_address: str,
        user_agent: str
    ):
        """Store a session for tracking."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO active_sessions
                   (token_id, user, created_at, expires_at, ip_address, user_agent)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (token_id, username, created_at.isoformat(),
                 expires_at.isoformat(), ip_address, user_agent)
            )
            await db.commit()

    async def verify_token(self, token: str) -> Tuple[bool, Optional[dict], Optional[str]]:
        """
        Verify a JWT token.
        Returns (valid, payload, error_message).
        """
        secret = await self._get_jwt_secret()

        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=[AuthConfig.ALGORITHM]
            )

            # Check if session is revoked
            token_id = payload.get("jti")
            if token_id:
                is_revoked = await self._is_session_revoked(token_id)
                if is_revoked:
                    return False, None, "Token has been revoked"

            return True, payload, None

        except jwt.ExpiredSignatureError:
            return False, None, "Token has expired"
        except jwt.InvalidTokenError as e:
            return False, None, f"Invalid token: {str(e)}"

    async def _is_session_revoked(self, token_id: str) -> bool:
        """Check if a session has been revoked."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT revoked FROM active_sessions WHERE token_id = ?",
                (token_id,)
            )
            row = await cursor.fetchone()
            return bool(row and row[0])

    async def revoke_token(self, token: str) -> bool:
        """Revoke a token (logout)."""
        valid, payload, _ = await self.verify_token(token)
        if not valid or not payload:
            return False

        token_id = payload.get("jti")
        if not token_id:
            return False

        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE active_sessions SET revoked = 1 WHERE token_id = ?",
                (token_id,)
            )
            await db.commit()

        return True

    async def revoke_all_sessions(self, username: str):
        """Revoke all sessions for a user."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE active_sessions SET revoked = 1 WHERE user = ?",
                (username,)
            )
            await db.commit()

    async def get_active_sessions(self, username: str) -> list:
        """Get list of active (non-revoked, non-expired) sessions."""
        await self._ensure_initialized()
        now = datetime.now(timezone.utc).isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """SELECT token_id, created_at, expires_at, ip_address, user_agent
                   FROM active_sessions
                   WHERE user = ? AND revoked = 0 AND expires_at > ?
                   ORDER BY created_at DESC""",
                (username, now)
            )
            rows = await cursor.fetchall()
            return [
                {
                    "id": row[0][:8] + "...",  # Truncate ID for display
                    "created_at": row[1],
                    "expires_at": row[2],
                    "ip_address": row[3] or "unknown",
                    "user_agent": row[4] or "unknown"
                }
                for row in rows
            ]

    async def cleanup_expired_sessions(self):
        """Remove expired sessions from database."""
        await self._ensure_initialized()
        now = datetime.now(timezone.utc).isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            result = await db.execute(
                "DELETE FROM active_sessions WHERE expires_at < ?",
                (now,)
            )
            await db.commit()
            return result.rowcount


# Global service instance
_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    """Get or create the global auth service instance."""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
