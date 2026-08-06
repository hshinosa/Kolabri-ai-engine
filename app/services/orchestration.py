"""
Orchestration Service
=====================
Primary coordinator for the AI Engine. Implements the Teacher-AI Complementarity
loop by integrating RAG, Analytics, Anomaly Detection, and Proactive Interventions.
"""

import asyncio
import re
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime

from app.core.logging import get_logger
from app.core.config import settings
from app.services.rag import get_rag_pipeline
from app.services.nlp_analytics import (
    get_engagement_analyzer,
    EngagementAnalysis,
    EngagementType,
)
from app.services.intervention import get_intervention_service
from app.services.mongodb_logger import get_mongo_logger
from app.services.srl_classifier import get_srl_classifier, SRLPhase
from app.services.goal_validator import get_goal_validator
from app.services.logic_listener import get_logic_listener
from app.services.plan_vs_reality import get_plan_vs_reality_analyzer
from app.services.process_mining_anomaly import get_anomaly_detector
from app.services.notification_service import get_notification_service
from app.utils.logger import get_process_mining_logger

logger = get_logger(__name__)

ProviderContext = Dict[str, Any]


@dataclass
class OrchestrationResult:
    """Orchestration pipeline result.

    Note: ``error`` field contains user-safe messages only. Internal exception
    details are logged via ``logger.exception(...)`` and never exposed in this
    field. Route handlers may safely propagate ``error`` to clients.
    """

    reply: str
    intervention: Optional[str]
    intervention_type: Optional[str]
    analytics: Dict[str, Any]
    action_taken: str
    should_notify_teacher: bool
    quality_score: Optional[float]
    success: bool
    error: Optional[str] = None
    citations: Optional[List[Dict[str, Any]]] = None


class Orchestrator:
    """Central orchestration service implementing Teacher-AI Complementarity. MINOR-03: Analytics ownership — in-memory analytics (fading, streaks, message history) are ephemeral per-process. Database analytics (ChatLog, activity_logs) are persistent and authoritative in core-api. Future: consolidate to DB-only."""

    def __init__(self, provider_context: Optional[ProviderContext] = None, **services):
        self.rag = services.get("rag") or get_rag_pipeline(
            provider_context=provider_context
        )
        self.analyzer = services.get("analyzer") or get_engagement_analyzer()
        self.intervention = services.get("intervention") or get_intervention_service(
            provider_context=provider_context
        )
        self.pm_logger = services.get("pm_logger") or get_process_mining_logger()
        self.mongo_logger = get_mongo_logger()
        self.goal_validator = services.get("goal_validator") or get_goal_validator(
            provider_context=provider_context
        )
        self.logic_listener = services.get("logic_listener") or get_logic_listener()
        self.plan_vs_reality = get_plan_vs_reality_analyzer()
        self.anomaly_detector = get_anomaly_detector()
        self.notification_service = get_notification_service()

        # In-memory tracking with concurrency protection
        self._state_lock = asyncio.Lock()
        self._last_intervention: Dict[str, datetime] = {}
        self._group_messages: Dict[str, List[Dict[str, Any]]] = {}
        self._group_fading_levels: Dict[str, float] = {}
        self._group_smart_streak: Dict[str, int] = {}

        logger.info("orchestrator_initialized_with_concurrency_protection")

    async def handle_message(
        self, user_id: str, group_id: str, message: str, topic: str = None, **kwargs
    ) -> OrchestrationResult:
        """Handle student message through the full orchestration pipeline."""
        try:
            # 1. NLP Analysis
            analytics = self.analyzer.analyze_interaction(message)
            fading = self._group_fading_levels.get(group_id, 0.0)

            # 2. RAG Generation
            scaffolding_config = kwargs.get("scaffolding_config") or {}
            effective_level = scaffolding_config.get("scaffolding_level") or "auto"

            from app.services.llm import ChatMessage

            raw_history = kwargs.get("chat_history") or []
            chat_history = (
                [
                    ChatMessage(
                        role=m.role if hasattr(m, "role") else m.get("role", "user"),
                        content=m.content
                        if hasattr(m, "content")
                        else m.get("content", ""),
                    )
                    for m in raw_history[-10:]
                ]
                if raw_history
                else None
            )

            rag_result = await self.rag.query(
                query=message,
                collection_name=kwargs.get("collection_name"),
                fading_level=fading,
                chat_history=chat_history,
                guardrail_context={
                    "guardrail_policy": kwargs.get("guardrail_policy") or {},
                    "scaffolding_config": scaffolding_config,
                },
                session_week_index=kwargs.get("session_week_index"),
                max_week_index=kwargs.get("max_week_index"),
                week_context=kwargs.get("week_context"),
            )
            bot_reply = (
                rag_result.answer if rag_result.success else "Maaf, terjadi kesalahan."
            )

            # 3. Logging & Context
            session_id = (kwargs.get("chat_room_id") or "1").split("_")[-1]
            case_id = f"{group_id}_session_{session_id}"
            srl_obj = self.analyzer.extract_srl_object(
                message, default=topic or "General"
            )

            # PERF-AI-04: Parallelize mongo writes
            scaffolding_outcome = (
                "applied" if scaffolding_config.get("enabled", True) else "disabled"
            )

            student_message = {
                "CaseID": case_id,
                "Activity": "Student_Message",
                "Timestamp": datetime.now(),
                "Resource": f"Student_{user_id}",
                "Lifecycle": "complete",
                "Attributes": {
                    "original_text": message,
                    "srl_object": srl_obj,
                    "educational_category": analytics.engagement_type.value.capitalize(),
                    "is_hot": analytics.is_higher_order,
                    "lexical_variety": analytics.lexical_variety,
                    "scaffolding_trigger": False,
                },
            }

            bot_response = {
                "CaseID": case_id,
                "Activity": "Bot_Response",
                "Timestamp": datetime.now(),
                "Resource": "Kolabri_Bot",
                "Lifecycle": "complete",
                "Attributes": {
                    "original_text": bot_reply,
                    "srl_object": srl_obj,
                    "educational_category": "Instructional",
                    "scaffolding_trigger": rag_result.scaffolding_triggered,
                    "action_taken": "FETCH" if rag_result.sources else "NO_FETCH",
                    "guardrail_outcome": rag_result.outcome,
                    "guardrail_reason": rag_result.reason,
                    "grounding_ratio": getattr(rag_result, "grounding_ratio", None),
                    "srl_phase": getattr(rag_result, "srl_phase", None),
                    "srl_sub_phase": getattr(rag_result, "srl_sub_phase", None),
                    "scaffolding_level": effective_level,
                    "scaffolding_outcome": scaffolding_outcome,
                },
            }

            # Write both logs in parallel to reduce latency
            await asyncio.gather(
                self.mongo_logger.log_activity(student_message),
                self.mongo_logger.log_activity(bot_response),
            )

            await self._track_message(group_id, user_id, message, analytics)

            # 4. Intervention & Anomaly Detection
            int_msg, int_type, notify = None, None, False
            q_score = None

            async with self._state_lock:
                group_msgs = self._group_messages.get(group_id, [])
            if len(group_msgs) >= settings.INTERVENTION_MIN_MESSAGES:
                q_res = self.analyzer.get_discussion_quality_score(
                    [m["message"] for m in group_msgs[-10:]]
                )
                q_score = q_res["quality_score"]

                needed, reason = await self._should_intervene(
                    group_id, analytics, q_score
                )
                if needed:
                    int_msg = await self._generate_intervention_message(
                        group_id, analytics, q_score, reason, topic, kwargs
                    )
                    if int_msg:
                        int_type = self._map_intervention_type(reason)
                        await self.mongo_logger.log_intervention(
                            group_id, reason, int_msg, {"quality": q_score}, session_id
                        )
                        async with self._state_lock:
                            self._last_intervention[group_id] = datetime.now()

                # Anomaly Check (Gap 5)
                anoms = await self.anomaly_detector.detect_session_anomalies(
                    case_id, group_id
                )
                if anoms.has_anomalies:
                    await self.mongo_logger.log_activity(
                        {
                            "CaseID": case_id,
                            "Activity": "Anomaly_Detected",
                            "Timestamp": datetime.now(),
                            "Resource": "System_AnomalyDetector",
                            "Lifecycle": "complete",
                            "Attributes": {
                                "original_text": anoms.description,
                                "metadata": {
                                    "type": anoms.anomaly_type,
                                    "severity": anoms.severity,
                                },
                            },
                        }
                    )
                    if anoms.severity == "high":
                        notify = True
                        await self.notification_service.notify_teacher(
                            kwargs.get("course_id", "default"),
                            group_id,
                            f"ANOMALY_{anoms.anomaly_type.upper()}",
                            anoms.description,
                        )

            analytics_dict = self._analytics_to_dict(analytics)
            analytics_dict["scaffolding_level"] = effective_level
            analytics_dict["scaffolding_outcome"] = scaffolding_outcome
            return OrchestrationResult(
                bot_reply,
                int_msg,
                int_type,
                analytics_dict,
                "FETCH" if rag_result.sources else "NO_FETCH",
                notify,
                q_score,
                True,
                citations=getattr(rag_result, "citations", None) or [],
            )

        except Exception:
            logger.exception("orchestration_failed")
            return OrchestrationResult(
                "Maaf, terjadi kesalahan.",
                None,
                None,
                {},
                "ERROR",
                False,
                None,
                False,
                "Internal error",
                citations=[],
            )

    async def handle_message_stream(
        self, user_id: str, group_id: str, message: str, topic: str = None, **kwargs
    ):
        """Stream version of handle_message.

        PERF-AI-01: Yields dict events for SSE streaming.
        - NO_FETCH path: yields {"type":"token","content":chunk} per token
        - FETCH path: yields {"type":"full",...} with complete result
        - On completion: yields {"type":"done",...} with analytics + intervention data
        - On error: yields {"type":"error","content":str}

        Logging (mongo) + intervention check run on completion (after all tokens/full).
        """
        try:
            analytics = self.analyzer.analyze_interaction(message)
            fading = self._group_fading_levels.get(group_id, 0.0)

            scaffolding_config = kwargs.get("scaffolding_config") or {}
            effective_level = scaffolding_config.get("scaffolding_level") or "auto"

            from app.services.llm import ChatMessage

            raw_history = kwargs.get("chat_history") or []
            chat_history = (
                [
                    ChatMessage(
                        role=m.role if hasattr(m, "role") else m.get("role", "user"),
                        content=m.content
                        if hasattr(m, "content")
                        else m.get("content", ""),
                    )
                    for m in raw_history[-10:]
                ]
                if raw_history
                else None
            )

            full_content = ""
            rag_sources = []
            rag_citations = []
            rag_outcome = None
            rag_reason = None
            scaffolding_triggered = False
            grounding_ratio = None

            async for event in self.rag.query_stream(
                query=message,
                collection_name=kwargs.get("collection_name"),
                chat_history=chat_history,
                guardrail_context={
                    "guardrail_policy": kwargs.get("guardrail_policy") or {},
                    "scaffolding_config": scaffolding_config,
                },
                session_week_index=kwargs.get("session_week_index"),
                max_week_index=kwargs.get("max_week_index"),
                week_context=kwargs.get("week_context"),
            ):
                if event["type"] == "token":
                    full_content += event["content"]
                    yield event
                elif event["type"] == "full":
                    full_content = event["content"]
                    rag_sources = event.get("sources", [])
                    rag_citations = event.get("citations", [])
                    rag_outcome = event.get("outcome")
                    rag_reason = event.get("reason")
                    scaffolding_triggered = event.get("scaffolding_triggered", False)
                    grounding_ratio = event.get("grounding_ratio")
                    yield event
                elif event["type"] == "done":
                    rag_sources = event.get("sources", rag_sources)
                    rag_citations = event.get("citations", rag_citations)
                    # Don't yield done yet -- run logging + intervention first
                elif event["type"] == "error":
                    yield event
                    return

            # Logging (same as handle_message)
            session_id = (kwargs.get("chat_room_id") or "1").split("_")[-1]
            case_id = f"{group_id}_session_{session_id}"
            srl_obj = self.analyzer.extract_srl_object(
                message, default=topic or "General"
            )

            # Classify Zimmerman SRL phase
            try:
                classifier = get_srl_classifier()
                srl_classification = classifier.classify(message)
                srl_phase = srl_classification.phase.value
                srl_sub_phase = srl_classification.sub_phase
                srl_confidence = srl_classification.confidence
                srl_indicators = srl_classification.indicators
            except Exception as e:
                logger.warning(f"SRL classification failed: {e}")
                srl_phase = None
                srl_sub_phase = None
                srl_confidence = 0.0
                srl_indicators = []

            scaffolding_outcome = (
                "applied" if scaffolding_config.get("enabled", True) else "disabled"
            )

            student_message = {
                "CaseID": case_id,
                "Activity": "Student_Message",
                "Timestamp": datetime.now(),
                "Resource": f"Student_{user_id}",
                "Lifecycle": "complete",
                "Attributes": {
                    "original_text": message,
                    "srl_object": srl_obj,
                    "educational_category": analytics.engagement_type.value.capitalize(),
                    "is_hot": analytics.is_higher_order,
                    "lexical_variety": analytics.lexical_variety,
                    "scaffolding_trigger": False,
                    "srl_phase": srl_phase,
                    "srl_sub_phase": srl_sub_phase,
                    "srl_confidence": srl_confidence,
                },
            }

            bot_response = {
                "CaseID": case_id,
                "Activity": "Bot_Response",
                "Timestamp": datetime.now(),
                "Resource": "Kolabri_Bot",
                "Lifecycle": "complete",
                "Attributes": {
                    "original_text": full_content,
                    "srl_object": srl_obj,
                    "educational_category": "Instructional",
                    "scaffolding_trigger": scaffolding_triggered,
                    "action_taken": "FETCH" if rag_sources else "NO_FETCH",
                    "guardrail_outcome": rag_outcome,
                    "guardrail_reason": rag_reason,
                    "grounding_ratio": grounding_ratio,
                    "scaffolding_level": effective_level,
                    "scaffolding_outcome": scaffolding_outcome,
                    "srl_phase": srl_phase,
                    "srl_sub_phase": srl_sub_phase,
                    "srl_confidence": srl_confidence,
                },
            }

            await asyncio.gather(
                self.mongo_logger.log_activity(student_message),
                self.mongo_logger.log_activity(bot_response),
            )

            await self._track_message(group_id, user_id, message, analytics)

            # Intervention check (same as handle_message)
            int_msg, int_type, notify = None, None, False
            q_score = None

            async with self._state_lock:
                group_msgs = self._group_messages.get(group_id, [])
            if len(group_msgs) >= settings.INTERVENTION_MIN_MESSAGES:
                q_res = self.analyzer.get_discussion_quality_score(
                    [m["message"] for m in group_msgs[-10:]]
                )
                q_score = q_res["quality_score"]

                needed, reason = await self._should_intervene(
                    group_id, analytics, q_score
                )
                if needed:
                    int_msg = await self._generate_intervention_message(
                        group_id, analytics, q_score, reason, topic, kwargs
                    )
                    if int_msg:
                        int_type = self._map_intervention_type(reason)
                        await self.mongo_logger.log_intervention(
                            group_id, reason, int_msg, {"quality": q_score}, session_id
                        )
                        async with self._state_lock:
                            self._last_intervention[group_id] = datetime.now()

                anoms = await self.anomaly_detector.detect_session_anomalies(
                    case_id, group_id
                )
                if anoms.has_anomalies:
                    await self.mongo_logger.log_activity(
                        {
                            "CaseID": case_id,
                            "Activity": "Anomaly_Detected",
                            "Timestamp": datetime.now(),
                            "Resource": "System_AnomalyDetector",
                            "Lifecycle": "complete",
                            "Attributes": {
                                "original_text": anoms.description,
                                "metadata": {
                                    "type": anoms.anomaly_type,
                                    "severity": anoms.severity,
                                },
                            },
                        }
                    )
                    if anoms.severity == "high":
                        notify = True
                        await self.notification_service.notify_teacher(
                            kwargs.get("course_id", "default"),
                            group_id,
                            f"ANOMALY_{anoms.anomaly_type.upper()}",
                            anoms.description,
                        )

            analytics_dict = self._analytics_to_dict(analytics)
            analytics_dict["scaffolding_level"] = effective_level
            analytics_dict["scaffolding_outcome"] = scaffolding_outcome

            yield {
                "type": "done",
                "content": full_content,
                "sources": rag_sources,
                "citations": rag_citations,
                "analytics": analytics_dict,
                "intervention": int_msg,
                "intervention_type": int_type,
                "quality_score": q_score,
                "should_notify_teacher": notify,
                "guardrail_outcome": rag_outcome,
                "guardrail_reason": rag_reason,
                "scaffolding_level": effective_level,
                "scaffolding_outcome": scaffolding_outcome,
            }

        except Exception:
            logger.exception("orchestration_stream_failed")
            yield {
                "type": "error",
                "content": "Maaf, terjadi kesalahan.",
            }

    async def get_group_dashboard_data(self, group_id: str) -> Dict[str, Any]:
        """Consolidated Group Dashboard logic."""
        session_id = await self._get_latest_session_id(group_id)
        case_id = f"{group_id}_session_{session_id}"
        analytics = await self.get_group_analytics(group_id)
        impact = await self._calculate_intervention_impact(group_id)

        anoms = []
        try:
            det = await self.anomaly_detector.detect_session_anomalies(
                case_id, group_id
            )
            if det.has_anomalies:
                anoms.append(self._anomaly_to_dict(det))
        except:
            pass

        metrics = {
            "quality_score": analytics.get("quality_score"),
            "participation_equity": analytics.get("quality_breakdown", {}).get(
                "participation_gini"
            ),
            "hot_percentage": analytics.get("hot_percentage"),
            "lexical_variety": analytics.get("quality_breakdown", {}).get(
                "lexical_variety"
            ),
        }

        return {
            "context": "group",
            "group_id": group_id,
            "session_id": session_id,
            "status_color": self._calculate_group_traffic_light(metrics),
            "radar_chart_data": {
                "cognitive": round(metrics["hot_percentage"] / 10, 1)
                if metrics["hot_percentage"]
                else 0,
                "collaboration": round(
                    10 - (metrics.get("participation_equity") or 0) * 10, 1
                ),
                "consistency": round(
                    analytics.get("alignment", {}).get("score", 0) / 10, 1
                ),
                "vocabulary": round((metrics["lexical_variety"] or 0) * 10, 1),
                "engagement": min(10, round(analytics.get("message_count", 0) / 2, 1)),
            },
            "intervention_impact": impact,
            "metrics": metrics,
            "alignment": analytics.get("alignment"),
            "anomalies": anoms,
            "teacher_advice": self._generate_teacher_advice(
                metrics, analytics.get("alignment"), anoms
            ),
            "participants": analytics.get("participants"),
            "engagement_distribution": analytics.get("engagement_distribution"),
            "last_updated": datetime.now().isoformat(),
        }

    async def get_individual_dashboard_data(
        self, user_id: str, **kwargs
    ) -> Dict[str, Any]:
        """Consolidated Individual Dashboard logic."""
        logs = await self.mongo_logger.get_activity_logs(
            resource=f"Student_{user_id}", limit=100
        )
        if not logs:
            return {"context": "individual", "user_id": user_id, "message_count": 0}

        msgs = [l["Attributes"]["original_text"] for l in logs if "Attributes" in l]
        quality = self.analyzer.get_discussion_quality_score(msgs)
        hot_count = sum(1 for l in logs if l.get("Attributes", {}).get("is_hot"))
        avg_lex = sum(
            l.get("Attributes", {}).get("lexical_variety", 0) for l in logs
        ) / len(logs)

        metrics = {
            "avg_quality_score": quality["quality_score"],
            "hot_count": hot_count,
            "hot_percentage": (hot_count / len(logs)) * 100,
            "avg_lexical_variety": round(avg_lex, 3),
        }

        return {
            "context": "individual",
            "user_id": user_id,
            "status_color": self._calculate_individual_traffic_light(metrics),
            "radar_chart_data": {
                "critical_thinking": round(metrics["hot_percentage"] / 10, 1),
                "engagement": min(10, round(len(logs) / 2, 1)),
                "vocabulary": round(metrics["avg_lexical_variety"] * 10, 1),
                "quality": round(metrics["avg_quality_score"] / 10, 1),
                "consistency": 10.0,  # Standard placeholder for personal consistency
            },
            "total_messages": len(logs),
            "personal_metrics": metrics,
            "personal_advice": self._generate_individual_advice(metrics),
            "recent_topics": list(
                set(
                    l.get("Attributes", {}).get("srl_object")
                    for l in logs
                    if l.get("Attributes", {}).get("srl_object")
                )
            )[-5:],
            "recommendation": quality["recommendation"],
            "last_updated": datetime.now().isoformat(),
        }

    async def validate_goal(
        self,
        goal_text: str,
        user_id: str,
        session_discussion_id: str,
        week_context: Optional[Dict[str, Any]] = None,
        group_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        # BUG-01+02: Use group_id for CaseID and state tracking (not session_discussion_id)
        tracking_key = group_id or session_discussion_id
        res = self.goal_validator.validate_goal(goal_text)
        week_off_topic = False
        if week_context and week_context.get("week_title"):
            titles = week_context.get("material_titles") or []
            if len(goal_text.split()) >= 8 and titles:
                goal_words = set(re.findall(r"[a-z]{4,}", goal_text.lower()))

                overlap = 0
                for t in titles:
                    if not t:
                        continue
                    title_words = set(re.findall(r"[a-z]{4,}", t.lower()))
                    if title_words & goal_words:
                        overlap += 1

                week_off_topic = overlap == 0
                logger.info(
                    "off_topic_check",
                    goal_words=sorted(goal_words)[:15],
                    title_words_all=[
                        sorted(set(re.findall(r"[a-z]{4,}", t.lower())))
                        for t in titles
                        if t
                    ],
                    overlap_count=overlap,
                    week_off_topic=week_off_topic,
                )

        async with self._state_lock:
            streak = self._group_smart_streak.get(tracking_key, 0)

            if res.is_valid:
                streak += 1
                if streak >= 3:
                    curr = self._group_fading_levels.get(tracking_key, 0.0)
                    self._group_fading_levels[tracking_key] = min(curr + 0.2, 1.0)
                    streak = 0
            else:
                streak = 0

            self._group_smart_streak[tracking_key] = streak

        # Log event
        session_id = (
            session_discussion_id.split("_")[-1]
            if "_" in session_discussion_id
            else "1"
        )
        case_id = f"{tracking_key}_session_{session_id}"
        await asyncio.gather(
            self.mongo_logger.log_activity(
                {
                    "CaseID": case_id,
                    "Activity": "Goal_Validation",
                    "Timestamp": datetime.now(),
                    "Resource": f"Student_{user_id}",
                    "Lifecycle": "complete",
                    "Attributes": {
                        "original_text": goal_text,
                        "srl_object": "Learning_Goal",
                        "educational_category": "Metacognitive",
                        "is_hot": True,
                        "scaffolding_trigger": not res.is_valid,
                        "score": res.score,
                        "missingCriteria": res.missing_criteria,
                    },
                }
            ),
            self.mongo_logger.log_activity(
                {
                    "CaseID": case_id,
                    "Activity": "Goal_Setting",
                    "Timestamp": datetime.now(),
                    "Resource": f"Student_{user_id}",
                    "Lifecycle": "complete",
                    "metadata": {
                        "interactionType": "GOAL_SETTING",
                        "phase": "Forethought",
                    },
                    "content": goal_text,
                    "userId": user_id,
                }
            ),
        )

        is_valid = res.is_valid and not week_off_topic
        status = "accepted" if is_valid else "revise"

        hint: Optional[str] = None
        if not is_valid and (res.missing_criteria or week_off_topic):
            logger.info(
                "attempting_llm_hint",
                is_valid=is_valid,
                missing_criteria=res.missing_criteria,
                has_week_context=week_context is not None,
                week_off_topic=week_off_topic,
            )
            hint = await self.goal_validator.generate_llm_hint(
                goal_text, res.missing_criteria, week_context, week_off_topic
            )
            logger.info(
                "llm_hint_result",
                hint_used=hint is not None,
                hint_preview=hint[:80] if hint else None,
            )

        if not hint:
            hint = self.goal_validator.generate_socratic_hint(
                res.missing_criteria, goal_text, week_context
            )
            logger.info("using_fallback_hint", hint_preview=hint[:80] if hint else None)

        if week_off_topic:
            week_title = week_context.get("week_title", "minggu ini")
            mats = ", ".join((week_context.get("material_titles") or [])[:5])
            hint = (
                f"Goal belum selaras dengan {week_title}. "
                f"Hubungkan tujuan dengan materi minggu (mis. {mats}). {hint}"
            ).strip()

        return {
            "is_valid": is_valid,
            "status": status,
            "score": res.score,
            "feedback": res.feedback,
            "socratic_hint": hint,
            "missing_criteria": res.missing_criteria,
            "details": res.details,
            "success": True,
        }

    async def get_goal_refinement(
        self,
        current_goal: str,
        missing_criteria: List[str],
        provider_context: Optional[ProviderContext] = None,
    ) -> Dict[str, Any]:
        from app.services.llm import get_llm_service

        llm = get_llm_service(provider_context=provider_context)
        try:
            result = await llm.get_goal_refinement_suggestion(
                current_goal, missing_criteria
            )
            return {
                "success": True,
                "refined_goal": result.content,
                "explanation": f"Goal diperbaiki berdasarkan kriteria: {', '.join(missing_criteria)}",
                "suggestions": missing_criteria,
                "validation": {"is_valid": True, "score": 0.8},
                "tokens_used": result.tokens_used,
            }
        except Exception:
            logger.exception("goal_refinement_failed")
            return {"success": False, "error": "Internal error"}

    # --- Private Helpers ---

    async def _track_message(
        self, group_id: str, user_id: str, message: str, analytics: EngagementAnalysis
    ):
        """Track message with thread-safe state updates."""
        async with self._state_lock:
            if group_id not in self._group_messages:
                self._group_messages[group_id] = []
            self._group_messages[group_id].append(
                {
                    "user_id": user_id,
                    "message": message,
                    "timestamp": datetime.now(),
                    "engagement_type": analytics.engagement_type.value,
                    "is_hot": analytics.is_higher_order,
                    "lexical_variety": analytics.lexical_variety,
                }
            )
        # PERF-AI-09: Parallelize independent logic_listener calls
        await asyncio.gather(
            self.logic_listener.track_participation(group_id, user_id),
            self.logic_listener.update_last_message_time(group_id),
        )

    # BUG-05: Map orchestration issue reasons to valid InterventionType enum values
    _INTERVENTION_TYPE_MAP = {
        "low_lexical": "prompt",
        "low_quality": "clarify",
        "participation_inequity": "encourage",
    }

    def _map_intervention_type(self, reason: Optional[str]) -> Optional[str]:
        """Map internal issue reason to valid InterventionType string."""
        if not reason:
            return None
        return self._INTERVENTION_TYPE_MAP.get(reason, "prompt")

    async def _should_intervene(
        self, group_id: str, analytics: EngagementAnalysis, quality_score: float
    ) -> Tuple[bool, Optional[str]]:
        """Check if intervention is needed (thread-safe)."""
        async with self._state_lock:
            if group_id in self._last_intervention:
                if (
                    datetime.now() - self._last_intervention[group_id]
                ).total_seconds() < settings.INTERVENTION_COOLDOWN_MINUTES * 60:
                    return False, None

        if analytics.lexical_variety < settings.NLP_LOW_LEXICAL_THRESHOLD:
            return True, "low_lexical"
        if quality_score < settings.NLP_QUALITY_ALERT_THRESHOLD:
            return True, "low_quality"

        status = self.logic_listener.get_group_status(group_id)
        if (
            status.get("participation_gini", 0)
            > settings.LOGIC_LISTENER_PARTICIPATION_INEQUITY_THRESHOLD
        ):
            return True, "participation_inequity"

        return False, None

    async def _generate_intervention_message(
        self, group_id, analytics, quality_score, reason, topic, kwargs
    ) -> Optional[str]:
        """Generate intervention message via ChatInterventionService.analyze_and_intervene."""
        # Build messages list from group message history
        raw_messages = self._group_messages.get(group_id, [])
        messages = [
            {
                "role": "user",
                "content": m["message"],
                "sender_id": m["user_id"],
            }
            for m in raw_messages[-10:]
        ]

        chat_room_id = kwargs.get("chat_room_id") or group_id
        last_intervention_time = self._last_intervention.get(group_id)

        result = await self.intervention.analyze_and_intervene(
            messages=messages,
            topic=topic or "",
            chat_room_id=chat_room_id,
            last_intervention_time=last_intervention_time,
        )

        if result.should_intervene:
            return result.message
        return None

    async def get_group_analytics(self, group_id: str) -> Dict[str, Any]:
        """Aggregate in-memory and DB analytics."""
        msgs = self._group_messages.get(group_id, [])
        if not msgs:
            return {"group_id": group_id, "message_count": 0}

        q_res = self.analyzer.get_discussion_quality_score([m["message"] for m in msgs])
        parts = list(set(m["user_id"] for m in msgs))

        # Alignment (Gap 3)
        align_data = {}
        try:
            session_id = await self._get_latest_session_id(group_id)
            case_id = f"{group_id}_session_{session_id}"
            analysis = await self.plan_vs_reality.analyze_session(case_id)
            align_data = {
                "score": analysis.comparison.get("alignment_score", 0),
                "insights": analysis.insights[:3],
            }
        except:
            pass

        return {
            "group_id": group_id,
            "message_count": len(msgs),
            "quality_score": q_res["quality_score"],
            "alignment": align_data,
            "participants": parts,
            "engagement_distribution": {},
            "hot_percentage": sum(1 for m in msgs if m["is_hot"]) / len(msgs) * 100,
            "quality_breakdown": {
                "lexical_variety": sum(m["lexical_variety"] for m in msgs) / len(msgs)
            },
        }

    def _calculate_group_traffic_light(self, m) -> str:
        g = m.get("participation_equity")
        q = m.get("quality_score")
        if (g is not None and g > 0.6) or (q is not None and q < 40):
            return "red"
        if (g is not None and g > 0.4) or (q is not None and q < 60):
            return "yellow"
        return "green"

    def _calculate_individual_traffic_light(self, m) -> str:
        h = m.get("hot_percentage")
        if h is None:
            return "green"
        return "red" if h < 10 else "yellow" if h < 30 else "green"

    def _generate_teacher_advice(self, m, a, anoms) -> List[str]:
        adv = []
        equity = m.get("participation_equity")
        if equity is not None and equity > 0.6:
            adv.append("Dominasi Diskusi Terdeteksi.")

        hot = m.get("hot_percentage")
        if hot is not None and hot < 20:
            adv.append("Kualitas kognitif rendah.")

        align = a.get("score") if a else None
        if align is not None and align < 40:
            adv.append("Penyimpangan materi.")

        return adv or ["Kelompok berjalan stabil."]

    def _generate_individual_advice(self, m) -> List[str]:
        hot = m.get("hot_percentage")
        return (
            ["Tingkatkan analisis kognitif."]
            if hot is not None and hot < 20
            else ["Bagus!"]
        )

    def _analytics_to_dict(self, a: EngagementAnalysis) -> Dict[str, Any]:
        return {
            "lexical_variety": a.lexical_variety,
            "engagement_type": a.engagement_type.value,
            "is_higher_order": a.is_higher_order,
        }

    def _anomaly_to_dict(self, d) -> Dict[str, Any]:
        return {
            "type": d.anomaly_type,
            "severity": d.severity,
            "description": d.description,
            "timestamp": d.timestamp.isoformat(),
        }

    async def _get_latest_session_id(self, group_id: str) -> str:
        try:
            from app.services.repositories import ActivityLogRepository

            repo = ActivityLogRepository(self.mongo_logger.db)
            session_id = await repo.get_latest_session_for_group(group_id)
            return session_id or "1"
        except:
            return "1"

    async def _calculate_intervention_impact(self, group_id: str) -> Dict[str, Any]:
        try:
            from app.services.repositories import ActivityLogRepository

            repo = ActivityLogRepository(self.mongo_logger.db)
            last = await repo.get_last_intervention_for_group(group_id)
            if not last:
                return {"status": "none"}
            resp = await repo.get_first_student_message_after(
                group_id, last["Timestamp"]
            )
            return {"status": "positive" if resp else "no_response"}
        except:
            return {"status": "unknown"}

    def check_group_status(
        self, group_id: str, topic: Optional[str] = None
    ) -> Dict[str, Any]:
        """Check group status via Logic Listener."""
        return self.logic_listener.get_group_status(group_id)

    async def track_participation(self, group_id: str, user_id: str) -> Dict[str, Any]:
        """Track user participation via Logic Listener."""
        await self.logic_listener.track_participation(group_id, user_id)
        return {"status": "ok"}

    async def update_last_message_time(self, group_id: str) -> Dict[str, Any]:
        """Update last message timestamp via Logic Listener."""
        await self.logic_listener.update_last_message_time(group_id)
        return {"status": "ok"}

    async def set_group_topic(self, group_id: str, topic: str) -> Dict[str, Any]:
        """Set group topic via Logic Listener."""
        await self.logic_listener.set_group_topic(group_id, topic)
        return {"status": "ok"}


# Singleton
_orchestrator = None


def get_orchestrator(
    provider_context: Optional[ProviderContext] = None,
) -> Orchestrator:
    if provider_context is not None:
        return Orchestrator(provider_context=provider_context)

    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
