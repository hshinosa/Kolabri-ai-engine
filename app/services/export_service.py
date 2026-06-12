"""
Activity Data CSV Export Service
================================
Aggregates student activity data from MongoDB and exports it to CSV format
for manual assessment and pedagogical research.
"""

import csv
import io
from typing import Dict, List, Optional, Any
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class ExportService:
    """Service for exporting activity data to CSV format."""
    
    def __init__(self):
        """Initialize MongoDB connection."""
        self._client: Optional[AsyncIOMotorClient] = None
        self._db: Optional[AsyncIOMotorDatabase] = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize MongoDB connection."""
        if self._initialized:
            return
        
        self._client = AsyncIOMotorClient(settings.MONGO_URI)
        self._db = self._client[settings.MONGO_DB_NAME]
        self._initialized = True
        logger.info("export_service_initialized", db=settings.MONGO_DB_NAME)

    async def aggregate_activity_by_group(self, group_id: str) -> List[Dict[str, Any]]:
        """
        Agregasi metrik keterlibatan mahasiswa per group.
        Synchronized with XES Schema (PascalCase).
        """
        await self.initialize()
        
        try:
            from app.services.repositories import ActivityLogRepository
            repo = ActivityLogRepository(self._db)
            logs = await repo.list_student_messages_for_group(group_id)
            
            # Aggregate metrics per user (Resource)
            user_metrics = {}
            
            for log in logs:
                user_id = log.get("Resource", "unknown")
                attr = log.get("Attributes", {})
                content = attr.get("original_text", "")
                
                if user_id not in user_metrics:
                    user_metrics[user_id] = {
                        "user_id": user_id,
                        "name": user_id, # Fallback to ID
                        "message_count": 0,
                        "word_count": 0,
                        "hot_count": 0,
                        "total_lexical_variety": 0.0,
                        "engagement_score": 0.0
                    }
                
                m = user_metrics[user_id]
                m["message_count"] += 1
                m["word_count"] += len(content.split())
                if attr.get("is_hot", False):
                    m["hot_count"] += 1
                m["total_lexical_variety"] += attr.get("lexical_variety", 0.0)
            
            _finalize_group_engagement_metrics(user_metrics)
            
            return sorted(user_metrics.values(), key=lambda x: x["engagement_score"], reverse=True)
            
        except Exception as e:
            logger.error(
                "aggregation_failed",
                group_id=group_id,
                error=str(e)
            )
            raise
    
    async def aggregate_activity_by_chat_space(
        self,
        chat_space_id: str
    ) -> List[Dict[str, Any]]:
        """
        Agregasi metrik keterlibatan mahasiswa per chat space.
        Synchronized with XES Schema (PascalCase).
        """
        await self.initialize()
        
        try:
            from app.services.repositories import ActivityLogRepository
            repo = ActivityLogRepository(self._db)
            logs = await repo.list_student_messages_for_case(chat_space_id)
            
            user_metrics = {}
            for log in logs:
                user_id = log.get("Resource", "unknown")
                attr = log.get("Attributes", {})
                content = attr.get("original_text", "")
                
                if user_id not in user_metrics:
                    user_metrics[user_id] = {
                        "user_id": user_id,
                        "name": user_id,
                        "message_count": 0,
                        "word_count": 0,
                        "hot_count": 0,
                        "total_lexical_variety": 0.0,
                        "avg_lexical_variety": 0.0
                    }
                
                m = user_metrics[user_id]
                m["message_count"] += 1
                m["word_count"] += len(content.split())
                if attr.get("is_hot", False):
                    m["hot_count"] += 1
                m["total_lexical_variety"] += attr.get("lexical_variety", 0.0)
            
            _finalize_chat_space_metrics(user_metrics)
            
            return sorted(user_metrics.values(), key=lambda x: x["message_count"], reverse=True)
            
        except Exception as e:
            logger.error(
                "aggregation_failed",
                chat_space_id=chat_space_id,
                error=str(e)
            )
            raise
    
    def generate_csv_string(
        self,
        user_metrics: List[Dict[str, Any]],
        include_detailed: bool = True
    ) -> str:
        """
        Generate CSV string from user metrics.
        
        Args:
            user_metrics: List of aggregated user metrics
            include_detailed: Include detailed columns (HOT, engagement types)
            
        Returns:
            CSV string
        """
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Define headers
        if include_detailed:
            headers = [
                "Student Name",
                "User ID",
                "Message Count",
                "Total Words",
                "Avg Words/Message",
                "HOT Count",
                "HOT Percentage",
                "Cognitive Messages",
                "Behavioral Messages",
                "Emotional Messages",
                "Avg Lexical Variety",
                "Engagement Score"
            ]
        else:
            headers = [
                "Student Name",
                "Message Count",
                "Total Words",
                "HOT Count",
                "Engagement Score"
            ]
        
        writer.writerow(headers)
        
        # Write data rows
        for metrics in user_metrics:
            msg_count = metrics.get("message_count", 0)
            word_count = metrics.get("word_count", 0)
            hot_count = metrics.get("hot_count", 0)
            
            # Calculate averages
            avg_words = round(word_count / msg_count, 2) if msg_count > 0 else 0
            hot_percentage = round((hot_count / msg_count) * 100, 2) if msg_count > 0 else 0
            
            if include_detailed:
                row = [
                    metrics.get("name", "Unknown"),
                    metrics.get("user_id", "N/A"),
                    msg_count,
                    word_count,
                    avg_words,
                    hot_count,
                    hot_percentage,
                    metrics.get("cognitive_count", 0),
                    metrics.get("behavioral_count", 0),
                    metrics.get("emotional_count", 0),
                    metrics.get("avg_lexical_variety", 0.0),
                    metrics.get("engagement_score", 0.0)
                ]
            else:
                row = [
                    metrics.get("name", "Unknown"),
                    msg_count,
                    word_count,
                    hot_count,
                    metrics.get("engagement_score", 0.0)
                ]
            
            writer.writerow(row)
        
        # Add summary row
        if user_metrics:
            total_messages = sum(m.get("message_count", 0) for m in user_metrics)
            total_words = sum(m.get("word_count", 0) for m in user_metrics)
            total_hot = sum(m.get("hot_count", 0) for m in user_metrics)
            avg_engagement = sum(m.get("engagement_score", 0.0) for m in user_metrics) / len(user_metrics)
            
            if include_detailed:
                summary_row = [
                    "--- TOTAL ---",
                    "",
                    total_messages,
                    total_words,
                    round(total_words / total_messages, 2) if total_messages > 0 else 0,
                    total_hot,
                    round((total_hot / total_messages) * 100, 2) if total_messages > 0 else 0,
                    sum(m.get("cognitive_count", 0) for m in user_metrics),
                    sum(m.get("behavioral_count", 0) for m in user_metrics),
                    sum(m.get("emotional_count", 0) for m in user_metrics),
                    "",
                    round(avg_engagement, 2)
                ]
            else:
                summary_row = [
                    "--- TOTAL ---",
                    total_messages,
                    total_words,
                    total_hot,
                    round(avg_engagement, 2)
                ]
            
            writer.writerow(summary_row)
        
        csv_string = output.getvalue()
        output.close()
        
        logger.info(
            "csv_generated",
            rows=len(user_metrics),
            size_bytes=len(csv_string)
        )
        
        return csv_string
    
    async def export_group_activity_detailed(
        self,
        group_id: str
    ) -> str:
        """
        Export group activity with per-student breakdown.
        CSV structure focuses on what each student did across all chat spaces in the group.
        """
        await self.initialize()
        
        from app.services.repositories import ActivityLogRepository
        repo = ActivityLogRepository(self._db)
        logs = await repo.list_student_messages_for_group_sorted(group_id)
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # 2. Header
        writer.writerow(["=== LAPORAN AKTIVITAS MAHASISWA PER KELOMPOK ==="])
        writer.writerow(["Group ID", group_id])
        writer.writerow(["Waktu Ekspor", datetime.now().isoformat()])
        writer.writerow([])
        
        # 3. Process logs by student
        current_student = None
        for log in logs:
            student_id = log.get("Resource", "unknown")
            case_id = log.get("CaseID", "N/A")
            timestamp = log.get("Timestamp", "")
            attr = log.get("Attributes", {})
            text = attr.get("original_text", "")
            is_hot = "YA" if attr.get("is_hot") else "TIDAK"
            lexical = attr.get("lexical_variety", 0)
            
            # Add a separator and student header when student changes
            if student_id != current_student:
                if current_student is not None:
                    writer.writerow([]) # Empty line between students
                
                writer.writerow([f">>> MAHASISWA: {student_id} <<<"])
                writer.writerow(["Chat Space (Session)", "Waktu", "Pesan", "Kualitas HOT", "Variasi Leksikal"])
                current_student = student_id
            
            writer.writerow([case_id, timestamp, text[:100], is_hot, lexical])
            
        return output.getvalue()
    
    async def export_chat_space_activity(
        self,
        chat_space_id: str,
        include_detailed: bool = True
    ) -> str:
        """
        Export chat space activity to CSV string.
        
        Args:
            chat_space_id: ID chat space
            include_detailed: Include detailed metrics
            
        Returns:
            CSV string
        """
        user_metrics = await self.aggregate_activity_by_chat_space(chat_space_id)
        return self.generate_csv_string(user_metrics, include_detailed)
    
    async def close(self) -> None:
        """Close MongoDB connection."""
        if self._client:
            self._client.close()
            self._initialized = False
            logger.info("export_service_closed")





def _finalize_group_engagement_metrics(user_metrics: Dict[str, Dict[str, Any]]) -> None:
    """Compute avg lexical and engagement scores; skip users with zero messages."""
    for m in user_metrics.values():
        cnt = m["message_count"]
        if cnt > 0:
            m["avg_lexical_variety"] = round(m["total_lexical_variety"] / cnt, 2)
            hot_p = (m["hot_count"] / cnt) * 100
            m["engagement_score"] = round((hot_p * 0.4) + (m["avg_lexical_variety"] * 60), 1)


def _finalize_chat_space_metrics(user_metrics: Dict[str, Dict[str, Any]]) -> None:
    for m in user_metrics.values():
        if m["message_count"] > 0:
            m["avg_lexical_variety"] = round(
                m["total_lexical_variety"] / m["message_count"], 2
            )

# Singleton instance
_export_service: Optional[ExportService] = None


def get_export_service() -> ExportService:
    """Get singleton instance of ExportService."""
    global _export_service
    if _export_service is None:
        _export_service = ExportService()
    return _export_service