#!/usr/bin/env python3
"""Credential-gated MiniMax listening smoke test.

The script intentionally does nothing without MINIMAX_API_KEY. Generated files
stay local and contain no credentials or response bodies beyond the audio.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from narration import MiniMaxNarrationSynthesizer, NarrationRequest


PRESETS = (
    ("calm", "neutral", 0.92, -1),
    ("documentary", "neutral", 1.0, 0),
    ("story", "happy", 0.96, 1),
)


def main() -> int:
    api_key = os.getenv("MINIMAX_API_KEY", "").strip()
    if not api_key:
        print("SKIP: MINIMAX_API_KEY is not configured")
        return 0
    endpoint = os.getenv(
        "MINIMAX_T2A_ENDPOINT", "https://api.minimaxi.com/v1/t2a_v2"
    )
    voice_id = os.getenv("MINIMAX_VOICE_ID", "Chinese (Mandarin)_Gentleman")
    output = Path(os.getenv("NARRATION_SMOKE_OUTPUT", "/tmp/deeptravel-narration-smoke"))
    output.mkdir(parents=True, exist_ok=True)
    synthesizer = MiniMaxNarrationSynthesizer(
        api_key=api_key,
        endpoint=endpoint,
        model=os.getenv("MINIMAX_T2A_MODEL", "speech-2.8-hd"),
        timeout_seconds=float(os.getenv("MINIMAX_TIMEOUT_SECONDS", "45")),
    )
    transcript = os.getenv(
        "NARRATION_SMOKE_TRANSCRIPT",
        "先别急着拍照。你眼前的街道，首先是居民每天出入的生活空间。",
    )
    for label, emotion, speed, pitch in PRESETS:
        result = synthesizer.synthesize(
            NarrationRequest(transcript, voice_id, emotion, speed, pitch)
        )
        target = output / f"{label}.mp3"
        target.write_bytes(result.payload)
        print(f"OK {label}: {target} ({len(result.payload)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
