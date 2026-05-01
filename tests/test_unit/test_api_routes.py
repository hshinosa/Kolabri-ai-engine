import sys
from unittest.mock import MagicMock, AsyncMock, patch
import pytest

# Mock heavier modules before anything
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
sys.modules['numpy'] = MagicMock()
sys.modules['PIL'] = MagicMock()
sys.modules['motor'] = MagicMock()
sys.modules['motor.motor_asyncio'] = MagicMock()
sys.modules['redis.asyncio'] = MagicMock()
sys.modules['redis'] = MagicMock()
sys.modules['prometheus_client'] = MagicMock()

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)

@patch('app.services.llm.get_llm_service')
@patch('app.api.routes.get_vector_store')
@patch('app.api.routes.get_llm_service')
def test_health_check_healthy(mock_llm, mock_vs, mock_llm_svc):
    mock_vs_instance = MagicMock()
    mock_vs_instance._ensure_collection = AsyncMock()
    mock_vs.return_value = mock_vs_instance
    
    mock_llm_instance = MagicMock()
    mock_llm_instance.model = "test-model"
    mock_llm.return_value = mock_llm_instance
    mock_llm_svc.return_value = mock_llm_instance
    
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

@patch('app.api.routes.get_vector_store')
@patch('app.api.routes.get_llm_service')
def test_health_check_degraded(mock_llm, mock_vs):
    mock_vs_instance = MagicMock()
    mock_vs_instance._ensure_collection = AsyncMock(side_effect=Exception("Failed"))
    mock_vs.return_value = mock_vs_instance
    
    mock_llm_instance = MagicMock()
    mock_llm_instance.model = None
    mock_llm.return_value = mock_llm_instance
    
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"

@patch('app.api.routes.get_rag_pipeline')
def test_ask_question_success(mock_rag):
    mock_pipeline = MagicMock()
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.answer = "This is a test answer"
    mock_result.sources = [{"source": "test.pdf", "page": 1}]
    mock_pipeline.query = AsyncMock(return_value=mock_result)
    mock_rag.return_value = mock_pipeline
    
    payload = {
        "query": "test query",
        "course_id": "test_course"
    }
    
    response = client.post("/ask", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "This is a test answer" in data["answer"]
    assert "test.pdf" in data["answer"]

@patch('app.api.routes.get_rag_pipeline')
def test_ask_question_failure(mock_rag):
    mock_pipeline = MagicMock()
    mock_result = MagicMock()
    mock_result.success = False
    mock_result.error = "Test Error"
    mock_pipeline.query = AsyncMock(return_value=mock_result)
    mock_rag.return_value = mock_pipeline
    
    payload = {
        "query": "test query",
        "course_id": "test_course"
    }
    
    response = client.post("/ask", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "Maaf, saya tidak bisa menemukan jawaban" in data["answer"]

@patch('app.api.routes.get_engagement_analyzer')
def test_analyze_engagement(mock_analyzer):
    mock_analyzer_instance = MagicMock()
    mock_analysis = MagicMock()
    mock_analysis.lexical_variety = 0.8
    mock_analysis.engagement_type.value = "cognitive"
    mock_analysis.is_higher_order = True
    mock_analysis.hot_indicators = ["analyze"]
    mock_analyzer_instance.analyze_interaction.return_value = mock_analysis
    mock_analyzer.return_value = mock_analyzer_instance
    
    payload = {"text": "This is a test where we analyze things."}
    response = client.post("/analytics/engagement", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["lexical_variety"] == 0.8
    assert data["engagement_type"] == "cognitive"

@patch('app.api.routes.get_orchestrator')
def test_get_group_dashboard(mock_orchestrator):
    mock_orch_instance = MagicMock()
    mock_orch_instance.get_group_dashboard_data = AsyncMock(return_value={"group": "data"})
    mock_orchestrator.return_value = mock_orch_instance
    
    response = client.get("/analytics/dashboard/group/test-group")
    assert response.status_code == 200
    assert response.json() == {"group": "data"}

@patch('app.api.routes.get_orchestrator')
def test_get_individual_dashboard(mock_orchestrator):
    mock_orch_instance = MagicMock()
    mock_orch_instance.get_individual_dashboard_data = AsyncMock(return_value={"individual": "data"})
    mock_orchestrator.return_value = mock_orch_instance
    
    response = client.get("/analytics/dashboard/individual/test-user")
    assert response.status_code == 200
    assert response.json() == {"individual": "data"}
