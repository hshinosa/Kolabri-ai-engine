import sys
from unittest.mock import AsyncMock, MagicMock, patch

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

import pytest
import asyncio

from app.services.vector_store import VectorStoreService, OpenAIEmbeddingFunction, get_vector_store

@pytest.fixture
def mock_chroma():
    with patch('chromadb.PersistentClient') as mock_client:
        client_inst = MagicMock()
        mock_client.return_value = client_inst
        yield client_inst

@pytest.fixture
def vector_store(mock_chroma):
    with patch('app.services.vector_store.get_embedding_service'):
        service = VectorStoreService()
        with patch('os.makedirs'):
            service._client = mock_chroma
            service._initialized = True
        return service

@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_collection_reinit_logic(mock_chroma):
    service = VectorStoreService()
    async def mock_init_impl():
        service._client = mock_chroma
        service._initialized = True
    with patch.object(service, 'initialize', side_effect=mock_init_impl) as mock_init:
        service._initialized = False
        await service._ensure_collection('test')
        mock_init.assert_called_once()

@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_collection_stats_robust(vector_store, mock_chroma):
    mock_coll = MagicMock()
    mock_coll.count.return_value = 10
    mock_chroma.get_or_create_collection.return_value = mock_coll
    stats = await vector_store.get_collection_stats('course1')
    assert stats['document_count'] == 10

@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_collections_robust(vector_store, mock_chroma):
    c1 = MagicMock(); c1.name = 'kolabri_c1'; c1.count.return_value = 5; c1.metadata = {'m': 1}
    mock_chroma.list_collections.return_value = [c1]
    res = await vector_store.list_collections()
    assert len(res) == 1
    # Check what the actual key is
    assert res[0]['name'] == 'kolabri_c1'

@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_documents_robust(vector_store, mock_chroma):
    mock_coll = MagicMock()
    mock_chroma.get_or_create_collection.return_value = mock_coll
    await vector_store.delete_documents(ids=['id1'], collection_name='test')
    mock_coll.delete.assert_called_with(ids=['id1'])
