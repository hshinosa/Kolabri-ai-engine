"""
Logic Listener Service
======================
Real-time monitoring for group discussion dynamics:
- Off-topic detection using embedding similarity
- Silence detection using timestamp tracking
- Intervention triggers for SSRL (Socially-Shared Regulated Learning)
"""

import time
import asyncio
import random
import math
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum

import numpy as np

from app.core.config import settings
from app.core.logging import get_logger
from app.services.embeddings import get_embedding_service
from app.services.mongodb_logger import get_mongo_logger

logger = get_logger(__name__)

# Lock for thread-safe state management
_state_lock = asyncio.Lock()


class InterventionType(str, Enum):
    """Types of interventions that can be triggered"""
    OFF_TOPIC = "off_topic"
    SILENCE = "silence"
    PARTICIPATION_INEQUITY = "participation_inequity"


@dataclass
class InterventionTrigger:
    """Result of logic listener check"""
    should_intervene: bool
    intervention_type: Optional[InterventionType]
    reason: str
    suggested_message: str
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


class LogicListener:
    """
    Service to monitor group discussion relevance and activity in real-time.
    
    HARDENED:
    - Added state cleanup to prevent memory leaks (max 1000 groups)
    - Optimized Gini calculation using NumPy
    - Consolidated random selection
    """
    
    MAX_STATE_SIZE = 1000
    
    OFF_TOPIC_INTERVENTIONS = [
        "Tim, diskusi sepertinya mulai melenceng dari topik utama. Mari kita kembali fokus ke: {topic}",
        "Diskusi kita sedikit menyimpang. Bagaimana jika kita kembali membahas: {topic}?",
        "Mari kita kembali ke topik utama: {topic}. Apa pendapat kalian tentang itu?"
    ]
    
    SILENCE_INTERVENTIONS = [
        "Tim, sudah cukup lama tidak ada aktivitas. Apakah ada yang ingin memulai diskusi?",
        "Diskusi terhenti sejenak. Siapa yang ingin melanjutkan atau memberikan pendapat?",
        "Mari kita lanjutkan diskusi. Apakah ada pertanyaan atau ide baru?",
    ]
    
    PARTICIPATION_INTERVENTIONS = [
        "@{user}, bagaimana pendapatmu tentang topik ini?",
        "@{user}, apa yang kamu pikir tentang hal ini?",
        "@{user}, apakah kamu punya ide atau pertanyaan?",
    ]
    
    def __init__(self):
        self.embedding_service = get_embedding_service()
        self.mongo_logger = get_mongo_logger()

        self.off_topic_similarity_threshold = settings.LOGIC_LISTENER_OFF_TOPIC_SIMILARITY_THRESHOLD
        self.off_topic_consecutive_threshold = settings.LOGIC_LISTENER_OFF_TOPIC_CONSECUTIVE_THRESHOLD
        self.silence_threshold_minutes = settings.SILENCE_THRESHOLD_MINUTES
        self.participation_inequity_threshold = settings.LOGIC_LISTENER_PARTICIPATION_INEQUITY_THRESHOLD

        self._off_topic_counter: Dict[str, int] = {}
        self._last_message_timestamp: Dict[str, float] = {}
        self._group_topics: Dict[str, str] = {}
        self._participation_counts: Dict[str, Dict[str, int]] = {}
        self._state_lock = asyncio.Lock()

        logger.info("LogicListener initialized with memory protection and concurrency safety")

    async def _cleanup_state_if_needed(self):
        """Simple cleanup to prevent unbounded dictionary growth (async-safe)."""
        if len(self._last_message_timestamp) > self.MAX_STATE_SIZE:
            # Remove 100 oldest entries based on timestamp
            sorted_groups = sorted(self._last_message_timestamp.items(), key=lambda x: x[1])
            for gid, _ in sorted_groups[:100]:
                self._off_topic_counter.pop(gid, None)
                self._last_message_timestamp.pop(gid, None)
                self._group_topics.pop(gid, None)
                self._participation_counts.pop(gid, None)
            logger.info("logic_listener_state_cleanup_performed")

    async def set_group_topic(self, group_id: str, topic: str) -> None:
        """Set the topic for a group (thread-safe)."""
        async with self._state_lock:
            self._group_topics[group_id] = topic
        logger.info("group_topic_set", group_id=group_id, topic=topic[:50])
    
    async def update_last_message_time(self, group_id: str) -> None:
        """Update last message timestamp and perform cleanup (thread-safe)."""
        async with self._state_lock:
            self._last_message_timestamp[group_id] = time.time()
            await self._cleanup_state_if_needed()
        logger.debug("last_message_updated", group_id=group_id)
    
    async def track_participation(self, group_id: str, user_id: str) -> None:
        """Track participation (thread-safe)."""
        async with self._state_lock:
            if group_id not in self._participation_counts:
                self._participation_counts[group_id] = {}
            
            self._participation_counts[group_id][user_id] = \
                self._participation_counts[group_id].get(user_id, 0) + 1
            
            await self._cleanup_state_if_needed()
        logger.debug("participation_tracked", group_id=group_id, user_id=user_id)
    
    async def check_relevance(
        self, 
        message: str, 
        group_id: str
    ) -> InterventionTrigger:
        """DEPRECATED (MINOR-02): Dead code — superseded by core-api silence/escalation system.
        No production callers. Retained for backward compat with tests only.

        Check if message is relevant to the group topic.
        Uses embedding similarity to detect off-topic discussions.
        Triggers intervention if 3 consecutive messages have similarity < 0.6.
        """
        topic = self._group_topics.get(group_id, "")
        
        if not topic:
            logger.warning("no_topic_set", group_id=group_id)
            return InterventionTrigger(
                should_intervene=False,
                intervention_type=None,
                reason="No topic set for group",
                suggested_message="",
                metadata={}
            )
        
        try:
            # Get embeddings
            msg_vec = await self.embedding_service.get_embedding(message)
            topic_vec = await self.embedding_service.get_embedding(topic)
            
            # Calculate cosine similarity
            similarity = self._calculate_cosine_similarity(msg_vec, topic_vec)
            
            logger.info(
                "relevance_checked",
                group_id=group_id,
                similarity=round(similarity, 3),
                message=message[:50]
            )
            
            # Update counter based on similarity (thread-safe)
            async with self._state_lock:
                if similarity < self.off_topic_similarity_threshold:
                    self._off_topic_counter[group_id] = \
                        self._off_topic_counter.get(group_id, 0) + 1
                    
                    logger.warning(
                        "off_topic_detected",
                        group_id=group_id,
                        count=self._off_topic_counter[group_id],
                        similarity=round(similarity, 3)
                    )
                else:
                    # Reset counter if message is relevant
                    if group_id in self._off_topic_counter:
                        del self._off_topic_counter[group_id]
                
                # Check if intervention is needed
                consecutive_count = self._off_topic_counter.get(group_id, 0)
            should_intervene = consecutive_count >= self.off_topic_consecutive_threshold
            
            if should_intervene:
                intervention_msg = self._get_off_topic_intervention(topic)
                
                # Log intervention to MongoDB
                await self._log_intervention(
                    group_id=group_id,
                    intervention_type=InterventionType.OFF_TOPIC,
                    reason=f"Off-topic detected: {consecutive_count} consecutive messages",
                    metadata={
                        "similarity": similarity,
                        "consecutive_count": consecutive_count,
                        "threshold": self.off_topic_similarity_threshold
                    }
                )
                
                return InterventionTrigger(
                    should_intervene=True,
                    intervention_type=InterventionType.OFF_TOPIC,
                    reason=f"Off-topic discussion detected ({consecutive_count} consecutive messages)",
                    suggested_message=intervention_msg,
                    metadata={
                        "similarity": similarity,
                        "consecutive_count": consecutive_count
                    }
                )
            
            return InterventionTrigger(
                should_intervene=False,
                intervention_type=None,
                reason="",
                suggested_message="",
                metadata={"similarity": similarity}
            )
            
        except Exception:
            logger.exception("relevance_check_failed", group_id=group_id)
            return InterventionTrigger(
                should_intervene=False,
                intervention_type=None,
                reason="Error checking relevance: internal error",
                suggested_message="",
                metadata={}
            )
    
    def check_silence(self, group_id: str) -> InterventionTrigger:
        """DEPRECATED (MINOR-02): Dead code — superseded by core-api silence/escalation system.
        No production callers. Retained for backward compat with tests only.

        Check if group has been silent for too long.
        """
        last_timestamp = self._last_message_timestamp.get(group_id)
        
        if not last_timestamp:
            logger.debug("no_last_message", group_id=group_id)
            return InterventionTrigger(
                should_intervene=False,
                intervention_type=None,
                reason="No previous message timestamp",
                suggested_message="",
                metadata={}
            )
        
        # Calculate idle time in minutes
        idle_time_minutes = (time.time() - last_timestamp) / 60
        
        logger.debug(
            "silence_checked",
            group_id=group_id,
            idle_minutes=round(idle_time_minutes, 2),
            threshold=self.silence_threshold_minutes
        )
        
        if idle_time_minutes >= self.silence_threshold_minutes:
            intervention_msg = self._get_silence_intervention()
            
            # Use try/except or check loop to avoid crash in tests without event loop
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._log_intervention(
                    group_id=group_id,
                    intervention_type=InterventionType.SILENCE,
                    reason=f"Silence detected: {round(idle_time_minutes, 2)} minutes",
                    metadata={
                        "idle_minutes": idle_time_minutes,
                        "threshold": self.silence_threshold_minutes
                    }
                ))
            except RuntimeError:
                logger.warning("no_event_loop_for_async_task")
            
            return InterventionTrigger(
                should_intervene=True,
                intervention_type=InterventionType.SILENCE,
                reason=f"Silence detected: {round(idle_time_minutes, 2)} minutes",
                suggested_message=intervention_msg,
                metadata={"idle_minutes": idle_time_minutes}
            )
        
        return InterventionTrigger(
            should_intervene=False,
            intervention_type=None,
            reason="",
            suggested_message="",
            metadata={"idle_minutes": idle_time_minutes}
        )
    
    def check_participation_inequity(
        self, 
        group_id: str
    ) -> InterventionTrigger:
        """
        Check if there's participation inequity in the group.
        
        Uses Gini coefficient to measure inequality in message distribution.
        Threshold: Gini > 0.4 indicates significant inequity.
        
        Args:
            group_id: Group identifier
        
        Returns:
            InterventionTrigger with intervention details if inequity detected
        """
        participation = self._participation_counts.get(group_id, {})
        
        if len(participation) < 2:
            logger.debug("insufficient_participants", group_id=group_id, count=len(participation))
            return InterventionTrigger(
                should_intervene=False,
                intervention_type=None,
                reason="Insufficient participants for equity check",
                suggested_message="",
                metadata={"participant_count": len(participation)}
            )
        
        total_messages = sum(participation.values())
        gini = self._calculate_gini_coefficient(list(participation.values()))
        gini_norm = self._calculate_normalized_gini(participation)
        
        logger.info(
            "participation_equity_checked",
            group_id=group_id,
            gini=round(gini, 3),
            gini_norm=round(gini_norm, 3),
            participants=len(participation),
            distribution=participation
        )
        
        if self._should_intervene_participation(participation, total_messages):
            # Find the least active user
            least_active_user = min(participation.items(), key=lambda x: x[1])[0]
            
            intervention_msg = self._get_participation_intervention(least_active_user)
            
            # Use try/except or check loop to avoid crash in tests without event loop
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._log_intervention(
                    group_id=group_id,
                    intervention_type=InterventionType.PARTICIPATION_INEQUITY,
                    reason=f"Participation inequity detected: Gini = {round(gini, 3)}",
                    metadata={
                        "gini_coefficient": gini,
                        "gini_norm": gini_norm,
                        "total_messages": total_messages,
                        "threshold": self.participation_inequity_threshold,
                        "distribution": participation,
                        "least_active_user": least_active_user
                    }
                ))
            except RuntimeError:
                logger.warning("no_event_loop_for_async_task")
            
            return InterventionTrigger(
                should_intervene=True,
                intervention_type=InterventionType.PARTICIPATION_INEQUITY,
                reason=f"Participation inequity detected (Gini: {round(gini, 3)}, Gini_norm: {round(gini_norm, 3)})",
                suggested_message=intervention_msg,
                metadata={
                    "gini_coefficient": gini,
                    "gini_norm": gini_norm,
                    "total_messages": total_messages,
                    "distribution": participation,
                    "least_active_user": least_active_user
                }
            )
        
        return InterventionTrigger(
            should_intervene=False,
            intervention_type=None,
            reason="",
            suggested_message="",
            metadata={"gini_coefficient": gini, "gini_norm": gini_norm, "total_messages": total_messages}
        )
    
    def get_all_silent_groups(self) -> List[str]:
        """Get a list of all group IDs that are currently exceeding the silence threshold."""
        silent_groups = []
        current_time = time.time()
        
        for group_id, last_ts in self._last_message_timestamp.items():
            idle_minutes = (current_time - last_ts) / 60
            if idle_minutes >= self.silence_threshold_minutes:
                # To avoid spamming, we only return groups that haven't been processed
                # This could be handled by checking when the last intervention was sent
                silent_groups.append(group_id)
        
        return silent_groups

    def get_group_topic(self, group_id: str) -> Optional[str]:
        """Get the current topic for a group."""
        return self._group_topics.get(group_id)

    def get_group_status(self, group_id: str) -> Dict[str, Any]:
        """Get current monitoring status for a group."""
        participation = self._participation_counts.get(group_id, {})
        gini_norm = (
            self._calculate_normalized_gini(participation) if len(participation) >= 2 else 0.0
        )
        return {
            "participation_gini": gini_norm,
            "participant_count": len(participation),
            "has_topic": group_id in self._group_topics,
        }

    def _calculate_cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """
        Calculate cosine similarity between two vectors.
        
        Args:
            vec1: First vector
            vec2: Second vector
        
        Returns:
            Cosine similarity score (0.0 - 1.0)
        """
        # Cosine similarity is only defined for equal-length vectors; a silent
        # truncation here would produce a bogus similarity score. Mismatches
        # raise (caught by check_relevance's caller and logged).
        dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=True))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        norm_product = norm1 * norm2
        
        if norm_product == 0:
            return 0.0
        
        return float(dot_product / norm_product)
    
    def _calculate_gini_coefficient(self, values: List[int]) -> float:
        """Optimized Gini coefficient using pure Python math."""
        if not values or sum(values) == 0:
            return 0.0

        sorted_values = sorted(values)
        n = len(sorted_values)
        total = sum(sorted_values)
        weighted_sum = sum((2 * i - n - 1) * val for i, val in enumerate(sorted_values, start=1))
        return float(weighted_sum / (n * total))

    def _calculate_normalized_gini(self, distribution: Dict[str, int]) -> float:
        """Calculate TA-normalized Gini coefficient: Gini × √N_users."""
        values = list(distribution.values())
        if len(values) < 2:
            return 0.0

        raw_gini = self._calculate_gini_coefficient(values)
        return float(raw_gini * math.sqrt(len(values)))

    def _should_intervene_participation(self, distribution: Dict[str, int], total_messages: int) -> bool:
        """Apply TA threshold and cold-start protection for participation inequity."""
        if total_messages <= 10:
            return False

        return self._calculate_normalized_gini(distribution) > self.participation_inequity_threshold
    
    def _get_off_topic_intervention(self, topic: str) -> str:
        """Get random off-topic message."""
        return random.choice(self.OFF_TOPIC_INTERVENTIONS).format(topic=topic)
    
    def _get_silence_intervention(self) -> str:
        """Get random silence message."""
        return random.choice(self.SILENCE_INTERVENTIONS)
    
    def _get_participation_intervention(self, user_id: str) -> str:
        """Get random participation message."""
        return random.choice(self.PARTICIPATION_INTERVENTIONS).format(user=user_id)
    
    async def _log_intervention(
        self,
        group_id: str,
        intervention_type: InterventionType,
        reason: str,
        metadata: Dict[str, Any]
    ) -> None:
        """
        Log intervention to MongoDB for analytics and process mining.
        
        Args:
            group_id: Group identifier
            intervention_type: Type of intervention
            reason: Reason for intervention
            metadata: Additional metadata
        """
        try:
            await self.mongo_logger.log_intervention(
                group_id=group_id,
                intervention_type=intervention_type.value,
                reason=reason,
                metadata=metadata
            )
            
            logger.info(
                "intervention_logged",
                group_id=group_id,
                type=intervention_type.value,
                reason=reason
            )
        except Exception:
            logger.exception("intervention_logging_failed", group_id=group_id)


# Singleton instance
_logic_listener: Optional[LogicListener] = None


def get_logic_listener() -> LogicListener:
    """
    Get singleton instance of LogicListener.
    
    Returns:
        LogicListener instance
    """
    global _logic_listener
    if _logic_listener is None:
        _logic_listener = LogicListener()
    return _logic_listener
