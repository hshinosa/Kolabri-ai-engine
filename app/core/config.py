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
    ENV: Literal["development", "production", "testing"] = "production"  # ✅ SEC: Default to production
    DEBUG: bool = False  # ✅ SEC: Default to False for security
    
    # API Docs Configuration (KOL-141)
    DOCS_ENABLED: bool = False  # ✅ SEC: Disabled by default
    ENABLE_DOCS_IN_PRODUCTION: bool = False  # ✅ SEC: Never enable docs in prod

    # OpenAI Compatible API (GPT 5.2 - Best Performance)
    # ✅ SEC: No hardcoded secrets - must be loaded from environment
    OPENAI_API_KEY: str  # Required, no default
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"  # ✅ SEC: HTTPS default
    OPENAI_MODEL: str = "gpt-5.2"
    OPENAI_EMBEDDING_MODEL: str = "embedding-2"
    OPENAI_TEMPERATURE: float = 0.7
    OPENAI_MAX_TOKENS: int = 2048

    # Google Gemini API (Gemini 2.5 Flash) - Legacy, kept for compatibility
    GOOGLE_API_KEY: str = ""
    GEMINI_API_KEY: str = ""  # Alias for GOOGLE_API_KEY
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_EMBEDDING_MODEL: str = "models/text-embedding-004"
    GEMINI_TEMPERATURE: float = 0.7
    GEMINI_TOP_P: float = 0.95
    GEMINI_MAX_OUTPUT_TOKENS: int = 2048

    # Vector Database (ChromaDB)
    CHROMA_PERSIST_DIR: str = "./data/chroma"
    CHROMA_COLLECTION_PREFIX: str = "kolabri"

    # Document Processing
    MAX_FILE_SIZE_MB: int = 10
    MAX_UPLOAD_SIZE_MB: int = 10
    MAX_ZIP_SIZE_MB: int = 50  # Max size for ZIP files
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    ENABLE_OCR: bool = True

    # [PHASE 4: MULTIMODAL RAG]
    ENABLE_MULTIMODAL_PROCESSING: bool = True
    GEMINI_VISION_MODEL: str = "gpt-4o-mini"
    MIN_IMAGE_WIDTH: int = 250
    MIN_IMAGE_HEIGHT: int = 250
    STORAGE_IMAGE_DIR: str = "./data/static/images"

    # RAG Configuration
    TOP_K_RESULTS: int = 5
    SIMILARITY_THRESHOLD: float = 0.7
    RAG_MIN_QUERY_WORDS: int = 3  # Minimum words for FETCH policy

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
    CORE_API_SECRET: str  # SEC: Required, no default

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
    RERANK_MODEL_NAME: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    RERANK_TOP_K: int = 3
    RERANK_RETRIEVE_K: int = 10

    # Redis Configuration
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 32768
    REDIS_DB: int = 0

    # Efficiency Guard Configuration
    ENABLE_EFFICIENCY_GUARD: bool = True
    CACHE_TTL_SECONDS: int = 3600  # 1 hour default
    MAX_CACHE_SIZE: int = 1000
    RATE_LIMIT_MAX_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Logic Listener Thresholds
    GINI_THRESHOLD: float = 0.6
    SILENCE_THRESHOLD_MINUTES: int = 10

    @model_validator(mode="after")
    def set_gemini_api_key(self) -> "Settings":
        """Use GOOGLE_API_KEY as fallback for GEMINI_API_KEY."""
        if not self.GEMINI_API_KEY and self.GOOGLE_API_KEY:
            self.GEMINI_API_KEY = self.GOOGLE_API_KEY
        return self
    
    @model_validator(mode="after")
    def validate_security_secrets(self) -> "Settings":
        """
        ✅ SEC: KOL-143 - Validate mandatory secrets are loaded from environment.
        Fail-fast startup if security-critical env vars are missing.
        """
        if self.ENV == "production":
            errors = []
            
            # Check API keys
            if not self.OPENAI_API_KEY or self.OPENAI_API_KEY == "sk-kolabri":
                errors.append("OPENAI_API_KEY (must be set via environment, not hardcoded)")
            
            if not self.CORE_API_SECRET:
                errors.append("CORE_API_SECRET")
            
            # ✅ SEC: KOL-146 - Validate HTTPS for production URLs
            if self.OPENAI_BASE_URL.startswith("http://"):
                errors.append("OPENAI_BASE_URL must use HTTPS in production")
            
            if self.CORE_API_URL.startswith("http://"):
                errors.append("CORE_API_URL must use HTTPS in production")
            
            if errors:
                logger.critical(
                    "Security config invalid: %s", 
                    ', '.join(errors),
                    extra={"missing_vars": errors}
                )
                raise ValueError(
                    f"Security configuration invalid: {', '.join(errors)}. "
                    "Please set these via environment variables."
                )
        
        return self
    
    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        """
        ✅ SEC: KOL-141 - Ensure secure defaults for production.
        """
        if self.ENV == "production":
            if self.DEBUG:
                logger.warning(
                    "SECURITY WARNING: DEBUG enabled in production!"
                )
            
            if self.DOCS_ENABLED or self.ENABLE_DOCS_IN_PRODUCTION:
                logger.warning(
                    "SECURITY WARNING: API Docs enabled in production"
                )
            
            if self.DOCS_ENABLED or self.ENABLE_DOCS_IN_PRODUCTION:
                logger.warning(
                    "production_docs_enabled",
                    message="⚠️ SECURITY WARNING: API Docs enabled in production. This exposes API structure."
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
