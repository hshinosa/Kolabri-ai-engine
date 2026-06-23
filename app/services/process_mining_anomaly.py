"""
Process Mining Anomaly Detection Service
========================================
Detects deviations in learning process patterns based on XES event logs.
Identifies bottlenecks, sequence skips, and engagement anomalies.
"""

from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import statistics

from app.core.logging import get_logger
from app.core.config import settings
from app.services.mongodb_logger import MongoDBLogger, get_mongo_logger
from app.services.conformance_checker import ConformanceChecker

logger = get_logger(__name__)


@dataclass
class AnomalyDetectionResult:
    """Result from anomaly detection."""
    has_anomalies: bool
    anomaly_type: str
    severity: str  # 'low', 'medium', 'high'
    description: str
    affected_users: List[str]
    affected_groups: List[str]
    metrics: Dict[str, Any]
    recommendations: List[str]
    timestamp: datetime


@dataclass
class ProcessPattern:
    """Represents a learning process pattern."""
    pattern_id: str
    sequence: List[str]
    frequency: int
    avg_duration: float
    success_rate: float


class ProcessMiningAnomalyDetector:
    """
    Detects anomalies in learning process patterns.
    
    Features:
    - Sequence anomaly detection (missing phases)
    - Duration anomaly detection (too fast/too slow)
    - Participation anomaly detection (uneven engagement)
    - Quality anomaly detection (low HOT percentage)
    - Bottleneck detection (stuck in specific phases)
    
    Uses MongoDB event logs with Gen-SRL taxonomy tags.
    """
    
    # Expected learning sequence based on Zimmerman's cycle
    EXPECTED_SEQUENCE = [
        "GOAL_SETTING",      # Forethought phase
        "STUDENT_MESSAGE",   # Performance phase
        "BOT_RESPONSE",      # Performance phase
        "SYSTEM_INTERVENTION",  # Performance phase (optional)
        "REFLECTION_SUBMITTED"  # Reflection phase
    ]
    
    # Anomaly thresholds
    MIN_SEQUENCE_COMPLETION = 0.6  # 60% of expected sequence
    MAX_SESSION_DURATION_HOURS = 4.0
    MIN_SESSION_DURATION_MINUTES = 5.0
    MIN_HOT_PERCENTAGE = 20.0
    MIN_PARTICIPATION_EQUITY = 0.6  # Gini coefficient threshold
    MAX_SILENCE_DURATION_MINUTES = 15.0
    
    def __init__(self, mongo_logger: Optional[MongoDBLogger] = None):
        """
        Initialize the anomaly detector.
        
        Args:
            mongo_logger: MongoDB logger for accessing event logs
        """
        self.mongo_logger = mongo_logger or get_mongo_logger()
        self._cache: Dict[str, Any] = {}
        self._cache_ttl = timedelta(minutes=5)
        self._conformance_checker = ConformanceChecker()
        
        logger.info("process_mining_anomaly_detector_initialized")
    
    async def detect_session_anomalies(
        self,
        session_discussion_id: str,
        group_id: Optional[str] = None
    ) -> AnomalyDetectionResult:
        """
        Detect anomalies in a learning session.
        
        Args:
            session_discussion_id: The session discussion ID to analyze
            group_id: Optional group ID for context
            
        Returns:
            AnomalyDetectionResult with detected anomalies
        """
        try:
            # Get event logs for the session
            events = await self.mongo_logger.get_activity_logs(
                case_id=session_discussion_id,
                limit=1000
            )
            
            if not events:
                return AnomalyDetectionResult(
                    has_anomalies=False,
                    anomaly_type="no_data",
                    severity="low",
                    description="No event logs found for this session",
                    affected_users=[],
                    affected_groups=[group_id] if group_id else [],
                    metrics={},
                    recommendations=[],
                    timestamp=datetime.now()
                )
            
            # Analyze sequence
            sequence_anomalies = self._detect_sequence_anomalies(events)
            
            # Analyze duration
            duration_anomalies = self._detect_duration_anomalies(events)
            
            # Analyze participation
            participation_anomalies = self._detect_participation_anomalies(events)
            
            # Analyze quality
            quality_anomalies = self._detect_quality_anomalies(events)
            
            # Analyze bottlenecks
            bottleneck_anomalies = self._detect_bottlenecks(events)
            
            # Aggregate anomalies
            all_anomalies = [
                sequence_anomalies,
                duration_anomalies,
                participation_anomalies,
                quality_anomalies,
                bottleneck_anomalies
            ]
            
            # Filter out None results
            valid_anomalies = [a for a in all_anomalies if a is not None]
            
            if not valid_anomalies:
                return AnomalyDetectionResult(
                    has_anomalies=False,
                    anomaly_type="none",
                    severity="low",
                    description="No anomalies detected in this session",
                    affected_users=[],
                    affected_groups=[group_id] if group_id else [],
                    metrics=self._calculate_session_metrics(events),
                    recommendations=[],
                    timestamp=datetime.now()
                )
            
            # Get highest severity anomaly
            highest_severity = max(valid_anomalies, key=lambda x: self._severity_score(x.severity))
            
            # Aggregate affected users and groups
            affected_users = list(set(
                user for anomaly in valid_anomalies for user in anomaly.affected_users
            ))
            affected_groups = list(set(
                grp for anomaly in valid_anomalies for grp in anomaly.affected_groups
            ))
            
            # Aggregate recommendations
            recommendations = []
            for anomaly in valid_anomalies:
                recommendations.extend(anomaly.recommendations)
            
            # Aggregate metrics
            metrics = self._calculate_session_metrics(events)
            observed_sequence = [
                event.get("metadata", {}).get("interactionType", "UNKNOWN")
                for event in events
            ]
            conformance = self._conformance_checker.check(observed_sequence)
            metrics["conformance"] = {
                "is_conformant": conformance.is_conformant,
                "alignment_score": conformance.alignment_score,
                "token_replay_score": conformance.token_replay_score,
                "missing_activities": conformance.missing_activities,
                "extra_activities": conformance.extra_activities,
                "alignment_details": conformance.alignment_details,
            }
            for anomaly in valid_anomalies:
                metrics.update(anomaly.metrics)
            
            return AnomalyDetectionResult(
                has_anomalies=True,
                anomaly_type=highest_severity.anomaly_type,
                severity=highest_severity.severity,
                description=f"Detected {len(valid_anomalies)} anomaly type(s): {', '.join([a.anomaly_type for a in valid_anomalies])}",
                affected_users=affected_users,
                affected_groups=affected_groups,
                metrics=metrics,
                recommendations=list(set(recommendations)),
                timestamp=datetime.now()
            )
            
        except Exception:
            logger.exception(
                "session_anomaly_detection_failed",
                session_discussion_id=session_discussion_id
            )

            return AnomalyDetectionResult(
                has_anomalies=False,
                anomaly_type="error",
                severity="low",
                description="Failed to detect anomalies: internal error",
                affected_users=[],
                affected_groups=[group_id] if group_id else [],
                metrics={},
                recommendations=[],
                timestamp=datetime.now()
            )
    
    async def detect_course_anomalies(
        self,
        course_id: str
    ) -> AnomalyDetectionResult:
        """
        Detect anomalies across all sessions in a course.
        
        Args:
            course_id: The course ID to analyze
            
        Returns:
            AnomalyDetectionResult with course-level anomalies
        """
        try:
            # Get all event logs for the course
            events = await self.mongo_logger.get_activity_logs_by_course(
                course_id=course_id,
                limit=5000
            )
            
            if not events:
                return AnomalyDetectionResult(
                    has_anomalies=False,
                    anomaly_type="no_data",
                    severity="low",
                    description="No event logs found for this course",
                    affected_users=[],
                    affected_groups=[],
                    metrics={},
                    recommendations=[],
                    timestamp=datetime.now()
                )
            
            # Group events by session discussion
            session_discussion_events = defaultdict(list)
            for event in events:
                session_discussion_id = event.get("CaseID")
                if session_discussion_id:
                    session_discussion_events[session_discussion_id].append(event)
            
            # Detect anomalies in each session
            session_anomalies = []
            for session_discussion_id, session_events in session_discussion_events.items():
                group_id = session_events[0].get("groupId") if session_events else None
                anomaly = await self.detect_session_anomalies(
                    session_discussion_id=session_discussion_id,
                    group_id=group_id
                )
                if anomaly.has_anomalies:
                    session_anomalies.append(anomaly)
            
            if not session_anomalies:
                return AnomalyDetectionResult(
                    has_anomalies=False,
                    anomaly_type="none",
                    severity="low",
                    description="No anomalies detected across all sessions",
                    affected_users=[],
                    affected_groups=[],
                    metrics=self._calculate_course_metrics(events),
                    recommendations=[],
                    timestamp=datetime.now()
                )
            
            # Aggregate results
            affected_users = list(set(
                user for anomaly in session_anomalies for user in anomaly.affected_users
            ))
            affected_groups = list(set(
                grp for anomaly in session_anomalies for grp in anomaly.affected_groups
            ))
            
            # Count anomaly types
            anomaly_types = Counter([a.anomaly_type for a in session_anomalies])
            
            # Aggregate recommendations
            recommendations = []
            for anomaly in session_anomalies:
                recommendations.extend(anomaly.recommendations)
            
            # Calculate course metrics
            metrics = self._calculate_course_metrics(events)
            observed_sequence = [
                event.get("metadata", {}).get("interactionType", "UNKNOWN")
                for event in events
            ]
            conformance = self._conformance_checker.check(observed_sequence)
            metrics["conformance"] = {
                "is_conformant": conformance.is_conformant,
                "alignment_score": conformance.alignment_score,
                "token_replay_score": conformance.token_replay_score,
                "missing_activities": conformance.missing_activities,
                "extra_activities": conformance.extra_activities,
                "alignment_details": conformance.alignment_details,
            }
            metrics["anomaly_summary"] = dict(anomaly_types)
            metrics["sessions_with_anomalies"] = len(session_anomalies)
            metrics["total_sessions"] = len(session_discussion_events)
            
            return AnomalyDetectionResult(
                has_anomalies=True,
                anomaly_type="course_level",
                severity="high" if len(session_anomalies) > len(session_discussion_events) * 0.5 else "medium",
                description=f"Detected anomalies in {len(session_anomalies)}/{len(session_discussion_events)} sessions",
                affected_users=affected_users,
                affected_groups=affected_groups,
                metrics=metrics,
                recommendations=list(set(recommendations)),
                timestamp=datetime.now()
            )
            
        except Exception:
            logger.exception(
                "course_anomaly_detection_failed",
                course_id=course_id
            )

            return AnomalyDetectionResult(
                has_anomalies=False,
                anomaly_type="error",
                severity="low",
                description="Failed to detect anomalies: internal error",
                affected_users=[],
                affected_groups=[],
                metrics={},
                recommendations=[],
                timestamp=datetime.now()
            )
    
    def _detect_sequence_anomalies(
        self,
        events: List[Dict[str, Any]]
    ) -> Optional[AnomalyDetectionResult]:
        """Detect sequence anomalies (missing phases)."""
        try:
            # Extract interaction types
            interaction_types = [
                event.get("metadata", {}).get("interactionType", "UNKNOWN")
                for event in events
            ]
            
            # Check for missing phases
            missing_phases = []
            for expected_phase in self.EXPECTED_SEQUENCE:
                if expected_phase not in interaction_types:
                    missing_phases.append(expected_phase)
            
            # Calculate sequence completion
            completion_rate = len(set(interaction_types) & set(self.EXPECTED_SEQUENCE)) / len(self.EXPECTED_SEQUENCE)
            
            if completion_rate < self.MIN_SEQUENCE_COMPLETION:
                severity = "high" if completion_rate < 0.3 else "medium"
                
                return AnomalyDetectionResult(
                    has_anomalies=True,
                    anomaly_type="sequence_anomaly",
                    severity=severity,
                    description=f"Learning sequence incomplete: {completion_rate:.1%} completion. Missing phases: {', '.join(missing_phases)}",
                    affected_users=[event.get("userId") for event in events if event.get("userId")],
                    affected_groups=[event.get("groupId") for event in events if event.get("groupId")],
                    metrics={
                        "completion_rate": completion_rate,
                        "missing_phases": missing_phases,
                        "actual_sequence": interaction_types
                    },
                    recommendations=[
                        "Encourage students to complete all learning phases",
                        "Provide guidance on missing phases",
                        "Review session structure with students"
                    ],
                    timestamp=datetime.now()
                )
            
            return None
            
        except Exception as e:
            logger.error("sequence_anomaly_detection_failed", error=str(e))
            return None
    
    def _detect_duration_anomalies(
        self,
        events: List[Dict[str, Any]]
    ) -> Optional[AnomalyDetectionResult]:
        """Detect duration anomalies (too fast/too slow)."""
        try:
            if len(events) < 2:
                return None
            
            # Calculate session duration
            start_time = min(event.get("createdAt") for event in events)
            end_time = max(event.get("createdAt") for event in events)
            duration_hours = (end_time - start_time).total_seconds() / 3600
            duration_minutes = (end_time - start_time).total_seconds() / 60
            
            # Check for anomalies
            if duration_hours > self.MAX_SESSION_DURATION_HOURS:
                return AnomalyDetectionResult(
                    has_anomalies=True,
                    anomaly_type="duration_anomaly",
                    severity="medium",
                    description=f"Session duration too long: {duration_hours:.1f} hours",
                    affected_users=[event.get("userId") for event in events if event.get("userId")],
                    affected_groups=[event.get("groupId") for event in events if event.get("groupId")],
                    metrics={
                        "duration_hours": duration_hours,
                        "duration_minutes": duration_minutes,
                        "event_count": len(events)
                    },
                    recommendations=[
                        "Consider breaking long sessions into smaller chunks",
                        "Check if students are stuck on specific topics",
                        "Provide more structured guidance"
                    ],
                    timestamp=datetime.now()
                )
            
            if duration_minutes < self.MIN_SESSION_DURATION_MINUTES:
                return AnomalyDetectionResult(
                    has_anomalies=True,
                    anomaly_type="duration_anomaly",
                    severity="low",
                    description=f"Session duration too short: {duration_minutes:.1f} minutes",
                    affected_users=[event.get("userId") for event in events if event.get("userId")],
                    affected_groups=[event.get("groupId") for event in events if event.get("groupId")],
                    metrics={
                        "duration_hours": duration_hours,
                        "duration_minutes": duration_minutes,
                        "event_count": len(events)
                    },
                    recommendations=[
                        "Encourage more in-depth discussion",
                        "Provide additional learning materials",
                        "Extend session time if needed"
                    ],
                    timestamp=datetime.now()
                )
            
            return None
            
        except Exception as e:
            logger.error("duration_anomaly_detection_failed", error=str(e))
            return None
    
    def _detect_participation_anomalies(
        self,
        events: List[Dict[str, Any]]
    ) -> Optional[AnomalyDetectionResult]:
        """Detect participation anomalies (uneven engagement)."""
        try:
            # Count messages per user
            user_messages = defaultdict(int)
            for event in events:
                user_id = event.get("userId")
                if user_id and event.get("senderType") == "student":
                    user_messages[user_id] += 1
            
            if len(user_messages) < 2:
                return None
            
            # Calculate Gini coefficient
            message_counts = list(user_messages.values())
            gini = self._calculate_gini_coefficient(message_counts)
            
            if gini > (1.0 - self.MIN_PARTICIPATION_EQUITY):
                severity = "high" if gini > 0.7 else "medium"
                
                # Identify silent and dominant users
                avg_messages = statistics.mean(message_counts)
                silent_users = [uid for uid, count in user_messages.items() if count < avg_messages * 0.5]
                dominant_users = [uid for uid, count in user_messages.items() if count > avg_messages * 2.0]
                
                return AnomalyDetectionResult(
                    has_anomalies=True,
                    anomaly_type="participation_anomaly",
                    severity=severity,
                    description=f"Participation inequity detected: Gini coefficient {gini:.2f}",
                    affected_users=silent_users + dominant_users,
                    affected_groups=[event.get("groupId") for event in events if event.get("groupId")],
                    metrics={
                        "gini_coefficient": gini,
                        "user_count": len(user_messages),
                        "silent_users": len(silent_users),
                        "dominant_users": len(dominant_users),
                        "message_distribution": dict(user_messages)
                    },
                    recommendations=[
                        "Encourage silent users to participate more",
                        "Ask dominant users to let others speak",
                        "Use structured turn-taking if needed",
                        "Provide specific prompts to silent users"
                    ],
                    timestamp=datetime.now()
                )
            
            return None
            
        except Exception as e:
            logger.error("participation_anomaly_detection_failed", error=str(e))
            return None
    
    def _detect_quality_anomalies(
        self,
        events: List[Dict[str, Any]]
    ) -> Optional[AnomalyDetectionResult]:
        """Detect quality anomalies (low HOT percentage)."""
        try:
            # Calculate HOT percentage
            hot_count = 0
            total_count = 0
            
            for event in events:
                engagement = event.get("engagement", {})
                if engagement.get("isHigherOrder"):
                    hot_count += 1
                total_count += 1
            
            if total_count == 0:
                return None
            
            hot_percentage = (hot_count / total_count) * 100
            
            if hot_percentage < self.MIN_HOT_PERCENTAGE:
                severity = "high" if hot_percentage < 10 else "medium"
                
                return AnomalyDetectionResult(
                    has_anomalies=True,
                    anomaly_type="quality_anomaly",
                    severity=severity,
                    description=f"Low Higher-Order Thinking detected: {hot_percentage:.1f}% HOT",
                    affected_users=[event.get("userId") for event in events if event.get("userId")],
                    affected_groups=[event.get("groupId") for event in events if event.get("groupId")],
                    metrics={
                        "hot_percentage": hot_percentage,
                        "hot_count": hot_count,
                        "total_count": total_count
                    },
                    recommendations=[
                        "Encourage deeper thinking with 'why' and 'how' questions",
                        "Provide examples of higher-order thinking",
                        "Use Socratic questioning techniques",
                        "Reward analytical responses"
                    ],
                    timestamp=datetime.now()
                )
            
            return None
            
        except Exception as e:
            logger.error("quality_anomaly_detection_failed", error=str(e))
            return None
    
    def _detect_bottlenecks(
        self,
        events: List[Dict[str, Any]]
    ) -> Optional[AnomalyDetectionResult]:
        """Detect bottlenecks (stuck in specific phases)."""
        try:
            # Count events by interaction type
            interaction_counts = Counter([
                event.get("metadata", {}).get("interactionType", "UNKNOWN")
                for event in events
            ])
            
            # Check for excessive time in specific phases
            phase_durations = defaultdict(list)
            prev_time = None
            prev_phase = None
            
            for event in sorted(events, key=lambda x: x.get("createdAt", datetime.now())):
                current_time = event.get("createdAt")
                current_phase = event.get("metadata", {}).get("interactionType", "UNKNOWN")
                
                if prev_time and prev_phase:
                    duration = (current_time - prev_time).total_seconds() / 60  # minutes
                    phase_durations[prev_phase].append(duration)
                
                prev_time = current_time
                prev_phase = current_phase
            
            # Check for bottlenecks
            bottlenecks = []
            for phase, durations in phase_durations.items():
                avg_duration = self._average_phase_duration(durations)
                if avg_duration is not None and avg_duration > self.MAX_SILENCE_DURATION_MINUTES:
                    bottlenecks.append({
                        "phase": phase,
                        "avg_duration": avg_duration,
                        "max_duration": max(durations),
                    })
            
            if bottlenecks:
                bottleneck_info = ", ".join([
                    f"{b['phase']} ({b['avg_duration']:.1f} min)" for b in bottlenecks
                ])
                
                return AnomalyDetectionResult(
                    has_anomalies=True,
                    anomaly_type="bottleneck",
                    severity="medium",
                    description=f"Bottlenecks detected in phases: {bottleneck_info}",
                    affected_users=[event.get("userId") for event in events if event.get("userId")],
                    affected_groups=[event.get("groupId") for event in events if event.get("groupId")],
                    metrics={
                        "bottlenecks": bottlenecks,
                        "phase_distribution": dict(interaction_counts)
                    },
                    recommendations=[
                        "Provide additional support for stuck phases",
                        "Break down complex tasks into smaller steps",
                        "Offer alternative approaches",
                        "Check for technical issues or confusion"
                    ],
                    timestamp=datetime.now()
                )
            
            return None
            
        except Exception as e:
            logger.error("bottleneck_detection_failed", error=str(e))
            return None
    
    def _calculate_session_metrics(
        self,
        events: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Calculate session-level metrics."""
        try:
            if not events:
                return {}
            
            # Duration
            start_time = min(event.get("createdAt") for event in events)
            end_time = max(event.get("createdAt") for event in events)
            duration_minutes = (end_time - start_time).total_seconds() / 60
            
            # User count
            unique_users = len(set(event.get("userId") for event in events if event.get("userId")))
            
            # Message count
            message_count = len(events)
            
            # HOT percentage
            hot_count = sum(1 for event in events if event.get("engagement", {}).get("isHigherOrder"))
            hot_percentage = (hot_count / message_count * 100) if message_count > 0 else 0
            
            # Average lexical variety
            lexical_varieties = [
                event.get("engagement", {}).get("lexicalVariety", 0)
                for event in events
            ]
            avg_lexical = statistics.mean(lexical_varieties) if lexical_varieties else 0
            
            return {
                "duration_minutes": duration_minutes,
                "unique_users": unique_users,
                "message_count": message_count,
                "hot_percentage": hot_percentage,
                "avg_lexical_variety": avg_lexical
            }
            
        except Exception as e:
            logger.error("session_metrics_calculation_failed", error=str(e))
            return {}
    
    def _calculate_course_metrics(
        self,
        events: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Calculate course-level metrics."""
        try:
            if not events:
                return {}
            
            # Group by session discussion
            session_discussion_events = defaultdict(list)
            for event in events:
                session_discussion_id = event.get("CaseID")
                if session_discussion_id:
                    session_discussion_events[session_discussion_id].append(event)
            
            # Calculate metrics for each session
            session_metrics = []
            for session_discussion_id, session_events in session_discussion_events.items():
                metrics = self._calculate_session_metrics(session_events)
                session_metrics.append(metrics)
            
            # Aggregate metrics
            total_sessions = len(session_metrics)
            avg_duration = statistics.mean([m.get("duration_minutes", 0) for m in session_metrics]) if session_metrics else 0
            avg_hot = statistics.mean([m.get("hot_percentage", 0) for m in session_metrics]) if session_metrics else 0
            
            return {
                "total_sessions": total_sessions,
                "avg_duration_minutes": avg_duration,
                "avg_hot_percentage": avg_hot,
                "total_messages": len(events)
            }
            
        except Exception as e:
            logger.error("course_metrics_calculation_failed", error=str(e))
            return {}
    
    def _calculate_gini_coefficient(self, values: List[float]) -> float:
        """Calculate Gini coefficient for inequality measurement."""
        try:
            if not values or len(values) < 2:
                return 0.0
            
            sorted_values = sorted(values)
            n = len(values)
            cumulative_sum = 0
            
            for i, value in enumerate(sorted_values):
                cumulative_sum += (i + 1) * value
            
            gini = (2 * cumulative_sum) / (n * sum(sorted_values)) - (n + 1) / n
            return max(0.0, min(1.0, gini))
            
        except Exception as e:
            logger.error("gini_calculation_failed", error=str(e))
            return 0.0
    
    def _severity_score(self, severity: str) -> int:
        """Convert severity to numeric score for comparison."""
        severity_scores = {"low": 1, "medium": 2, "high": 3}
        return severity_scores.get(severity, 0)
    @staticmethod
    def _average_phase_duration(durations: List[float]) -> Optional[float]:
        if not durations:
            return None
        return statistics.mean(durations)


# Singleton instance
_anomaly_detector: Optional[ProcessMiningAnomalyDetector] = None


def get_anomaly_detector() -> ProcessMiningAnomalyDetector:
    """Get or create the anomaly detector singleton."""
    global _anomaly_detector
    if _anomaly_detector is None:
        _anomaly_detector = ProcessMiningAnomalyDetector()
    return _anomaly_detector
