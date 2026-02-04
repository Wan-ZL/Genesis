"""Tests for authentication service and API."""
import asyncio
import importlib
import os
import pytest
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, AsyncMock


# Define auth test environment variables
AUTH_TEST_ENV = {
    "ASSISTANT_AUTH_ENABLED": "true",
    "ASSISTANT_AUTH_USERNAME": "testuser",
    "ASSISTANT_JWT_SECRET": "test-secret-key-for-testing-32chars",
    "ASSISTANT_TOKEN_EXPIRE_MINUTES": "5",
    "ASSISTANT_MAX_LOGIN_ATTEMPTS": "3",
    "ASSISTANT_LOGIN_LOCKOUT_MINUTES": "1",
}


@pytest.fixture(autouse=True)
def auth_test_env():
    """Set up auth environment for all tests in this module."""
    # Save original values
    original_env = {k: os.environ.get(k) for k in AUTH_TEST_ENV}

    # Set test values
    for key, value in AUTH_TEST_ENV.items():
        os.environ[key] = value

    # Reload auth module to pick up new env
    import server.services.auth as auth_module
    importlib.reload(auth_module)

    yield

    # Restore original values
    for key, value in original_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    # Reset global service
    auth_module._auth_service = None


class TestAuthConfig:
    """Tests for AuthConfig class."""

    def test_generate_secret_key(self):
        """Test secret key generation."""
        from server.services.auth import AuthConfig
        key1 = AuthConfig.generate_secret_key()
        key2 = AuthConfig.generate_secret_key()

        assert len(key1) >= 32
        assert key1 != key2

    def test_hash_password(self):
        """Test password hashing."""
        from server.services.auth import AuthConfig
        password = "testpassword123"
        hashed = AuthConfig.hash_password(password)

        assert hashed != password
        assert len(hashed) > 0
        assert hashed.startswith("$2")  # bcrypt prefix

    def test_verify_password_correct(self):
        """Test password verification with correct password."""
        from server.services.auth import AuthConfig
        password = "testpassword123"
        hashed = AuthConfig.hash_password(password)

        assert AuthConfig.verify_password(password, hashed)

    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password."""
        from server.services.auth import AuthConfig
        password = "testpassword123"
        hashed = AuthConfig.hash_password(password)

        assert not AuthConfig.verify_password("wrongpassword", hashed)

    def test_config_from_env(self):
        """Test configuration loading from environment."""
        from server.services.auth import AuthConfig
        assert AuthConfig.is_enabled() is True
        assert AuthConfig.get_username() == "testuser"
        assert AuthConfig.get_token_expire_minutes() == 5
        assert AuthConfig.get_max_login_attempts() == 3


class TestAuthService:
    """Tests for AuthService class."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            yield Path(f.name)
        os.unlink(f.name)

    @pytest.fixture
    def auth_service(self, temp_db):
        """Create auth service with temporary database."""
        from server.services.auth import AuthService
        return AuthService(db_path=temp_db)

    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self, auth_service):
        """Test database initialization creates required tables."""
        await auth_service._ensure_initialized()

        # Verify tables exist by trying to query them
        import aiosqlite
        async with aiosqlite.connect(auth_service.db_path) as db:
            await db.execute("SELECT * FROM auth_config LIMIT 1")
            await db.execute("SELECT * FROM login_attempts LIMIT 1")
            await db.execute("SELECT * FROM active_sessions LIMIT 1")

    @pytest.mark.asyncio
    async def test_set_and_get_password(self, auth_service):
        """Test setting and retrieving password hash."""
        from server.services.auth import AuthConfig
        password = "securepassword123"
        await auth_service.set_password(password)

        stored_hash = await auth_service.get_password_hash()
        assert stored_hash is not None
        assert AuthConfig.verify_password(password, stored_hash)

    @pytest.mark.asyncio
    async def test_authenticate_success(self, auth_service):
        """Test successful authentication."""
        password = "securepassword123"
        await auth_service.set_password(password)

        success, error = await auth_service.authenticate(
            "testuser", password, "127.0.0.1"
        )
        assert success is True
        assert error is None

    @pytest.mark.asyncio
    async def test_authenticate_wrong_username(self, auth_service):
        """Test authentication with wrong username."""
        password = "securepassword123"
        await auth_service.set_password(password)

        success, error = await auth_service.authenticate(
            "wronguser", password, "127.0.0.1"
        )
        assert success is False
        assert "Invalid credentials" in error

    @pytest.mark.asyncio
    async def test_authenticate_wrong_password(self, auth_service):
        """Test authentication with wrong password."""
        await auth_service.set_password("correctpassword")

        success, error = await auth_service.authenticate(
            "testuser", "wrongpassword", "127.0.0.1"
        )
        assert success is False
        assert "Invalid credentials" in error

    @pytest.mark.asyncio
    async def test_rate_limiting(self, auth_service):
        """Test login rate limiting after failed attempts."""
        from server.services.auth import AuthConfig
        await auth_service.set_password("correctpassword")

        # Make MAX_LOGIN_ATTEMPTS failed attempts
        for _ in range(AuthConfig.get_max_login_attempts()):
            await auth_service.authenticate(
                "testuser", "wrongpassword", "192.168.1.1"
            )

        # Next attempt should be rate limited
        success, error = await auth_service.authenticate(
            "testuser", "correctpassword", "192.168.1.1"
        )
        assert success is False
        assert "Too many failed attempts" in error

    @pytest.mark.asyncio
    async def test_rate_limit_different_ip(self, auth_service):
        """Test that rate limiting is per-IP."""
        from server.services.auth import AuthConfig
        await auth_service.set_password("correctpassword")

        # Exhaust rate limit for one IP
        for _ in range(AuthConfig.get_max_login_attempts()):
            await auth_service.authenticate(
                "testuser", "wrongpassword", "192.168.1.1"
            )

        # Different IP should not be rate limited
        success, error = await auth_service.authenticate(
            "testuser", "correctpassword", "192.168.1.2"
        )
        assert success is True

    @pytest.mark.asyncio
    async def test_create_access_token(self, auth_service):
        """Test access token creation."""
        token = await auth_service.create_access_token(
            "testuser", "127.0.0.1", "TestAgent"
        )

        assert token is not None
        assert len(token) > 0

        valid, payload, error = await auth_service.verify_token(token)
        assert valid is True
        assert payload["sub"] == "testuser"
        assert payload["type"] == "access"

    @pytest.mark.asyncio
    async def test_create_refresh_token(self, auth_service):
        """Test refresh token creation."""
        token = await auth_service.create_refresh_token(
            "testuser", "127.0.0.1", "TestAgent"
        )

        assert token is not None

        valid, payload, error = await auth_service.verify_token(token)
        assert valid is True
        assert payload["sub"] == "testuser"
        assert payload["type"] == "refresh"

    @pytest.mark.asyncio
    async def test_verify_expired_token(self, auth_service):
        """Test verification of expired token."""
        from server.services.auth import AuthConfig
        import jwt

        secret = await auth_service._get_jwt_secret()
        expired_payload = {
            "sub": "testuser",
            "jti": "test-token-id",
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            "type": "access"
        }
        expired_token = jwt.encode(
            expired_payload, secret, algorithm=AuthConfig.ALGORITHM
        )

        valid, payload, error = await auth_service.verify_token(expired_token)
        assert valid is False
        assert "expired" in error.lower()

    @pytest.mark.asyncio
    async def test_revoke_token(self, auth_service):
        """Test token revocation."""
        token = await auth_service.create_access_token(
            "testuser", "127.0.0.1", "TestAgent"
        )

        # Token should be valid
        valid, _, _ = await auth_service.verify_token(token)
        assert valid is True

        # Revoke token
        result = await auth_service.revoke_token(token)
        assert result is True

        # Token should now be invalid
        valid, _, error = await auth_service.verify_token(token)
        assert valid is False
        assert "revoked" in error.lower()

    @pytest.mark.asyncio
    async def test_revoke_all_sessions(self, auth_service):
        """Test revoking all sessions for a user."""
        # Create multiple tokens
        token1 = await auth_service.create_access_token("testuser", "127.0.0.1", "Agent1")
        token2 = await auth_service.create_access_token("testuser", "127.0.0.2", "Agent2")

        # Both should be valid
        valid1, _, _ = await auth_service.verify_token(token1)
        valid2, _, _ = await auth_service.verify_token(token2)
        assert valid1 is True
        assert valid2 is True

        # Revoke all
        await auth_service.revoke_all_sessions("testuser")

        # Both should now be invalid
        valid1, _, _ = await auth_service.verify_token(token1)
        valid2, _, _ = await auth_service.verify_token(token2)
        assert valid1 is False
        assert valid2 is False

    @pytest.mark.asyncio
    async def test_get_active_sessions(self, auth_service):
        """Test retrieving active sessions."""
        # Create sessions
        await auth_service.create_access_token("testuser", "127.0.0.1", "Chrome")
        await auth_service.create_access_token("testuser", "127.0.0.2", "Firefox")

        sessions = await auth_service.get_active_sessions("testuser")
        assert len(sessions) >= 2

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(self, auth_service):
        """Test cleanup of expired sessions."""
        import jwt

        # Create an expired session directly in database
        secret = await auth_service._get_jwt_secret()
        await auth_service._ensure_initialized()

        expired_time = datetime.now(timezone.utc) - timedelta(hours=1)
        import aiosqlite
        async with aiosqlite.connect(auth_service.db_path) as db:
            await db.execute(
                """INSERT INTO active_sessions
                   (token_id, user, created_at, expires_at, ip_address, user_agent)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                ("expired-token", "testuser", expired_time.isoformat(),
                 expired_time.isoformat(), "127.0.0.1", "Test")
            )
            await db.commit()

        # Cleanup should remove expired session
        count = await auth_service.cleanup_expired_sessions()
        assert count >= 1

    @pytest.mark.asyncio
    async def test_jwt_secret_persistence(self, auth_service):
        """Test that JWT secret is persisted."""
        from server.services.auth import AuthService
        secret1 = await auth_service._get_jwt_secret()

        # Create new service instance with same db
        auth_service2 = AuthService(db_path=auth_service.db_path)
        secret2 = await auth_service2._get_jwt_secret()

        assert secret1 == secret2


class TestAuthAPI:
    """Tests for authentication API endpoints."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            yield Path(f.name)
        os.unlink(f.name)

    @pytest.fixture
    def client(self, temp_db):
        """Create test client with temporary database."""
        import config
        original_db = config.DATABASE_PATH
        config.DATABASE_PATH = temp_db

        # Reset global auth service
        import server.services.auth as auth_module
        auth_module._auth_service = None

        from fastapi.testclient import TestClient
        from server.main import app
        yield TestClient(app)

        config.DATABASE_PATH = original_db
        auth_module._auth_service = None

    def test_auth_status_endpoint(self, client):
        """Test GET /api/auth/status endpoint."""
        response = client.get("/api/auth/status")
        assert response.status_code == 200

        data = response.json()
        assert "auth_enabled" in data
        assert "auth_configured" in data
        assert "username" in data

    def test_login_no_password_set(self, client):
        """Test login when password not configured."""
        response = client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "anypassword"
        })
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is False
        assert "not configured" in data["error"].lower()

    def test_set_password(self, client):
        """Test setting initial password."""
        response = client.post("/api/auth/set-password", json={
            "password": "securepassword123"
        })
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_set_password_too_short(self, client):
        """Test setting password that's too short."""
        response = client.post("/api/auth/set-password", json={
            "password": "short"
        })
        assert response.status_code == 400

    def test_set_password_already_set(self, client):
        """Test setting password when already set."""
        # Set password first time
        client.post("/api/auth/set-password", json={
            "password": "securepassword123"
        })

        # Try to set again
        response = client.post("/api/auth/set-password", json={
            "password": "newpassword123"
        })
        assert response.status_code == 403

    def test_login_success(self, client):
        """Test successful login."""
        # Set password
        client.post("/api/auth/set-password", json={
            "password": "securepassword123"
        })

        # Login
        response = client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "securepassword123"
        })
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "Bearer"

    def test_login_wrong_password(self, client):
        """Test login with wrong password."""
        # Set password
        client.post("/api/auth/set-password", json={
            "password": "securepassword123"
        })

        # Login with wrong password
        response = client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "wrongpassword"
        })
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is False
        assert "Invalid credentials" in data["error"]

    def test_protected_route_without_token(self, client):
        """Test accessing protected route without token."""
        response = client.get("/api/status")
        assert response.status_code == 401

    def test_protected_route_with_valid_token(self, client):
        """Test accessing protected route with valid token."""
        # Set password and login
        client.post("/api/auth/set-password", json={
            "password": "securepassword123"
        })
        login_response = client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "securepassword123"
        })
        token = login_response.json()["access_token"]

        # Access protected route
        response = client.get(
            "/api/status",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    def test_protected_route_with_invalid_token(self, client):
        """Test accessing protected route with invalid token."""
        response = client.get(
            "/api/status",
            headers={"Authorization": "Bearer invalid-token"}
        )
        assert response.status_code == 401

    def test_refresh_token(self, client):
        """Test refreshing access token."""
        # Set password and login
        client.post("/api/auth/set-password", json={
            "password": "securepassword123"
        })
        login_response = client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "securepassword123"
        })
        refresh_token = login_response.json()["refresh_token"]

        # Refresh
        response = client.post("/api/auth/refresh", json={
            "refresh_token": refresh_token
        })
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert "access_token" in data

    def test_logout(self, client):
        """Test logout endpoint."""
        # Set password and login
        client.post("/api/auth/set-password", json={
            "password": "securepassword123"
        })
        login_response = client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "securepassword123"
        })
        token = login_response.json()["access_token"]

        # Logout
        response = client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

        # Token should no longer work
        response = client.get(
            "/api/status",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401

    def test_logout_all(self, client):
        """Test logout all sessions."""
        # Set password and login
        client.post("/api/auth/set-password", json={
            "password": "securepassword123"
        })

        # Create multiple sessions
        login1 = client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "securepassword123"
        })
        login2 = client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "securepassword123"
        })

        token1 = login1.json()["access_token"]
        token2 = login2.json()["access_token"]

        # Logout all with first token
        response = client.post(
            "/api/auth/logout-all",
            headers={"Authorization": f"Bearer {token1}"}
        )
        assert response.status_code == 200

        # Both tokens should be invalid
        response = client.get(
            "/api/status",
            headers={"Authorization": f"Bearer {token2}"}
        )
        assert response.status_code == 401

    def test_change_password(self, client):
        """Test changing password."""
        # Set initial password
        client.post("/api/auth/set-password", json={
            "password": "securepassword123"
        })

        # Login
        login_response = client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "securepassword123"
        })
        token = login_response.json()["access_token"]

        # Change password
        response = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "securepassword123",
                "new_password": "newpassword456"
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

        # Login with new password
        login_response = client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "newpassword456"
        })
        assert login_response.json()["success"] is True


class TestAuthDisabled:
    """Tests for when authentication is disabled."""

    @pytest.fixture
    def client_no_auth(self, tmp_path):
        """Create test client with auth disabled."""
        import config
        original_db = config.DATABASE_PATH
        config.DATABASE_PATH = tmp_path / "test.db"

        # Disable auth
        with patch.dict(os.environ, {"ASSISTANT_AUTH_ENABLED": "false"}):
            # Reset global auth service
            import server.services.auth as auth_module
            auth_module._auth_service = None

            # Reimport to pick up new env
            import importlib
            importlib.reload(auth_module)

            from fastapi.testclient import TestClient
            from server.main import app
            yield TestClient(app)

            config.DATABASE_PATH = original_db
            auth_module._auth_service = None

            # Restore auth enabled for other tests
            os.environ["ASSISTANT_AUTH_ENABLED"] = "true"
            importlib.reload(auth_module)

    def test_protected_route_accessible_without_auth(self, client_no_auth):
        """Test that routes are accessible when auth is disabled."""
        response = client_no_auth.get("/api/status")
        # Should work without token
        assert response.status_code == 200

    def test_login_returns_disabled_message(self, client_no_auth):
        """Test login endpoint when auth disabled."""
        response = client_no_auth.post("/api/auth/login", json={
            "username": "any",
            "password": "any"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "disabled" in data["error"].lower()
