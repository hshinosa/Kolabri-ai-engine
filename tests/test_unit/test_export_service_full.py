"""
Comprehensive tests for export_service.py - 100% coverage target.
"""

import csv
import io
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, Mock

import pytest

from app.services.export_service import ExportService, get_export_service


@pytest.fixture
def mock_mongo_client():
    """Create mock MongoDB client."""
    return AsyncMock()


@pytest.fixture
def mock_db():
    """Create mock database."""
    return AsyncMock()


@pytest.fixture
def export_service():
    """Create ExportService instance."""
    return ExportService()


class TestExportServiceInit:
    """Test ExportService initialization."""
    
    def test_init(self, export_service):
        """Test ExportService initializes with None values."""
        assert export_service._client is None
        assert export_service._db is None
        assert export_service._initialized is False


class TestExportServiceInitialize:
    """Test ExportService.initialize method."""
    
    @pytest.mark.asyncio
    async def test_initialize_already_initialized(self, export_service):
        """Test initialize when already initialized."""
        export_service._initialized = True
        export_service._client = MagicMock()
        
        # Should return immediately without creating new client
        await export_service.initialize()
        
        assert export_service._initialized is True
    
    @pytest.mark.asyncio
    async def test_initialize_first_time(self, export_service):
        """Test initialize on first call."""
        with patch('app.services.export_service.AsyncIOMotorClient') as mock_client_class, \
             patch('app.services.export_service.settings') as mock_settings:
            
            mock_settings.MONGO_URI = "mongodb://localhost:27017"
            mock_settings.MONGO_DB_NAME = "test_db"
            
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            
            await export_service.initialize()
            
            assert export_service._initialized is True
            assert export_service._client == mock_client
            assert export_service._db == mock_client.__getitem__.return_value
            mock_client_class.assert_called_once_with("mongodb://localhost:27017")
    
    @pytest.mark.asyncio
    async def test_initialize_logs_info(self, export_service):
        """Test initialize logs info message."""
        with patch('app.services.export_service.AsyncIOMotorClient'), \
             patch('app.services.export_service.settings') as mock_settings, \
             patch('app.services.export_service.logger') as mock_logger:
            
            mock_settings.MONGO_URI = "mongodb://localhost"
            mock_settings.MONGO_DB_NAME = "test_db"
            
            await export_service.initialize()
            
            mock_logger.info.assert_called_once_with(
                "export_service_initialized",
                db="test_db"
            )


class TestAggregateActivityByGroup:
    """Test aggregate_activity_by_group method."""
    
    @pytest.mark.asyncio
    async def test_aggregate_activity_by_group(self, export_service):
        """Test aggregating activity by group."""
        with patch.object(export_service, 'initialize', new_callable=AsyncMock), \
             patch('app.services.export_service.logger') as mock_logger:
            
            # Mock MongoDB cursor
            mock_cursor = AsyncMock()
            mock_logs = [
                {
                    "Resource": "user1",
                    "Attributes": {
                        "original_text": "Hello world",
                        "is_hot": True,
                        "lexical_variety": 0.8
                    }
                },
                {
                    "Resource": "user1",
                    "Attributes": {
                        "original_text": "Test message",
                        "is_hot": False,
                        "lexical_variety": 0.6
                    }
                },
                {
                    "Resource": "user2",
                    "Attributes": {
                        "original_text": "Another message",
                        "is_hot": True,
                        "lexical_variety": 0.9
                    }
                }
            ]
            mock_cursor.to_list = AsyncMock(return_value=mock_logs)
            
            export_service._db = MagicMock()
            export_service._db.activity_logs.find.return_value = mock_cursor
            
            result = await export_service.aggregate_activity_by_group("group1")
            
            assert len(result) == 2
            # Results are sorted by engagement_score descending
            # Just check we have both users
            user_ids = [r["user_id"] for r in result]
            assert "user1" in user_ids
            assert "user2" in user_ids
            
            export_service._db.activity_logs.find.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_aggregate_activity_by_group_empty(self, export_service):
        """Test aggregating activity with no logs."""
        with patch.object(export_service, 'initialize', new_callable=AsyncMock):
            mock_cursor = AsyncMock()
            mock_cursor.to_list = AsyncMock(return_value=[])
            
            export_service._db = MagicMock()
            export_service._db.activity_logs.find.return_value = mock_cursor
            
            result = await export_service.aggregate_activity_by_group("group1")
            
            assert result == []
    
    @pytest.mark.asyncio
    async def test_aggregate_activity_by_group_error(self, export_service):
        """Test aggregating activity with error."""
        with patch.object(export_service, 'initialize', new_callable=AsyncMock), \
             patch('app.services.export_service.logger') as mock_logger:
            
            export_service._db = MagicMock()
            export_service._db.activity_logs.find.side_effect = Exception("DB Error")
            
            with pytest.raises(Exception, match="DB Error"):
                await export_service.aggregate_activity_by_group("group1")
            
            mock_logger.error.assert_called_once()


class TestAggregateActivityBySessionDiscussion:
    """Test aggregate_activity_by_session_discussion method."""
    
    @pytest.mark.asyncio
    async def test_aggregate_by_session_discussion(self, export_service):
        """Test aggregating activity by session discussion."""
        with patch.object(export_service, 'initialize', new_callable=AsyncMock):
            mock_cursor = AsyncMock()
            mock_logs = [
                {
                    "Resource": "user1",
                    "Attributes": {
                        "original_text": "Message one",
                        "is_hot": True,
                        "lexical_variety": 0.7
                    }
                },
                {
                    "Resource": "user2",
                    "Attributes": {
                        "original_text": "Message two three",
                        "is_hot": False,
                        "lexical_variety": 0.5
                    }
                }
            ]
            mock_cursor.to_list = AsyncMock(return_value=mock_logs)
            
            export_service._db = MagicMock()
            export_service._db.activity_logs.find.return_value = mock_cursor
            
            result = await export_service.aggregate_activity_by_session_discussion("chat1")
            
            assert len(result) == 2
            # Results sorted by message_count descending
            user_ids = [r["user_id"] for r in result]
            assert "user1" in user_ids
            assert "user2" in user_ids
    
    @pytest.mark.asyncio
    async def test_aggregate_by_session_discussion_empty(self, export_service):
        """Test aggregating with no logs."""
        with patch.object(export_service, 'initialize', new_callable=AsyncMock):
            mock_cursor = AsyncMock()
            mock_cursor.to_list = AsyncMock(return_value=[])
            
            export_service._db = MagicMock()
            export_service._db.activity_logs.find.return_value = mock_cursor
            
            result = await export_service.aggregate_activity_by_session_discussion("chat1")
            
            assert result == []
    
    @pytest.mark.asyncio
    async def test_aggregate_by_session_discussion_error(self, export_service):
        """Test aggregating with error."""
        with patch.object(export_service, 'initialize', new_callable=AsyncMock), \
             patch('app.services.export_service.logger') as mock_logger:
            
            export_service._db = MagicMock()
            export_service._db.activity_logs.find.side_effect = Exception("Error")
            
            with pytest.raises(Exception):
                await export_service.aggregate_activity_by_session_discussion("chat1")
            
            mock_logger.error.assert_called_once()


class TestGenerateCsvString:
    """Test generate_csv_string method."""
    
    def test_generate_csv_detailed(self, export_service):
        """Test generating detailed CSV."""
        user_metrics = [
            {
                "name": "John Doe",
                "user_id": "user1",
                "message_count": 10,
                "word_count": 500,
                "hot_count": 5,
                "cognitive_count": 8,
                "behavioral_count": 1,
                "emotional_count": 1,
                "avg_lexical_variety": 0.75,
                "engagement_score": 85.5
            }
        ]
        
        csv_string = export_service.generate_csv_string(user_metrics, include_detailed=True)
        
        assert "Student Name" in csv_string
        assert "John Doe" in csv_string
        assert "10" in csv_string  # message_count
        assert "500" in csv_string  # word_count
        assert "--- TOTAL ---" in csv_string
    
    def test_generate_csv_summary_only(self, export_service):
        """Test generating summary CSV."""
        user_metrics = [
            {
                "name": "Jane Doe",
                "user_id": "user2",
                "message_count": 5,
                "word_count": 250,
                "hot_count": 2,
                "engagement_score": 70.0
            }
        ]
        
        csv_string = export_service.generate_csv_string(user_metrics, include_detailed=False)
        
        assert "Student Name" in csv_string
        assert "Jane Doe" in csv_string
        assert "Message Count" in csv_string
        assert "--- TOTAL ---" in csv_string
    
    def test_generate_csv_empty(self, export_service):
        """Test generating CSV with no data."""
        csv_string = export_service.generate_csv_string([], include_detailed=True)
        
        assert "Student Name" in csv_string
        assert "--- TOTAL ---" not in csv_string  # No summary for empty data
    
    def test_generate_csv_multiple_users(self, export_service):
        """Test generating CSV with multiple users."""
        user_metrics = [
            {
                "name": "User 1",
                "user_id": "u1",
                "message_count": 10,
                "word_count": 100,
                "hot_count": 5,
                "cognitive_count": 8,
                "behavioral_count": 1,
                "emotional_count": 1,
                "avg_lexical_variety": 0.8,
                "engagement_score": 90.0
            },
            {
                "name": "User 2",
                "user_id": "u2",
                "message_count": 5,
                "word_count": 50,
                "hot_count": 2,
                "cognitive_count": 4,
                "behavioral_count": 0,
                "emotional_count": 1,
                "avg_lexical_variety": 0.6,
                "engagement_score": 60.0
            }
        ]
        
        csv_string = export_service.generate_csv_string(user_metrics, include_detailed=True)
        
        # Verify both users are present
        assert "User 1" in csv_string
        assert "User 2" in csv_string
        
        # Verify totals
        lines = csv_string.strip().split('\n')
        assert len(lines) == 4  # Header + 2 users + summary
    
    def test_generate_csv_zero_division_protection(self, export_service):
        """Test CSV generation handles zero messages."""
        user_metrics = [
            {
                "name": "User",
                "user_id": "u1",
                "message_count": 0,
                "word_count": 0,
                "hot_count": 0,
                "cognitive_count": 0,
                "behavioral_count": 0,
                "emotional_count": 0,
                "avg_lexical_variety": 0.0,
                "engagement_score": 0.0
            }
        ]
        
        # Should not raise division by zero error
        csv_string = export_service.generate_csv_string(user_metrics, include_detailed=True)
        
        assert "User" in csv_string


class TestExportGroupActivityDetailed:
    """Test export_group_activity_detailed method."""
    
    @pytest.mark.asyncio
    async def test_export_group_detailed(self, export_service):
        """Test exporting detailed group activity."""
        with patch.object(export_service, 'initialize', new_callable=AsyncMock):
            mock_logs = [
                {
                    "Resource": "user1",
                    "CaseID": "group1_session1",
                    "Timestamp": "2024-01-01T10:00:00",
                    "Attributes": {
                        "original_text": "Hello",
                        "is_hot": True,
                        "lexical_variety": 0.8
                    }
                }
            ]
            
            mock_cursor = MagicMock()
            mock_cursor.to_list = AsyncMock(return_value=mock_logs)
            
            # Mock the find().sort() chain
            export_service._db = MagicMock()
            export_service._db.activity_logs.find.return_value = mock_cursor
            mock_cursor.sort.return_value = mock_cursor
            
            result = await export_service.export_group_activity_detailed("group1")
            
            assert "LAPORAN AKTIVITAS MAHASISWA PER KELOMPOK" in result
            assert "group1" in result
            assert "user1" in result
            assert "Hello" in result
    
    @pytest.mark.asyncio
    async def test_export_group_detailed_empty(self, export_service):
        """Test exporting with no logs."""
        with patch.object(export_service, 'initialize', new_callable=AsyncMock):
            mock_cursor = MagicMock()
            mock_cursor.to_list = AsyncMock(return_value=[])
            
            # Mock the find().sort() chain
            export_service._db = MagicMock()
            export_service._db.activity_logs.find.return_value = mock_cursor
            mock_cursor.sort.return_value = mock_cursor
            
            result = await export_service.export_group_activity_detailed("group1")
            
            assert "LAPORAN AKTIVITAS MAHASISWA PER KELOMPOK" in result
            assert "group1" in result


class TestExportSessionDiscussionActivity:
    """Test export_session_discussion_activity method."""
    
    @pytest.mark.asyncio
    async def test_export_session_discussion(self, export_service):
        """Test exporting session discussion activity."""
        with patch.object(export_service, 'initialize', new_callable=AsyncMock), \
             patch.object(export_service, 'aggregate_activity_by_session_discussion', new_callable=AsyncMock) as mock_aggregate, \
             patch.object(export_service, 'generate_csv_string') as mock_generate:
            
            mock_aggregate.return_value = [{"user_id": "user1", "message_count": 5}]
            mock_generate.return_value = "CSV content"
            
            result = await export_service.export_session_discussion_activity("chat1", include_detailed=True)
            
            mock_aggregate.assert_called_once_with("chat1")
            mock_generate.assert_called_once_with(mock_aggregate.return_value, True)
            assert result == "CSV content"


class TestClose:
    """Test close method."""
    
    @pytest.mark.asyncio
    async def test_close(self, export_service):
        """Test closing MongoDB connection."""
        with patch('app.services.export_service.logger') as mock_logger:
            mock_client = MagicMock()
            export_service._client = mock_client
            export_service._initialized = True
            
            await export_service.close()
            
            mock_client.close.assert_called_once()
            assert export_service._initialized is False
            mock_logger.info.assert_called_once_with("export_service_closed")
    
    @pytest.mark.asyncio
    async def test_close_no_client(self, export_service):
        """Test close when no client exists."""
        export_service._client = None
        
        # Should not raise
        await export_service.close()
        
        assert export_service._initialized is False


class TestGetExportService:
    """Test get_export_service singleton function."""
    
    def test_get_export_service_singleton(self):
        """Test get_export_service returns singleton."""
        # Reset singleton
        import app.services.export_service as export_module
        export_module._export_service = None
        
        service1 = get_export_service()
        service2 = get_export_service()
        
        assert service1 is service2
        assert isinstance(service1, ExportService)
    
    def test_get_export_service_creates_new_if_none(self):
        """Test get_export_service creates new instance if none exists."""
        import app.services.export_service as export_module
        export_module._export_service = None
        
        service = get_export_service()
        
        assert service is not None
        assert isinstance(service, ExportService)
        assert export_module._export_service is service


class TestExportServiceEdgeCases:
    """Test edge cases and error conditions."""
    
    @pytest.mark.asyncio
    async def test_aggregate_with_unknown_user(self, export_service):
        """Test aggregation handles missing Resource field."""
        with patch.object(export_service, 'initialize', new_callable=AsyncMock):
            mock_cursor = AsyncMock()
            mock_logs = [
                {
                    "Attributes": {
                        "original_text": "Message without user",
                        "is_hot": False,
                        "lexical_variety": 0.5
                    }
                }
            ]
            mock_cursor.to_list = AsyncMock(return_value=mock_logs)
            
            export_service._db = MagicMock()
            export_service._db.activity_logs.find.return_value = mock_cursor
            
            result = await export_service.aggregate_activity_by_group("group1")
            
            assert len(result) == 1
            assert result[0]["user_id"] == "unknown"
    
    @pytest.mark.asyncio
    async def test_aggregate_with_missing_attributes(self, export_service):
        """Test aggregation handles missing Attributes field."""
        with patch.object(export_service, 'initialize', new_callable=AsyncMock):
            mock_cursor = AsyncMock()
            mock_logs = [
                {
                    "Resource": "user1"
                }
            ]
            mock_cursor.to_list = AsyncMock(return_value=mock_logs)
            
            export_service._db = MagicMock()
            export_service._db.activity_logs.find.return_value = mock_cursor
            
            result = await export_service.aggregate_activity_by_group("group1")
            
            assert len(result) == 1
            assert result[0]["message_count"] == 1
            assert result[0]["word_count"] == 0  # No text
    
    def test_generate_csv_with_missing_fields(self, export_service):
        """Test CSV generation handles missing fields."""
        user_metrics = [
            {
                "name": "Test User"
                # Missing other fields
            }
        ]
        
        csv_string = export_service.generate_csv_string(user_metrics, include_detailed=True)
        
        assert "Test User" in csv_string
        # Should use defaults for missing fields
        assert "0" in csv_string


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
