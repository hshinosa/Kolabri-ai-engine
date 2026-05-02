"""
Test Configuration and Shared Fixtures for Kolabri AI-Engine
==========================================================

Uses patterns from python-testing-patterns skill:
- Session-scoped fixtures for expensive resources
- Auto-use fixtures for common setup
- Async fixtures for FastAPI testing
"""

import sys
from unittest.mock import MagicMock

# Global Mocks for Heavy Modules
sys.modules['qdrant_client'] = MagicMock()
sys.modules['qdrant_client.models'] = MagicMock()
sys.modules['qdrant_client.http'] = MagicMock()
sys.modules['fastembed'] = MagicMock()
sys.modules['chromadb'] = MagicMock()
sys.modules['chromadb.config'] = MagicMock()
sys.modules['chromadb.utils'] = MagicMock()
sys.modules['hnswlib'] = MagicMock()
sys.modules['pypdf'] = MagicMock()
sys.modules['fitz'] = MagicMock()
sys.modules['docx'] = MagicMock()
sys.modules['pptx'] = MagicMock()
sys.modules['openpyxl'] = MagicMock()
sys.modules['pandas'] = MagicMock()
_numpy_mock = MagicMock()
_numpy_mock.floating = float
_numpy_mock.integer = int
_numpy_mock.ndarray = list
_numpy_mock.float64 = float
_numpy_mock.float32 = float
_numpy_mock.int64 = int
_numpy_mock.int32 = int
_numpy_mock.bool_ = bool
sys.modules['numpy'] = _numpy_mock
_pil_mock = MagicMock()

class _FakeImage:
    def __init__(self, mode="RGB", size=(100, 100)):
        self.mode = mode
        self.size = size
        self.width = size[0]
        self.height = size[1]
    def convert(self, mode):
        return _FakeImage(mode, self.size)
    def thumbnail(self, size, *args, **kwargs):
        self.size = size
        self.width = size[0]
        self.height = size[1]
    def resize(self, size, *args, **kwargs):
        return _FakeImage(self.mode, size)
    def close(self):
        pass
    def tobytes(self):
        return b'\x00' * (self.width * self.height * 3)
    def save(self, fp=None, *args, **kwargs):
        if fp and hasattr(fp, 'write'):
            fp.write(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100)

class _FakeResampling:
    LANCZOS = 1
    BICUBIC = 3

class _FakeImageModule:
    Image = _FakeImage
    Resampling = _FakeResampling
    LANCZOS = 1
    BICUBIC = 3
    new = staticmethod(lambda mode, size, *a, **kw: _FakeImage(mode, size))
    frombytes = staticmethod(lambda mode, size, data, *a, **kw: _FakeImage(mode, size))
    @staticmethod
    def open(fp, *a, **kw):
        PNG_MAGIC = b'\x89PNG'
        JPEG_MAGIC = b'\xff\xd8\xff'
        if isinstance(fp, bytes):
            data = fp
        elif hasattr(fp, 'read'):
            data = fp.read(16)
            if hasattr(fp, 'seek'):
                fp.seek(0)
        else:
            data = b''
        if not (data[:4] == PNG_MAGIC or data[:3] == JPEG_MAGIC):
            raise Exception("cannot identify image file")
        return _FakeImage("RGB", (200, 200))

_pil_mock.Image = _FakeImageModule
sys.modules['PIL'] = _pil_mock
sys.modules['PIL.Image'] = _FakeImageModule
sys.modules['motor'] = MagicMock()
sys.modules['motor.motor_asyncio'] = MagicMock()
sys.modules['redis.asyncio'] = MagicMock()
sys.modules['redis'] = MagicMock()
sys.modules['prometheus_client'] = MagicMock()
sys.modules['psutil'] = MagicMock()

import pytest
import asyncio
from typing import Generator, AsyncGenerator
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from datetime import datetime
from fastapi import FastAPI
from fastapi.testclient import TestClient
from contextlib import asynccontextmanager
import httpx

# Import project modules
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# ==============================================================================
# MOCK FIXTURES (For unit tests without real dependencies)
# ==============================================================================

@pytest.fixture
def mock_mongo_logger() -> Mock:
    """Mock MongoDB logger for unit tests."""
    mock = MagicMock()
    mock.connect = AsyncMock()
    mock.log_activity = AsyncMock()
    mock.log_intervention = AsyncMock()
    mock.export_to_csv = AsyncMock(return_value="header1,header2\nrow1,row2")
    
    # Mock get_activity_logs
    async def mock_get_logs(**kwargs):
        case_id = kwargs.get("case_id") or kwargs.get("chat_space_id")
        resource = kwargs.get("resource") or kwargs.get("user_id")
        
        if not case_id and not resource:
            return []
        
        return [
            {
                "_id": "mock_id_1",
                "CaseID": case_id or "mock_case",
                "Activity": "Student_Message",
                "Timestamp": datetime.now(),
                "Resource": resource or "Student_1",
                "Attributes": {
                    "original_text": "Test message",
                    "srl_object": "Test_Object",
                    "educational_category": "Cognitive",
                    "is_hot": True,
                    "lexical_variety": 0.5,
                    "scaffolding_trigger": False
                }
            }
        ]
    
    mock.get_activity_logs.side_effect = mock_get_logs
    
    return mock


@pytest.fixture
def mock_vector_store() -> Mock:
    """Mock vector store for unit tests."""
    mock = MagicMock()
    
    mock.search = AsyncMock(return_value=[
        {
            "content": "Mock content",
            "metadata": {"source": "test_document.pdf", "page": 1, "course_id": "test"},
            "score": 0.85
        }
    ])
    
    mock.add_documents = AsyncMock(return_value=None)
    mock._ensure_collection = AsyncMock()
    
    return mock


@pytest.fixture
def mock_llm_service() -> Mock:
    """Mock LLM service for unit tests."""
    from app.services.llm import LLMResponse
    
    mock = MagicMock()
    
    mock.generate = AsyncMock(return_value=LLMResponse(
        content="Mock LLM response",
        tokens_used=50,
        model="mock-model",
        success=True
    ))
    
    mock.generate_rag_response = AsyncMock(return_value=LLMResponse(
        content="RAG response",
        tokens_used=75,
        model="mock-rag-model",
        success=True
    ))
    
    mock.reframe_to_socratic = AsyncMock(return_value=LLMResponse(
        content="Socratic version",
        tokens_used=30,
        model="mock-model",
        success=True
    ))
    
    mock.model = "mock-model"
    
    return mock


@pytest.fixture
def mock_analyzer() -> Mock:
    """Mock engagement analyzer for unit tests."""
    from app.services.nlp_analytics import EngagementAnalysis, EngagementType
    
    mock = MagicMock()
    
    def mock_analyze(text):
        is_hot = ("analisis" in text.lower() or "evaluate" in text.lower() or "evaluasi" in text.lower())
        return EngagementAnalysis(
            lexical_variety=0.5 if len(set(text.split())) / (len(text.split()) or 1) > 0.3 else 0.2,
            engagement_type=EngagementType.COGNITIVE if is_hot else EngagementType.BEHAVIORAL,
            is_higher_order=is_hot,
            hot_indicators=["analisis"] if is_hot else [],
            word_count=len(text.split()),
            unique_words=len(set(text.split())),
            confidence=0.8
        )
    
    mock.analyze_interaction.side_effect = mock_analyze
    mock.get_discussion_quality_score.return_value = {"quality_score": 75.0, "recommendation": "Good"}
    mock.extract_srl_object.return_value = "General"
    
    return mock


@pytest.fixture
def mock_notification_service() -> Mock:
    """Mock notification service for unit tests."""
    mock = MagicMock()
    
    mock.send_intervention = AsyncMock(return_value=True)
    mock.notify_teacher = AsyncMock(return_value=True)
    
    return mock


# ==============================================================================
# APP FIXTURES (For integration tests with real FastAPI app)
# ==============================================================================

@pytest.fixture(scope="function")
def app() -> FastAPI:
    """
    Create FastAPI application with test configuration.
    
    Overrides settings for testing environment.
    """
    # Force reload of app components to ensure they use mocked settings
    import sys
    import importlib
    from contextlib import asynccontextmanager
    
    # Modules to reload if they've been imported
    modules_to_reload = [
        'app.core.config',
        'app.services.vector_store',
        'app.services.mongodb_logger',
        'app.services.logic_listener',
        'app.services.notification_service',
        'app.api.routes',
        'main'
    ]
    
    for mod in modules_to_reload:
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])
    
    from main import app as fastapi_app
    
    # Replace lifespan with a mock to avoid starting background tasks/real DB connections
    @asynccontextmanager
    async def mock_lifespan(app):
        yield
        
    fastapi_app.router.lifespan_context = mock_lifespan
    
    return fastapi_app


@pytest.fixture
def test_client(app: FastAPI) -> Generator[TestClient, None, None]:
    """
    Create TestClient for FastAPI application.
    
    This uses synchronous client which is easier for most tests.
    For async testing, use async_httpx_client fixture instead.
    """
    return TestClient(app)


@pytest.fixture
async def async_httpx_client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    Create async HTTPX client for testing FastAPI endpoints asynchronously.
    
    Required for testing endpoints that use dependencies with async operations.
    """
    from fastapi.testclient import TestClient
    
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        yield client


# ==============================================================================
# DATA FIXTURES
# ==============================================================================

@pytest.fixture
def sample_valid_goal() -> str:
    """Sample valid SMART goal."""
    return "Membuat prototype aplikasi to-do list menggunakan React dan Redux dengan fitur CRUD yang lengkap dalam waktu 5 hari"


@pytest.fixture
def sample_invalid_goal() -> str:
    """Sample invalid goal (missing SMART criteria)."""
    return "Belajar React"


@pytest.fixture
def sample_student_message() -> str:
    """Sample student message with HOT indicators."""
    return "Saya menganalisis struktur database dan menemukan bahwa ada redundant data yang bisa dioptimasi"


@pytest.fixture
def sample_course_material() -> str:
    """Sample course material for RAG testing."""
    return """
    React adalah JavaScript library untuk membangun antarmuka pengguna.
    React menggunakan konsep komponen yang bersifat reusable.
    State management di React dapat dilakukan dengan hooks seperti useState dan useEffect.
    Redux adalah library untuk state management global yang populer di ekosistem React.
    """


@pytest.fixture
def sample_chat_messages() -> list:
    """Sample chat messages for intervention testing."""
    return [
        {"sender": "student_1", "content": "Halo semua", "timestamp": "2024-01-01T10:00:00"},
        {"sender": "student_2", "content": "Halo", "timestamp": "2024-01-01T10:01:00"},
        {"sender": "student_1", "content": "Mari kita mulai diskusi tentang database", "timestamp": "2024-01-01T10:02:00"},
        {"sender": "student_3", "content": "Saya agree, mari kita bahas tentang normalization", "timestamp": "2024-01-01T10:03:00"},
    ]


# ==============================================================================
# TEMPORARY FILE FIXTURES
# ==============================================================================

@pytest.fixture
def temp_upload_file(tmp_path) -> str:
    """
    Create a temporary test file for upload testing.
    
    Returns path to the created file.
    """
    test_file = tmp_path / "test_document.txt"
    test_file.write_text("This is a test document for upload testing.")
    return str(test_file)


@pytest.fixture
def temp_pdf_file(tmp_path) -> str:
    """
    Create a temporary PDF file for document processing testing.
    
    Note: This creates a minimal valid PDF structure for testing.
    """
    from pypdf import PdfWriter
    
    pdf_file = tmp_path / "test_document.pdf"
    pdf_writer = PdfWriter()
    pdf_writer.add_blank_page(width=200, height=200)
    
    with open(pdf_file, "wb") as f:
        pdf_writer.write(f)
    
    return str(pdf_file)


# ==============================================================================
# AUTO-USE FIXTURES
# ==============================================================================

@pytest.fixture(autouse=True)
def reset_singletons():
    """
    Reset singleton instances before each test.
    
    This ensures test isolation by preventing state leakage between tests.
    """
    yield
    
    # Reset singletons if needed
    from app.services.llm import _llm_service
    from app.services.rag import _rag_pipeline
    from app.services.nlp_analytics import _analyzer
    from app.services.goal_validator import _goal_validator
    from app.services.logic_listener import _logic_listener
    from app.services.orchestration import _orchestrator
    from app.services.efficiency_guard import _efficiency_guard
    
    # Reset to None for next test
    _llm_service = None
    _rag_pipeline = None
    _analyzer = None
    _goal_validator = None
    _logic_listener = None
    _orchestrator = None
    _efficiency_guard = None


# ==============================================================================
# CUSTOM MARKERS
# ==============================================================================

def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )
    config.addinivalue_line(
        "markers", "e2e: marks tests as end-to-end tests"
    )
    config.addinivalue_line(
        "markers", "requires_llm: marks tests that require LLM API connection"
    )
    config.addinivalue_line(
        "markers", "requires_mongodb: marks tests that require MongoDB connection"
    )
