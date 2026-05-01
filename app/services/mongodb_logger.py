"""
MongoDB Integration for Event Logging
=====================================
Logs educational events and discussion dynamics in XES-compatible format
for Process Mining and student analytics.
"""

import csv
import io
from typing import Optional, Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from app.core.config import settings
from app.core.logging import get_logger
from app.services.pii_detector import PIIDetector

logger = get_logger(__name__)

class MongoDBLogger:
    """Service for logging educational events optimized for Process Mining."""
    
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
        self.enabled = settings.ENABLE_MONGODB_LOGGING
        self._pii_detector = PIIDetector()
        
    async def connect(self):
        """Establish and verify connection to MongoDB with connection pooling."""
        if not self.enabled:
            return
            
        try:
            # OPTIMIZATION: Connection pooling configuration
            # KOL-138: MongoDB Connection Pooling Optimization
            self.client = AsyncIOMotorClient(
                settings.MONGO_URI,
                maxPoolSize=settings.MONGO_MAX_POOL_SIZE,          # Max 50 connections
                minPoolSize=settings.MONGO_MIN_POOL_SIZE,          # Min 10 connections
                maxIdleTimeMS=settings.MONGO_MAX_IDLE_TIME_MS,     # 30 seconds
                connectTimeoutMS=settings.MONGO_CONNECT_TIMEOUT_MS, # 5 seconds
                serverSelectionTimeoutMS=5000,                     # 5 seconds
                socketTimeoutMS=30000,                             # 30 seconds
                retryWrites=True,                                  # Enable retry writes
                retryReads=True,                                   # Enable retry reads
            )
            self.db = self.client[settings.MONGO_DB_NAME]
            await self.client.admin.command('ping')
            
            # Indexes for performance and data retention
            await self.db.activity_logs.create_index([("CaseID", 1), ("Timestamp", -1)])
            await self.db.activity_logs.create_index([("Activity", 1)])
            await self.db.silence_events.create_index("createdAt", expireAfterSeconds=2592000)
            
            logger.info(
                "mongodb_connection_pool_initialized",
                db_name=settings.MONGO_DB_NAME,
                max_pool_size=settings.MONGO_MAX_POOL_SIZE,
                min_pool_size=settings.MONGO_MIN_POOL_SIZE,
                max_idle_time_ms=settings.MONGO_MAX_IDLE_TIME_MS
            )
        except Exception as e:
            logger.error("mongodb_connection_failed", error=str(e))
            self.enabled = False

    async def log_activity(self, entry: Dict[str, Any]):
        """Log a standard XES-compatible event log entry."""
        if not self.enabled or self.db is None: return
            
        try:
            attributes = entry.get("Attributes", {})
            if isinstance(attributes, dict) and attributes.get("original_text"):
                attributes["original_text"] = self._pii_detector.mask(str(attributes["original_text"]))
                entry["Attributes"] = attributes

            if "Timestamp" not in entry:
                entry["Timestamp"] = datetime.now()
            
            await self.db.activity_logs.insert_one(entry)
            logger.debug("activity_logged", case_id=entry.get("CaseID"), activity=entry.get("Activity"))
        except Exception as e:
            logger.error("mongodb_log_activity_failed", error=str(e))

    async def log_intervention(self, group_id: str, intervention_type: str, reason: str, metadata: Dict[str, Any], session_id: str = "1"):
        """High-level helper to log proactive interventions."""
        entry = {
            "CaseID": f"{group_id}_session_{session_id}",
            "Activity": f"System_Intervention_{intervention_type.upper()}",
            "Timestamp": datetime.now(),
            "Resource": "System_Orchestrator",
            "Lifecycle": "complete",
            "Attributes": {
                "original_text": reason,
                "srl_object": "Discussion_Dynamics",
                "educational_category": "Behavioral",
                "scaffolding_trigger": True,
                "metadata": metadata
            }
        }
        await self.log_activity(entry)

    async def get_activity_logs(self, case_id: Optional[str] = None, resource: Optional[str] = None, limit: int = 100, **kwargs) -> list:
        """Retrieve activity logs with flexible filtering."""
        if not self.enabled or self.db is None: return []
            
        try:
            query = {}
            # Handle both new and legacy parameters
            cid = case_id or kwargs.get("chat_space_id")
            if cid: query["CaseID"] = cid
            
            res = resource or kwargs.get("user_id")
            if res: query["Resource"] = res
            
            cursor = self.db.activity_logs.find(query).sort("Timestamp", 1).limit(limit)
            logs = await cursor.to_list(length=limit)
            
            for log in logs:
                log["_id"] = str(log["_id"])
                if isinstance(log.get("Timestamp"), datetime):
                    log["Timestamp"] = log["Timestamp"].isoformat()
            
            return logs
        except Exception as e:
            logger.error("mongodb_get_logs_failed", error=str(e))
            return []

    async def export_to_csv(self, case_id: Optional[str] = None) -> str:
        """Export logs to CSV format ready for Process Mining tools."""
        logs = await self.get_activity_logs(case_id=case_id, limit=10000)
        output = io.StringIO()
        writer = csv.writer(output)
        
        writer.writerow(["CaseID", "Activity", "Timestamp", "Resource", "Lifecycle", "original_text", "srl_object", "educational_category", "is_hot", "lexical_variety", "scaffolding_trigger"])
        
        for log in logs:
            attr = log.get("Attributes", {})
            writer.writerow([
                log.get(f, "") for f in ["CaseID", "Activity", "Timestamp", "Resource", "Lifecycle"]
            ] + [
                attr.get(f, "") for f in ["original_text", "srl_object", "educational_category", "is_hot", "lexical_variety", "scaffolding_trigger"]
            ])
            
        return output.getvalue()

    async def close(self):
        if self.client:
            self.client.close()

_mongo_logger: Optional[MongoDBLogger] = None

def get_mongo_logger() -> MongoDBLogger:
    global _mongo_logger
    if _mongo_logger is None:
        _mongo_logger = MongoDBLogger()
    return _mongo_logger
