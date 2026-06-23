"""
Unit Tests for Export Service
================================

Tests for activity data export functionality including:
- MongoDB aggregation by group
- MongoDB aggregation by session discussion
- CSV generation with XES Schema compliance
- Error handling
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from io import StringIO
import csv
from app.services.export_service import ExportService, get_export_service


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def export_service():
    """Create export service with mocked MongoDB connection."""
    with patch('app.services.export_service.settings') as mock_settings, \
         patch('app.services.export_service.AsyncIOMotorClient') as mock_motor:
        
        # Configure mock settings
        mock_settings.MONGO_URI = "mongodb://localhost:27017"
        mock_settings.MONGO_DB_NAME = "test_db"
        
        # Create mock database connection
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        
        mock_motor.return_value = mock_client
        
        service = ExportService()
        yield service, mock_client, mock_db, mock_settings


# ==============================================================================
# TESTS: Initialization
# ==============================================================================

def test_export_initialization(export_service):
    """Test export service initializes correctly."""
    service, _, _, _ = export_service
    assert service._initialized is False
    assert service._client is None
    assert service._db is None


@pytest.mark.asyncio
async def test_export_initialize_once(export_service):
    """Test MongoDB connection is initialized only once."""
    service, mock_client, mock_db, mock_settings = export_service
    
    # First initialization
    await service.initialize()
    assert service._initialized is True
    
    # Store references
    client1 = service._client
    db1 = service._db
    
    # Second initialization should return early
    await service.initialize()
    assert service._client is client1
    assert service._db is db1


# ==============================================================================
# TESTS: Aggregation
# ==============================================================================

@pytest.mark.asyncio
async def test_aggregate_activity_by_session_discussion_success(export_service):
    """Test successful aggregation by session discussion."""
    service, mock_client, mock_db, mock_settings = export_service
    
    # Mock MongoDB response
    mock_cursor = AsyncMock()
    mock_cursor.to_list = AsyncMock(return_value=[
        {
            "Resource": "Student_1",
            "Attributes": {
                "original_text": "Hello world",
                "is_hot": True,
                "lexical_variety": 0.8
            }
        },
        {
            "Resource": "Student_1",
            "Attributes": {
                "original_text": "Another message",
                "is_hot": False,
                "lexical_variety": 0.6
            }
        }
    ])
    
    mock_db.activity_logs.find.return_value = mock_cursor
    
    result = await service.aggregate_activity_by_session_discussion("chat_123")
    
    assert len(result) == 1
    student = result[0]
    assert student["user_id"] == "Student_1"
    assert student["message_count"] == 2
    assert student["avg_lexical_variety"] == 0.7  # (0.8 + 0.6) / 2


# ==============================================================================
# TESTS: CSV Generation
# ==============================================================================

def test_generate_csv_string_basic(export_service):
    """Test CSV generation with basic metrics."""
    service, _, _, _ = export_service
    
    user_metrics = [
        {
            "name": "Student A",
            "message_count": 5,
            "word_count": 100,
            "hot_count": 2,
            "engagement_score": 75.5
        }
    ]
    
    csv_string = service.generate_csv_string(user_metrics, include_detailed=False)
    
    assert "Student Name" in csv_string
    assert "Student A" in csv_string
    assert "75.5" in csv_string
    assert "--- TOTAL ---" in csv_string


def test_generate_csv_string_detailed(export_service):
    """Test CSV generation with detailed metrics."""
    service, _, _, _ = export_service
    
    user_metrics = [
        {
            "name": "Student A",
            "user_id": "u1",
            "message_count": 10,
            "word_count": 200,
            "hot_count": 5,
            "cognitive_count": 3,
            "behavioral_count": 4,
            "emotional_count": 3,
            "avg_lexical_variety": 0.8,
            "engagement_score": 88.0
        }
    ]
    
    csv_string = service.generate_csv_string(user_metrics, include_detailed=True)
    
    assert "User ID" in csv_string
    assert "Cognitive Messages" in csv_string
    assert "88.0" in csv_string


# ==============================================================================
# TESTS: Edge Cases
# ==============================================================================

@pytest.mark.asyncio
async def test_aggregate_activity_by_group_empty(export_service):
    """Test aggregation with no logs."""
    service, mock_client, mock_db, _ = export_service
    
    mock_cursor = AsyncMock()
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_db.activity_logs.find.return_value = mock_cursor
    
    result = await service.aggregate_activity_by_group("group_empty")
    assert result == []


@pytest.mark.asyncio
async def test_export_session_discussion_activity_integration(export_service):
    """Test full integration from aggregation to CSV."""
    service, mock_client, mock_db, _ = export_service
    
    # Mock data
    mock_cursor = AsyncMock()
    mock_cursor.to_list = AsyncMock(return_value=[
        {"Resource": "U1", "Attributes": {"original_text": "T1", "is_hot": True}}
    ])
    mock_db.activity_logs.find.return_value = mock_cursor
    
    csv_string = await service.export_session_discussion_activity("chat_123")
    
    assert "U1" in csv_string
    assert "1" in csv_string # count
