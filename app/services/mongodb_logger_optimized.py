"""
Optimized MongoDB Logger dengan Connection Pooling
==================================================

Priority 2: MongoDB Connection Pooling Optimization

Features:
- Connection pooling (maxPoolSize=50)
- Min pool size untuk maintain warm connections
- Max idle time untuk cleanup idle connections
- Connection timeout dan server selection timeout
"""

from typing import Optional, Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from app.core.config import settings
from app.core.logging import get_logger


logger = get_logger(__name__)

# Connection pool configuration
MONGO_POOL_CONFIG = {
    "maxPoolSize": 50,          # Maximum connections in pool
    "minPoolSize": 10,          # Minimum connections to maintain
    "maxIdleTimeMS": 45000,     # Max idle time before closing (45s)
    "waitQueueTimeoutMS": 5000, # Max wait time for connection (5s)
    "serverSelectionTimeoutMS": 5000,  # Server selection timeout (5s)
    "heartbeatFrequencyMS": 10000,     # Health check interval (10s)
}


class OptimizedMongoDBLogger:
    """Optimized MongoDB Logger dengan connection pooling."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
        self.enabled = settings.ENABLE_MONGODB_LOGGING
        self._initialized = True
        
    async def connect(self):
        """Connect dengan connection pooling."""
        if not self.enabled or self.client:
            return
            
        try:
            # Create client dengan pool configuration
            self.client = AsyncIOMotorClient(
                settings.MONGO_URI,
                **MONGO_POOL_CONFIG
            )
            self.db = self.client[settings.MONGO_DB_NAME]
            
            # Verify connection
            await self.client.admin.command('ping')
            
            # Create indexes
            await self._setup_indexes()
            
            logger.info(
                "mongodb_connected_optimized",
                db_name=settings.MONGO_DB_NAME,
                max_pool=MONGO_POOL_CONFIG["maxPoolSize"],
                min_pool=MONGO_POOL_CONFIG["minPoolSize"]
            )
        except Exception as e:
            logger.error("mongodb_connection_failed", error=str(e))
            self.enabled = False
    
    async def _setup_indexes(self):
        """Setup database indexes untuk performance."""
        # Activity logs indexes
        await self.db.activity_logs.create_index([("CaseID", 1), ("Timestamp", -1)])
        await self.db.activity_logs.create_index([("Activity", 1)])
        await self.db.activity_logs.create_index([("Timestamp", -1)], expireAfterSeconds=2592000)
        
        # Silence events indexes
        await self.db.silence_events.create_index("createdAt", expireAfterSeconds=2592000)
        await self.db.silence_events.create_index([("group_id", 1), ("createdAt", -1)])
        
        # Cache analytics indexes
        await self.db.cache_analytics.create_index([("query_hash", 1)], unique=True)
        await self.db.cache_analytics.create_index([("hit_count", -1)])
    
    async def log_activity(self, entry: Dict[str, Any]):
        """Log activity dengan fire-and-forget (non-blocking)."""
        if not self.enabled or not self.db:
            return
        
        try:
            if "Timestamp" not in entry:
                entry["Timestamp"] = datetime.now()
            
            # Use write concern w=0 untuk fire-and-forget (fastest)
            await self.db.activity_logs.insert_one(
                entry,
                write_concern=None  # Fire-and-forget, no acknowledgment
            )
        except Exception as e:
            # Silent fail - don't block main flow
            logger.debug("mongodb_log_skipped", error=str(e))
    
    async def log_batch(self, entries: List[Dict[str, Any]]):
        """Batch insert untuk multiple entries."""
        if not self.enabled or not self.db or not entries:
            return
        
        try:
            # Add timestamps
            for entry in entries:
                if "Timestamp" not in entry:
                    entry["Timestamp"] = datetime.now()
            
            # Batch insert
            await self.db.activity_logs.insert_many(entries, ordered=False)
            logger.debug("mongodb_batch_logged", count=len(entries))
        except Exception as e:
            logger.error("mongodb_batch_log_failed", error=str(e))
    
    async def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics."""
        if not self.client:
            return {"error": "Not connected"}
        
        try:
            # Get server status
            status = await self.client.admin.command("serverStatus")
            connections = status.get("connections", {})
            
            return {
                "current": connections.get("current", 0),
                "available": connections.get("available", 0),
                "total_created": connections.get("totalCreated", 0),
                "max_pool_size": MONGO_POOL_CONFIG["maxPoolSize"],
                "min_pool_size": MONGO_POOL_CONFIG["minPoolSize"],
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def close(self):
        """Close connection gracefully."""
        if self.client:
            self.client.close()
            logger.info("mongodb_connection_closed")


# Global instance
_mongodb_logger = None


async def get_optimized_mongodb_logger() -> OptimizedMongoDBLogger:
    """Get singleton instance."""
    global _mongodb_logger
    if _mongodb_logger is None:
        _mongodb_logger = OptimizedMongoDBLogger()
        await _mongodb_logger.connect()
    return _mongodb_logger
