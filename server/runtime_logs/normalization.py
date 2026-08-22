from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .domain import LogEvent, LogLevel, LogSourceType

REDACTED = "[REDACTED]"

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BEARER_RE = re.compile(r"(?i)\b(bearer|basic)\s+[a-z0-9._~+/=-]+")
_DATABASE_URL_RE = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^\s:/@]+:)([^\s@/]+)(@)")
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)([\"']?(?:authorization|password|passwd|pwd|token|access[_-]?token|refresh[_-]?token|"
    r"api[_-]?key|secret|cookie|set-cookie|database[_-]?url)[\"']?\s*[:=]\s*)([\"']?)([^\s,;}&\"']+)([\"']?)"
)
_SECRET_QUERY_RE = re.compile(
    r"(?i)([?&](?:password|passwd|pwd|token|access_token|refresh_token|api_key|secret)=)([^&#\s]+)"
)
_SENSITIVE_KEY_RE = re.compile(
    r"(?i)(authorization|password|passwd|pwd|token|api.?key|secret|cookie|database.?url|connection.?string)"
)

_LEVEL_ALIASES: dict[str, LogLevel] = {
    "trace": "debug",
    "debug": "debug",
    "verbose": "debug",
    "info": "info",
    "notice": "info",
    "warn": "warning",
    "warning": "warning",
    "error": "error",
    "err": "error",
    "fatal": "critical",
    "critical": "critical",
    "panic": "critical",
}


@dataclass(frozen=True, slots=True)
class NormalizationLimits:
    message_chars: int = 8_000
    category_chars: int = 120
    source_chars: int = 120
    context_depth: int = 4
    context_keys: int = 40
    context_string_chars: int = 1_000


def redact_text(value: str) -> str:
    cleaned = _CONTROL_RE.sub("", value)
    cleaned = _BEARER_RE.sub(lambda match: f"{match.group(1)} {REDACTED}", cleaned)
    cleaned = _DATABASE_URL_RE.sub(lambda match: f"{match.group(1)}{REDACTED}{match.group(3)}", cleaned)
    cleaned = _SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}{REDACTED}", cleaned)
    return _SECRET_QUERY_RE.sub(lambda match: f"{match.group(1)}{REDACTED}", cleaned)


def normalize_level(value: str | None) -> LogLevel:
    normalized = (value or "info").strip().lower()
    return _LEVEL_ALIASES.get(normalized, "info")


def _bounded_text(value: Any, limit: int) -> tuple[str, bool]:
    text = redact_text(str(value))
    if len(text) <= limit:
        return text, False
    return f"{text[: max(0, limit - 1)]}…", True


def normalize_context(value: Any, limits: NormalizationLimits, depth: int = 0) -> Any:
    if depth >= limits.context_depth:
        return "[MAX_DEPTH]"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for index, (raw_key, raw_value) in enumerate(value.items()):
            if index >= limits.context_keys:
                result["_truncated"] = True
                break
            key, _ = _bounded_text(raw_key, 120)
            if _SENSITIVE_KEY_RE.search(key):
                result[key] = REDACTED
            else:
                result[key] = normalize_context(raw_value, limits, depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        items = [normalize_context(item, limits, depth + 1) for item in value[: limits.context_keys]]
        if len(value) > limits.context_keys:
            items.append("[TRUNCATED]")
        return items
    if isinstance(value, str):
        return _bounded_text(value, limits.context_string_chars)[0]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _bounded_text(value, limits.context_string_chars)[0]


def normalize_event(
    *,
    cursor: str,
    occurred_at: datetime,
    source_type: LogSourceType,
    source: str,
    level: str | None,
    category: str,
    message: str,
    context: dict[str, Any] | None = None,
    received_at: datetime | None = None,
    limits: NormalizationLimits | None = None,
) -> LogEvent:
    active_limits = limits or NormalizationLimits()
    normalized_source, source_truncated = _bounded_text(source, active_limits.source_chars)
    normalized_category, category_truncated = _bounded_text(category, active_limits.category_chars)
    normalized_message, message_truncated = _bounded_text(message, active_limits.message_chars)
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    received = received_at or datetime.now(UTC)
    if received.tzinfo is None:
        received = received.replace(tzinfo=UTC)
    return LogEvent(
        cursor=cursor,
        occurred_at=occurred_at.astimezone(UTC),
        received_at=received.astimezone(UTC),
        source_type=source_type,
        source=normalized_source,
        level=normalize_level(level),
        category=normalized_category,
        message=normalized_message,
        context=normalize_context(context or {}, active_limits),
        truncated=source_truncated or category_truncated or message_truncated,
    )
