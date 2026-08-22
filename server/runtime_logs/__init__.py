"""Runtime log collection and delivery primitives."""

from .domain import LogEvent
from .normalization import NormalizationLimits, normalize_context, normalize_event, redact_text

__all__ = [
    "LogEvent",
    "NormalizationLimits",
    "normalize_context",
    "normalize_event",
    "redact_text",
]
