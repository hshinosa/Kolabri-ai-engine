import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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


def make_llm_response(content: str, tokens: int = 123):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(total_tokens=tokens),
    )


async def make_stream(chunks):
    for content in chunks:
        yield SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=content))]
        )


def make_orchestration_result(**overrides):
    data = {
        "success": True,
        "reply": "Bot reply",
        "intervention": None,
        "intervention_type": None,
        "action_taken": "FETCH",
        "should_notify_teacher": False,
        "quality_score": 0.92,
        "analytics": {"source": "test"},
        "error": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def make_intervention_result(**overrides):
    data = {
        "success": True,
        "should_intervene": True,
        "message": "Intervene now",
        "intervention_type": SimpleNamespace(value="redirect"),
        "confidence": 0.88,
        "reason": "off-topic",
        "error": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@patch('app.api.routes.get_rag_pipeline')
def test_ask_question_success_without_sources(mock_rag):
    mock_pipeline = MagicMock()
    mock_result = MagicMock(success=True, answer="Jawaban ringkas", sources=[])
    mock_pipeline.query = AsyncMock(return_value=mock_result)
    mock_rag.return_value = mock_pipeline

    response = client.post('/ask', json={'query': 'apa itu ai?', 'course_id': 'if101'})

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert data['answer'] == 'Jawaban ringkas'


@patch('app.api.routes.get_rag_pipeline')
def test_ask_question_invalid_course_id_returns_safe_failure(mock_rag):
    response = client.post('/ask', json={'query': 'tes', 'course_id': 'bad id!'})

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is False
    assert 'Maaf, terjadi kesalahan' in data['answer']
    mock_rag.assert_not_called()


@patch('app.api.routes.get_rag_pipeline')
def test_ask_question_pipeline_exception(mock_rag):
    mock_pipeline = MagicMock()
    mock_pipeline.query = AsyncMock(side_effect=Exception('rag down'))
    mock_rag.return_value = mock_pipeline

    response = client.post('/ask', json={'query': 'tes', 'course_id': 'if101'})

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is False
    assert data['error'] == 'rag down'


@patch('app.api.routes.get_llm_service')
def test_personal_chat_success(mock_get_llm):
    mock_llm = MagicMock()
    mock_llm.model = 'gpt-test'
    mock_llm.client.chat.completions.create = AsyncMock(
        return_value=make_llm_response('Halo juga', 77)
    )
    mock_get_llm.return_value = mock_llm

    payload = {
        'message': 'Halo',
        'history': [{'role': 'user', 'content': 'Hai sebelumnya'}],
        'user_name': 'Budi',
    }
    response = client.post('/chat/personal', json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert data['reply'] == 'Halo juga'
    assert data['tokens_used'] == 77


@patch('app.api.routes.get_llm_service')
def test_personal_chat_failure(mock_get_llm):
    mock_llm = MagicMock()
    mock_llm.model = 'gpt-test'
    mock_llm.client.chat.completions.create = AsyncMock(side_effect=Exception('llm failed'))
    mock_get_llm.return_value = mock_llm

    response = client.post('/chat/personal', json={'message': 'Halo', 'history': []})

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is False
    assert data['reply'].startswith('Maaf')
    assert data['error'] == 'llm failed'


@patch('app.api.routes.get_llm_service')
def test_personal_chat_stream_success(mock_get_llm):
    mock_llm = MagicMock()
    mock_llm.model = 'gpt-test'
    mock_llm.client.chat.completions.create = AsyncMock(
        return_value=make_stream(['Halo', ' dunia'])
    )
    mock_get_llm.return_value = mock_llm

    response = client.post('/chat/personal/stream', json={'message': 'Halo', 'history': []})

    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/event-stream')
    assert 'data: {"content": "Halo"}' in response.text
    assert 'data: [DONE]' in response.text


@patch('app.api.routes.get_llm_service')
def test_personal_chat_stream_failure_event(mock_get_llm):
    mock_llm = MagicMock()
    mock_llm.model = 'gpt-test'
    mock_llm.client.chat.completions.create = AsyncMock(side_effect=Exception('stream failed'))
    mock_get_llm.return_value = mock_llm

    response = client.post('/chat/personal/stream', json={'message': 'Halo', 'history': []})

    assert response.status_code == 200
    assert 'stream failed' in response.text


@patch('app.api.routes._process_ingest_background', new_callable=AsyncMock)
def test_ingest_document_success(mock_background_task):
    response = client.post(
        '/ingest',
        data={'course_id': 'if101', 'file_id': 'file-1'},
        files={'file': ('materi.txt', b'konten singkat', 'text/plain')},
    )

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert data['file_id'] == 'file-1'
    assert data['file_type'] == 'txt'
    mock_background_task.assert_awaited_once()


@patch('app.api.routes._process_ingest_background', new_callable=AsyncMock)
def test_ingest_document_rejects_unsupported_extension(mock_background_task):
    response = client.post(
        '/ingest',
        data={'course_id': 'if101', 'file_id': 'file-2'},
        files={'file': ('script.exe', b'binary', 'application/octet-stream')},
    )

    assert response.status_code == 400
    assert 'Unsupported file type' in response.json()['detail']
    mock_background_task.assert_not_awaited()


@patch.object(__import__('app.api.routes', fromlist=['settings']).settings, 'MAX_UPLOAD_SIZE_MB', 0)
@patch('app.api.routes._process_ingest_background', new_callable=AsyncMock)
def test_ingest_document_rejects_oversized_file(mock_background_task):
    response = client.post(
        '/ingest',
        data={'course_id': 'if101', 'file_id': 'file-3'},
        files={'file': ('materi.txt', b'x', 'text/plain')},
    )

    assert response.status_code == 400
    assert response.json()['detail'] == 'File size exceeds limit'
    mock_background_task.assert_not_awaited()


@patch('app.api.routes._process_batch_file_background', new_callable=AsyncMock)
def test_ingest_batch_success(mock_background_task):
    response = client.post(
        '/ingest/batch',
        data={'course_id': 'if101', 'extract_images': 'true', 'perform_ocr': 'false'},
        files=[
            ('files', ('a.txt', b'alpha', 'text/plain')),
            ('files', ('b.md', b'beta', 'text/markdown')),
        ],
    )

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert data['total_files'] == 2
    assert '2 dokumen sedang diproses' in data['message']
    assert mock_background_task.await_count == 2


@patch('app.api.routes.tempfile.NamedTemporaryFile', side_effect=Exception('disk full'))
def test_ingest_batch_returns_400_when_no_valid_files(mock_tempfile):
    response = client.post(
        '/ingest/batch',
        data={'course_id': 'if101', 'extract_images': 'true', 'perform_ocr': 'false'},
        files=[('files', ('a.txt', b'alpha', 'text/plain'))],
    )

    assert response.status_code == 400
    assert response.json()['detail'] == 'No valid files provided'
    mock_tempfile.assert_called_once()


@patch('app.api.routes.get_orchestrator')
def test_validate_goal_success(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.validate_goal = AsyncMock(
        return_value={'is_valid': True, 'score': 0.9, 'feedback': 'bagus'}
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.post(
        '/goals/validate',
        data={'goal_text': 'Belajar AI minggu ini', 'user_id': 'u1', 'chat_space_id': 'c1'},
    )

    assert response.status_code == 200
    data = response.json()
    assert data['is_valid'] is True
    assert data['score'] == 0.9


@patch('app.api.routes.get_orchestrator')
def test_validate_goal_failure(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.validate_goal = AsyncMock(side_effect=Exception('service unavailable'))
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.post(
        '/goals/validate',
        data={'goal_text': 'Belajar AI', 'user_id': 'u1', 'chat_space_id': 'c1'},
    )

    assert response.status_code == 500
    assert 'Failed to validate goal' in response.json()['detail']


@patch('app.api.routes.get_orchestrator')
def test_goal_refinement_success(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.get_goal_refinement = AsyncMock(
        return_value={'success': True, 'hint': 'Tambahkan target terukur'}
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.post(
        '/goals/refine',
        data={'current_goal': 'Mau jago AI', 'missing_criteria': '["specific", "measurable"]'},
    )

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert 'hint' in data


@patch('app.api.routes.get_orchestrator')
def test_goal_refinement_invalid_json(mock_get_orchestrator):
    response = client.post(
        '/goals/refine',
        data={'current_goal': 'Mau jago AI', 'missing_criteria': 'not-json'},
    )

    assert response.status_code == 400
    assert response.json()['detail'] == 'Invalid JSON format for missing_criteria'
    mock_get_orchestrator.assert_not_called()


@patch('app.api.routes.get_orchestrator')
def test_goal_refinement_failure(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.get_goal_refinement = AsyncMock(side_effect=Exception('llm timeout'))
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.post(
        '/goals/refine',
        data={'current_goal': 'Mau jago AI', 'missing_criteria': '["time-bound"]'},
    )

    assert response.status_code == 500
    assert 'Failed to get refinement' in response.json()['detail']


@patch('app.api.routes.get_orchestrator')
def test_check_group_status_success(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.check_group_status = AsyncMock(
        return_value={'should_intervene': True, 'interventions': ['prompt']}
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.get('/groups/group-1/status', params={'topic': 'AI ethics'})

    assert response.status_code == 200
    assert response.json()['should_intervene'] is True


@patch('app.api.routes.get_orchestrator')
def test_track_participation_success(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.track_participation = AsyncMock(return_value={'success': True, 'tracked': True})
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.post('/groups/group-1/track-participation', data={'user_id': 'user-1'})

    assert response.status_code == 200
    assert response.json()['tracked'] is True


@patch('app.api.routes.get_orchestrator')
def test_update_last_message_time_success(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.update_last_message_time = AsyncMock(return_value={'success': True, 'updated': True})
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.post('/groups/group-1/update-last-message')

    assert response.status_code == 200
    assert response.json()['updated'] is True


@patch('app.api.routes.get_orchestrator')
def test_set_group_topic_success(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.set_group_topic = AsyncMock(return_value={'success': True, 'topic': 'AI ethics'})
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.post('/groups/group-1/set-topic', data={'topic': 'AI ethics'})

    assert response.status_code == 200
    assert response.json()['topic'] == 'AI ethics'


@patch.object(__import__('app.api.routes', fromlist=['settings']).settings, 'ENABLE_EFFICIENCY_GUARD', True)
@patch('app.api.routes.get_efficiency_guard')
def test_get_cache_statistics_enabled(mock_get_guard):
    mock_guard = MagicMock()
    mock_guard.get_cache_statistics.return_value = {
        'cache_hits': 10,
        'cache_misses': 5,
        'hit_rate_percent': 66.7,
    }
    mock_get_guard.return_value = mock_guard

    response = client.get('/efficiency/cache/statistics')

    assert response.status_code == 200
    data = response.json()
    assert data['enabled'] is True
    assert data['cache_hits'] == 10


@patch.object(__import__('app.api.routes', fromlist=['settings']).settings, 'ENABLE_EFFICIENCY_GUARD', False)
def test_get_cache_statistics_disabled():
    response = client.get('/efficiency/cache/statistics')

    assert response.status_code == 200
    assert response.json()['enabled'] is False


@patch.object(__import__('app.api.routes', fromlist=['settings']).settings, 'ENABLE_EFFICIENCY_GUARD', True)
@patch('app.api.routes.get_efficiency_guard')
def test_clear_cache_success(mock_get_guard):
    mock_guard = MagicMock()
    mock_get_guard.return_value = mock_guard

    response = client.get('/efficiency/cache/clear')

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    mock_guard.clear_cache.assert_called_once()


@patch.object(__import__('app.api.routes', fromlist=['settings']).settings, 'ENABLE_EFFICIENCY_GUARD', True)
@patch('app.api.routes.get_efficiency_guard')
def test_get_efficiency_statistics_enabled(mock_get_guard):
    mock_guard = MagicMock()
    mock_guard.get_statistics.return_value = {
        'rate_limit': {'total_requests': 12},
        'performance': {'cache_hit_rate_percent': 75.0},
    }
    mock_get_guard.return_value = mock_guard

    response = client.get('/efficiency/statistics')

    assert response.status_code == 200
    data = response.json()
    assert data['enabled'] is True
    assert data['rate_limit']['total_requests'] == 12


@patch.object(__import__('app.api.routes', fromlist=['settings']).settings, 'ENABLE_EFFICIENCY_GUARD', True)
@patch('app.api.routes.get_efficiency_guard')
def test_get_rate_limit_info_enabled(mock_get_guard):
    mock_guard = MagicMock()
    mock_guard.get_rate_limit_info.return_value = {
        'remaining_requests': 4,
        'is_allowed': True,
    }
    mock_get_guard.return_value = mock_guard

    response = client.get('/efficiency/rate-limit/user-1')

    assert response.status_code == 200
    data = response.json()
    assert data['enabled'] is True
    assert data['remaining_requests'] == 4


@patch.object(__import__('app.api.routes', fromlist=['settings']).settings, 'ENABLE_EFFICIENCY_GUARD', True)
@patch('app.api.routes.get_efficiency_guard')
def test_get_high_frequency_queries_enabled(mock_get_guard):
    mock_guard = MagicMock()
    mock_guard.get_high_frequency_queries.return_value = [
        {'query': 'apa itu ai?', 'count': 8},
        {'query': 'contoh ml', 'count': 5},
    ]
    mock_get_guard.return_value = mock_guard

    response = client.get('/efficiency/high-frequency-queries', params={'limit': 2})

    assert response.status_code == 200
    data = response.json()
    assert data['enabled'] is True
    assert len(data['queries']) == 2


@patch('app.api.routes.get_monitor')
def test_metrics_success(mock_get_monitor):
    mock_monitor = MagicMock()
    mock_monitor.get_metrics.return_value = 'requests_total 1\n'
    mock_monitor.get_content_type.return_value = 'text/plain; version=0.0.4'
    mock_get_monitor.return_value = mock_monitor

    response = client.get('/metrics')

    assert response.status_code == 200
    assert response.text == 'requests_total 1\n'
    assert response.headers['content-type'].startswith('text/plain')


@patch('app.api.routes.get_monitor')
def test_monitoring_status_success(mock_get_monitor):
    mock_monitor = MagicMock()
    mock_monitor.get_dashboard_data.return_value = {'status': 'ok', 'uptime': 100}
    mock_get_monitor.return_value = mock_monitor

    response = client.get('/health/monitoring')

    assert response.status_code == 200
    assert response.json()['status'] == 'ok'


@patch('app.api.routes.get_llm_circuit_breaker')
def test_get_circuit_breaker_status_success(mock_get_cb):
    mock_cb = MagicMock()
    mock_cb.get_metrics.return_value = {'state': 'closed', 'failures': 0}
    mock_get_cb.return_value = mock_cb

    response = client.get('/health/circuit-breakers')

    assert response.status_code == 200
    data = response.json()
    assert data['llm_service']['state'] == 'closed'


@patch('app.api.routes.get_reranker')
def test_get_reranker_status_success(mock_get_reranker):
    mock_reranker = MagicMock()
    mock_reranker.get_metrics.return_value = {'enabled': True, 'model': 'cross-encoder'}
    mock_get_reranker.return_value = mock_reranker

    response = client.get('/health/reranker')

    assert response.status_code == 200
    assert response.json()['enabled'] is True


@patch('app.api.routes.get_export_service')
def test_export_group_activity_csv_success(mock_get_export_service):
    mock_service = MagicMock()
    mock_service.export_group_activity_detailed = AsyncMock(return_value='name,count\nA,1\n')
    mock_get_export_service.return_value = mock_service

    response = client.get('/export/activity/group/group-1')

    assert response.status_code == 200
    assert response.text == 'name,count\nA,1\n'
    assert response.headers['content-type'].startswith('text/csv')


@patch('app.api.routes.get_export_service')
def test_export_chat_space_activity_csv_success(mock_get_export_service):
    mock_service = MagicMock()
    mock_service.export_chat_space_activity = AsyncMock(return_value='user,msg\nu1,halo\n')
    mock_get_export_service.return_value = mock_service

    response = client.get('/export/activity/chat-space/chat-1', params={'include_detailed': 'true'})

    assert response.status_code == 200
    assert response.text == 'user,msg\nu1,halo\n'
    assert 'attachment;' in response.headers['content-disposition']


@patch('app.services.mongodb_logger.get_mongo_logger')
def test_export_process_mining_case_csv_success(mock_get_mongo_logger):
    mock_logger = MagicMock()
    mock_logger.export_to_csv = AsyncMock(return_value='CaseID,Activity\n1,Start\n')
    mock_get_mongo_logger.return_value = mock_logger

    response = client.get('/export/process-mining/case/case-1')

    assert response.status_code == 200
    assert response.text == 'CaseID,Activity\n1,Start\n'
    assert response.headers['content-type'].startswith('text/csv')


@patch('app.api.routes.get_mongo_logger')
def test_analytics_export_json_success(mock_get_mongo_logger):
    mock_logger = MagicMock()
    mock_logger.export_to_csv = AsyncMock(return_value='CaseID,Activity\n1,Start\n1,End\n2,Start\n')
    mock_get_mongo_logger.return_value = mock_logger

    response = client.get('/analytics/export')

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert data['total_events'] == 3
    assert data['unique_cases'] == 2


@patch('app.api.routes.get_mongo_logger')
def test_analytics_export_csv_success(mock_get_mongo_logger):
    mock_logger = MagicMock()
    mock_logger.export_to_csv = AsyncMock(return_value='CaseID,Activity\n1,Start\n')
    mock_get_mongo_logger.return_value = mock_logger

    response = client.get('/analytics/export', params={'format': 'csv'})

    assert response.status_code == 200
    assert response.text == 'CaseID,Activity\n1,Start\n'
    assert response.headers['content-type'].startswith('text/csv')


@patch('app.api.routes.get_orchestrator')
def test_orchestrated_chat_success(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.handle_message = AsyncMock(
        return_value=make_orchestration_result(
            reply='Ini jawaban AI',
            intervention='Coba fokus ke topik',
            intervention_type='redirect',
        )
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    payload = {
        'user_id': 'u1',
        'group_id': 'g1',
        'message': 'Apa itu AI?',
        'topic': 'Artificial Intelligence',
        'collection_name': 'course_if101',
        'course_id': 'if101',
        'chat_room_id': 'room-1',
    }
    response = client.post('/chat', json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert data['bot_response'] == 'Ini jawaban AI'
    assert data['action_taken'] == 'FETCH'


@patch('app.api.routes.get_orchestrator')
def test_orchestrated_chat_failure(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.handle_message = AsyncMock(side_effect=Exception('pipeline error'))
    mock_get_orchestrator.return_value = mock_orchestrator

    payload = {'user_id': 'u1', 'group_id': 'g1', 'message': 'Apa itu AI?'}
    response = client.post('/chat', json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is False
    assert data['action_taken'] == 'ERROR'
    assert data['error'] == 'pipeline error'


@patch('app.api.routes.get_intervention_service')
def test_analyze_intervention_success(mock_get_service):
    mock_service = MagicMock()
    mock_service.analyze_and_intervene = AsyncMock(return_value=make_intervention_result())
    mock_get_service.return_value = mock_service

    payload = {
        'messages': [
            {'sender': 'Alice', 'content': 'Mari fokus', 'timestamp': '2025-01-01T00:00:00', 'sender_id': 'u1'}
        ],
        'topic': 'AI ethics',
        'chat_room_id': 'room-1',
    }
    response = client.post('/intervention/analyze', json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert data['should_intervene'] is True
    assert data['intervention_type'] == 'redirect'


@patch('app.api.routes.get_intervention_service')
def test_analyze_intervention_failure(mock_get_service):
    mock_service = MagicMock()
    mock_service.analyze_and_intervene = AsyncMock(side_effect=Exception('analysis failed'))
    mock_get_service.return_value = mock_service

    payload = {
        'messages': [{'sender': 'Alice', 'content': 'test'}],
        'topic': 'AI ethics',
        'chat_room_id': 'room-1',
    }
    response = client.post('/intervention/analyze', json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is False
    assert data['error'] == 'analysis failed'


@patch('app.api.routes.get_intervention_service')
def test_generate_summary_success(mock_get_service):
    mock_service = MagicMock()
    mock_service.generate_summary = AsyncMock(
        return_value=SimpleNamespace(success=True, message='Ringkasan diskusi', error=None)
    )
    mock_get_service.return_value = mock_service

    payload = {
        'messages': [
            {'sender': 'Alice', 'content': 'Pesan 1'},
            {'sender': 'Bob', 'content': 'Pesan 2'},
        ],
        'chat_room_id': 'room-1',
    }
    response = client.post('/intervention/summary', json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert data['summary'] == 'Ringkasan diskusi'
    assert data['message_count'] == 2


@patch('app.api.routes.get_intervention_service')
def test_generate_prompt_success(mock_get_service):
    mock_service = MagicMock()
    mock_service.generate_discussion_prompt = AsyncMock(
        return_value=SimpleNamespace(success=True, message='Apa dampak AI?', error=None)
    )
    mock_get_service.return_value = mock_service

    response = client.post(
        '/intervention/prompt',
        json={'topic': 'AI ethics', 'context': 'kelas 1', 'difficulty': 'medium'},
    )

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert data['prompt'] == 'Apa dampak AI?'
    assert data['topic'] == 'AI ethics'


@patch('app.api.routes.get_orchestrator')
def test_get_group_analytics_alias_success(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.get_group_dashboard_data = AsyncMock(
        return_value={
            'message_count': 20,
            'quality_score': 0.85,
            'quality_breakdown': {'clarity': 0.8},
            'recommendation': 'Pertahankan diskusi',
            'participants': ['u1', 'u2'],
            'participant_count': 2,
            'engagement_distribution': {'high': 2},
            'hot_percentage': 70.0,
        }
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.get('/analytics/group/group-1')

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert data['group_id'] == 'group-1'
    assert data['participant_count'] == 2


@patch('app.api.routes.get_vector_store')
def test_delete_document_success(mock_get_vector_store):
    mock_store = MagicMock()
    mock_store.delete_documents = AsyncMock()
    mock_get_vector_store.return_value = mock_store

    response = client.delete('/documents/doc-1', params={'collection_name': 'course_if101'})

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert 'doc-1' in data['message']


@patch('app.api.routes.get_vector_store')
def test_delete_document_failure(mock_get_vector_store):
    mock_store = MagicMock()
    mock_store.delete_documents = AsyncMock(side_effect=Exception('delete failed'))
    mock_get_vector_store.return_value = mock_store

    response = client.delete('/documents/doc-1')

    assert response.status_code == 500
    assert response.json()['detail'] == 'delete failed'


@patch('app.api.routes.get_engagement_analyzer')
def test_analyze_engagement_failure(mock_get_analyzer):
    mock_analyzer = MagicMock()
    mock_analyzer.analyze_interaction.side_effect = Exception('nlp failed')
    mock_get_analyzer.return_value = mock_analyzer

    response = client.post('/analytics/engagement', json={'text': 'tes engagement'})

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is False
    assert data['engagement_type'] == 'unknown'
    assert data['error'] == 'nlp failed'
