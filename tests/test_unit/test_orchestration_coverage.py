import importlib
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import app.services.orchestration as orchestration_module
from app.services.nlp_analytics import EngagementAnalysis, EngagementType
from app.services.orchestration import Orchestrator, get_orchestrator


def make_analysis(
    lexical_variety=0.5,
    engagement_type=EngagementType.COGNITIVE,
    is_higher_order=True,
    hot_indicators=None,
    word_count=10,
    unique_words=8,
    confidence=0.8,
):
    return EngagementAnalysis(
        lexical_variety=lexical_variety,
        engagement_type=engagement_type,
        is_higher_order=is_higher_order,
        hot_indicators=hot_indicators or [],
        word_count=word_count,
        unique_words=unique_words,
        confidence=confidence,
    )


@pytest.fixture
def patched_settings():
    with patch("app.services.orchestration.settings") as mock_settings:
        mock_settings.INTERVENTION_MIN_MESSAGES = 5
        mock_settings.INTERVENTION_COOLDOWN_MINUTES = 5
        mock_settings.NLP_LOW_LEXICAL_THRESHOLD = 0.3
        mock_settings.NLP_QUALITY_ALERT_THRESHOLD = 40
        mock_settings.LOGIC_LISTENER_PARTICIPATION_INEQUITY_THRESHOLD = 0.5
        yield mock_settings


@pytest.fixture
def orchestrator_factory(patched_settings):
    def _make():
        mock_rag = AsyncMock()
        mock_rag.query = AsyncMock(
            return_value=MagicMock(
                answer="test",
                success=True,
                sources=[],
                scaffolding_triggered=False,
                grounding_ratio=None,
                srl_phase=None,
                srl_sub_phase=None,
            )
        )

        mock_analyzer = MagicMock()
        mock_analyzer.analyze_interaction = MagicMock(return_value=make_analysis())
        mock_analyzer.extract_srl_object = MagicMock(return_value="Topic")
        mock_analyzer.get_discussion_quality_score = MagicMock(
            return_value={"quality_score": 75, "recommendation": "Good"}
        )

        mock_mongo = AsyncMock()
        mock_mongo.log_activity = AsyncMock()
        mock_mongo.log_intervention = AsyncMock()
        mock_mongo.get_activity_logs = AsyncMock(return_value=[])
        mock_mongo.db = MagicMock()
        mock_mongo.db.activity_logs = MagicMock()
        mock_mongo.db.activity_logs.find_one = AsyncMock(return_value=None)

        mock_intervention = MagicMock()
        mock_intervention.analyze_and_intervene = AsyncMock(
            return_value=MagicMock(message="Intervene!", should_intervene=True)
        )

        mock_logic = MagicMock()
        mock_logic.track_participation = AsyncMock()
        mock_logic.update_last_message_time = AsyncMock()
        mock_logic.get_group_status = MagicMock(return_value={"participation_gini": 0.3})

        mock_goal = MagicMock()
        mock_goal.validate_goal = MagicMock(
            return_value=MagicMock(
                is_valid=True,
                score=0.9,
                feedback="Valid goal",
                missing_criteria=[],
                details={"specific": True},
            )
        )
        mock_goal.generate_socratic_hint = MagicMock(return_value="Hint")
        mock_goal.generate_llm_hint = AsyncMock(return_value=None)

        mock_notification = MagicMock()
        mock_notification.notify_teacher = AsyncMock()

        mock_anomaly = MagicMock()
        mock_anomaly.detect_session_anomalies = AsyncMock(
            return_value=MagicMock(
                has_anomalies=False,
                description="",
                anomaly_type="",
                severity="low",
                timestamp=datetime(2024, 1, 1, 8, 0, 0),
            )
        )

        mock_plan = MagicMock()
        mock_plan.analyze_session = AsyncMock(
            return_value=MagicMock(
                comparison={"alignment_score": 82},
                insights=["Keep focus", "Good pacing", "Solid collaboration", "Extra insight"],
            )
        )

        mock_pm_logger = MagicMock()

        with patch("app.services.orchestration.get_mongo_logger", return_value=mock_mongo), patch(
            "app.services.orchestration.get_plan_vs_reality_analyzer", return_value=mock_plan
        ), patch("app.services.orchestration.get_anomaly_detector", return_value=mock_anomaly), patch(
            "app.services.orchestration.get_notification_service", return_value=mock_notification
        ):
            orchestrator = Orchestrator(
                rag=mock_rag,
                analyzer=mock_analyzer,
                intervention=mock_intervention,
                pm_logger=mock_pm_logger,
                goal_validator=mock_goal,
                logic_listener=mock_logic,
            )

        orchestrator.mongo_logger = mock_mongo
        orchestrator.anomaly_detector = mock_anomaly
        orchestrator.notification_service = mock_notification
        orchestrator.plan_vs_reality = mock_plan

        mocks = {
            "rag": mock_rag,
            "analyzer": mock_analyzer,
            "mongo": mock_mongo,
            "intervention": mock_intervention,
            "logic": mock_logic,
            "goal": mock_goal,
            "notification": mock_notification,
            "anomaly": mock_anomaly,
            "plan": mock_plan,
            "pm_logger": mock_pm_logger,
        }
        return orchestrator, mocks

    return _make


@pytest.mark.asyncio
async def test_handle_message_success_below_intervention_threshold(orchestrator_factory, patched_settings):
    patched_settings.INTERVENTION_MIN_MESSAGES = 10
    orchestrator, mocks = orchestrator_factory()
    mocks["rag"].query.return_value.sources = ["doc-1"]

    result = await orchestrator.handle_message(
        user_id="user-1",
        group_id="group-1",
        message="Mari analisis topik ini",
        topic="Database",
        chat_room_id="room_123",
        collection_name="course_materials",
    )

    assert result.success is True
    assert result.reply == "test"
    assert result.action_taken == "FETCH"
    assert result.intervention is None
    assert result.quality_score is None
    assert len(orchestrator._group_messages["group-1"]) == 1
    mocks["mongo"].log_activity.assert_awaited()
    mocks["logic"].track_participation.assert_awaited_once_with("group-1", "user-1")
    mocks["logic"].update_last_message_time.assert_awaited_once_with("group-1")


@pytest.mark.asyncio
async def test_handle_message_intervention_and_high_anomaly_notify_teacher(orchestrator_factory, patched_settings):
    patched_settings.INTERVENTION_MIN_MESSAGES = 2
    orchestrator, mocks = orchestrator_factory()
    orchestrator._group_messages["group-1"] = [
        {
            "user_id": "u0",
            "message": "Pesan awal",
            "timestamp": datetime.now(),
            "engagement_type": "cognitive",
            "is_hot": True,
            "lexical_variety": 0.4,
        }
    ]
    mocks["anomaly"].detect_session_anomalies.return_value = MagicMock(
        has_anomalies=True,
        description="Long silence detected",
        anomaly_type="silence_gap",
        severity="high",
        timestamp=datetime(2024, 1, 1, 8, 0, 0),
    )

    with patch.object(orchestrator, "_should_intervene", new=AsyncMock(return_value=(True, "low_quality"))):
        result = await orchestrator.handle_message(
            user_id="user-2",
            group_id="group-1",
            message="Diskusi mulai dangkal",
            topic="API",
            chat_room_id="room_789",
            course_id="course-1",
        )

    assert result.success is True
    assert result.intervention == "Intervene!"
    assert result.intervention_type == "clarify"  # BUG-05: mapped from "low_quality"
    assert result.should_notify_teacher is True
    assert result.quality_score == 75
    mocks["mongo"].log_intervention.assert_awaited_once()
    mocks["notification"].notify_teacher.assert_awaited_once_with(
        "course-1",
        "group-1",
        "ANOMALY_SILENCE_GAP",
        "Long silence detected",
    )
    assert "group-1" in orchestrator._last_intervention


@pytest.mark.asyncio
async def test_handle_message_anomaly_low_severity_does_not_notify(orchestrator_factory, patched_settings):
    patched_settings.INTERVENTION_MIN_MESSAGES = 1
    orchestrator, mocks = orchestrator_factory()
    mocks["anomaly"].detect_session_anomalies.return_value = MagicMock(
        has_anomalies=True,
        description="Minor drift",
        anomaly_type="topic_drift",
        severity="medium",
        timestamp=datetime(2024, 1, 1, 8, 0, 0),
    )

    with patch.object(orchestrator, "_should_intervene", new=AsyncMock(return_value=(False, None))):
        result = await orchestrator.handle_message(
            user_id="user-3",
            group_id="group-2",
            message="Pesan biasa",
            chat_room_id="room_999",
        )

    assert result.success is True
    assert result.should_notify_teacher is False
    mocks["notification"].notify_teacher.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_message_anomaly_detector_returns_no_anomalies(
    orchestrator_factory, patched_settings
):
    patched_settings.INTERVENTION_MIN_MESSAGES = 1
    orchestrator, mocks = orchestrator_factory()
    mocks["anomaly"].detect_session_anomalies.return_value = MagicMock(
        has_anomalies=False,
        description="",
        anomaly_type="",
        severity="low",
        timestamp=datetime(2024, 1, 1, 8, 0, 0),
    )
    with patch.object(orchestrator, "_should_intervene", new=AsyncMock(return_value=(False, None))):
        result = await orchestrator.handle_message(
            user_id="user-4",
            group_id="group-no-anom",
            message="Pesan biasa",
            chat_room_id="room_100",
        )
    assert result.success is True
    mocks["anomaly"].detect_session_anomalies.assert_awaited()
    for call in mocks["mongo"].log_activity.await_args_list:
        if call[0][0].get("Activity") == "Anomaly_Detected":
            pytest.fail("unexpected Anomaly_Detected log")


@pytest.mark.asyncio
async def test_handle_message_returns_error_result_on_exception(orchestrator_factory):
    orchestrator, mocks = orchestrator_factory()
    mocks["analyzer"].analyze_interaction.side_effect = RuntimeError("boom")

    result = await orchestrator.handle_message("user-4", "group-3", "hello")

    assert result.success is False
    assert result.reply == "Maaf, terjadi kesalahan."
    assert result.action_taken == "ERROR"
    assert result.error == "Internal error"


@pytest.mark.asyncio
async def test_get_group_dashboard_data_with_anomaly(orchestrator_factory):
    orchestrator, mocks = orchestrator_factory()
    mocks["anomaly"].detect_session_anomalies.return_value = MagicMock(
        has_anomalies=True,
        description="Participation imbalance",
        anomaly_type="imbalance",
        severity="high",
        timestamp=datetime(2024, 1, 2, 9, 30, 0),
    )

    with patch.object(orchestrator, "_get_latest_session_id", new=AsyncMock(return_value="77")), patch.object(
        orchestrator,
        "get_group_analytics",
        new=AsyncMock(
            return_value={
                "quality_score": 35,
                "quality_breakdown": {"participation_gini": 0.72, "lexical_variety": 0.41},
                "hot_percentage": 15,
                "alignment": {"score": 30, "insights": ["off topic"]},
                "message_count": 18,
                "participants": ["u1", "u2"],
                "engagement_distribution": {"cognitive": 6},
            }
        ),
    ), patch.object(orchestrator, "_calculate_intervention_impact", new=AsyncMock(return_value={"status": "positive"})):
        result = await orchestrator.get_group_dashboard_data("group-10")

    assert result["context"] == "group"
    assert result["group_id"] == "group-10"
    assert result["session_id"] == "77"
    assert result["status_color"] == "red"
    assert result["anomalies"][0]["type"] == "imbalance"
    assert "Dominasi Diskusi Terdeteksi." in result["teacher_advice"]
    assert "Penyimpangan materi." in result["teacher_advice"]


@pytest.mark.asyncio
async def test_get_group_dashboard_data_ignores_anomaly_detector_failure(orchestrator_factory):
    orchestrator, mocks = orchestrator_factory()
    mocks["anomaly"].detect_session_anomalies.side_effect = RuntimeError("detector down")

    with patch.object(orchestrator, "_get_latest_session_id", new=AsyncMock(return_value="5")), patch.object(
        orchestrator,
        "get_group_analytics",
        new=AsyncMock(
            return_value={
                "quality_score": 72,
                "quality_breakdown": {"participation_gini": 0.2, "lexical_variety": 0.6},
                "hot_percentage": 45,
                "alignment": {"score": 88, "insights": []},
                "message_count": 6,
                "participants": ["u1"],
                "engagement_distribution": {},
            }
        ),
    ), patch.object(orchestrator, "_calculate_intervention_impact", new=AsyncMock(return_value={"status": "none"})):
        result = await orchestrator.get_group_dashboard_data("group-11")

    assert result["anomalies"] == []
    assert result["status_color"] == "green"


@pytest.mark.asyncio
async def test_get_group_dashboard_data_anomaly_detector_no_anomalies(
    orchestrator_factory,
):
    orchestrator, mocks = orchestrator_factory()
    mocks["mongo"].get_activity_logs = AsyncMock(
        return_value=[
            {
                "Attributes": {"original_text": "hi"},
                "Resource": "u1",
                "Timestamp": datetime(2024, 1, 1, 9, 0, 0),
            }
        ]
    )
    mocks["analyzer"].analyze_interaction = MagicMock(return_value=make_analysis())
    mocks["anomaly"].detect_session_anomalies = AsyncMock(
        return_value=MagicMock(has_anomalies=False)
    )
    result = await orchestrator.get_group_dashboard_data("g-clean")
    assert result.get("anomalies") == []


@pytest.mark.asyncio
async def test_get_individual_dashboard_data_no_logs(orchestrator_factory):
    orchestrator, mocks = orchestrator_factory()
    mocks["mongo"].get_activity_logs.return_value = []

    result = await orchestrator.get_individual_dashboard_data("student-1")

    assert result == {"context": "individual", "user_id": "student-1", "message_count": 0}


@pytest.mark.asyncio
async def test_get_individual_dashboard_data_with_logs(orchestrator_factory):
    orchestrator, mocks = orchestrator_factory()
    mocks["mongo"].get_activity_logs.return_value = [
        {
            "Attributes": {
                "original_text": "Analisis API",
                "is_hot": True,
                "lexical_variety": 0.5,
                "srl_object": "API",
            }
        },
        {
            "Attributes": {
                "original_text": "Bandingkan database",
                "is_hot": False,
                "lexical_variety": 0.7,
                "srl_object": "Database",
            }
        },
        {
            "Attributes": {
                "original_text": "Evaluasi desain",
                "is_hot": True,
                "lexical_variety": 0.4,
                "srl_object": "Design",
            }
        },
    ]
    mocks["analyzer"].get_discussion_quality_score.return_value = {
        "quality_score": 82,
        "recommendation": "Excellent",
    }

    result = await orchestrator.get_individual_dashboard_data("student-2")

    assert result["context"] == "individual"
    assert result["status_color"] == "green"
    assert result["total_messages"] == 3
    assert result["personal_metrics"]["hot_count"] == 2
    assert result["personal_metrics"]["hot_percentage"] == pytest.approx(66.6666666)
    assert result["personal_metrics"]["avg_lexical_variety"] == 0.533
    assert result["recommendation"] == "Excellent"
    assert set(result["recent_topics"]) == {"API", "Database", "Design"}


@pytest.mark.asyncio
async def test_validate_goal_single_valid_updates_streak_without_fading(orchestrator_factory):
    orchestrator, _ = orchestrator_factory()

    result = await orchestrator.validate_goal("Goal 1", "user-1", "space_1")

    assert result["is_valid"] is True
    assert orchestrator._group_smart_streak["space_1"] == 1
    assert orchestrator._group_fading_levels.get("space_1", 0.0) == 0.0


@pytest.mark.asyncio
async def test_validate_goal_three_valid_goals_increase_fading_and_reset_streak(orchestrator_factory):
    orchestrator, _ = orchestrator_factory()

    await orchestrator.validate_goal("Goal 1", "user-1", "space_2")
    await orchestrator.validate_goal("Goal 2", "user-1", "space_2")
    result = await orchestrator.validate_goal("Goal 3", "user-1", "space_2")

    assert result["success"] is True
    assert orchestrator._group_fading_levels["space_2"] == pytest.approx(0.2)
    assert orchestrator._group_smart_streak["space_2"] == 0


@pytest.mark.asyncio
async def test_validate_goal_invalid_resets_streak(orchestrator_factory):
    orchestrator, mocks = orchestrator_factory()
    orchestrator._group_smart_streak["space_3"] = 2
    mocks["goal"].validate_goal.return_value = MagicMock(
        is_valid=False,
        score=0.4,
        feedback="Need more detail",
        missing_criteria=["measurable"],
        details={"specific": False},
    )
    mocks["goal"].generate_socratic_hint.return_value = "Tambah ukuran keberhasilan"

    result = await orchestrator.validate_goal("Goal invalid", "user-2", "space_3")

    assert result["is_valid"] is False
    assert result["socratic_hint"] == "Tambah ukuran keberhasilan"
    assert orchestrator._group_smart_streak["space_3"] == 0


@pytest.mark.asyncio
async def test_should_intervene_respects_cooldown(orchestrator_factory):
    orchestrator, _ = orchestrator_factory()
    orchestrator._last_intervention["group-cooldown"] = datetime.now() - timedelta(minutes=1)

    needed, reason = await orchestrator._should_intervene(
        "group-cooldown",
        make_analysis(lexical_variety=0.1),
        10,
    )

    assert (needed, reason) == (False, None)


@pytest.mark.asyncio
async def test_should_intervene_after_cooldown_expired_checks_metrics(
    orchestrator_factory, patched_settings
):
    patched_settings.INTERVENTION_COOLDOWN_MINUTES = 5
    orchestrator, _ = orchestrator_factory()
    orchestrator._last_intervention["group-expired"] = datetime.now() - timedelta(
        minutes=30
    )
    needed, reason = await orchestrator._should_intervene(
        "group-expired", make_analysis(lexical_variety=0.1), 50
    )
    assert (needed, reason) == (True, "low_lexical")


@pytest.mark.asyncio
async def test_should_intervene_for_low_lexical_variety(orchestrator_factory):
    orchestrator, _ = orchestrator_factory()

    needed, reason = await orchestrator._should_intervene("group-lex", make_analysis(lexical_variety=0.1), 90)

    assert (needed, reason) == (True, "low_lexical")


@pytest.mark.asyncio
async def test_should_intervene_for_low_quality(orchestrator_factory):
    orchestrator, _ = orchestrator_factory()

    needed, reason = await orchestrator._should_intervene("group-quality", make_analysis(lexical_variety=0.8), 20)

    assert (needed, reason) == (True, "low_quality")


@pytest.mark.asyncio
async def test_should_intervene_for_participation_inequity(orchestrator_factory):
    orchestrator, mocks = orchestrator_factory()
    mocks["logic"].get_group_status.return_value = {"participation_gini": 0.9}

    needed, reason = await orchestrator._should_intervene("group-gini", make_analysis(lexical_variety=0.8), 90)

    assert (needed, reason) == (True, "participation_inequity")


@pytest.mark.asyncio
async def test_should_intervene_returns_false_when_all_metrics_healthy(orchestrator_factory):
    orchestrator, mocks = orchestrator_factory()
    mocks["logic"].get_group_status.return_value = {"participation_gini": 0.2}

    needed, reason = await orchestrator._should_intervene("group-ok", make_analysis(lexical_variety=0.8), 90)

    assert (needed, reason) == (False, None)


@pytest.mark.asyncio
async def test_generate_intervention_message_uses_service(orchestrator_factory):
    orchestrator, _ = orchestrator_factory()
    
    message = await orchestrator._generate_intervention_message(
        "test-group", make_analysis(), 30, "low_quality", "Testing", {}
    )
    
    assert message == "Intervene!"


@pytest.mark.asyncio
async def test_get_group_analytics_no_messages(orchestrator_factory):
    orchestrator, _ = orchestrator_factory()

    result = await orchestrator.get_group_analytics("empty-group")

    assert result == {"group_id": "empty-group", "message_count": 0}


@pytest.mark.asyncio
async def test_get_group_analytics_with_alignment(orchestrator_factory):
    orchestrator, mocks = orchestrator_factory()
    orchestrator._group_messages["group-a"] = [
        {"user_id": "u1", "message": "Analisis 1", "is_hot": True, "lexical_variety": 0.4},
        {"user_id": "u2", "message": "Analisis 2", "is_hot": False, "lexical_variety": 0.6},
        {"user_id": "u1", "message": "Analisis 3", "is_hot": True, "lexical_variety": 0.8},
    ]
    mocks["analyzer"].get_discussion_quality_score.return_value = {"quality_score": 70, "recommendation": "Good"}

    result = await orchestrator.get_group_analytics("group-a")

    assert result["group_id"] == "group-a"
    assert result["message_count"] == 3
    assert result["quality_score"] == 70
    assert set(result["participants"]) == {"u1", "u2"}
    assert result["alignment"]["score"] == 82
    assert result["alignment"]["insights"] == ["Keep focus", "Good pacing", "Solid collaboration"]
    assert result["hot_percentage"] == pytest.approx(66.6666666)
    assert result["quality_breakdown"]["lexical_variety"] == pytest.approx(0.6)


@pytest.mark.asyncio
async def test_get_group_analytics_alignment_failure_falls_back(orchestrator_factory):
    orchestrator, mocks = orchestrator_factory()
    orchestrator._group_messages["group-b"] = [
        {"user_id": "u1", "message": "Pesan", "is_hot": False, "lexical_variety": 0.5}
    ]
    mocks["plan"].analyze_session.side_effect = RuntimeError("align failed")

    result = await orchestrator.get_group_analytics("group-b")

    assert result["alignment"] == {}
    assert result["quality_breakdown"]["lexical_variety"] == 0.5


def test_calculate_group_traffic_light_red(orchestrator_factory):
    orchestrator, _ = orchestrator_factory()

    assert orchestrator._calculate_group_traffic_light({"participation_equity": 0.7, "quality_score": 80}) == "red"
    assert orchestrator._calculate_group_traffic_light({"participation_equity": 0.2, "quality_score": 30}) == "red"


def test_calculate_group_traffic_light_yellow(orchestrator_factory):
    orchestrator, _ = orchestrator_factory()

    assert orchestrator._calculate_group_traffic_light({"participation_equity": 0.5, "quality_score": 80}) == "yellow"
    assert orchestrator._calculate_group_traffic_light({"participation_equity": 0.2, "quality_score": 50}) == "yellow"


def test_calculate_group_traffic_light_green(orchestrator_factory):
    orchestrator, _ = orchestrator_factory()

    assert orchestrator._calculate_group_traffic_light({"participation_equity": 0.2, "quality_score": 80}) == "green"


def test_calculate_individual_traffic_light_all_states(orchestrator_factory):
    orchestrator, _ = orchestrator_factory()

    assert orchestrator._calculate_individual_traffic_light({"hot_percentage": None}) == "green"
    assert orchestrator._calculate_individual_traffic_light({"hot_percentage": 5}) == "red"
    assert orchestrator._calculate_individual_traffic_light({"hot_percentage": 20}) == "yellow"
    assert orchestrator._calculate_individual_traffic_light({"hot_percentage": 35}) == "green"


def test_generate_teacher_advice_all_conditions(orchestrator_factory):
    orchestrator, _ = orchestrator_factory()

    advice = orchestrator._generate_teacher_advice(
        {"participation_equity": 0.8, "hot_percentage": 10},
        {"score": 20},
        [{"type": "imbalance"}],
    )

    assert advice == [
        "Dominasi Diskusi Terdeteksi.",
        "Kualitas kognitif rendah.",
        "Penyimpangan materi.",
    ]


def test_generate_teacher_advice_stable_default(orchestrator_factory):
    orchestrator, _ = orchestrator_factory()

    advice = orchestrator._generate_teacher_advice(
        {"participation_equity": 0.2, "hot_percentage": 60},
        {"score": 90},
        [],
    )

    assert advice == ["Kelompok berjalan stabil."]


def test_generate_individual_advice_both_paths(orchestrator_factory):
    orchestrator, _ = orchestrator_factory()

    assert orchestrator._generate_individual_advice({"hot_percentage": 10}) == ["Tingkatkan analisis kognitif."]
    assert orchestrator._generate_individual_advice({"hot_percentage": 35}) == ["Bagus!"]


def test_anomaly_to_dict_serializes_timestamp(orchestrator_factory):
    orchestrator, _ = orchestrator_factory()
    anomaly = MagicMock(
        anomaly_type="silence_gap",
        severity="high",
        description="Gap too long",
        timestamp=datetime(2024, 3, 1, 10, 15, 0),
    )

    result = orchestrator._anomaly_to_dict(anomaly)

    assert result == {
        "type": "silence_gap",
        "severity": "high",
        "description": "Gap too long",
        "timestamp": "2024-03-01T10:15:00",
    }


@pytest.mark.asyncio
async def test_get_latest_session_id_returns_latest_value(orchestrator_factory):
    orchestrator, mocks = orchestrator_factory()
    mocks["mongo"].db.activity_logs.find_one.return_value = {"CaseID": "group-z_session_42"}

    result = await orchestrator._get_latest_session_id("group-z")

    assert result == "42"


@pytest.mark.asyncio
async def test_get_latest_session_id_returns_default_on_exception(orchestrator_factory):
    orchestrator, mocks = orchestrator_factory()
    mocks["mongo"].db.activity_logs.find_one.side_effect = RuntimeError("db failure")

    result = await orchestrator._get_latest_session_id("group-z")

    assert result == "1"


@pytest.mark.asyncio
async def test_calculate_intervention_impact_none(orchestrator_factory):
    orchestrator, mocks = orchestrator_factory()
    mocks["mongo"].db.activity_logs.find_one = AsyncMock(side_effect=[None])

    result = await orchestrator._calculate_intervention_impact("group-impact-none")

    assert result == {"status": "none"}


@pytest.mark.asyncio
async def test_calculate_intervention_impact_positive(orchestrator_factory):
    orchestrator, mocks = orchestrator_factory()
    mocks["mongo"].db.activity_logs.find_one = AsyncMock(
        side_effect=[
            {"Timestamp": datetime(2024, 1, 1, 10, 0, 0)},
            {"Timestamp": datetime(2024, 1, 1, 10, 5, 0)},
        ]
    )

    result = await orchestrator._calculate_intervention_impact("group-impact-positive")

    assert result == {"status": "positive"}


@pytest.mark.asyncio
async def test_calculate_intervention_impact_no_response(orchestrator_factory):
    orchestrator, mocks = orchestrator_factory()
    mocks["mongo"].db.activity_logs.find_one = AsyncMock(
        side_effect=[
            {"Timestamp": datetime(2024, 1, 1, 10, 0, 0)},
            None,
        ]
    )

    result = await orchestrator._calculate_intervention_impact("group-impact-no-response")

    assert result == {"status": "no_response"}


@pytest.mark.asyncio
async def test_calculate_intervention_impact_unknown_on_exception(orchestrator_factory):
    orchestrator, mocks = orchestrator_factory()
    mocks["mongo"].db.activity_logs.find_one.side_effect = RuntimeError("db down")

    result = await orchestrator._calculate_intervention_impact("group-impact-error")

    assert result == {"status": "unknown"}


def test_get_orchestrator_returns_singleton_instance():
    orchestration_module._orchestrator = None
    fake_instance = MagicMock(name="singleton_orchestrator")

    with patch("app.services.orchestration.Orchestrator", return_value=fake_instance) as mock_ctor:
        first = get_orchestrator()
        second = get_orchestrator()

    assert first is fake_instance
    assert second is fake_instance
    mock_ctor.assert_called_once_with()
    orchestration_module._orchestrator = None
