from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

import httpx


class NarrationSynthesisError(RuntimeError):
    def __init__(self, code: str, message: str = "语音服务暂不可用"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class NarrationRequest:
    transcript: str
    voice_id: str
    emotion: str
    speed: float
    pitch: int
    pronunciation: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NarrationResult:
    payload: bytes
    mime_type: str
    provider: str
    model: str
    request_id: str | None = None


class NarrationSynthesizer(Protocol):
    provider: str
    model: str

    def synthesize(self, request: NarrationRequest) -> NarrationResult: ...


class DeterministicNarrationSynthesizer:
    provider = "fake"
    model = "deterministic-v1"

    def synthesize(self, request: NarrationRequest) -> NarrationResult:
        digest = hashlib.sha256(repr(request).encode()).digest()
        return NarrationResult(b"ID3" + digest, "audio/mpeg", self.provider, self.model, digest.hex()[:16])


class MiniMaxNarrationSynthesizer:
    provider = "minimax"

    def __init__(self, *, api_key: str, endpoint: str, model: str = "speech-2.8-hd", timeout_seconds: float = 45.0, client: httpx.Client | None = None):
        self.api_key = api_key
        self.endpoint = endpoint
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.client = client or httpx.Client(timeout=timeout_seconds)

    def synthesize(self, request: NarrationRequest) -> NarrationResult:
        if not self.api_key:
            raise NarrationSynthesisError("credentials_unavailable", "尚未配置 MiniMax 语音凭证")
        payload = {
            "model": self.model,
            "text": request.transcript,
            "stream": False,
            "voice_setting": {
                "voice_id": request.voice_id,
                "speed": request.speed,
                "vol": 1.0,
                "pitch": request.pitch,
                "emotion": request.emotion,
            },
            "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
            "pronunciation_dict": {"tone": list(request.pronunciation)},
        }
        try:
            response = self.client.post(self.endpoint, headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, json=payload)
            response.raise_for_status()
            body = response.json()
            base_resp = body.get("base_resp") or {}
            if base_resp.get("status_code") not in (None, 0):
                raise NarrationSynthesisError("provider_rejected")
            audio_hex = (body.get("data") or {}).get("audio")
            if not isinstance(audio_hex, str) or not audio_hex:
                raise NarrationSynthesisError("invalid_provider_response")
            audio = bytes.fromhex(audio_hex)
            return NarrationResult(audio, "audio/mpeg", self.provider, self.model, body.get("trace_id"))
        except NarrationSynthesisError:
            raise
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise NarrationSynthesisError("provider_unavailable") from exc
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise NarrationSynthesisError("provider_error") from exc
