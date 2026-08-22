from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import httpx

from .domain import LogEvent
from .normalization import NormalizationLimits, normalize_event

_TIMESTAMP_RE = re.compile(r"^(\S+)\s+(.*)$", re.DOTALL)
_LEVEL_RE = re.compile(r"(?i)(?:^|[\s\[\]])(debug|info|notice|warn(?:ing)?|err(?:or)?|critical|fatal|panic)(?:[\s\]:-]|$)")


class DockerFrameDecoder:
    """Decode Docker's multiplexed raw-stream frames while accepting plain streams."""

    def __init__(self, max_frame_bytes: int = 1_048_576) -> None:
        self.buffer = bytearray()
        self.framed: bool | None = None
        self.max_frame_bytes = max_frame_bytes

    def feed(self, chunk: bytes) -> list[bytes]:
        if not chunk:
            return []
        self.buffer.extend(chunk)
        if self.framed is None and len(self.buffer) >= 8:
            size = int.from_bytes(self.buffer[4:8], "big")
            self.framed = (
                self.buffer[0] in (0, 1, 2, 3)
                and self.buffer[1:4] == b"\x00\x00\x00"
                and 0 <= size <= self.max_frame_bytes
            )
        if self.framed is False:
            data = bytes(self.buffer)
            self.buffer.clear()
            return [data]
        if self.framed is None:
            return []

        payloads: list[bytes] = []
        while len(self.buffer) >= 8:
            if self.buffer[0] not in (0, 1, 2, 3) or self.buffer[1:4] != b"\x00\x00\x00":
                data = bytes(self.buffer)
                self.buffer.clear()
                self.framed = False
                payloads.append(data)
                break
            size = int.from_bytes(self.buffer[4:8], "big")
            if size > self.max_frame_bytes:
                raise ValueError("Docker log frame exceeds configured limit")
            if len(self.buffer) < 8 + size:
                break
            payloads.append(bytes(self.buffer[8 : 8 + size]))
            del self.buffer[: 8 + size]
        return payloads

    def finish(self) -> bytes:
        remaining = bytes(self.buffer)
        self.buffer.clear()
        return remaining


def parse_docker_line(value: str) -> tuple[datetime, str, str]:
    text = value.rstrip("\r")
    occurred_at = datetime.now(UTC)
    match = _TIMESTAMP_RE.match(text)
    if match:
        candidate, remainder = match.groups()
        try:
            occurred_at = datetime.fromisoformat(candidate.replace("Z", "+00:00")).astimezone(UTC)
            text = remainder
        except ValueError:
            pass
    level_match = _LEVEL_RE.search(text)
    level = level_match.group(1) if level_match else "info"
    return occurred_at, level, text


class DockerLogSource:
    def __init__(
        self,
        *,
        socket_path: str,
        sources: dict[str, str],
        api_version: str,
        limits: NormalizationLimits,
    ) -> None:
        self.socket_path = socket_path
        self.sources = sources
        self.api_version = api_version.strip("/")
        self.limits = limits

    @property
    def available(self) -> bool:
        return bool(self.sources) and Path(self.socket_path).exists()

    async def follow(self, alias: str, *, tail: int) -> AsyncIterator[LogEvent]:
        target = self.sources.get(alias)
        if not target:
            raise KeyError(alias)
        transport = httpx.AsyncHTTPTransport(uds=self.socket_path)
        timeout = httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0)
        url = f"http://docker/{self.api_version}/containers/{quote(target, safe='')}/logs"
        params = {
            "stdout": "true",
            "stderr": "true",
            "timestamps": "true",
            "follow": "true",
            "tail": str(tail),
        }
        sequence = 0
        decoder = DockerFrameDecoder()
        line_buffer = ""
        async with httpx.AsyncClient(transport=transport, timeout=timeout) as client:
            async with client.stream("GET", url, params=params) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    for payload in decoder.feed(chunk):
                        line_buffer += payload.decode("utf-8", errors="replace")
                        while "\n" in line_buffer:
                            raw_line, line_buffer = line_buffer.split("\n", 1)
                            if not raw_line:
                                continue
                            sequence += 1
                            occurred_at, level, message = parse_docker_line(raw_line)
                            yield normalize_event(
                                cursor=f"backend:{alias}:{sequence}",
                                occurred_at=occurred_at,
                                source_type="backend",
                                source=alias,
                                level=level,
                                category="container",
                                message=message,
                                limits=self.limits,
                            )
                remainder = decoder.finish().decode("utf-8", errors="replace")
                line_buffer += remainder
                if line_buffer.strip():
                    sequence += 1
                    occurred_at, level, message = parse_docker_line(line_buffer)
                    yield normalize_event(
                        cursor=f"backend:{alias}:{sequence}",
                        occurred_at=occurred_at,
                        source_type="backend",
                        source=alias,
                        level=level,
                        category="container",
                        message=message,
                        limits=self.limits,
                    )
