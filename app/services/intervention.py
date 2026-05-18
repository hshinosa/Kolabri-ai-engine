"""
Chat Intervention Service
=========================
Monitors group conversations and generates AI-driven pedagogical interventions.
Part of the Socially-Shared Regulated Learning (SSRL) support system.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.core.prompt_styles import GROUP_INTERVENTION_STYLE
from app.services.llm import OpenAILLMService, get_llm_service

logger = get_logger(__name__)


class InterventionType(str, Enum):
    """Types of chat interventions."""

    REDIRECT = "redirect"  # Redirect off-topic discussions
    PROMPT = "prompt"  # Provide discussion prompts
    SUMMARIZE = "summarize"  # Summarize discussion
    CLARIFY = "clarify"  # Ask for clarification
    RESOURCE = "resource"  # Suggest resources
    ENCOURAGE = "encourage"  # Encourage participation


@dataclass
class InterventionResult:
    """Result from intervention generation."""

    message: str
    intervention_type: InterventionType
    confidence: float
    should_intervene: bool
    reason: str
    success: bool
    error: Optional[str] = None


class ChatInterventionService:
    """
    Service for generating AI interventions in chat conversations.

    Features:
    - Detect when intervention is needed
    - Generate appropriate intervention messages
    - Track intervention effectiveness (future)
    """

    def __init__(self, llm_service: Optional[OpenAILLMService] = None):
        """Initialize intervention service."""
        self.llm_service = llm_service or get_llm_service()
        self.off_topic_threshold = settings.INTERVENTION_OFF_TOPIC_THRESHOLD
        self.inactivity_threshold_minutes = settings.INTERVENTION_INACTIVITY_THRESHOLD_MINUTES
        self.minimum_messages_for_summary = settings.INTERVENTION_MINIMUM_MESSAGES_FOR_SUMMARY
        self.prompt_temperature = settings.INTERVENTION_PROMPT_TEMPERATURE
        self.confidence_off_topic = settings.INTERVENTION_CONFIDENCE_OFF_TOPIC
        self.confidence_inactivity = settings.INTERVENTION_CONFIDENCE_INACTIVITY
        self.confidence_summarize = settings.INTERVENTION_CONFIDENCE_SUMMARIZE
        self.confidence_prompt = settings.INTERVENTION_CONFIDENCE_PROMPT
        logger.info("chat_intervention_service_initialized")

    async def analyze_and_intervene(
        self,
        messages: List[Dict[str, Any]],
        topic: str,
        chat_room_id: str,
        last_intervention_time: Optional[datetime] = None,
    ) -> InterventionResult:
        """
        Analyze chat and determine if intervention is needed.

        Args:
            messages: Recent chat messages
            topic: Expected discussion topic
            chat_room_id: Chat room identifier
            last_intervention_time: When last intervention occurred

        Returns:
            InterventionResult with intervention decision
        """
        if not messages:
            return InterventionResult(
                message="",
                intervention_type=InterventionType.ENCOURAGE,
                confidence=0,
                should_intervene=False,
                reason="No messages to analyze",
                success=True,
            )

        # Check various intervention triggers
        triggers = await self._check_triggers(
            messages=messages,
            topic=topic,
            last_intervention_time=last_intervention_time,
        )

        # Determine best intervention type
        intervention_type, confidence, reason = self._select_intervention(triggers)

        if not triggers.get("should_intervene", False):
            return InterventionResult(
                message="",
                intervention_type=intervention_type,
                confidence=confidence,
                should_intervene=False,
                reason=reason,
                success=True,
            )

        # Generate intervention message
        try:
            llm_response = await self.llm_service.generate_intervention(
                chat_messages=messages,
                intervention_type=intervention_type.value,
                topic=topic,
            )

            logger.info(
                "intervention_generated",
                chat_room=chat_room_id,
                type=intervention_type.value,
                confidence=confidence,
            )

            return InterventionResult(
                message=llm_response.content,
                intervention_type=intervention_type,
                confidence=confidence,
                should_intervene=True,
                reason=reason,
                success=llm_response.success,
                error=llm_response.error,
            )

        except Exception as e:
            logger.error(
                "intervention_generation_failed", error=str(e), chat_room=chat_room_id
            )

            return InterventionResult(
                message="",
                intervention_type=intervention_type,
                confidence=confidence,
                should_intervene=False,
                reason=f"Generation failed: {str(e)}",
                success=False,
                error=str(e),
            )

    async def generate_summary(
        self, messages: List[Dict[str, Any]], chat_room_id: str
    ) -> InterventionResult:
        """
        Generate a discussion summary.

        Args:
            messages: Messages to summarize
            chat_room_id: Chat room identifier

        Returns:
            InterventionResult with summary
        """
        if len(messages) < self.minimum_messages_for_summary:
            return InterventionResult(
                message="Belum cukup pesan untuk membuat ringkasan.",
                intervention_type=InterventionType.SUMMARIZE,
                confidence=1.0,
                should_intervene=False,
                reason=f"Need at least {self.minimum_messages_for_summary} messages",
                success=True,
            )

        try:
            llm_response = await self.llm_service.generate_summary(
                messages=messages, include_action_items=True
            )

            logger.info(
                "summary_generated", chat_room=chat_room_id, message_count=len(messages)
            )

            return InterventionResult(
                message=llm_response.content,
                intervention_type=InterventionType.SUMMARIZE,
                confidence=1.0,
                should_intervene=True,
                reason="Summary requested",
                success=llm_response.success,
                error=llm_response.error,
            )

        except Exception as e:
            logger.error(
                "summary_generation_failed", error=str(e), chat_room=chat_room_id
            )

            return InterventionResult(
                message="",
                intervention_type=InterventionType.SUMMARIZE,
                confidence=0,
                should_intervene=False,
                reason=f"Summary failed: {str(e)}",
                success=False,
                error=str(e),
            )

    async def generate_discussion_prompt(
        self, topic: str, context: Optional[str] = None, difficulty: str = "medium"
    ) -> InterventionResult:
        """
        Generate a discussion prompt for the topic.

        Args:
            topic: Discussion topic
            context: Optional additional context
            difficulty: Prompt difficulty (easy, medium, hard)

        Returns:
            InterventionResult with discussion prompt
        """
        prompt = f"""Buatkan pertanyaan diskusi untuk topik: {topic}

Tingkat kesulitan: {difficulty}
"""
        if context:
            prompt += f"\nKonteks tambahan: {context}"

        prompt += """

Buatkan 1-2 pertanyaan yang:
- Mendorong pemikiran kritis
- Mengaitkan dengan pengalaman nyata
- Membuka ruang untuk berbagai perspektif"""

        try:
            llm_response = await self.llm_service.generate(
                prompt=prompt,
                system_prompt="""Anda adalah fasilitator diskusi akademik Kolabri.
Buat pertanyaan yang memicu diskusi mendalam dan bermakna. """ + GROUP_INTERVENTION_STYLE,
                temperature=self.prompt_temperature,
            )

            if not llm_response.success:
                return InterventionResult(
                    message="",
                    intervention_type=InterventionType.PROMPT,
                    confidence=0,
                    should_intervene=False,
                    reason=f"Prompt generation failed: {llm_response.error}",
                    success=False,
                    error=llm_response.error,
                )

            return InterventionResult(
                message=llm_response.content,
                intervention_type=InterventionType.PROMPT,
                confidence=1.0,
                should_intervene=True,
                reason="Prompt requested",
                success=llm_response.success,
                error=llm_response.error,
            )

        except Exception as e:
            return InterventionResult(
                message="",
                intervention_type=InterventionType.PROMPT,
                confidence=0,
                should_intervene=False,
                reason=f"Prompt generation failed: {str(e)}",
                success=False,
                error=str(e),
            )

    async def _check_triggers(
        self,
        messages: List[Dict[str, Any]],
        topic: str,
        last_intervention_time: Optional[datetime],
    ) -> Dict[str, Any]:
        """Check various intervention triggers."""
        triggers = {
            "should_intervene": False,
            "off_topic": False,
            "off_topic_score": 0.0,
            "inactive": False,
            "needs_summary": False,
            "low_engagement": False,
        }

        # Check for inactivity
        if messages:
            last_message_time = messages[-1].get("timestamp")
            if last_message_time:
                if isinstance(last_message_time, str):
                    last_message_time = datetime.fromisoformat(
                        last_message_time.replace("Z", "+00:00")
                    )

                minutes_since = (
                    datetime.now(last_message_time.tzinfo) - last_message_time
                ).total_seconds() / 60
                if minutes_since > self.inactivity_threshold_minutes:
                    triggers["inactive"] = True
                    triggers["should_intervene"] = True

        # Check if enough messages for summary
        if len(messages) >= self.minimum_messages_for_summary:
            # Check if no recent summary
            if last_intervention_time:
                messages_since_intervention = [
                    m
                    for m in messages
                    if m.get("timestamp")
                    and datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00"))
                    > last_intervention_time
                ]
                if (
                    len(messages_since_intervention)
                    >= self.minimum_messages_for_summary
                ):
                    triggers["needs_summary"] = True

        # Simple off-topic detection (can be enhanced with embeddings)
        if topic and len(messages) >= 5:
            recent_content = " ".join(
                [m.get("content", "") for m in messages[-5:]]
            ).lower()

            topic_words = topic.lower().split()
            matches = sum(1 for word in topic_words if word in recent_content)
            topic_relevance = matches / len(topic_words) if topic_words else 1

            triggers["off_topic_score"] = 1 - topic_relevance
            if topic_relevance < 0.3:  # Less than 30% topic words found
                triggers["off_topic"] = True
                triggers["should_intervene"] = True

        return triggers

    def _select_intervention(
        self, triggers: Dict[str, Any]
    ) -> tuple[InterventionType, float, str]:
        """Select the best intervention type based on triggers."""
        if triggers.get("off_topic"):
            return (
                InterventionType.REDIRECT,
                triggers.get("off_topic_score", self.confidence_off_topic),
                "Discussion appears off-topic",
            )

        if triggers.get("inactive"):
            return (InterventionType.ENCOURAGE, self.confidence_inactivity, "Chat has been inactive")

        if triggers.get("needs_summary"):
            return (InterventionType.SUMMARIZE, self.confidence_summarize, "Enough messages for summary")

        if triggers.get("low_engagement"):
            return (InterventionType.PROMPT, self.confidence_prompt, "Low engagement detected")

        return (InterventionType.ENCOURAGE, 0.0, "No intervention needed")


# Singleton instance
_intervention_service: Optional[ChatInterventionService] = None


def get_intervention_service() -> ChatInterventionService:
    """Get or create the intervention service singleton."""
    global _intervention_service
    if _intervention_service is None:
        _intervention_service = ChatInterventionService()
    return _intervention_service
