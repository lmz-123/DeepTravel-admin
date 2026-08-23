from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = (
    f"sqlite+pysqlite:///{Path(_TEMP_DIR.name) / 'runtime-logs.db'}"
)
os.environ["ADMIN_TOKEN"] = "admin-test-token"
os.environ["CLIENT_LOG_INGEST_TOKEN"] = "client-test-token"
os.environ["MEDIA_ROOT"] = str(Path(_TEMP_DIR.name) / "media")
os.environ["BACKEND_LOGS_ENABLED"] = "false"
os.environ["LOG_SOURCES"] = "travel-api=deeptravel-api-1"
os.environ["NARRATION_PROVIDER"] = "fake"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, inspect, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import main  # noqa: E402
from content_schema import ensure_photo_mission_guidance_schema  # noqa: E402
from models import (  # noqa: E402
    Base,
    ClientRuntimeLog,
    FragmentNarrationTrack,
    Journey,
    MediaAsset,
    NarrationVoiceProfile,
    StoryFragment,
)
from runtime_logs.docker_source import (  # noqa: E402
    DockerFrameDecoder,
    DockerLogSource,
    parse_docker_line,
)
from runtime_logs.normalization import (  # noqa: E402
    NormalizationLimits,
    normalize_context,
    normalize_event,
    redact_text,
)
from runtime_logs.storage import (  # noqa: E402
    cleanup_client_logs,
    ensure_client_log_schema,
    query_client_events,
)
from runtime_logs.streaming import StreamLimiter, limited_stream, sse_message  # noqa: E402
from narration import NarrationSynthesisError  # noqa: E402


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
            {
                "token": "private",
                "nested": {"password": "also-private", "safe": "visible"},
            },
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
            self.assertEqual(
                [event.message for event in latest], ["event-2", "event-3"]
            )
            resumed = query_client_events(
                db, after_cursor=int(latest[0].cursor), limit=10
            )
            self.assertEqual([event.message for event in resumed], ["event-3"])
            removed = cleanup_client_logs(
                db, retention_days=7, max_rows=2, batch_size=10, now=now
            )
            db.commit()
            self.assertEqual(removed, 2)
            self.assertEqual(len(query_client_events(db, limit=10)), 2)


class ContentSchemaTests(unittest.TestCase):
    def test_guidance_columns_are_added_to_legacy_table_idempotently(self):
        database = create_engine("sqlite+pysqlite:///:memory:")
        with database.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE photo_missions ("
                    "id VARCHAR(36) PRIMARY KEY, fragment_id VARCHAR(36), prompt TEXT)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO photo_missions (id, fragment_id, prompt) "
                    "VALUES ('legacy', 'fragment', '旧照片任务')"
                )
            )

        ensure_photo_mission_guidance_schema(database)
        ensure_photo_mission_guidance_schema(database)

        columns = {
            column["name"] for column in inspect(database).get_columns("photo_missions")
        }
        self.assertTrue(
            {"vantage_point", "shooting_direction", "composition_tip"}.issubset(columns)
        )
        with database.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT prompt, vantage_point, shooting_direction, composition_tip "
                    "FROM photo_missions WHERE id = 'legacy'"
                )
            ).one()
        self.assertEqual(row.prompt, "旧照片任务")
        self.assertEqual(tuple(row)[1:], (None, None, None))


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
                {
                    "key": "cover",
                    "storage_path": "images/route.png",
                    "mime_type": "image/png",
                },
                {
                    "key": "audio-one",
                    "storage_path": "audio/one.m4a",
                    "mime_type": "audio/mp4",
                },
                {
                    "key": "audio-two",
                    "storage_path": "audio/two.m4a",
                    "mime_type": "audio/mp4",
                },
            ],
            "city": {
                "id": "city-test",
                "slug": "test-city",
                "name": "测试城",
                "subtitle": "测试",
                "hero_image": "images/route.png",
                "latitude": 22.5,
                "longitude": 114.0,
            },
            "route": {
                "id": "route-test",
                "slug": "route-test",
                "title": "测试路线",
                "subtitle": "测试副标题",
                "description": "测试说明",
                "duration_minutes": 30,
                "distance_km": 1.0,
                "difficulty": "轻松",
                "theme": "测试",
                "hero_image": "images/route.png",
                "is_featured": False,
            },
            "story_arc": {
                "id": "arc-test",
                "title": "完整故事",
                "central_question": "发生了什么？",
                "complete_story": "第一件事带来了第二件事。",
                "causal_model": [
                    {"id": "cause-one", "text": "第一件事发生"},
                    {"id": "cause-two", "text": "第二件事发生"},
                ],
                "pronunciation_notes": [],
                "script_version": version,
                "review_state": "reviewed",
                "field_audit_state": "reviewed",
                "reviewed_by": "tester",
                "reviewed_at": "2026-08-22T00:00:00Z",
                "source_version": "source-v1",
                "publication_decision": None,
            },
            "sources": [
                {
                    "id": "source-test",
                    "title": "官方资料",
                    "publisher": "测试机构",
                    "url": "https://example.com/source",
                    "source_type": "government",
                    "accessed_at": "2026-08-22T00:00:00Z",
                    "review_state": "reviewed",
                    "summary": "支持测试主张",
                }
            ],
            "claims": [
                {
                    "id": "claim-one",
                    "canonical_text": "第一件事存在",
                    "claim_kind": "fact",
                    "certainty": "documented",
                    "review_state": "reviewed",
                    "boundary_note": "",
                    "supersedes_claim_id": None,
                    "reviewed_by": "tester",
                    "reviewed_at": "2026-08-22T00:00:00Z",
                    "source_ids": ["source-test"],
                    "support_notes": {"source-test": "直接支持"},
                },
                {
                    "id": "claim-two",
                    "canonical_text": "第二件事存在",
                    "claim_kind": "fact",
                    "certainty": "documented",
                    "review_state": "reviewed",
                    "boundary_note": "",
                    "supersedes_claim_id": None,
                    "reviewed_by": "tester",
                    "reviewed_at": "2026-08-22T00:00:00Z",
                    "source_ids": ["source-test"],
                    "support_notes": {"source-test": "直接支持"},
                },
            ],
            "required_photo_mission_count": 0,
            "fragments": [
                self.fragment(
                    "fragment-one",
                    1,
                    "audio/one.m4a",
                    "claim-one",
                    22.5000,
                    114.0000,
                    [],
                    True,
                ),
                self.fragment(
                    "fragment-two",
                    2,
                    "audio/two.m4a",
                    "claim-two",
                    22.5030,
                    114.0030,
                    ["fragment-one"],
                    False,
                ),
            ],
        }

    def fragment(
        self,
        identity,
        position,
        audio,
        claim,
        latitude,
        longitude,
        dependencies,
        mission,
    ):
        script = f"第 {position} 段经过审核的旁白。"
        value = {
            "id": identity,
            "position": position,
            "title": f"线索 {position}",
            "safe_preview": "请继续前行",
            "experience_tags": [" 安静 ", "安静", f"未来标签 {position}"],
            "narration_script": script,
            "transcript": script,
            "audio_path": audio,
            "audio_mime_type": "audio/mp4",
            "audio_size_bytes": 9,
            "script_version": "test-v1",
            "interaction_type": "photo" if mission else "passive",
            "completion_threshold": 0.9,
            "key_claim": "经过来源支持的主张",
            "answers_question": "回答前一问",
            "raises_question": "提出下一问",
            "authenticity_label": "documented",
            "review_state": "reviewed",
            "dependency_ids": dependencies,
            "claim_ids": [claim],
            "trigger_region": {
                "id": f"trigger-{position}",
                "latitude": latitude,
                "longitude": longitude,
                "entry_radius_m": 50,
                "exit_radius_m": 85,
                "max_accuracy_m": 35,
                "qualifying_samples": 2,
                "sample_window_seconds": 15,
                "cooldown_seconds": 120,
                "audit_state": "reviewed",
                "coordinate_system": "WGS84",
                "source_coordinate_system": "WGS84",
                "coordinate_source": "现场 GPS 复核",
                "field_notes": "公共步行区域",
            },
        }
        if mission:
            value["photo_mission"] = {
                "id": "mission-one",
                "prompt": "拍摄现场标志",
                "field_subject": "公共标志",
                "vantage_point": "站在公共步道内侧的导览牌旁",
                "shooting_direction": "朝向现场标志正面",
                "composition_tip": "保留标志与周边环境，主体置于画面中央",
                "safety_copy": "请勿进入车道",
                "accessibility_alternative": "可拍摄邻近导览牌",
                "authenticity_label": "documented",
                "required": False,
                "audit_state": "reviewed",
            }
        return value

    def test_import_validate_publish_idempotency_and_version_lock(self):
        unauthorized = self.client.post(
            "/api/admin/fragmented-routes/import", json=self.payload()
        )
        self.assertEqual(unauthorized.status_code, 401)

        now = datetime.now(UTC)
        with main.SessionLocal() as db:
            db.add(
                MediaAsset(
                    key="legacy-cover",
                    storage_path="images/route.png",
                    mime_type="image/png",
                    created_at=now,
                    updated_at=now,
                )
            )
            db.commit()

        imported = self.client.post(
            "/api/admin/fragmented-routes/import",
            headers=self.headers,
            json=self.payload(),
        )
        self.assertEqual(imported.status_code, 201, imported.text)
        self.assertTrue(imported.json()["validation"]["valid"], imported.text)
        self.assertIsNone(imported.json()["route"]["published_at"])

        imported_graph = self.client.get(
            "/api/admin/routes/route-test/content", headers=self.headers
        ).json()
        self.assertEqual(
            imported_graph["fragments"][0]["experience_tags"],
            ["安静", "未来标签 1"],
        )
        now = datetime.now(UTC)
        script = imported_graph["fragments"][0]["narration_script"]
        with main.SessionLocal() as db:
            db.add(
                NarrationVoiceProfile(
                    id="save-test-profile",
                    slug="save-test-profile",
                    display_name="保存测试音色",
                    description="",
                    provider="fake",
                    model="fake",
                    voice_id="fake",
                    emotion="neutral",
                    speed=1.0,
                    pitch=0,
                    status="published",
                    is_default=False,
                    created_at=now,
                    updated_at=now,
                    published_at=now,
                )
            )
            db.add(
                FragmentNarrationTrack(
                    id="save-test-track",
                    fragment_id="fragment-one",
                    profile_id="save-test-profile",
                    transcript_hash=hashlib.sha256(script.strip().encode()).hexdigest(),
                    script_version="test-v1",
                    media_path="audio/one.m4a",
                    mime_type="audio/mp4",
                    size_bytes=9,
                    checksum_sha256=None,
                    generation_metadata_json={"test": True},
                    approved_at=now,
                    published_at=now,
                )
            )
            db.commit()
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
        self.assertEqual(
            saved.json()["content"]["fragments"][0]["experience_tags"],
            ["安静", "未来标签 1"],
        )
        saved_mission = saved.json()["content"]["fragments"][0]["photo_mission"]
        self.assertEqual(saved_mission["vantage_point"], "站在公共步道内侧的导览牌旁")
        self.assertEqual(saved_mission["shooting_direction"], "朝向现场标志正面")
        self.assertEqual(
            saved_mission["composition_tip"],
            "保留标志与周边环境，主体置于画面中央",
        )
        with main.SessionLocal() as db:
            saved_track = db.get(FragmentNarrationTrack, "save-test-track")
            self.assertIsNotNone(saved_track)
            self.assertEqual(saved_track.media_path, "audio/one.m4a")
        protected_media = self.client.delete(
            "/api/admin/media/audio-one", headers=self.headers
        )
        self.assertEqual(protected_media.status_code, 409, protected_media.text)

        repeated = self.client.post(
            "/api/admin/fragmented-routes/import",
            headers=self.headers,
            json=self.payload(),
        )
        self.assertEqual(repeated.status_code, 201, repeated.text)
        self.assertTrue(repeated.json()["idempotent"])

        submitted = self.client.post(
            "/api/admin/routes/route-test/submit-review", headers=self.headers
        )
        self.assertEqual(submitted.status_code, 200, submitted.text)
        self.assertEqual(submitted.json()["route"]["content_status"], "in_review")
        verified = self.client.post(
            "/api/admin/routes/route-test/verify", headers=self.headers
        )
        self.assertEqual(verified.status_code, 200, verified.text)
        self.assertEqual(verified.json()["route"]["content_status"], "verified")
        self.assertFalse(verified.json()["route"]["is_public_visible"])
        published = self.client.post(
            "/api/admin/routes/route-test/publish", headers=self.headers
        )
        self.assertEqual(published.status_code, 200, published.text)
        self.assertTrue(published.json()["validation"]["valid"])
        self.assertTrue(published.json()["route"]["is_public_visible"])
        invalid_repeat = self.client.post(
            "/api/admin/routes/route-test/publish", headers=self.headers
        )
        self.assertEqual(invalid_repeat.status_code, 409)

        with main.SessionLocal() as db:
            db.add(Journey(id="journey-test", route_id="route-test", status="active"))
            db.commit()
        graph = self.client.get(
            "/api/admin/routes/route-test/content", headers=self.headers
        ).json()
        graph["fragments"][0]["experience_tags"] = ["试图绕过发布锁"]
        locked = self.client.put(
            "/api/admin/routes/route-test/content", headers=self.headers, json=graph
        )
        self.assertEqual(locked.status_code, 409, locked.text)

    def test_legacy_stop_tags_normalize_and_invalid_update_does_not_mutate(self):
        city = self.client.post(
            "/api/admin/cities",
            headers=self.headers,
            json={
                "slug": "tag-city",
                "name": "标签城",
                "subtitle": "测试",
                "hero_image": "images/route.png",
                "latitude": 22.5,
                "longitude": 114.0,
            },
        )
        self.assertEqual(city.status_code, 201, city.text)
        route = self.client.post(
            "/api/admin/routes",
            headers=self.headers,
            json={
                "city_id": city.json()["id"],
                "slug": "tag-route",
                "title": "标签路线",
                "subtitle": "测试",
                "description": "测试",
                "duration_minutes": 30,
                "distance_km": 1,
                "difficulty": "轻松",
                "theme": "历史",
                "hero_image": "images/route.png",
                "is_featured": False,
            },
        )
        self.assertEqual(route.status_code, 201, route.text)
        payload = {
            "route_id": route.json()["id"],
            "position": 1,
            "title": "老城门",
            "kicker": "抬头看",
            "address": "旧城",
            "latitude": 22.5,
            "longitude": 114.0,
            "arrival_radius_m": 80,
            "story_title": "城门故事",
            "story_body": "故事",
            "audio_url": None,
            "image": "images/route.png",
            "insight": "观察",
            "experience_tags": [" 老建筑 ", "老建筑", "未来新标签"],
        }
        created = self.client.post(
            "/api/admin/stops", headers=self.headers, json=payload
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["experience_tags"], ["老建筑", "未来新标签"])

        invalid = dict(payload)
        invalid["experience_tags"] = [f"标签-{index}" for index in range(9)]
        rejected = self.client.put(
            f"/api/admin/stops/{created.json()['id']}",
            headers=self.headers,
            json=invalid,
        )
        self.assertEqual(rejected.status_code, 422, rejected.text)
        rows = self.client.get(
            f"/api/admin/stops?route_id={route.json()['id']}",
            headers=self.headers,
        ).json()
        self.assertEqual(rows[0]["experience_tags"], ["老建筑", "未来新标签"])

    def test_publish_rejects_missing_media(self):
        payload = self.payload()
        payload["package_id"] = "invalid-package"
        payload["package_version"] = "invalid-v1"
        payload["route"]["id"] = "invalid-route"
        payload["route"]["slug"] = "invalid-route"
        payload["fragments"][0]["audio_path"] = "audio/not-registered.m4a"
        imported = self.client.post(
            "/api/admin/fragmented-routes/import", headers=self.headers, json=payload
        )
        self.assertEqual(imported.status_code, 201, imported.text)
        self.assertFalse(imported.json()["validation"]["valid"])
        submitted = self.client.post(
            "/api/admin/routes/invalid-route/submit-review", headers=self.headers
        )
        self.assertEqual(submitted.status_code, 200, submitted.text)
        verified = self.client.post(
            "/api/admin/routes/invalid-route/verify", headers=self.headers
        )
        self.assertEqual(verified.status_code, 422, verified.text)

    def test_validation_rejects_missing_photo_guidance_with_field_paths(self):
        payload = self.payload()
        payload["package_id"] = "missing-guidance-package"
        payload["package_version"] = "missing-guidance-v1"
        payload["route"]["id"] = "missing-guidance-route"
        payload["route"]["slug"] = "missing-guidance-route"
        payload["story_arc"]["id"] = "missing-guidance-arc"
        mission = payload["fragments"][0]["photo_mission"]
        for key in ("vantage_point", "shooting_direction", "composition_tip"):
            mission.pop(key)

        imported = self.client.post(
            "/api/admin/fragmented-routes/import",
            headers=self.headers,
            json=payload,
        )

        self.assertEqual(imported.status_code, 201, imported.text)
        validation = imported.json()["validation"]
        self.assertFalse(validation["valid"])
        self.assertEqual(
            {
                issue["path"]
                for issue in validation["errors"]
                if issue["code"] == "photo_guidance_required"
            },
            {
                "fragments[0].photo_mission.vantage_point",
                "fragments[0].photo_mission.shooting_direction",
                "fragments[0].photo_mission.composition_tip",
            },
        )

    def test_import_rewrites_legacy_package_paths_to_registered_cloud_objects(self):
        payload = self.payload()
        payload["package_id"] = "cloud-alias-package"
        payload["route"]["id"] = "cloud-alias-route"
        payload["route"]["slug"] = "cloud-alias-route"
        payload["story_arc"]["id"] = "cloud-alias-arc"
        now = datetime.now(UTC)
        mappings = {
            "cover": ("public/content/cloud-cover.png", b"png", "image/png"),
            "audio-one": (
                "public/content/cloud-one.m4a",
                b"audio-one",
                "audio/mp4",
            ),
            "audio-two": (
                "public/content/cloud-two.m4a",
                b"audio-two",
                "audio/mp4",
            ),
        }
        with main.SessionLocal() as db:
            for key, (object_key, content, mime_type) in mappings.items():
                target = Path(_TEMP_DIR.name) / "media" / object_key
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                db.add(
                    MediaAsset(
                        key=key,
                        storage_path=object_key,
                        mime_type=mime_type,
                        storage_provider="oss",
                        object_key=object_key,
                        canonical_url=f"https://cdn.example.test/{object_key}",
                        visibility="public",
                        size_bytes=len(content),
                        checksum_sha256=hashlib.sha256(content).hexdigest(),
                        metadata_json={},
                        created_at=now,
                        updated_at=now,
                    )
                )
            db.commit()

        imported = self.client.post(
            "/api/admin/fragmented-routes/import",
            headers=self.headers,
            json=payload,
        )
        self.assertEqual(imported.status_code, 201, imported.text)
        self.assertTrue(imported.json()["validation"]["valid"], imported.text)
        graph = self.client.get(
            "/api/admin/routes/cloud-alias-route/content", headers=self.headers
        ).json()
        self.assertEqual(
            graph["route"]["hero_image"],
            "https://cdn.example.test/public/content/cloud-cover.png",
        )
        self.assertEqual(
            graph["fragments"][0]["audio_path"],
            "https://cdn.example.test/public/content/cloud-one.m4a",
        )

    def test_three_narration_previews_do_not_bind_until_approval(self):
        imported = self.client.post(
            "/api/admin/fragmented-routes/import",
            headers=self.headers,
            json=self.payload(),
        )
        self.assertEqual(imported.status_code, 201, imported.text)
        before = self.client.get(
            "/api/admin/routes/route-test/content", headers=self.headers
        ).json()
        old_audio = before["fragments"][0]["audio_path"]

        config = self.client.get("/api/admin/narration/config", headers=self.headers)
        self.assertEqual(config.status_code, 200, config.text)
        self.assertEqual(
            config.json()["default_voice_id"], main.settings.minimax_voice_id
        )
        self.assertTrue(config.json()["credentials_configured"])
        self.assertEqual(len(config.json()["presets"]), 3)

        generated = self.client.post(
            "/api/admin/fragments/fragment-one/narration/previews",
            headers=self.headers,
            json={
                "variants": [
                    {
                        "label": "A",
                        "voice_id": "voice-field-test",
                        "emotion": "neutral",
                        "speed": 0.91,
                        "pitch": -2,
                    },
                    {
                        "label": "B",
                        "voice_id": "voice-field-test",
                        "emotion": "happy",
                        "speed": 1.01,
                        "pitch": 0,
                    },
                    {
                        "label": "C",
                        "voice_id": "voice-field-test",
                        "emotion": "surprised",
                        "speed": 0.96,
                        "pitch": 2,
                    },
                ]
            },
        )
        self.assertEqual(generated.status_code, 201, generated.text)
        previews = generated.json()["previews"]
        self.assertEqual(len(previews), 3)
        self.assertTrue(all(item["status"] == "ready" for item in previews))
        self.assertTrue(
            all(item["voice_id"] == "voice-field-test" for item in previews)
        )
        self.assertEqual(
            [item["emotion"] for item in previews], ["neutral", "happy", "surprised"]
        )
        self.assertEqual([item["pitch"] for item in previews], [-2, 0, 2])
        unchanged = self.client.get(
            "/api/admin/routes/route-test/content", headers=self.headers
        ).json()
        self.assertEqual(unchanged["fragments"][0]["audio_path"], old_audio)

        audio = self.client.get(
            f"/api/admin{previews[0]['playback_path']}", headers=self.headers
        )
        self.assertEqual(audio.status_code, 200)
        approved = self.client.post(
            f"/api/admin/narration/previews/{previews[0]['id']}/approve",
            headers=self.headers,
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        changed = self.client.get(
            "/api/admin/routes/route-test/content", headers=self.headers
        ).json()
        self.assertTrue(
            changed["fragments"][0]["audio_path"].startswith(
                "public/narration/fragment-one/"
            )
        )

    def test_stale_narration_preview_cannot_replace_current_script(self):
        imported = self.client.post(
            "/api/admin/fragmented-routes/import",
            headers=self.headers,
            json=self.payload(),
        )
        self.assertEqual(imported.status_code, 201, imported.text)
        generated = self.client.post(
            "/api/admin/fragments/fragment-one/narration/previews",
            headers=self.headers,
            json={},
        ).json()["previews"]
        with main.SessionLocal() as db:
            fragment = db.get(StoryFragment, "fragment-one")
            fragment.narration_script = "编辑已经修改了这段文字稿。"
            fragment.transcript = fragment.narration_script
            db.commit()

        rejected = self.client.post(
            f"/api/admin/narration/previews/{generated[0]['id']}/approve",
            headers=self.headers,
        )
        self.assertEqual(rejected.status_code, 409, rejected.text)

    def test_voice_profile_requires_complete_coverage_and_never_overwrites_default(
        self,
    ):
        imported = self.client.post(
            "/api/admin/fragmented-routes/import",
            headers=self.headers,
            json=self.payload(),
        )
        self.assertEqual(imported.status_code, 201, imported.text)
        original_audio = (
            imported.json()["graph"]["fragments"][0]["audio_path"]
            if "graph" in imported.json()
            else "audio/one.m4a"
        )

        created = self.client.post(
            "/api/admin/narration/profiles",
            headers=self.headers,
            json={
                "slug": "warm-storyteller",
                "display_name": "温柔讲述者",
                "description": "温暖、克制",
                "voice_id": "voice-warm",
                "display_order": 12,
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        profile = created.json()
        self.assertEqual(profile["status"], "draft")

        coverage = self.client.get(
            f"/api/admin/routes/route-test/narration/coverage?profile_id={profile['id']}",
            headers=self.headers,
        ).json()
        self.assertFalse(coverage["ready"])
        self.assertEqual(
            [item["id"] for item in coverage["missing"]],
            ["fragment-one", "fragment-two"],
        )
        rejected = self.client.post(
            f"/api/admin/narration/profiles/{profile['id']}/publish",
            headers=self.headers,
            json={"route_id": "route-test"},
        )
        self.assertEqual(rejected.status_code, 409, rejected.text)

        approved_paths = []
        for fragment_id in ("fragment-one", "fragment-two"):
            generated = self.client.post(
                f"/api/admin/fragments/{fragment_id}/narration/previews",
                headers=self.headers,
                json={"profile_id": profile["id"]},
            )
            self.assertEqual(generated.status_code, 201, generated.text)
            preview = generated.json()["previews"][0]
            self.assertEqual(preview["profile_id"], profile["id"])
            approved = self.client.post(
                f"/api/admin/narration/previews/{preview['id']}/approve",
                headers=self.headers,
            )
            self.assertEqual(approved.status_code, 200, approved.text)
            approved_paths.append(approved.json()["track"]["media_path"])

        self.assertEqual(len(set(approved_paths)), 2)
        self.assertTrue(all("/warm-storyteller/" in path for path in approved_paths))
        graph = self.client.get(
            "/api/admin/routes/route-test/content", headers=self.headers
        ).json()
        self.assertEqual(graph["fragments"][0]["audio_path"], original_audio)

        ready = self.client.get(
            f"/api/admin/routes/route-test/narration/coverage?profile_id={profile['id']}",
            headers=self.headers,
        ).json()
        self.assertTrue(ready["ready"])
        published = self.client.post(
            f"/api/admin/narration/profiles/{profile['id']}/publish",
            headers=self.headers,
            json={"route_id": "route-test"},
        )
        self.assertEqual(published.status_code, 200, published.text)
        with main.SessionLocal() as db:
            rows = list(
                db.query(FragmentNarrationTrack).filter_by(profile_id=profile["id"])
            )
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row.published_at is not None for row in rows))
            self.assertTrue(db.get(NarrationVoiceProfile, profile["id"]) is not None)

        made_default = self.client.post(
            f"/api/admin/narration/profiles/{profile['id']}/set-default",
            headers=self.headers,
        )
        self.assertEqual(made_default.status_code, 200, made_default.text)
        changed = self.client.get(
            "/api/admin/routes/route-test/content", headers=self.headers
        ).json()
        self.assertEqual(changed["fragments"][0]["audio_path"], approved_paths[0])

        with main.SessionLocal() as db:
            fragment = db.get(StoryFragment, "fragment-two")
            fragment.narration_script = "文字稿发生变化。"
            fragment.transcript = fragment.narration_script
            db.commit()
        stale = self.client.get(
            f"/api/admin/routes/route-test/narration/coverage?profile_id={profile['id']}",
            headers=self.headers,
        ).json()
        self.assertFalse(stale["ready"])
        self.assertEqual([item["id"] for item in stale["stale"]], ["fragment-two"])

    def test_two_non_default_profiles_generate_distinct_complete_route_tracks(self):
        imported = self.client.post(
            "/api/admin/fragmented-routes/import",
            headers=self.headers,
            json=self.payload(),
        )
        self.assertEqual(imported.status_code, 201, imported.text)
        original = self.client.get(
            "/api/admin/routes/route-test/content", headers=self.headers
        ).json()["fragments"][0]["audio_path"]
        all_paths = []
        for slug, name, voice_id in (
            ("calm-walker", "沉静同行者", "voice-calm"),
            ("vivid-storyteller", "生动讲述者", "voice-vivid"),
        ):
            created = self.client.post(
                "/api/admin/narration/profiles",
                headers=self.headers,
                json={"slug": slug, "display_name": name, "voice_id": voice_id},
            )
            self.assertEqual(created.status_code, 201, created.text)
            profile_id = created.json()["id"]
            for fragment_id in ("fragment-one", "fragment-two"):
                generated = self.client.post(
                    f"/api/admin/fragments/{fragment_id}/narration/previews",
                    headers=self.headers,
                    json={"profile_id": profile_id},
                )
                self.assertEqual(generated.status_code, 201, generated.text)
                approved = self.client.post(
                    f"/api/admin/narration/previews/{generated.json()['previews'][0]['id']}/approve",
                    headers=self.headers,
                )
                self.assertEqual(approved.status_code, 200, approved.text)
                all_paths.append(approved.json()["track"]["media_path"])
            published = self.client.post(
                f"/api/admin/narration/profiles/{profile_id}/publish",
                headers=self.headers,
                json={"route_id": "route-test"},
            )
            self.assertEqual(published.status_code, 200, published.text)

        self.assertEqual(len(all_paths), len(set(all_paths)))
        self.assertTrue(any("/calm-walker/" in item for item in all_paths))
        self.assertTrue(any("/vivid-storyteller/" in item for item in all_paths))
        unchanged = self.client.get(
            "/api/admin/routes/route-test/content", headers=self.headers
        ).json()["fragments"][0]["audio_path"]
        self.assertEqual(unchanged, original)

    def test_route_batch_generates_formal_tracks_and_retries_only_failed_nodes(self):
        imported = self.client.post(
            "/api/admin/fragmented-routes/import",
            headers=self.headers,
            json=self.payload(),
        )
        self.assertEqual(imported.status_code, 201, imported.text)
        created = self.client.post(
            "/api/admin/narration/profiles",
            headers=self.headers,
            json={
                "slug": "route-batch-voice",
                "display_name": "整线讲述者",
                "voice_id": "voice-route-batch",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        profile_id = created.json()["id"]
        original_synthesizer = main.narration_synthesizer

        class FailSecondFragment:
            provider = original_synthesizer.provider
            model = original_synthesizer.model

            def synthesize(self, request):
                if "第 2 段" in request.transcript:
                    raise NarrationSynthesisError("provider_unavailable")
                return original_synthesizer.synthesize(request)

        main.narration_synthesizer = FailSecondFragment()
        try:
            partial = self.client.post(
                "/api/admin/routes/route-test/narration/generate",
                headers=self.headers,
                json={"profile_id": profile_id, "regenerate_all": True},
            )
        finally:
            main.narration_synthesizer = original_synthesizer
        self.assertEqual(partial.status_code, 201, partial.text)
        self.assertEqual(partial.json()["generated_count"], 1)
        self.assertEqual(partial.json()["failed_count"], 1)
        self.assertFalse(partial.json()["coverage"]["ready"])
        self.assertEqual(
            [
                item["fragment_id"]
                for item in partial.json()["results"]
                if item["status"] == "failed"
            ],
            ["fragment-two"],
        )

        retried = self.client.post(
            "/api/admin/routes/route-test/narration/generate",
            headers=self.headers,
            json={"profile_id": profile_id},
        )
        self.assertEqual(retried.status_code, 201, retried.text)
        self.assertEqual(retried.json()["generated_count"], 1)
        self.assertEqual(retried.json()["failed_count"], 0)
        self.assertEqual(retried.json()["skipped_count"], 1)
        self.assertTrue(retried.json()["coverage"]["ready"])
        self.assertEqual(retried.json()["profile"]["status"], "draft")
        with main.SessionLocal() as db:
            tracks = list(
                db.query(FragmentNarrationTrack).filter_by(profile_id=profile_id)
            )
            self.assertEqual(len(tracks), 2)
            self.assertTrue(
                all("/route-batch-voice/" in row.media_path for row in tracks)
            )

    def test_same_checksum_assets_share_object_without_unsafe_deletion(self):
        first = self.client.post(
            "/api/admin/media",
            headers=self.headers,
            data={"key": "shared-a"},
            files={"file": ("same.mp3", b"same-audio", "audio/mpeg")},
        )
        self.assertEqual(first.status_code, 201, first.text)
        with main.SessionLocal() as db:
            original = db.get(MediaAsset, "shared-a")
            now = datetime.now(UTC)
            db.add(
                MediaAsset(
                    key="shared-b",
                    storage_path="legacy/shared-alias.mp3",
                    mime_type="audio/mpeg",
                    storage_provider=original.storage_provider,
                    object_key=original.object_key,
                    canonical_url=original.canonical_url,
                    visibility="public",
                    size_bytes=original.size_bytes,
                    checksum_sha256=original.checksum_sha256,
                    metadata_json={"legacy_alias": True},
                    created_at=now,
                    updated_at=now,
                )
            )
            db.commit()

        deleted = self.client.delete("/api/admin/media/shared-a", headers=self.headers)
        self.assertEqual(deleted.status_code, 204, deleted.text)
        surviving = self.client.get("/api/admin/media", headers=self.headers).json()
        shared_b = next(item for item in surviving if item["key"] == "shared-b")
        object_path = Path(_TEMP_DIR.name) / "media" / shared_b["object_key"]
        self.assertTrue(object_path.is_file())

    def test_home_story_review_publish_withdraw_and_stale_track_guard(self):
        imported = self.client.post(
            "/api/admin/fragmented-routes/import",
            headers=self.headers,
            json=self.payload(),
        )
        self.assertEqual(imported.status_code, 201, imported.text)
        self.client.post(
            "/api/admin/routes/route-test/submit-review", headers=self.headers
        )
        self.client.post("/api/admin/routes/route-test/verify", headers=self.headers)
        published_route = self.client.post(
            "/api/admin/routes/route-test/publish", headers=self.headers
        )
        self.assertEqual(published_route.status_code, 200, published_route.text)

        saved = self.client.put(
            "/api/admin/home-stories/arc-test",
            headers=self.headers,
            json={
                "title": "城墙听见的故事",
                "introduction": "",
                "cover_image": "",
                "selection_weight": 3,
            },
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["publication"]["introduction"], "测试副标题")
        self.assertEqual(saved.json()["publication"]["cover_image"], "images/route.png")
        self.assertNotIn("简介为空", saved.json()["blockers"])
        self.assertNotIn("封面为空", saved.json()["blockers"])
        self.assertIn("尚未选择完整故事音频", saved.json()["blockers"])

        profile_id = self.client.get(
            "/api/admin/narration/profiles", headers=self.headers
        ).json()[0]["id"]
        uploaded = self.client.post(
            "/api/admin/home-stories/arc-test/upload",
            headers=self.headers,
            data={"profile_id": profile_id, "duration_ms": "42000"},
            files={"file": ("story.mp3", b"manual-story-audio", "audio/mpeg")},
        )
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        self.assertEqual(uploaded.json()["tracks"][0]["duration_ms"], 42000)
        self.assertTrue(uploaded.json()["tracks"][0]["is_current"])

        generated = self.client.post(
            "/api/admin/home-stories/arc-test/generate",
            headers=self.headers,
            json={},
        )
        self.assertEqual(generated.status_code, 201, generated.text)
        track = generated.json()["tracks"][0]
        self.assertTrue(track["is_current"])
        audio = self.client.get(
            f"/api/admin{track['playback_path']}", headers=self.headers
        )
        self.assertEqual(audio.status_code, 200, audio.text)

        for action, expected in (
            ("submit-review", "in_review"),
            ("approve", "approved"),
            ("publish", "published"),
            ("withdraw", "withdrawn"),
            ("archive", "archived"),
        ):
            transitioned = self.client.post(
                f"/api/admin/home-stories/arc-test/{action}", headers=self.headers
            )
            self.assertEqual(transitioned.status_code, 200, transitioned.text)
            self.assertEqual(transitioned.json()["publication"]["status"], expected)

        # A changed canonical transcript can never reuse the previously approved audio.
        with main.SessionLocal() as db:
            arc = db.get(main.StoryArc, "arc-test")
            arc.complete_story = "正文已经更新，旧音频不应再次发布。"
            db.commit()
        stale = self.client.get("/api/admin/home-stories", headers=self.headers).json()[
            0
        ]
        self.assertFalse(stale["tracks"][0]["is_current"])
        self.assertIn("已选音频与当前正文不一致，请重新生成", stale["blockers"])

    def test_city_story_catalog_uses_canonical_source_and_fixed_home_module(self):
        imported = self.client.post(
            "/api/admin/fragmented-routes/import",
            headers=self.headers,
            json=self.payload(),
        )
        self.assertEqual(imported.status_code, 201, imported.text)
        with main.SessionLocal() as db:
            fragment = db.get(StoryFragment, "fragment-one")
            profile = NarrationVoiceProfile(
                id="catalog-profile",
                slug="catalog-profile",
                display_name="目录测试音色",
                description="",
                provider="fake",
                model="fake",
                voice_id="fake",
                emotion="neutral",
                speed=1.0,
                pitch=0,
                display_order=0,
                status="published",
                is_default=False,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                published_at=datetime.now(UTC),
            )
            track_id = "catalog-track"
            db.add(profile)
            db.add(
                FragmentNarrationTrack(
                    id=track_id,
                    fragment_id=fragment.id,
                    profile_id=profile.id,
                    transcript_hash=hashlib.sha256(
                        fragment.narration_script.strip().encode()
                    ).hexdigest(),
                    script_version=fragment.script_version,
                    media_path=fragment.audio_path,
                    mime_type=fragment.audio_mime_type,
                    size_bytes=fragment.audio_size_bytes,
                    checksum_sha256=None,
                    generation_metadata_json={"source": "test"},
                    approved_at=datetime.now(UTC),
                    published_at=datetime.now(UTC),
                )
            )
            db.commit()

        created = self.client.post(
            "/api/admin/story-catalog",
            headers=self.headers,
            json={
                "city_id": "city-test",
                "source_kind": "story_fragment",
                "source_id": "fragment-one",
                "title": "一段街角故事",
                "summary": "三分钟认识一个现场细节",
                "cover_image": "images/route.png",
                "content_type": "未来新增类型",
                "themes": ["未来主题"],
                "place_context": "测试城的一处公共街角",
                "observable_detail": "墙面的旧砖尺寸并不相同",
                "attention_hint": "可以留意转角处的砖缝",
                "sources": [{"title": "官方资料", "status": "documented"}],
                "variants": [{"role": "short_preview", "track_id": track_id}],
                "placements": [
                    {
                        "channel": "home",
                        "module_key": "today_city_story",
                        "display_order": 0,
                    }
                ],
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        body = created.json()
        self.assertEqual(body["content_type"], "未来新增类型")
        self.assertEqual(body["themes"], ["未来主题"])
        self.assertNotIn("audio_path", body)
        self.assertEqual(body["source"]["source_id"], "fragment-one")

        item_id = body["id"]
        for action, expected in (
            ("submit-review", "in_review"),
            ("verify", "verified"),
            ("publish", "published"),
        ):
            transitioned = self.client.post(
                f"/api/admin/story-catalog/{item_id}/{action}", headers=self.headers
            )
            self.assertEqual(transitioned.status_code, 200, transitioned.text)
            self.assertEqual(transitioned.json()["status"], expected)

        preview = self.client.get(
            "/api/admin/cities/city-test/home-story-preview", headers=self.headers
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(len(preview.json()["modules"]), 5)
        self.assertEqual(preview.json()["modules"][0]["items"][0]["id"], item_id)

    def test_multi_city_import_requires_preview_then_writes_draft_atomically(self):
        package = {
            "schema_version": "1.0",
            "package_id": "multi-city-test",
            "package_version": "1",
            "entities": {
                "cities": [
                    {
                        "id": "city-imported",
                        "slug": "imported-city",
                        "name": "导入城市",
                        "subtitle": "预检后写入",
                        "hero_image": "images/route.png",
                        "latitude": 30.0,
                        "longitude": 120.0,
                    }
                ],
                "routes": [],
                "stops": [],
                "story_arcs": [],
                "story_fragments": [],
                "catalog_items": [],
                "variants": [],
                "placements": [],
                "pretrip_guidance": [],
                "media": [],
            },
        }
        preview = self.client.post(
            "/api/admin/multi-city-import/preview",
            headers=self.headers,
            files={"file": ("package.json", json.dumps(package), "application/json")},
        )
        self.assertEqual(preview.status_code, 201, preview.text)
        self.assertTrue(preview.json()["can_confirm"])
        self.assertEqual(preview.json()["counts"]["new"], 1)
        with main.SessionLocal() as db:
            self.assertIsNone(db.get(main.City, "city-imported"))

        confirmed = self.client.post(
            "/api/admin/multi-city-import/confirm",
            headers=self.headers,
            json={"confirmation_token": preview.json()["confirmation_token"]},
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        with main.SessionLocal() as db:
            self.assertEqual(db.get(main.City, "city-imported").name, "导入城市")

        replay_preview = self.client.post(
            "/api/admin/multi-city-import/preview",
            headers=self.headers,
            files={"file": ("package.json", json.dumps(package), "application/json")},
        )
        self.assertEqual(replay_preview.status_code, 201, replay_preview.text)
        replay = self.client.post(
            "/api/admin/multi-city-import/confirm",
            headers=self.headers,
            json={"confirmation_token": replay_preview.json()["confirmation_token"]},
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(replay.json()["replayed"])

    def test_multi_city_preview_reports_json_pointer_without_content_writes(self):
        invalid = {
            "schema_version": "1.0",
            "package_id": "invalid-media",
            "package_version": "1",
            "entities": {
                "cities": [],
                "routes": [{"id": "route-missing-city", "city_id": "missing"}],
                "media": [{"key": "not-uploaded"}],
            },
        }
        response = self.client.post(
            "/api/admin/multi-city-import/preview",
            headers=self.headers,
            files={"file": ("package.json", json.dumps(invalid), "application/json")},
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertFalse(response.json()["can_confirm"])
        paths = {item["path"] for item in response.json()["problems"]}
        self.assertIn("/entities/routes/0/city_id", paths)
        self.assertIn("/entities/media/0/key", paths)
        self.assertIsNone(response.json()["confirmation_token"])


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
                    "context": {
                        "endpoint": "/cities",
                        "authorization": "Bearer private",
                    },
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
        self.assertEqual(
            [event["message"] for event in resumed.json()["events"]],
            ["audio service warning"],
        )

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
            headers={
                "X-Client-Log-Token": "client-test-token",
                "Content-Length": "999999",
            },
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
