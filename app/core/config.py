"""
Application Configuration
=========================
Pydantic settings for environment variable management.
"""

import os
import logging
from pathlib import Path
from typing import Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from functools import lru_cache


# Get the ai-engine directory path
AI_ENGINE_DIR = Path(__file__).resolve().parent.parent.parent

# Setup logger for config validation
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    VERSION: str = "1.0.0"

    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8001
    ENV: Literal["development", "production", "testing"] = (
        "production"  # ✅ SEC: Default to production
    )
    DEBUG: bool = False  # ✅ SEC: Default to False for security

    # API Docs Configuration (KOL-141)
    DOCS_ENABLED: bool = False  # ✅ SEC: Disabled by default
    ENABLE_DOCS_IN_PRODUCTION: bool = False  # ✅ SEC: Never enable docs in prod

    # OpenAI Compatible API (GPT 5.2 - Best Performance)
    # ✅ SEC: No hardcoded secrets - must be loaded from environment
    OPENAI_API_KEY: str = ""  # Validated in production via model_validator
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"  # ✅ SEC: HTTPS default
    OPENAI_MODEL: str = "deepseek/deepseek-chat"
    OPENAI_EMBEDDING_MODEL: str = "embedding-2"
    OPENAI_TEMPERATURE: float = 0.7
    OPENAI_MAX_TOKENS: int = 2048

    # No Google services used (project focuses on OpenAI-compatible only)

    # Vector Database (Qdrant)
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION_PREFIX: str = "kolabri"

    # Embedding (Local FastEmbed)
    EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    # Document Processing
    MAX_FILE_SIZE_MB: int = 10
    MAX_UPLOAD_SIZE_MB: int = 10
    MAX_ZIP_SIZE_MB: int = 50  # Max size for ZIP files
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    ENABLE_OCR: bool = True

    # [PHASE 4: MULTIMODAL RAG]
    ENABLE_MULTIMODAL_PROCESSING: bool = True
    MIN_IMAGE_WIDTH: int = 250
    MIN_IMAGE_HEIGHT: int = 250
    STORAGE_IMAGE_DIR: str = "./data/static/images"

    # Server
    WORKERS: int = 2

    # RAG Configuration
    TOP_K_RESULTS: int = 7
    SIMILARITY_THRESHOLD: float = 0.15  # Lowered from 0.25 to further improve recall
    RAG_MIN_QUERY_WORDS: int = 3  # Minimum words for FETCH policy
    RAG_SEMANTIC_CACHE_THRESHOLD: float = 0.85
    RAG_GROUNDING_THRESHOLD: float = 0.4

    # NLP Analytics (SSRL Metrics)
    NLP_LOW_LEXICAL_THRESHOLD: float = 0.3  # Below this = shallow discussion
    NLP_HOT_TARGET_PERCENTAGE: float = 40.0  # Target % of HOT messages
    NLP_QUALITY_ALERT_THRESHOLD: float = 30.0  # Notify teacher below this

    # Orchestration (Teacher-AI Complementarity)
    INTERVENTION_COOLDOWN_MINUTES: int = 5  # Min time between interventions
    INTERVENTION_MIN_MESSAGES: int = 5  # Min messages before quality check
    NOTIFY_TEACHER_ON_LOW_QUALITY: bool = True

    # Scaffolding Fading Configuration
    SCAFFOLDING_FULL_THRESHOLD: float = 0.3
    SCAFFOLDING_MINIMAL_THRESHOLD: float = 0.7
    SCAFFOLDING_MAX_MESSAGES: int = 20

    # Core-API Integration
    CORE_API_URL: str = "https://api.kolabri.com"  # SEC: HTTPS default
    CORE_API_SECRET: str = ""  # Validated in production via model_validator

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["json", "console"] = "json"

    # MongoDB Configuration
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "kolabri"
    ENABLE_MONGODB_LOGGING: bool = True

    # MongoDB Connection Pooling (KOL-138)
    MONGO_MAX_POOL_SIZE: int = 50
    MONGO_MIN_POOL_SIZE: int = 10
    MONGO_MAX_IDLE_TIME_MS: int = 30000
    MONGO_CONNECT_TIMEOUT_MS: int = 5000

    # Circuit Breaker Configuration (KOL-135)
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = 60
    CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int = 3

    # RAG Re-Ranking Configuration (KOL-136)
    ENABLE_RERANKING: bool = True
    # Backend: fastembed.rerank.cross_encoder.TextCrossEncoder (ONNX-runtime).
    # jina-reranker-v2-base-multilingual is multilingual (incl. Indonesian) and
    # ships an ONNX wheel via fastembed - works on Intel Mac + Python 3.13
    # without torch. Override via env if you need a different model from
    # TextCrossEncoder.list_supported_models().
    RERANK_MODEL_NAME: str = "jinaai/jina-reranker-v2-base-multilingual"
    RERANK_TOP_K: int = 3
    RERANK_RETRIEVE_K: int = 10
    # Persistent cache dir for downloaded reranker models. macOS evicts /var/folders
    # tmp dirs unpredictably, breaking fastembed's cache integrity check. Setting an
    # explicit project-local path avoids that. Empty string = let fastembed use its
    # default (tmp dir).
    RERANK_CACHE_DIR: str = ""

    # Redis Configuration
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None

    # Efficiency Guard Configuration
    ENABLE_EFFICIENCY_GUARD: bool = True
    CACHE_TTL_SECONDS: int = 3600  # 1 hour default
    MAX_CACHE_SIZE: int = 1000
    RATE_LIMIT_MAX_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Logic Listener Thresholds
    LOGIC_LISTENER_OFF_TOPIC_SIMILARITY_THRESHOLD: float = 0.6
    LOGIC_LISTENER_OFF_TOPIC_CONSECUTIVE_THRESHOLD: int = 3
    LOGIC_LISTENER_PARTICIPATION_INEQUITY_THRESHOLD: float = 0.6
    SILENCE_THRESHOLD_MINUTES: int = 10

    # Intervention Thresholds
    INTERVENTION_OFF_TOPIC_THRESHOLD: float = 0.6
    INTERVENTION_INACTIVITY_THRESHOLD_MINUTES: int = 30
    INTERVENTION_MINIMUM_MESSAGES_FOR_SUMMARY: int = 10
    INTERVENTION_PROMPT_TEMPERATURE: float = 0.8
    INTERVENTION_CONFIDENCE_OFF_TOPIC: float = 0.5
    INTERVENTION_CONFIDENCE_INACTIVITY: float = 0.8
    INTERVENTION_CONFIDENCE_SUMMARIZE: float = 0.7
    INTERVENTION_CONFIDENCE_PROMPT: float = 0.6

    # LLM Retry & Timeout
    LLM_MAX_RETRIES: int = 3
    LLM_RETRY_DELAY_BASE: float = 1.0
    LLM_RETRY_DELAY_MULTIPLIER: float = 2.0
    LLM_TIMEOUT_CONNECT_SECONDS: float = 10.0
    LLM_TIMEOUT_READ_SECONDS: float = 45.0  # PERF-AI-07: Reduced from 90s for faster fail-fast
    LLM_RETRY_DEFAULT_RETRY_AFTER_SECONDS: int = 30

    UNIFIED_PROVIDER_ENABLED: bool = False
    UNIFIED_PROVIDER_PERSONAL_CHAT: bool = False
    UNIFIED_PROVIDER_ORCHESTRATION: bool = False
    UNIFIED_PROVIDER_INTERVENTIONS: bool = False
    UNIFIED_PROVIDER_SUMMARIES: bool = False
    UNIFIED_PROVIDER_GOALS: bool = False
    UNIFIED_PROVIDER_RAG: bool = False
    UNIFIED_PROVIDER_ANALYTICS: bool = False

    @model_validator(mode="after")
    def validate_security_secrets(self) -> "Settings":
        """
        ✅ SEC: KOL-143 - Validate mandatory secrets are loaded from environment.
        Fail-fast startup if security-critical env vars are missing.
        """
        if self.ENV == "production":
            errors = []

            # Always reject known placeholder keys (even when unified provider is on)
            if self.OPENAI_API_KEY == "sk-kolabri":
                errors.append(
                    "OPENAI_API_KEY (must be set via environment, not hardcoded)"
                )

            # Check API keys (skip empty check when unified provider is source of truth)
            if not self.UNIFIED_PROVIDER_ENABLED:
                if not self.OPENAI_API_KEY:
                    errors.append(
                        "OPENAI_API_KEY (must be set via environment, not hardcoded)"
                    )

            # ✅ SEC: Reject default/weak secrets
            if not self.CORE_API_SECRET:
                errors.append("CORE_API_SECRET")
            elif self.CORE_API_SECRET in [
                "shared-secret-key",
                "secret",
                "default",
                "changeme",
            ]:
                errors.append(
                    "CORE_API_SECRET menggunakan nilai default yang lemah. Harap gunakan secret yang kuat."
                )

            if not self.UNIFIED_PROVIDER_ENABLED:
                if self.OPENAI_API_KEY and len(self.OPENAI_API_KEY) < 20:
                    errors.append(
                        "OPENAI_API_KEY terlalu pendek, kemungkinan tidak valid atau lemah"
                    )

            # ✅ SEC: KOL-146 - Validate HTTPS for production URLs
            if self.OPENAI_BASE_URL.startswith("http://"):
                errors.append("OPENAI_BASE_URL must use HTTPS in production")

            if self.CORE_API_URL.startswith("http://"):
                errors.append("CORE_API_URL must use HTTPS in production")

            if errors:
                logger.critical(
                    "Security config invalid: %s",
                    ", ".join(errors),
                    extra={"missing_vars": errors},
                )
                raise RuntimeError(
                    f"❌ Konfigurasi keamanan tidak valid: {', '.join(errors)}. "
                    "Silakan atur variabel ini melalui environment variables dengan nilai yang kuat."
                )

        return self

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        """
        ✅ SEC: KOL-141 - Ensure secure defaults for production.
        """
        if self.ENV == "production":
            if self.DEBUG:
                logger.warning("SECURITY WARNING: DEBUG enabled in production!")

            if self.DOCS_ENABLED or self.ENABLE_DOCS_IN_PRODUCTION:
                logger.warning("SECURITY WARNING: API Docs enabled in production")

            if self.DOCS_ENABLED or self.ENABLE_DOCS_IN_PRODUCTION:
                logger.warning(
                    "production_docs_enabled",
                    message="⚠️ SECURITY WARNING: API Docs enabled in production. This exposes API structure.",
                )

        return self

    model_config = SettingsConfigDict(
        env_file=str(AI_ENGINE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # Ignore extra environment variables (from Laravel, etc.)
    )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()
