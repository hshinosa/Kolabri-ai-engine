from __future__ import annotations

from typing import Any

SENSITIVE_KEYS = (
    "password",
    "api_key",
    "apikey",
    "token",
    "secret",
    "authorization",
    "credential",
)


def sanitize_sensitive_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if any(pattern in key.lower() for pattern in SENSITIVE_KEYS)
            else sanitize_sensitive_data(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_sensitive_data(item) for item in value]
    return value


def sanitize_error_message(message: str) -> str:
    sanitized = message
    for marker in ("sk-", "Bearer "):
        if marker in sanitized:
            prefix, _, _ = sanitized.partition(marker)
            return f"{prefix}[REDACTED]"
    return sanitized
