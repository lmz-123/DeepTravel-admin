from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any


def sse_message(event: str, data: dict[str, Any], *, cursor: str | None = None) -> str:
    lines: list[str] = []
    if cursor:
        lines.append(f"id: {cursor}")
    lines.append(f"event: {event}")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    lines.extend(f"data: {line}" for line in payload.splitlines() or [""])
    return "\n".join(lines) + "\n\n"


class StreamLimiter:
    def __init__(self, maximum: int) -> None:
        self.maximum = max(1, maximum)
        self._active = 0
        self._lock = asyncio.Lock()

    @property
    def active(self) -> int:
        return self._active

    async def acquire(self) -> bool:
        async with self._lock:
            if self._active >= self.maximum:
                return False
            self._active += 1
            return True

    async def release(self) -> None:
        async with self._lock:
            self._active = max(0, self._active - 1)


async def limited_stream(source: AsyncIterator[str], limiter: StreamLimiter) -> AsyncIterator[str]:
    try:
        async for item in source:
            yield item
    finally:
        await limiter.release()
