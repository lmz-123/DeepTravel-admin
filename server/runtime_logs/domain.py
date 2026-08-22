from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

LogLevel = Literal["debug", "info", "warning", "error", "critical"]
LogSourceType = Literal["backend", "client", "system"]


def utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class LogEvent:
    cursor: str
    occurred_at: datetime
    received_at: datetime
    source_type: LogSourceType
    source: str
    level: LogLevel
    category: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "cursor": self.cursor,
            "occurred_at": utc_iso(self.occurred_at),
            "received_at": utc_iso(self.received_at),
            "source_type": self.source_type,
            "source": self.source,
            "level": self.level,
            "category": self.category,
            "message": self.message,
            "context": self.context,
            "truncated": self.truncated,
        }
