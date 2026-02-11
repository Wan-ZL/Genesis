"""Push notification service for PWA support.

Implements Web Push protocol with VAPID authentication.
Integrates with ProactiveService to send OS-level notifications.
"""
import aiosqlite
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
import base64

try:
    from py_vapid import Vapid01  # type: ignore[import-untyped]
    from pywebpush import webpush, WebPushException  # type: ignore[import-untyped]
    from cryptography.hazmat.primitives import serialization
    HAS_WEBPUSH = True
except ImportError:
    HAS_WEBPUSH = False

logger = logging.getLogger(__name__)


@dataclass
class PushSubscription:
    """Represents a Web Push subscription."""
    id: str
    endpoint: str
    p256dh: str
    auth: str
    created_at: str
    user_agent: Optional[str] = None


class PushService:
    """Service for managing Web Push notifications."""

    def __init__(self, db_path: Path, vapid_private_key: Optional[str] = None):
        self.db_path = db_path
        self._initialized = False
        self._vapid_private_key = vapid_private_key
        self._vapid_public_key: Optional[str] = None
        self._vapid_claims = {
            "sub": "mailto:genesis@localhost"  # Replace with actual email if deploying
        }

        # Generate or load VAPID keys
        self._ensure_vapid_keys()

    def _ensure_vapid_keys(self):
        """Generate VAPID keys if not provided."""
        if not HAS_WEBPUSH:
            logger.warning("pywebpush/py_vapid not installed - push notifications disabled")
            self._vapid_public_key = ""
            return

        if self._vapid_private_key:
            try:
                vapid = Vapid01.from_string(self._vapid_private_key)
                raw_pub = vapid.public_key.public_bytes(
                    encoding=serialization.Encoding.X962,
                    format=serialization.PublicFormat.UncompressedPoint
                )
                self._vapid_public_key = base64.urlsafe_b64encode(raw_pub).rstrip(b'=').decode('utf-8')
                logger.info("Loaded existing VAPID keys")
            except Exception as e:
                logger.error(f"Failed to load VAPID key: {e}")
                self._generate_vapid_keys()
        else:
            self._generate_vapid_keys()

    def _generate_vapid_keys(self):
        """Generate new VAPID key pair."""
        if not HAS_WEBPUSH:
            self._vapid_public_key = ""
            return

        try:
            vapid = Vapid01()
            vapid.generate_keys()

            self._vapid_private_key = vapid.private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ).decode('utf-8')

            raw_pub = vapid.public_key.public_bytes(
                encoding=serialization.Encoding.X962,
                format=serialization.PublicFormat.UncompressedPoint
            )
            self._vapid_public_key = base64.urlsafe_b64encode(raw_pub).rstrip(b'=').decode('utf-8')

            logger.info("Generated new VAPID keys")
        except Exception as e:
            logger.error(f"Failed to generate VAPID keys: {e}")
            raise

    async def _ensure_initialized(self):
        """Ensure database tables exist."""
        if self._initialized:
            return

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA busy_timeout=5000")

            # Push subscriptions table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS push_subscriptions (
                    id TEXT PRIMARY KEY,
                    endpoint TEXT UNIQUE NOT NULL,
                    p256dh TEXT NOT NULL,
                    auth TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    user_agent TEXT
                )
            """)

            await db.commit()
        self._initialized = True

    def get_public_key(self) -> str:
        """Get VAPID public key for client subscription."""
        return self._vapid_public_key or ""

    async def save_subscription(
        self,
        subscription: dict,
        user_agent: Optional[str] = None
    ) -> PushSubscription:
        """Save a push subscription."""
        await self._ensure_initialized()

        endpoint = subscription['endpoint']
        keys = subscription['keys']
        p256dh = keys['p256dh']
        auth = keys['auth']

        # Generate subscription ID from endpoint hash
        import hashlib
        sub_id = hashlib.sha256(endpoint.encode()).hexdigest()[:16]

        push_sub = PushSubscription(
            id=sub_id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            created_at=datetime.now().isoformat(),
            user_agent=user_agent
        )

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO push_subscriptions
                   (id, endpoint, p256dh, auth, created_at, user_agent)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    push_sub.id,
                    push_sub.endpoint,
                    push_sub.p256dh,
                    push_sub.auth,
                    push_sub.created_at,
                    push_sub.user_agent
                )
            )
            await db.commit()

        logger.info(f"Saved push subscription: {sub_id}")
        return push_sub

    async def get_all_subscriptions(self) -> list[PushSubscription]:
        """Get all active push subscriptions."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT id, endpoint, p256dh, auth, created_at, user_agent FROM push_subscriptions"
            )
            rows = await cursor.fetchall()

        return [
            PushSubscription(
                id=row[0],
                endpoint=row[1],
                p256dh=row[2],
                auth=row[3],
                created_at=row[4],
                user_agent=row[5]
            )
            for row in rows
        ]

    async def delete_subscription(self, endpoint: str) -> bool:
        """Delete a push subscription."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM push_subscriptions WHERE endpoint = ?",
                (endpoint,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def send_notification(
        self,
        title: str,
        body: str,
        icon: str = "/static/icons/icon-192x192.png",
        badge: str = "/static/icons/badge-72x72.png",
        tag: str = "genesis-notification",
        data: Optional[dict] = None
    ) -> dict:
        """Send push notification to all subscribed clients."""
        if not HAS_WEBPUSH:
            logger.debug("Push notifications disabled (pywebpush not installed)")
            return {"sent": 0, "failed": 0}

        await self._ensure_initialized()

        subscriptions = await self.get_all_subscriptions()

        if not subscriptions:
            logger.info("No push subscriptions to send to")
            return {"sent": 0, "failed": 0}

        payload = json.dumps({
            "title": title,
            "body": body,
            "icon": icon,
            "badge": badge,
            "tag": tag,
            "data": data or {}
        })

        sent_count = 0
        failed_count = 0
        failed_endpoints: list[str] = []

        for sub in subscriptions:
            try:
                subscription_info = {
                    "endpoint": sub.endpoint,
                    "keys": {
                        "p256dh": sub.p256dh,
                        "auth": sub.auth
                    }
                }

                webpush(  # type: ignore[possibly-undefined]
                    subscription_info=subscription_info,
                    data=payload,
                    vapid_private_key=self._vapid_private_key,
                    vapid_claims=self._vapid_claims
                )

                sent_count += 1
                logger.debug(f"Push notification sent to {sub.id}")

            except WebPushException as e:  # type: ignore[possibly-undefined]
                failed_count += 1
                logger.warning(f"Push notification failed for {sub.id}: {e}")

                # If subscription is gone (410), remove it
                if e.response and e.response.status_code == 410:
                    failed_endpoints.append(sub.endpoint)

            except Exception as e:
                failed_count += 1
                logger.error(f"Push notification error for {sub.id}: {e}")

        # Clean up dead subscriptions
        for endpoint in failed_endpoints:
            await self.delete_subscription(endpoint)
            logger.info(f"Removed dead subscription: {endpoint[:50]}...")

        logger.info(f"Push notifications sent: {sent_count}, failed: {failed_count}")
        return {"sent": sent_count, "failed": failed_count}


# Singleton instance
_push_service: Optional[PushService] = None


def get_push_service(db_path: Optional[Path] = None, vapid_private_key: Optional[str] = None) -> PushService:
    """Get or create the push service singleton."""
    global _push_service
    if _push_service is None:
        if db_path is None:
            raise ValueError("db_path required for first initialization")
        _push_service = PushService(db_path, vapid_private_key)
    return _push_service


def init_push_service(db_path: Path, vapid_private_key: Optional[str] = None) -> PushService:
    """Initialize the push service with a specific path."""
    global _push_service
    _push_service = PushService(db_path, vapid_private_key)
    return _push_service
