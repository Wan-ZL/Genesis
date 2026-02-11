"""Push notification API routes for PWA support."""
import logging
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional

import config
from server.services.push import init_push_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize push service
push_service = None


def init_push():
    """Initialize push service on startup."""
    global push_service
    push_service = init_push_service(config.DATABASE_PATH)
    logger.info("Push notification service initialized")


class SubscriptionRequest(BaseModel):
    """Push subscription request body."""
    endpoint: str
    keys: dict  # Contains p256dh and auth


class NotificationRequest(BaseModel):
    """Manual notification request body."""
    title: str
    body: str
    icon: Optional[str] = "/static/icons/icon-192x192.png"
    badge: Optional[str] = "/static/icons/badge-72x72.png"
    tag: Optional[str] = "genesis-notification"
    data: Optional[dict] = None


@router.get("/push/vapid-key")
async def get_vapid_key():
    """Get VAPID public key for client subscription."""
    if not push_service:
        raise HTTPException(status_code=503, detail="Push service not initialized")

    return {
        "public_key": push_service.get_public_key()
    }


@router.post("/push/subscribe")
async def subscribe(subscription: SubscriptionRequest, request: Request):
    """Save a push subscription."""
    if not push_service:
        raise HTTPException(status_code=503, detail="Push service not initialized")

    user_agent = request.headers.get("User-Agent")

    try:
        sub = await push_service.save_subscription(
            subscription.model_dump(),
            user_agent=user_agent
        )

        return {
            "success": True,
            "subscription_id": sub.id
        }
    except Exception as e:
        logger.error(f"Failed to save subscription: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/push/unsubscribe")
async def unsubscribe(endpoint: str):
    """Remove a push subscription."""
    if not push_service:
        raise HTTPException(status_code=503, detail="Push service not initialized")

    try:
        deleted = await push_service.delete_subscription(endpoint)

        return {
            "success": deleted
        }
    except Exception as e:
        logger.error(f"Failed to delete subscription: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/push/send")
async def send_notification(notification: NotificationRequest):
    """Send a push notification to all subscribed clients (for testing)."""
    if not push_service:
        raise HTTPException(status_code=503, detail="Push service not initialized")

    try:
        result = await push_service.send_notification(
            title=notification.title,
            body=notification.body,
            icon=notification.icon or "/static/icons/icon-192x192.png",
            badge=notification.badge or "/static/icons/badge-72x72.png",
            tag=notification.tag or "genesis-notification",
            data=notification.data
        )

        return {
            "success": True,
            "sent": result["sent"],
            "failed": result["failed"]
        }
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/push/subscriptions")
async def get_subscriptions():
    """Get all active push subscriptions."""
    if not push_service:
        raise HTTPException(status_code=503, detail="Push service not initialized")

    try:
        subscriptions = await push_service.get_all_subscriptions()

        return {
            "subscriptions": [
                {
                    "id": sub.id,
                    "endpoint": sub.endpoint[:50] + "...",  # Truncate for privacy
                    "created_at": sub.created_at,
                    "user_agent": sub.user_agent
                }
                for sub in subscriptions
            ],
            "count": len(subscriptions)
        }
    except Exception as e:
        logger.error(f"Failed to get subscriptions: {e}")
        raise HTTPException(status_code=500, detail=str(e))
