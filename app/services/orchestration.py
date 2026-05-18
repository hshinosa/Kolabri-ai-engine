"""
Orchestration Service
=====================
Primary coordinator for the AI Engine. Implements the Teacher-AI Complementarity 
loop by integrating RAG, Analytics, Anomaly Detection, and Proactive Interventions.
"""

import asyncio
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime

from app.core.logging import get_logger
from app.core.config import settings
from app.services.rag import get_rag_pipeline
from app.services.nlp_analytics import get_engagement_analyzer, EngagementAnalysis, EngagementType
from app.services.intervention import get_intervention_service
from app.services.mongodb_logger import get_mongo_logger
from app.services.goal_validator import get_goal_validator
from app.services.logic_listener import get_logic_listener
from app.services.plan_vs_reality import get_plan_vs_reality_analyzer
from app.services.process_mining_anomaly import get_anomaly_detector
from app.services.notification_service import get_notification_service
from app.utils.logger import get_process_mining_logger

logger = get_logger(__name__)

@dataclass
class OrchestrationResult:
    reply: str
    intervention: Optional[str]
    intervention_type: Optional[str]
    analytics: Dict[str, Any]
    action_taken: str
    should_notify_teacher: bool
    quality_score: Optional[float]
    success: bool
    error: Optional[str] = None

class Orchestrator:
    """Central orchestration service implementing Teacher-AI Complementarity."""
    
    def __init__(self, **services):
        self.rag = services.get('rag') or get_rag_pipeline()
        self.analyzer = services.get('analyzer') or get_engagement_analyzer()
        self.intervention = services.get('intervention') or get_intervention_service()
        self.pm_logger = services.get('pm_logger') or get_process_mining_logger()
        self.mongo_logger = get_mongo_logger()
        self.goal_validator = services.get('goal_validator') or get_goal_validator()
        self.logic_listener = services.get('logic_listener') or get_logic_listener()
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

    async def handle_message(self, user_id: str, group_id: str, message: str, topic: str = None, **kwargs) -> OrchestrationResult:
        """Handle student message through the full orchestration pipeline."""
        try:
            # 1. NLP Analysis
            analytics = self.analyzer.analyze_interaction(message)
            fading = self._group_fading_levels.get(group_id, 0.0)
            
            # 2. RAG Generation
            rag_result = await self.rag.query(query=message, collection_name=kwargs.get('collection_name'), fading_level=fading)
            bot_reply = rag_result.answer if rag_result.success else "Maaf, terjadi kesalahan."
            
            # 3. Logging & Context
            session_id = kwargs.get('chat_room_id', '1').split('_')[-1]
            case_id = f"{group_id}_session_{session_id}"
            srl_obj = self.analyzer.extract_srl_object(message, default=topic or "General")
            
            # Log Student Message
            await self.mongo_logger.log_activity({
                "CaseID": case_id, "Activity": "Student_Message", "Timestamp": datetime.now(),
                "Resource": f"Student_{user_id}", "Lifecycle": "complete",
                "Attributes": {
                    "original_text": message, "srl_object": srl_obj, "educational_category": analytics.engagement_type.value.capitalize(),
                    "is_hot": analytics.is_higher_order, "lexical_variety": analytics.lexical_variety, "scaffolding_trigger": False
                }
            })
            
            # Log Bot Response
            await self.mongo_logger.log_activity({
                "CaseID": case_id, "Activity": "Bot_Response", "Timestamp": datetime.now(),
                "Resource": "Kolabri_Bot", "Lifecycle": "complete",
                "Attributes": {
                    "original_text": bot_reply, "srl_object": srl_obj, "educational_category": "Instructional",
                    "scaffolding_trigger": rag_result.scaffolding_triggered, "action_taken": "FETCH" if rag_result.sources else "NO_FETCH",
                    "grounding_ratio": getattr(rag_result, "grounding_ratio", None),
                    "srl_phase": getattr(rag_result, "srl_phase", None),
                    "srl_sub_phase": getattr(rag_result, "srl_sub_phase", None)
                }
            })
            
            await self._track_message(group_id, user_id, message, analytics)
            
            # 4. Intervention & Anomaly Detection
            int_msg, int_type, notify = None, None, False
            q_score = None
            
            async with self._state_lock:
                group_msgs = self._group_messages.get(group_id, [])
            if len(group_msgs) >= settings.INTERVENTION_MIN_MESSAGES:
                q_res = self.analyzer.get_discussion_quality_score([m['message'] for m in group_msgs[-10:]])
                q_score = q_res['quality_score']
                
                needed, reason = await self._should_intervene(group_id, analytics, q_score)
                if needed:
                    int_msg = self._generate_intervention_message(analytics, q_score, reason, topic)
                    int_type = reason
                    await self.mongo_logger.log_intervention(group_id, reason, int_msg, {"quality": q_score}, session_id)
                    async with self._state_lock:
                        self._last_intervention[group_id] = datetime.now()
                
                # Anomaly Check (Gap 5)
                anoms = await self.anomaly_detector.detect_session_anomalies(case_id, group_id)
                if anoms.has_anomalies:
                    await self.mongo_logger.log_activity({
                        "CaseID": case_id, "Activity": "Anomaly_Detected", "Timestamp": datetime.now(),
                        "Resource": "System_AnomalyDetector", "Lifecycle": "complete",
                        "Attributes": {"original_text": anoms.description, "metadata": {"type": anoms.anomaly_type, "severity": anoms.severity}}
                    })
                    if anoms.severity == "high":
                        notify = True
                        await self.notification_service.notify_teacher(kwargs.get('course_id', 'default'), group_id, f"ANOMALY_{anoms.anomaly_type.upper()}", anoms.description)

            return OrchestrationResult(bot_reply, int_msg, int_type, self._analytics_to_dict(analytics), "FETCH" if rag_result.sources else "NO_FETCH", notify, q_score, True)
            
        except Exception as e:
            logger.error("orchestration_failed", error=str(e))
            return OrchestrationResult("Maaf, terjadi kesalahan.", None, None, {}, "ERROR", False, None, False, str(e))

    async def get_group_dashboard_data(self, group_id: str) -> Dict[str, Any]:
        """Consolidated Group Dashboard logic."""
        session_id = await self._get_latest_session_id(group_id)
        case_id = f"{group_id}_session_{session_id}"
        analytics = await self.get_group_analytics(group_id)
        impact = await self._calculate_intervention_impact(group_id)
        
        anoms = []
        try:
            det = await self.anomaly_detector.detect_session_anomalies(case_id, group_id)
            if det.has_anomalies: anoms.append(self._anomaly_to_dict(det))
        except: pass

        metrics = {
            "quality_score": analytics.get("quality_score"),
            "participation_equity": analytics.get("quality_breakdown", {}).get("participation_gini"),
            "hot_percentage": analytics.get("hot_percentage"),
            "lexical_variety": analytics.get("quality_breakdown", {}).get("lexical_variety")
        }
        
        return {
            "context": "group", "group_id": group_id, "session_id": session_id,
            "status_color": self._calculate_group_traffic_light(metrics),
            "radar_chart_data": {
                "cognitive": round(metrics["hot_percentage"] / 10, 1) if metrics["hot_percentage"] else 0,
                "collaboration": round(10 - (metrics.get("participation_equity") or 0) * 10, 1),
                "consistency": round(analytics.get("alignment", {}).get("score", 0) / 10, 1),
                "vocabulary": round((metrics["lexical_variety"] or 0) * 10, 1),
                "engagement": min(10, round(analytics.get("message_count", 0) / 2, 1))
            },
            "intervention_impact": impact, "metrics": metrics,
            "alignment": analytics.get("alignment"), "anomalies": anoms,
            "teacher_advice": self._generate_teacher_advice(metrics, analytics.get("alignment"), anoms),
            "participants": analytics.get("participants"), "engagement_distribution": analytics.get("engagement_distribution"),
            "last_updated": datetime.now().isoformat()
        }

    async def get_individual_dashboard_data(self, user_id: str, **kwargs) -> Dict[str, Any]:
        """Consolidated Individual Dashboard logic."""
        logs = await self.mongo_logger.get_activity_logs(resource=f"Student_{user_id}", limit=100)
        if not logs: return {"context": "individual", "user_id": user_id, "message_count": 0}
            
        msgs = [l["Attributes"]["original_text"] for l in logs if "Attributes" in l]
        quality = self.analyzer.get_discussion_quality_score(msgs)
        hot_count = sum(1 for l in logs if l.get("Attributes", {}).get("is_hot"))
        avg_lex = sum(l.get("Attributes", {}).get("lexical_variety", 0) for l in logs) / len(logs)
        
        metrics = {
            "avg_quality_score": quality["quality_score"], "hot_count": hot_count,
            "hot_percentage": (hot_count / len(logs)) * 100, "avg_lexical_variety": round(avg_lex, 3)
        }
        
        return {
            "context": "individual", "user_id": user_id, "status_color": self._calculate_individual_traffic_light(metrics),
            "radar_chart_data": {
                "critical_thinking": round(metrics["hot_percentage"] / 10, 1),
                "engagement": min(10, round(len(logs) / 2, 1)),
                "vocabulary": round(metrics["avg_lexical_variety"] * 10, 1),
                "quality": round(metrics["avg_quality_score"] / 10, 1),
                "consistency": 10.0 # Standard placeholder for personal consistency
            },
            "total_messages": len(logs), "personal_metrics": metrics,
            "personal_advice": self._generate_individual_advice(metrics),
            "recent_topics": list(set(l.get("Attributes", {}).get("srl_object") for l in logs if l.get("Attributes", {}).get("srl_object")))[-5:],
            "recommendation": quality["recommendation"], "last_updated": datetime.now().isoformat()
        }

    async def validate_goal(self, goal_text: str, user_id: str, chat_space_id: str) -> Dict[str, Any]:
        """Validate learning goal and handle adaptive fading (thread-safe)."""
        res = self.goal_validator.validate_goal(goal_text)
        
        async with self._state_lock:
            streak = self._group_smart_streak.get(chat_space_id, 0)
            
            if res.is_valid:
                streak += 1
                if streak >= 3:
                    curr = self._group_fading_levels.get(chat_space_id, 0.0)
                    self._group_fading_levels[chat_space_id] = min(curr + 0.2, 1.0)
                    streak = 0
            else:
                streak = 0
            
            self._group_smart_streak[chat_space_id] = streak
        
        # Log event
        session_id = chat_space_id.split('_')[-1] if '_' in chat_space_id else '1'
        await self.mongo_logger.log_activity({
            "CaseID": f"{chat_space_id}_session_{session_id}", "Activity": "Goal_Validation", "Timestamp": datetime.now(),
            "Resource": f"Student_{user_id}", "Lifecycle": "complete",
            "Attributes": {
                "original_text": goal_text, "srl_object": "Learning_Goal", "educational_category": "Metacognitive",
                "is_hot": True, "scaffolding_trigger": not res.is_valid, "score": res.score, "missingCriteria": res.missing_criteria
            }
        })
        await self.mongo_logger.log_activity({
            "CaseID": f"{chat_space_id}_session_{session_id}", "Activity": "Goal_Setting",
            "Timestamp": datetime.now(), "Resource": f"Student_{user_id}", "Lifecycle": "complete",
            "metadata": {"interactionType": "GOAL_SETTING", "phase": "Forethought"},
            "content": goal_text, "userId": user_id,
        })
        
        return {
            "is_valid": res.is_valid, "score": res.score, "feedback": res.feedback,
            "socratic_hint": self.goal_validator.generate_socratic_hint(res.missing_criteria),
            "missing_criteria": res.missing_criteria, "details": res.details, "success": True
        }

    async def get_goal_refinement(self, current_goal: str, missing_criteria: List[str]) -> Dict[str, Any]:
        from app.services.llm import get_llm_service
        llm = get_llm_service()
        try:
            result = await llm.get_goal_refinement_suggestion(current_goal, missing_criteria)
            return {
                "success": True,
                "refined_goal": result.content,
                "explanation": f"Goal diperbaiki berdasarkan kriteria: {', '.join(missing_criteria)}",
                "suggestions": missing_criteria,
                "validation": {"is_valid": True, "score": 0.8},
                "tokens_used": result.tokens_used,
            }
        except Exception as e:
            logger.error("goal_refinement_failed", error=str(e))
            return {"success": False, "error": str(e)}

    # --- Private Helpers ---

    async def _track_message(self, group_id: str, user_id: str, message: str, analytics: EngagementAnalysis):
        """Track message with thread-safe state updates."""
        async with self._state_lock:
            if group_id not in self._group_messages: 
                self._group_messages[group_id] = []
            self._group_messages[group_id].append({
                "user_id": user_id, "message": message, "timestamp": datetime.now(),
                "engagement_type": analytics.engagement_type.value, "is_hot": analytics.is_higher_order,
                "lexical_variety": analytics.lexical_variety
            })
        await self.logic_listener.track_participation(group_id, user_id)
        await self.logic_listener.update_last_message_time(group_id)

    async def _should_intervene(self, group_id: str, analytics: EngagementAnalysis, quality_score: float) -> Tuple[bool, Optional[str]]:
        """Check if intervention is needed (thread-safe)."""
        async with self._state_lock:
            if group_id in self._last_intervention:
                if (datetime.now() - self._last_intervention[group_id]).total_seconds() < settings.INTERVENTION_COOLDOWN_MINUTES * 60:
                    return False, None
        
        if analytics.lexical_variety < settings.NLP_LOW_LEXICAL_THRESHOLD: return True, "low_lexical"
        if quality_score < settings.NLP_QUALITY_ALERT_THRESHOLD: return True, "low_quality"
        
        status = self.logic_listener.get_group_status(group_id)
        if status.get("participation_gini", 0) > settings.LOGIC_LISTENER_PARTICIPATION_INEQUITY_THRESHOLD: return True, "participation_inequity"
        
        return False, None

    def _generate_intervention_message(self, analytics, quality_score, reason, topic) -> str:
        return self.intervention.generate_intervention(
            EngagementAnalysis(analytics.lexical_variety, analytics.engagement_type, analytics.is_higher_order, [], 0, 0, 1.0),
            reason, topic
        ).message

    async def get_group_analytics(self, group_id: str) -> Dict[str, Any]:
        """Aggregate in-memory and DB analytics."""
        msgs = self._group_messages.get(group_id, [])
        if not msgs: return {"group_id": group_id, "message_count": 0}
        
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
                "insights": analysis.insights[:3]
            }
        except: pass

        return {
            "group_id": group_id, "message_count": len(msgs), "quality_score": q_res["quality_score"],
            "alignment": align_data, "participants": parts, "engagement_distribution": {},
            "hot_percentage": sum(1 for m in msgs if m["is_hot"]) / len(msgs) * 100,
            "quality_breakdown": {"lexical_variety": sum(m["lexical_variety"] for m in msgs) / len(msgs)}
        }

    def _calculate_group_traffic_light(self, m) -> str:
        g = m.get("participation_equity")
        q = m.get("quality_score")
        if (g is not None and g > 0.6) or (q is not None and q < 40): return "red"
        if (g is not None and g > 0.4) or (q is not None and q < 60): return "yellow"
        return "green"

    def _calculate_individual_traffic_light(self, m) -> str:
        h = m.get("hot_percentage")
        if h is None: return "green"
        return "red" if h < 10 else "yellow" if h < 30 else "green"

    def _generate_teacher_advice(self, m, a, anoms) -> List[str]:
        adv = []
        equity = m.get("participation_equity")
        if equity is not None and equity > 0.6: adv.append("Dominasi Diskusi Terdeteksi.")
        
        hot = m.get("hot_percentage")
        if hot is not None and hot < 20: adv.append("Kualitas kognitif rendah.")
        
        align = a.get("score") if a else None
        if align is not None and align < 40: adv.append("Penyimpangan materi.")
        
        return adv or ["Kelompok berjalan stabil."]

    def _generate_individual_advice(self, m) -> List[str]:
        hot = m.get("hot_percentage")
        return ["Tingkatkan analisis kognitif."] if hot is not None and hot < 20 else ["Bagus!"]

    def _analytics_to_dict(self, a: EngagementAnalysis) -> Dict[str, Any]:
        return {"lexical_variety": a.lexical_variety, "engagement_type": a.engagement_type.value, "is_higher_order": a.is_higher_order}

    def _anomaly_to_dict(self, d) -> Dict[str, Any]:
        return {"type": d.anomaly_type, "severity": d.severity, "description": d.description, "timestamp": d.timestamp.isoformat()}

    async def _get_latest_session_id(self, group_id: str) -> str:
        try:
            from app.services.repositories import ActivityLogRepository
            repo = ActivityLogRepository(self.mongo_logger.db)
            session_id = await repo.get_latest_session_for_group(group_id)
            return session_id or "1"
        except: return "1"

    async def _calculate_intervention_impact(self, group_id: str) -> Dict[str, Any]:
        try:
            from app.services.repositories import ActivityLogRepository
            repo = ActivityLogRepository(self.mongo_logger.db)
            last = await repo.get_last_intervention_for_group(group_id)
            if not last: return {"status": "none"}
            resp = await repo.get_first_student_message_after(group_id, last["Timestamp"])
            return {"status": "positive" if resp else "no_response"}
        except: return {"status": "unknown"}

# Singleton
_orchestrator = None

def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
