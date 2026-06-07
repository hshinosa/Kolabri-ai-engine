"""
Notification Service
====================
Webhook client for communicating with Core-API. Sends proactive interventions 
and teacher alerts with exponential backoff retry logic.
"""

import httpx
import asyncio
from typing import Dict, Any, Optional
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

class NotificationService:
    """Service to send notifications and interventions back to Core-API with retry support."""
    
    def __init__(self):
        self.base_url = settings.CORE_API_URL
        self.secret = settings.CORE_API_SECRET
    
    async def _send_with_retry(self, url: str, payload: Dict[str, Any], headers: Dict[str, str], max_retries: int = 3) -> bool:
        """Helper to send webhook with exponential backoff retry."""
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(url, json=payload, headers=headers, timeout=5.0)
                    if response.status_code in [200, 201]:
                        return True
                    
                    logger.warning(
                        "webhook_attempt_failed",
                        attempt=attempt + 1,
                        status=response.status_code,
                        url=url
                    )
            except Exception:
                logger.exception("webhook_error", attempt=attempt + 1)
            
            if attempt < max_retries - 1:
                # Exponential backoff
                await asyncio.sleep(2 ** attempt)
        
        return False

    async def send_intervention(
        self,
        group_id: str,
        message: str,
        intervention_type: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send an AI intervention to Core-API."""
        url = f"{self.base_url}/api/webhooks/ai-intervention"
        payload = {
            "groupId": group_id,
            "message": message,
            "type": intervention_type,
            "metadata": metadata or {},
            "timestamp": "now"
        }
        headers = {
            "X-API-Key": self.secret,
            "Content-Type": "application/json"
        }
        
        success = await self._send_with_retry(url, payload, headers)
        if success:
            logger.info("intervention_webhook_sent", group_id=group_id, type=intervention_type)
        return success

    async def notify_teacher(
        self,
        course_id: str,
        group_id: str,
        alert_type: str,
        message: str,
        data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Notify teacher about issues."""
        url = f"{self.base_url}/api/webhooks/teacher-notification"
        payload = {
            "courseId": course_id,
            "groupId": group_id,
            "type": alert_type,
            "message": message,
            "data": data or {}
        }
        headers = {
            "X-API-Key": self.secret,
            "Content-Type": "application/json"
        }
        
        return await self._send_with_retry(url, payload, headers)

# Singleton
_notification_service = None

def get_notification_service() -> NotificationService:
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
