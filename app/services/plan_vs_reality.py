"""
Plan vs Reality Analysis Service
================================
Compares planned learning goals with actual discussion activities
to support student reflection and SRL mastery.
"""

from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
from collections import defaultdict, Counter
import statistics

from app.core.logging import get_logger
from app.core.config import settings
from app.services.mongodb_logger import MongoDBLogger, get_mongo_logger

logger = get_logger(__name__)


@dataclass
class PlanVsRealityResult:
    """Result from plan vs reality analysis."""
    case_id: str
    goal_id: Optional[str]
    plan: Dict[str, Any]
    reality: Dict[str, Any]
    comparison: Dict[str, Any]
    visualization_data: Dict[str, Any]
    insights: List[str]
    recommendations: List[str]
    timestamp: datetime


@dataclass
class TopicAnalysis:
    """Analysis of topics discussed."""
    planned_topics: List[str]
    actual_topics: List[str]
    coverage: Dict[str, float]  # topic -> coverage percentage
    missing_topics: List[str]
    extra_topics: List[str]


class PlanVsRealityAnalyzer:
    """
    Analyzes and visualizes the comparison between planned learning goals
    and actual learning activities.
    
    Features:
    - Topic coverage analysis
    - Time allocation comparison
    - Goal achievement tracking
    - Keyword frequency comparison
    - Reflection insights generation
    """
    
    def __init__(self, mongo_logger: Optional[MongoDBLogger] = None):
        """
        Initialize the analyzer.
        
        Args:
            mongo_logger: MongoDB logger for accessing event logs
        """
        self.mongo_logger = mongo_logger or get_mongo_logger()
        
        logger.info("plan_vs_reality_analyzer_initialized")
    
    async def analyze_session(
        self,
        chat_space_id: str,
        goal_id: Optional[str] = None
    ) -> PlanVsRealityResult:
        """
        Analyze plan vs reality for a learning session.
        
        Args:
            chat_space_id: The chat space ID to analyze
            goal_id: Optional goal ID for specific goal analysis
            
        Returns:
            PlanVsRealityResult with comparison and visualization data
        """
        try:
            # Get event logs for the session
            events = await self.mongo_logger.get_activity_logs(
                case_id=chat_space_id,
                limit=1000
            )
            
            if not events:
                return PlanVsRealityResult(
                    case_id=chat_space_id,
                    goal_id=goal_id,
                    plan={},
                    reality={},
                    comparison={},
                    visualization_data={},
                    insights=["No event logs found for this session"],
                    recommendations=[],
                    timestamp=datetime.now()
                )
            
            # Extract plan (Forethought phase)
            plan = self._extract_plan(events, goal_id)
            
            # Extract reality (Performance phase)
            reality = self._extract_reality(events)
            
            # Compare plan vs reality
            comparison = self._compare_plan_reality(plan, reality)
            
            # Generate visualization data
            visualization_data = self._generate_visualization_data(plan, reality, comparison)
            
            # Generate insights
            insights = self._generate_insights(plan, reality, comparison)
            
            # Generate recommendations
            recommendations = self._generate_recommendations(plan, reality, comparison)
            
            return PlanVsRealityResult(
                case_id=chat_space_id,
                goal_id=goal_id,
                plan=plan,
                reality=reality,
                comparison=comparison,
                visualization_data=visualization_data,
                insights=insights,
                recommendations=recommendations,
                timestamp=datetime.now()
            )
            
        except Exception:
            logger.exception(
                "plan_vs_reality_analysis_failed",
                chat_space_id=chat_space_id
            )

            return PlanVsRealityResult(
                case_id=chat_space_id,
                goal_id=goal_id,
                plan={},
                reality={},
                comparison={},
                visualization_data={},
                insights=["Analysis failed: internal error"],
                recommendations=[],
                timestamp=datetime.now()
            )
    
    def _extract_plan(
        self,
        events: List[Dict[str, Any]],
        goal_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Extract planned learning goals from Forethought phase."""
        try:
            # Filter for goal setting events — use Activity field (primary) or metadata (backward compat)
            goal_events = [
                e for e in events
                if e.get("Activity") in ["Goal_Setting", "Goal_Validation"]
                or e.get("metadata", {}).get("interactionType") == "GOAL_SETTING"
                or e.get("metadata", {}).get("phase") == "Forethought"
            ]

            if not goal_events:
                return {
                    "has_plan": False,
                    "goals": [],
                    "topics": [],
                    "keywords": [],
                    "time_allocation": {}
                }

            # Extract goals — content/userId for Goal_Setting events, Attributes for others
            goals = []
            for event in goal_events:
                content = event.get("content") or event.get("Attributes", {}).get("original_text", "")
                if content:
                    goals.append({
                        "content": content,
                        "timestamp": event.get("Timestamp") or event.get("createdAt"),
                        "user_id": event.get("userId") or event.get("Resource", "").replace("Student_", "")
                    })

            # Extract topics from goals
            topics = self._extract_topics_from_goals(goals)

            # Extract keywords from goals
            keywords = self._extract_keywords_from_goals(goals)

            # Calculate time allocation (if available)
            time_allocation = self._calculate_time_allocation(goal_events)

            return {
                "has_plan": True,
                "goals": goals,
                "topics": topics,
                "keywords": keywords,
                "time_allocation": time_allocation,
                "goal_count": len(goals)
            }

        except Exception:
            logger.exception("plan_extraction_failed")
            return {
                "has_plan": False,
                "goals": [],
                "topics": [],
                "keywords": [],
                "time_allocation": {}
            }
    
    def _extract_reality(
        self,
        events: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Extract actual learning activities from Performance phase."""
        try:
            # Filter for performance phase events — use Activity field (primary) or metadata (backward compat)
            performance_events = [
                e for e in events
                if e.get("Activity") in ["Student_Message", "Bot_Response"]
                or e.get("metadata", {}).get("interactionType") in ["STUDENT_MESSAGE", "BOT_RESPONSE"]
                or e.get("metadata", {}).get("phase") == "Performance"
            ]

            if not performance_events:
                return {
                    "has_reality": False,
                    "topics": [],
                    "keywords": [],
                    "message_count": 0,
                    "duration_minutes": 0,
                    "engagement_metrics": {}
                }

            # Normalize events to have "content" field (from Attributes.original_text or content)
            normalized_events = []
            for e in performance_events:
                normalized = e.copy()
                if "content" not in normalized:
                    normalized["content"] = e.get("Attributes", {}).get("original_text", "")
                normalized_events.append(normalized)

            # Extract topics from messages
            topics = self._extract_topics_from_messages(normalized_events)

            # Extract keywords from messages
            keywords = self._extract_keywords_from_messages(normalized_events)

            # Calculate duration
            duration_minutes = self._calculate_session_duration(normalized_events)

            # Calculate engagement metrics
            engagement_metrics = self._calculate_engagement_metrics(normalized_events)

            return {
                "has_reality": True,
                "topics": topics,
                "keywords": keywords,
                "message_count": len(normalized_events),
                "duration_minutes": duration_minutes,
                "engagement_metrics": engagement_metrics
            }
            
        except Exception:
            logger.exception("reality_extraction_failed")
            return {
                "has_reality": False,
                "topics": [],
                "keywords": [],
                "message_count": 0,
                "duration_minutes": 0,
                "engagement_metrics": {}
            }
    
    def _compare_plan_reality(
        self,
        plan: Dict[str, Any],
        reality: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compare plan vs reality."""
        try:
            # Topic coverage
            planned_topics = set(plan.get("topics", []))
            actual_topics = set(reality.get("topics", []))
            
            covered_topics = planned_topics & actual_topics
            missing_topics = planned_topics - actual_topics
            extra_topics = actual_topics - planned_topics
            
            topic_coverage = {
                "planned_count": len(planned_topics),
                "actual_count": len(actual_topics),
                "covered_count": len(covered_topics),
                "missing_count": len(missing_topics),
                "extra_count": len(extra_topics),
                "coverage_percentage": (len(covered_topics) / len(planned_topics) * 100) if planned_topics else 0,
                "covered_topics": list(covered_topics),
                "missing_topics": list(missing_topics),
                "extra_topics": list(extra_topics)
            }
            
            # Keyword comparison
            planned_keywords = plan.get("keywords", [])
            actual_keywords = reality.get("keywords", [])
            
            keyword_overlap = set(planned_keywords) & set(actual_keywords)
            keyword_coverage = {
                "planned_count": len(planned_keywords),
                "actual_count": len(actual_keywords),
                "overlap_count": len(keyword_overlap),
                "overlap_percentage": (len(keyword_overlap) / len(planned_keywords) * 100) if planned_keywords else 0,
                "overlap_keywords": list(keyword_overlap)
            }
            
            # Time comparison
            planned_time = plan.get("time_allocation", {})
            actual_duration = reality.get("duration_minutes", 0)
            
            time_comparison = {
                "planned_minutes": planned_time.get("total_minutes", 0),
                "actual_minutes": actual_duration,
                "difference_minutes": actual_duration - planned_time.get("total_minutes", 0),
                "percentage_difference": ((actual_duration - planned_time.get("total_minutes", 0)) / planned_time.get("total_minutes", 1) * 100) if planned_time.get("total_minutes", 0) > 0 else 0
            }
            
            # Overall alignment score
            alignment_score = self._calculate_alignment_score(topic_coverage, keyword_coverage)
            
            return {
                "topic_coverage": topic_coverage,
                "keyword_coverage": keyword_coverage,
                "time_comparison": time_comparison,
                "alignment_score": alignment_score,
                "overall_status": self._get_overall_status(alignment_score)
            }
            
        except Exception:
            logger.exception("plan_reality_comparison_failed")
            return {}
    
    def _generate_visualization_data(
        self,
        plan: Dict[str, Any],
        reality: Dict[str, Any],
        comparison: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate data for visualization."""
        try:
            # Radar chart data
            radar_data = {
                "labels": ["Topic Coverage", "Keyword Alignment", "Time Management", "Goal Achievement", "Engagement Quality"],
                "plan_values": [
                    comparison.get("topic_coverage", {}).get("coverage_percentage", 0),
                    comparison.get("keyword_coverage", {}).get("overlap_percentage", 0),
                    100,  # Plan assumes 100% time management
                    100,  # Plan assumes 100% goal achievement
                    100   # Plan assumes 100% engagement
                ],
                "reality_values": [
                    comparison.get("topic_coverage", {}).get("coverage_percentage", 0),
                    comparison.get("keyword_coverage", {}).get("overlap_percentage", 0),
                    min(100, max(0, 100 - abs(comparison.get("time_comparison", {}).get("percentage_difference", 0)))),
                    comparison.get("topic_coverage", {}).get("coverage_percentage", 0),
                    reality.get("engagement_metrics", {}).get("hot_percentage", 0)
                ]
            }
            
            # Bar chart data for topic comparison
            topic_bar_data = {
                "planned": comparison.get("topic_coverage", {}).get("planned_count", 0),
                "covered": comparison.get("topic_coverage", {}).get("covered_count", 0),
                "missing": comparison.get("topic_coverage", {}).get("missing_count", 0),
                "extra": comparison.get("topic_coverage", {}).get("extra_count", 0)
            }
            
            # Word cloud data
            word_cloud_data = {
                "planned_keywords": plan.get("keywords", []),
                "actual_keywords": reality.get("keywords", []),
                "overlap_keywords": comparison.get("keyword_coverage", {}).get("overlap_keywords", [])
            }
            
            # Timeline data
            timeline_data = {
                "planned_duration": comparison.get("time_comparison", {}).get("planned_minutes", 0),
                "actual_duration": comparison.get("time_comparison", {}).get("actual_minutes", 0),
                "difference": comparison.get("time_comparison", {}).get("difference_minutes", 0)
            }
            
            return {
                "radar_chart": radar_data,
                "topic_bar_chart": topic_bar_data,
                "word_cloud": word_cloud_data,
                "timeline": timeline_data
            }
            
        except Exception:
            logger.exception("visualization_data_generation_failed")
            return {}
    
    def _generate_insights(
        self,
        plan: Dict[str, Any],
        reality: Dict[str, Any],
        comparison: Dict[str, Any]
    ) -> List[str]:
        """Generate insights from plan vs reality comparison."""
        insights = []
        
        try:
            # Topic coverage insights
            topic_coverage = comparison.get("topic_coverage", {})
            coverage_percentage = topic_coverage.get("coverage_percentage", 0)
            
            if coverage_percentage >= 80:
                insights.append(f"Excellent topic coverage: {coverage_percentage:.1f}% of planned topics were discussed")
            elif coverage_percentage >= 60:
                insights.append(f"Good topic coverage: {coverage_percentage:.1f}% of planned topics were discussed")
            elif coverage_percentage >= 40:
                insights.append(f"Moderate topic coverage: {coverage_percentage:.1f}% of planned topics were discussed")
            else:
                insights.append(f"Low topic coverage: Only {coverage_percentage:.1f}% of planned topics were discussed")
            
            # Missing topics
            missing_topics = topic_coverage.get("missing_topics", [])
            if missing_topics:
                insights.append(f"Missing topics: {', '.join(missing_topics[:3])}")
            
            # Extra topics
            extra_topics = topic_coverage.get("extra_topics", [])
            if extra_topics:
                insights.append(f"Extra topics explored: {', '.join(extra_topics[:3])}")
            
            # Time management insights
            time_comparison = comparison.get("time_comparison", {})
            time_diff = time_comparison.get("difference_minutes", 0)
            
            if abs(time_diff) < 5:
                insights.append("Time management: On track with planned duration")
            elif time_diff > 0:
                insights.append(f"Time management: Exceeded planned duration by {time_diff:.1f} minutes")
            else:
                insights.append(f"Time management: Under planned duration by {abs(time_diff):.1f} minutes")
            
            # Engagement insights
            engagement_metrics = reality.get("engagement_metrics", {})
            hot_percentage = engagement_metrics.get("hot_percentage", 0)
            
            if hot_percentage >= 40:
                insights.append(f"High-quality engagement: {hot_percentage:.1f}% Higher-Order Thinking")
            elif hot_percentage >= 20:
                insights.append(f"Moderate engagement: {hot_percentage:.1f}% Higher-Order Thinking")
            else:
                insights.append(f"Low engagement: Only {hot_percentage:.1f}% Higher-Order Thinking")
            
            # Overall alignment
            alignment_score = comparison.get("alignment_score", 0)
            if alignment_score >= 80:
                insights.append(f"Strong alignment between plan and reality ({alignment_score:.1f}%)")
            elif alignment_score >= 60:
                insights.append(f"Moderate alignment between plan and reality ({alignment_score:.1f}%)")
            else:
                insights.append(f"Weak alignment between plan and reality ({alignment_score:.1f}%)")
            
        except Exception:
            logger.exception("insights_generation_failed")
            insights.append("Unable to generate insights")
        
        return insights
    
    def _generate_recommendations(
        self,
        plan: Dict[str, Any],
        reality: Dict[str, Any],
        comparison: Dict[str, Any]
    ) -> List[str]:
        """Generate recommendations for improvement."""
        recommendations = []
        
        try:
            # Topic coverage recommendations
            topic_coverage = comparison.get("topic_coverage", {})
            coverage_percentage = topic_coverage.get("coverage_percentage", 0)
            
            if coverage_percentage < 60:
                recommendations.append("Focus on covering all planned topics in future sessions")
                missing_topics = topic_coverage.get("missing_topics", [])
                if missing_topics:
                    recommendations.append(f"Prioritize discussing: {', '.join(missing_topics[:2])}")
            
            # Time management recommendations
            time_comparison = comparison.get("time_comparison", {})
            time_diff = time_comparison.get("difference_minutes", 0)
            
            if time_diff > 10:
                recommendations.append("Consider breaking down complex topics into smaller sessions")
            elif time_diff < -10:
                recommendations.append("Consider extending session time to cover all planned topics")
            
            # Engagement recommendations
            engagement_metrics = reality.get("engagement_metrics", {})
            hot_percentage = engagement_metrics.get("hot_percentage", 0)
            
            if hot_percentage < 20:
                recommendations.append("Encourage deeper thinking with 'why' and 'how' questions")
                recommendations.append("Use Socratic questioning techniques to promote Higher-Order Thinking")
            
            # Keyword alignment recommendations
            keyword_coverage = comparison.get("keyword_coverage", {})
            overlap_percentage = keyword_coverage.get("overlap_percentage", 0)
            
            if overlap_percentage < 50:
                recommendations.append("Ensure discussion stays focused on planned keywords")
                recommendations.append("Use planned terminology consistently throughout the session")
            
            # Overall recommendations
            alignment_score = comparison.get("alignment_score", 0)
            if alignment_score < 70:
                recommendations.append("Review and refine learning goals to better match actual activities")
                recommendations.append("Consider adjusting time allocation to better match reality")
            
        except Exception:
            logger.exception("recommendations_generation_failed")
            recommendations.append("Unable to generate recommendations")
        
        return recommendations
    
    def _extract_topics_from_goals(self, goals: List[Dict[str, Any]]) -> List[str]:
        """Extract topics from goal statements."""
        topics = []
        
        # Common topic keywords
        topic_keywords = [
            "design", "wireframe", "prototype", "user experience", "ux",
            "interface", "navigation", "layout", "color", "typography",
            "testing", "usability", "accessibility", "responsive",
            "mobile", "web", "app", "software", "development",
            "analysis", "research", "planning", "implementation"
        ]
        
        for goal in goals:
            content = goal.get("content", "").lower()
            for keyword in topic_keywords:
                if keyword in content:
                    topics.append(keyword)
        
        return list(set(topics))
    
    def _extract_topics_from_messages(self, messages: List[Dict[str, Any]]) -> List[str]:
        """Extract topics from message content."""
        topics = []
        
        # Common topic keywords
        topic_keywords = [
            "design", "wireframe", "prototype", "user experience", "ux",
            "interface", "navigation", "layout", "color", "typography",
            "testing", "usability", "accessibility", "responsive",
            "mobile", "web", "app", "software", "development",
            "analysis", "research", "planning", "implementation"
        ]
        
        for message in messages:
            content = message.get("content", "").lower()
            for keyword in topic_keywords:
                if keyword in content:
                    topics.append(keyword)
        
        return list(set(topics))
    
    def _extract_keywords_from_goals(self, goals: List[Dict[str, Any]]) -> List[str]:
        """Extract keywords from goal statements."""
        keywords = []
        
        # Common words to filter out
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at",
            "to", "for", "of", "with", "by", "from", "as", "is", "was",
            "are", "were", "be", "been", "being", "have", "has", "had",
            "do", "does", "did", "will", "would", "could", "should",
            "may", "might", "must", "shall", "can", "need", "want",
            "make", "create", "build", "develop", "design", "implement"
        }
        
        for goal in goals:
            content = goal.get("content", "").lower()
            words = content.split()
            for word in words:
                # Remove punctuation
                word = word.strip(".,!?;:\"'()[]{}")
                if len(word) > 3 and word not in stop_words:
                    keywords.append(word)
        
        return list(set(keywords))
    
    def _extract_keywords_from_messages(self, messages: List[Dict[str, Any]]) -> List[str]:
        """Extract keywords from message content."""
        keywords = []
        
        # Common words to filter out
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at",
            "to", "for", "of", "with", "by", "from", "as", "is", "was",
            "are", "were", "be", "been", "being", "have", "has", "had",
            "do", "does", "did", "will", "would", "could", "should",
            "may", "might", "must", "shall", "can", "need", "want",
            "make", "create", "build", "develop", "design", "implement",
            "yes", "no", "ok", "okay", "yeah", "nope", "hmm", "uh"
        }
        
        for message in messages:
            content = message.get("content", "").lower()
            words = content.split()
            for word in words:
                # Remove punctuation
                word = word.strip(".,!?;:\"'()[]{}")
                if len(word) > 3 and word not in stop_words:
                    keywords.append(word)
        
        return list(set(keywords))
    
    def _calculate_time_allocation(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate time allocation from events."""
        if not events:
            return {"total_minutes": 0}
        
        # Extract timestamps - try Timestamp field first, then createdAt
        timestamps = []
        for e in events:
            ts = e.get("Timestamp") or e.get("createdAt")
            if ts:
                timestamps.append(ts)
        
        if len(timestamps) < 2:
            return {"total_minutes": 0}
        
        try:
            start_time = min(timestamps)
            end_time = max(timestamps)
            duration_minutes = (end_time - start_time).total_seconds() / 60
        except (TypeError, AttributeError):
            # If timestamps are strings or can't be subtracted, return 0
            return {"total_minutes": 0}
        
        return {
            "total_minutes": duration_minutes,
            "start_time": start_time,
            "end_time": end_time
        }
    
    def _calculate_session_duration(self, events: List[Dict[str, Any]]) -> float:
        """Calculate session duration in minutes."""
        if not events:
            return 0.0
        
        # Extract timestamps - try Timestamp (capital T) first, then timestamp (lowercase), then createdAt
        timestamps = []
        for e in events:
            ts = e.get("Timestamp") or e.get("timestamp") or e.get("createdAt")
            if ts:
                timestamps.append(ts)
        
        if len(timestamps) < 2:
            return 0.0
        
        try:
            start_time = min(timestamps)
            end_time = max(timestamps)
            return (end_time - start_time).total_seconds() / 60
        except (TypeError, AttributeError):
            return 0.0
    
    def _calculate_engagement_metrics(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate engagement metrics."""
        if not events:
            return {}
        
        # Calculate HOT percentage - check Attributes.is_hot or engagement.isHigherOrder
        hot_count = sum(
            1 for e in events 
            if e.get("Attributes", {}).get("is_hot") 
            or e.get("engagement", {}).get("isHigherOrder")
        )
        total_count = len(events)
        hot_percentage = (hot_count / total_count * 100) if total_count > 0 else 0
        
        # Calculate average lexical variety - check Attributes.lexical_variety or engagement.lexicalVariety
        lexical_varieties = [
            e.get("Attributes", {}).get("lexical_variety") 
            or e.get("engagement", {}).get("lexicalVariety") 
            or 0
            for e in events
        ]
        avg_lexical = statistics.mean(lexical_varieties) if lexical_varieties else 0
        
        # Calculate engagement type distribution - use Attributes.srl_object or engagement.engagementType
        engagement_types = defaultdict(int)
        for e in events:
            eng_type = (
                e.get("Attributes", {}).get("srl_object") 
                or e.get("engagement", {}).get("engagementType") 
                or "behavioral"
            )
            engagement_types[eng_type] += 1
        
        return {
            "hot_percentage": hot_percentage,
            "avg_lexical_variety": avg_lexical,
            "engagement_distribution": dict(engagement_types)
        }
    
    def _calculate_alignment_score(
        self,
        topic_coverage: Dict[str, Any],
        keyword_coverage: Dict[str, Any]
    ) -> float:
        """Calculate overall alignment score."""
        try:
            topic_score = topic_coverage.get("coverage_percentage", 0)
            keyword_score = keyword_coverage.get("overlap_percentage", 0)
            
            # Weighted average (topics more important than keywords)
            alignment_score = (topic_score * 0.7) + (keyword_score * 0.3)
            
            return round(alignment_score, 1)
            
        except Exception:
            logger.exception("alignment_score_calculation_failed")
            return 0.0
    
    def _get_overall_status(self, alignment_score: float) -> str:
        """Get overall status based on alignment score."""
        if alignment_score >= 80:
            return "excellent"
        elif alignment_score >= 60:
            return "good"
        elif alignment_score >= 40:
            return "moderate"
        else:
            return "poor"


# Singleton instance
_plan_vs_reality_analyzer: Optional[PlanVsRealityAnalyzer] = None


def get_plan_vs_reality_analyzer() -> PlanVsRealityAnalyzer:
    """Get or create the plan vs reality analyzer singleton."""
    global _plan_vs_reality_analyzer
    if _plan_vs_reality_analyzer is None:
        _plan_vs_reality_analyzer = PlanVsRealityAnalyzer()
    return _plan_vs_reality_analyzer