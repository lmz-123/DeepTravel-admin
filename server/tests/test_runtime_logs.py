from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{Path(_TEMP_DIR.name) / 'runtime-logs.db'}"
os.environ["ADMIN_TOKEN"] = "admin-test-token"
os.environ["CLIENT_LOG_INGEST_TOKEN"] = "client-test-token"
os.environ["MEDIA_ROOT"] = str(Path(_TEMP_DIR.name) / "media")
os.environ["BACKEND_LOGS_ENABLED"] = "false"
os.environ["LOG_SOURCES"] = "travel-api=deeptravel-api-1"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import main  # noqa: E402
from models import Base, ClientRuntimeLog, Journey, MediaAsset  # noqa: E402
from runtime_logs.docker_source import DockerFrameDecoder, DockerLogSource, parse_docker_line  # noqa: E402
from runtime_logs.normalization import (  # noqa: E402
    NormalizationLimits,
    normalize_context,
    normalize_event,
    redact_text,
)
from runtime_logs.storage import cleanup_client_logs, ensure_client_log_schema, query_client_events  # noqa: E402
from runtime_logs.streaming import StreamLimiter, limited_stream, sse_message  # noqa: E402


class NormalizationTests(unittest.TestCase):
    def test_redacts_credentials_and_bounds_content(self):
        value = (
            "Authorization: Bearer abc.def password=hunter2 "
            "mysql+pymysql://user:secret@mysql/jiandi?token=query-secret"
        )
        redacted = redact_text(value)
        self.assertNotIn("abc.def", redacted)
        self.assertNotIn("hunter2", redacted)
        self.assertNotIn("secret@", redacted)
        self.assertNotIn("query-secret", redacted)
        self.assertGreaterEqual(redacted.count("[REDACTED]"), 4)

        context = normalize_context(
            {"token": "private", "nested": {"password": "also-private", "safe": "visible"}},
            NormalizationLimits(),
        )
        self.assertEqual(context["token"], "[REDACTED]")
        self.assertEqual(context["nested"]["password"], "[REDACTED]")
        self.assertEqual(context["nested"]["safe"], "visible")

        event = normalize_event(
            cursor="1",
            occurred_at=datetime.now(UTC),
            source_type="client",
            source="app",
            level="fatal",
            category="network",
            message="x" * 30,
            limits=NormalizationLimits(message_chars=12),
        )
        self.assertEqual(event.level, "critical")
        self.assertTrue(event.truncated)
        self.assertEqual(len(event.message), 12)


class DockerDecoderTests(unittest.TestCase):
    def test_decodes_split_multiplexed_frames_and_plain_lines(self):
        payload = b"2026-08-22T04:00:00Z ERROR failed\n"
        frame = b"\x02\x00\x00\x00" + len(payload).to_bytes(4, "big") + payload
        decoder = DockerFrameDecoder()
        self.assertEqual(decoder.feed(frame[:6]), [])
        self.assertEqual(decoder.feed(frame[6:]), [payload])

        plain = DockerFrameDecoder()
        self.assertEqual(plain.feed(b"plain log\n"), [b"plain log\n"])
        occurred_at, level, message = parse_docker_line(payload.decode().strip())
        self.assertEqual(occurred_at.year, 2026)
        self.assertEqual(level.lower(), "error")
        self.assertEqual(message, "ERROR failed")

    def test_rejects_unknown_alias_without_contacting_docker(self):
        source = DockerLogSource(
            socket_path="/definitely/missing/docker.sock",
            sources={"travel-api": "travel-api-1"},
            api_version="v1.41",
            limits=NormalizationLimits(),
        )
        self.assertFalse(source.available)

        async def exercise():
            iterator = source.follow("arbitrary-container", tail=10)
            with self.assertRaises(KeyError):
                await anext(iterator)

        asyncio.run(exercise())


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        ensure_client_log_schema(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_query_cursor_order_and_retention(self):
        now = datetime.now(UTC)
        with Session(self.engine) as db:
            for index in range(4):
                db.add(
                    ClientRuntimeLog(
                        occurred_at=now - timedelta(days=20 if index == 0 else 0),
                        received_at=now - timedelta(days=20 if index == 0 else 0),
                        level="error" if index % 2 else "info",
                        category="network",
                        message=f"event-{index}",
                        session_id="session-a",
                        app_version="1.0.0",
                        platform="android",
                        source="deeptravel-flutter",
                        context_json={},
                        truncated=False,
                    )
                )
            db.commit()
            latest = query_client_events(db, limit=2)
            self.assertEqual([event.message for event in latest], ["event-2", "event-3"])
            resumed = query_client_events(db, after_cursor=int(latest[0].cursor), limit=10)
            self.assertEqual([event.message for event in resumed], ["event-3"])
            removed = cleanup_client_logs(db, retention_days=7, max_rows=2, batch_size=10, now=now)
            db.commit()
            self.assertEqual(removed, 2)
            self.assertEqual(len(query_client_events(db, limit=10)), 2)


class StreamingPrimitiveTests(unittest.TestCase):
    def test_sse_and_limiter_are_bounded(self):
        wire = sse_message("log", {"message": "你好"}, cursor="9")
        self.assertIn("id: 9\n", wire)
        self.assertIn("event: log\n", wire)
        self.assertIn('data: {"message":"你好"}', wire)
        self.assertIn("event: heartbeat", sse_message("heartbeat", {"at": "now"}))

        async def exercise():
            limiter = StreamLimiter(1)
            self.assertTrue(await limiter.acquire())
            self.assertFalse(await limiter.acquire())
            await limiter.release()
            self.assertTrue(await limiter.acquire())
            await limiter.release()

        asyncio.run(exercise())

    def test_stream_release_runs_when_consumer_disconnects(self):
        async def exercise():
            limiter = StreamLimiter(1)
            self.assertTrue(await limiter.acquire())

            async def source():
                yield "event: heartbeat\ndata: {}\n\n"
                await asyncio.sleep(60)

            stream = limited_stream(source(), limiter)
            self.assertIn("heartbeat", await anext(stream))
            await stream.aclose()
            self.assertEqual(limiter.active, 0)

        asyncio.run(exercise())


class FragmentedContentApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(main.engine)
        cls.client_context = TestClient(main.app)
        cls.client = cls.client_context.__enter__()
        media = Path(_TEMP_DIR.name) / "media"
        (media / "images").mkdir(parents=True, exist_ok=True)
        (media / "audio").mkdir(parents=True, exist_ok=True)
        (media / "images" / "route.png").write_bytes(b"png")
        (media / "audio" / "one.m4a").write_bytes(b"audio-one")
        (media / "audio" / "two.m4a").write_bytes(b"audio-two")

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)

    def setUp(self):
        Base.metadata.drop_all(main.engine)
        Base.metadata.create_all(main.engine)

    @property
    def headers(self):
        return {"Authorization": "Bearer admin-test-token"}

    def payload(self):
        version = "test-v1"
        return {
            "package_id": "route-package-test",
            "package_version": version,
            "media": [
                {"key": "cover", "storage_path": "images/route.png", "mime_type": "image/png"},
                {"key": "audio-one", "storage_path": "audio/one.m4a", "mime_type": "audio/mp4"},
                {"key": "audio-two", "storage_path": "audio/two.m4a", "mime_type": "audio/mp4"},
            ],
            "city": {"id": "city-test", "slug": "test-city", "name": "测试城", "subtitle": "测试", "hero_image": "images/route.png", "latitude": 22.5, "longitude": 114.0},
            "route": {"id": "route-test", "slug": "route-test", "title": "测试路线", "subtitle": "测试副标题", "description": "测试说明", "duration_minutes": 30, "distance_km": 1.0, "difficulty": "轻松", "theme": "测试", "hero_image": "images/route.png", "is_featured": False},
            "story_arc": {"id": "arc-test", "title": "完整故事", "central_question": "发生了什么？", "complete_story": "第一件事带来了第二件事。", "causal_model": [{"id": "cause-one", "text": "第一件事发生"}, {"id": "cause-two", "text": "第二件事发生"}], "pronunciation_notes": [], "script_version": version, "review_state": "reviewed", "field_audit_state": "reviewed", "reviewed_by": "tester", "reviewed_at": "2026-08-22T00:00:00Z", "source_version": "source-v1", "publication_decision": None},
            "sources": [{"id": "source-test", "title": "官方资料", "publisher": "测试机构", "url": "https://example.com/source", "source_type": "government", "accessed_at": "2026-08-22T00:00:00Z", "review_state": "reviewed", "summary": "支持测试主张"}],
            "claims": [
                {"id": "claim-one", "canonical_text": "第一件事存在", "claim_kind": "fact", "certainty": "documented", "review_state": "reviewed", "boundary_note": "", "supersedes_claim_id": None, "reviewed_by": "tester", "reviewed_at": "2026-08-22T00:00:00Z", "source_ids": ["source-test"], "support_notes": {"source-test": "直接支持"}},
                {"id": "claim-two", "canonical_text": "第二件事存在", "claim_kind": "fact", "certainty": "documented", "review_state": "reviewed", "boundary_note": "", "supersedes_claim_id": None, "reviewed_by": "tester", "reviewed_at": "2026-08-22T00:00:00Z", "source_ids": ["source-test"], "support_notes": {"source-test": "直接支持"}},
            ],
            "required_photo_mission_count": 1,
            "fragments": [
                self.fragment("fragment-one", 1, "audio/one.m4a", "claim-one", 22.5000, 114.0000, [], True),
                self.fragment("fragment-two", 2, "audio/two.m4a", "claim-two", 22.5030, 114.0030, ["fragment-one"], False),
            ],
        }

    def fragment(self, identity, position, audio, claim, latitude, longitude, dependencies, mission):
        script = f"第 {position} 段经过审核的旁白。"
        value = {"id": identity, "position": position, "title": f"线索 {position}", "safe_preview": "请继续前行", "narration_script": script, "transcript": script, "audio_path": audio, "audio_mime_type": "audio/mp4", "audio_size_bytes": 9, "script_version": "test-v1", "interaction_type": "photo" if mission else "passive", "completion_threshold": 0.9, "key_claim": "经过来源支持的主张", "answers_question": "回答前一问", "raises_question": "提出下一问", "authenticity_label": "documented", "review_state": "reviewed", "dependency_ids": dependencies, "claim_ids": [claim], "trigger_region": {"id": f"trigger-{position}", "latitude": latitude, "longitude": longitude, "entry_radius_m": 50, "exit_radius_m": 85, "max_accuracy_m": 35, "qualifying_samples": 2, "sample_window_seconds": 15, "cooldown_seconds": 120, "audit_state": "reviewed", "coordinate_system": "WGS84", "source_coordinate_system": "WGS84", "coordinate_source": "现场 GPS 复核", "field_notes": "公共步行区域"}}
        if mission:
            value["photo_mission"] = {"id": "mission-one", "prompt": "拍摄现场标志", "field_subject": "公共标志", "safety_copy": "请勿进入车道", "accessibility_alternative": "可拍摄邻近导览牌", "authenticity_label": "documented", "required": True, "audit_state": "reviewed"}
        return value

    def test_import_validate_publish_idempotency_and_version_lock(self):
        unauthorized = self.client.post("/api/admin/fragmented-routes/import", json=self.payload())
        self.assertEqual(unauthorized.status_code, 401)

        now = datetime.now(UTC)
        with main.SessionLocal() as db:
            db.add(MediaAsset(key="legacy-cover", storage_path="images/route.png", mime_type="image/png", created_at=now, updated_at=now))
            db.commit()

        imported = self.client.post("/api/admin/fragmented-routes/import", headers=self.headers, json=self.payload())
        self.assertEqual(imported.status_code, 201, imported.text)
        self.assertTrue(imported.json()["validation"]["valid"], imported.text)
        self.assertIsNone(imported.json()["route"]["published_at"])

        imported_graph = self.client.get(
            "/api/admin/routes/route-test/content", headers=self.headers
        ).json()
        imported_graph["story_arc"]["central_question"] = "后台表单修改后的问题？"
        saved = self.client.put(
            "/api/admin/routes/route-test/content",
            headers=self.headers,
            json=imported_graph,
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertTrue(saved.json()["validation"]["valid"], saved.text)
        self.assertEqual(
            saved.json()["content"]["story_arc"]["central_question"],
            "后台表单修改后的问题？",
        )
        self.assertEqual(
            [item["id"] for item in saved.json()["content"]["fragments"]],
            ["fragment-one", "fragment-two"],
        )
        protected_media = self.client.delete(
            "/api/admin/media/audio-one", headers=self.headers
        )
        self.assertEqual(protected_media.status_code, 409, protected_media.text)

        repeated = self.client.post("/api/admin/fragmented-routes/import", headers=self.headers, json=self.payload())
        self.assertEqual(repeated.status_code, 201, repeated.text)
        self.assertTrue(repeated.json()["idempotent"])

        published = self.client.post("/api/admin/routes/route-test/publish", headers=self.headers)
        self.assertEqual(published.status_code, 200, published.text)
        self.assertTrue(published.json()["validation"]["valid"])

        with main.SessionLocal() as db:
            db.add(Journey(id="journey-test", route_id="route-test", status="active"))
            db.commit()
        graph = self.client.get("/api/admin/routes/route-test/content", headers=self.headers).json()
        graph["story_arc"]["complete_story"] = "试图覆盖已使用版本"
        locked = self.client.put("/api/admin/routes/route-test/content", headers=self.headers, json=graph)
        self.assertEqual(locked.status_code, 409, locked.text)

    def test_publish_rejects_missing_media(self):
        payload = self.payload()
        payload["package_id"] = "invalid-package"
        payload["package_version"] = "invalid-v1"
        payload["route"]["id"] = "invalid-route"
        payload["route"]["slug"] = "invalid-route"
        payload["fragments"][0]["audio_path"] = "audio/not-registered.m4a"
        imported = self.client.post("/api/admin/fragmented-routes/import", headers=self.headers, json=payload)
        self.assertEqual(imported.status_code, 201, imported.text)
        self.assertFalse(imported.json()["validation"]["valid"])
        published = self.client.post("/api/admin/routes/invalid-route/publish", headers=self.headers)
        self.assertEqual(published.status_code, 422, published.text)


class RuntimeLogApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_context = TestClient(main.app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)
        main.engine.dispose()
        _TEMP_DIR.cleanup()

    def setUp(self):
        with main.SessionLocal() as db:
            db.query(ClientRuntimeLog).delete()
            db.commit()

    def _batch(self, message: str = "request failed token=top-secret"):
        return {
            "events": [
                {
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "level": "error",
                    "category": "network",
                    "message": message,
                    "session_id": "session-1",
                    "app_version": "1.0.0+1",
                    "platform": "android",
                    "source": "deeptravel-flutter",
                    "context": {"endpoint": "/cities", "authorization": "Bearer private"},
                }
            ]
        }

    def test_ingestion_history_redaction_and_cursor_resume(self):
        response = self.client.post(
            "/api/runtime/client-logs",
            headers={"X-Client-Log-Token": "client-test-token"},
            json=self._batch(),
        )
        self.assertEqual(response.status_code, 202, response.text)
        first_cursor = response.json()["first_cursor"]

        second = self.client.post(
            "/api/runtime/client-logs",
            headers={"X-Client-Log-Token": "client-test-token"},
            json=self._batch("audio service warning"),
        )
        self.assertEqual(second.status_code, 202)

        history = self.client.get(
            "/api/admin/logs/client/history",
            headers={"Authorization": "Bearer admin-test-token"},
        )
        self.assertEqual(history.status_code, 200)
        events = history.json()["events"]
        self.assertEqual(len(events), 2)
        self.assertNotIn("top-secret", events[0]["message"])
        self.assertEqual(events[0]["context"]["authorization"], "[REDACTED]")

        resumed = self.client.get(
            f"/api/admin/logs/client/history?after={first_cursor}",
            headers={"Authorization": "Bearer admin-test-token"},
        )
        self.assertEqual([event["message"] for event in resumed.json()["events"]], ["audio service warning"])

    def test_auth_validation_size_and_unknown_source(self):
        invalid = self.client.post(
            "/api/runtime/client-logs",
            headers={"X-Client-Log-Token": "wrong"},
            json=self._batch(),
        )
        self.assertEqual(invalid.status_code, 401)

        malformed = self.client.post(
            "/api/runtime/client-logs",
            headers={"X-Client-Log-Token": "client-test-token"},
            json={"events": [{"message": "missing required fields"}]},
        )
        self.assertEqual(malformed.status_code, 422)

        oversized = self.client.post(
            "/api/runtime/client-logs",
            headers={"X-Client-Log-Token": "client-test-token", "Content-Length": "999999"},
            content=b"{}",
        )
        self.assertEqual(oversized.status_code, 413)

        unauthorized = self.client.get("/api/admin/logs/sources")
        self.assertEqual(unauthorized.status_code, 401)
        unknown = self.client.get(
            "/api/admin/logs/backend/stream?source=arbitrary-container",
            headers={"Authorization": "Bearer admin-test-token"},
        )
        self.assertEqual(unknown.status_code, 404)

        sources = self.client.get(
            "/api/admin/logs/sources",
            headers={"Authorization": "Bearer admin-test-token"},
        )
        self.assertEqual(sources.status_code, 200)
        self.assertEqual(sources.json()["backend"][0]["id"], "travel-api")
        self.assertNotIn("deeptravel-api-1", sources.text)


if __name__ == "__main__":
    unittest.main()
