import pytest
import os
from unittest.mock import patch
from app.core.config import Settings


@pytest.mark.unit
def test_settings_overrides():
    # Test loading from environment
    with patch.dict(
        os.environ, {"OPENAI_API_KEY": "env_key", "OPENAI_MODEL": "env_model"}
    ):
        settings = Settings()
        assert settings.OPENAI_API_KEY == "env_key"
        assert settings.OPENAI_MODEL == "env_model"


@pytest.mark.unit
def test_production_settings_require_security_secrets():
    with pytest.raises(RuntimeError) as exc_info:
        Settings(
            ENV="production",
            OPENAI_API_KEY="",
            CORE_API_SECRET="",
            OPENAI_BASE_URL="http://insecure-openai.local",
            CORE_API_URL="http://insecure-core.local",
        )

    message = str(exc_info.value)
    assert "OPENAI_API_KEY" in message
    assert "CORE_API_SECRET" in message
    assert "OPENAI_BASE_URL must use HTTPS in production" in message
    assert "CORE_API_URL must use HTTPS in production" in message


@pytest.mark.unit
def test_production_settings_reject_hardcoded_placeholder_key():
    with pytest.raises(RuntimeError) as exc_info:
        Settings(
            ENV="production",
            OPENAI_API_KEY="sk-kolabri",
            CORE_API_SECRET="secret",
        )

    assert "OPENAI_API_KEY" in str(exc_info.value)


@pytest.mark.unit
def test_testing_settings_allow_missing_production_secrets():
    settings = Settings(
        ENV="testing",
        OPENAI_API_KEY="",
        CORE_API_SECRET="",
        OPENAI_BASE_URL="http://local-openai.test",
        CORE_API_URL="http://local-core.test",
    )

    assert settings.ENV == "testing"
    assert settings.OPENAI_API_KEY == ""
    assert settings.CORE_API_SECRET == ""


@pytest.mark.unit
def test_production_settings_warn_on_debug_enabled():
    with patch("app.core.config.logger.warning") as mock_warning:
        settings = Settings(
            ENV="production",
            OPENAI_API_KEY="a-very-long-production-openai-key-1234567890abcdef",
            CORE_API_SECRET="a-very-long-production-core-secret-1234567890abcdef",
            DEBUG=True,
            OPENAI_BASE_URL="https://api.openai.com/v1",
            CORE_API_URL="https://api.kolabri.com",
        )

    assert settings.DEBUG is True
    mock_warning.assert_any_call("SECURITY WARNING: DEBUG enabled in production!")


@pytest.mark.unit
def test_production_settings_warn_twice_when_docs_enabled():
    with patch("app.core.config.logger.warning") as mock_warning:
        settings = Settings(
            ENV="production",
            OPENAI_API_KEY="a-very-long-production-openai-key-1234567890abcdef",
            CORE_API_SECRET="a-very-long-production-core-secret-1234567890abcdef",
            DOCS_ENABLED=True,
            OPENAI_BASE_URL="https://api.openai.com/v1",
            CORE_API_URL="https://api.kolabri.com",
        )

    assert settings.DOCS_ENABLED is True
    assert mock_warning.call_count >= 2
    mock_warning.assert_any_call("SECURITY WARNING: API Docs enabled in production")
    mock_warning.assert_any_call(
        "production_docs_enabled",
        message="⚠️ SECURITY WARNING: API Docs enabled in production. This exposes API structure.",
    )


@pytest.mark.unit
def test_production_settings_warn_twice_when_enable_docs_in_production_flag_enabled():
    with patch("app.core.config.logger.warning") as mock_warning:
        settings = Settings(
            ENV="production",
            OPENAI_API_KEY="a-very-long-production-openai-key-1234567890abcdef",
            CORE_API_SECRET="a-very-long-production-core-secret-1234567890abcdef",
            ENABLE_DOCS_IN_PRODUCTION=True,
            OPENAI_BASE_URL="https://api.openai.com/v1",
            CORE_API_URL="https://api.kolabri.com",
        )

    assert settings.ENABLE_DOCS_IN_PRODUCTION is True
    assert mock_warning.call_count >= 2
