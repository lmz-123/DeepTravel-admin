from __future__ import annotations

import json
import unittest

import httpx

from narration import (
    DeterministicNarrationSynthesizer,
    MiniMaxNarrationSynthesizer,
    NarrationRequest,
    NarrationSynthesisError,
)


class NarrationSynthesizerTests(unittest.TestCase):
    def request(self):
        return NarrationRequest(
            transcript="城墙记住了海风。",
            voice_id="mandarin-curated",
            emotion="neutral",
            speed=0.92,
            pitch=-1,
            pronunciation=("南头/(nan2)(tou2)",),
        )

    def test_minimax_payload_maps_every_curated_setting(self):
        captured = {}

        def handler(request: httpx.Request):
            captured.update(json.loads(request.content))
            self.assertEqual(request.headers["Authorization"], "Bearer test-key")
            return httpx.Response(
                200,
                json={"data": {"audio": b"ID3audio".hex()}, "trace_id": "trace-safe", "base_resp": {"status_code": 0}},
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        synthesizer = MiniMaxNarrationSynthesizer(api_key="test-key", endpoint="https://tts.example.test/v1/t2a_v2", client=client)

        result = synthesizer.synthesize(self.request())

        self.assertEqual(result.payload, b"ID3audio")
        self.assertEqual(captured["model"], "speech-2.8-hd")
        self.assertEqual(captured["text"], "城墙记住了海风。")
        self.assertEqual(captured["voice_setting"], {"voice_id": "mandarin-curated", "speed": 0.92, "vol": 1.0, "pitch": -1, "emotion": "neutral"})
        self.assertEqual(captured["pronunciation_dict"], {"tone": ["南头/(nan2)(tou2)"]})
        self.assertEqual(captured["audio_setting"]["format"], "mp3")

    def test_credentials_and_provider_failures_are_sanitized(self):
        with self.assertRaises(NarrationSynthesisError) as missing:
            MiniMaxNarrationSynthesizer(api_key="", endpoint="https://tts.example.test").synthesize(self.request())
        self.assertEqual(missing.exception.code, "credentials_unavailable")

        client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(500, text="secret upstream detail")))
        with self.assertRaises(NarrationSynthesisError) as failed:
            MiniMaxNarrationSynthesizer(api_key="test-key", endpoint="https://tts.example.test", client=client).synthesize(self.request())
        self.assertEqual(failed.exception.code, "provider_error")
        self.assertNotIn("secret upstream detail", str(failed.exception))

        balance_client = httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    json={
                        "base_resp": {
                            "status_code": 1008,
                            "status_msg": "insufficient balance",
                        }
                    },
                )
            )
        )
        with self.assertRaises(NarrationSynthesisError) as balance:
            MiniMaxNarrationSynthesizer(
                api_key="test-key",
                endpoint="https://tts.example.test",
                client=balance_client,
            ).synthesize(self.request())
        self.assertEqual(balance.exception.code, "insufficient_balance")

    def test_fake_is_deterministic_without_paid_credentials(self):
        synthesizer = DeterministicNarrationSynthesizer()
        self.assertEqual(synthesizer.synthesize(self.request()).payload, synthesizer.synthesize(self.request()).payload)


if __name__ == "__main__":
    unittest.main()
