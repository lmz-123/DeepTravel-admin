from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from content_graph import validate_graph
from content_schema import (
    ensure_footprint_content_schema,
    ensure_photo_mission_guidance_schema,
    normalize_experience_tags,
    normalize_footprint_summary_options,
)
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from models import (
    Challenge,
    City,
    ClaimSource,
    FragmentClaim,
    FragmentDependency,
    FragmentNarrationTrack,
    HistoricalClaim,
    HistoricalSource,
    HomeStoryPublication,
    Journey,
    JourneyAnswer,
    MediaAsset,
    NarrationPreview,
    NarrationVoiceProfile,
    PhotoMission,
    Route,
    RoutePredepartureTrack,
    RoutePretripGuidance,
    Stop,
    StoryArc,
    StoryCatalogItem,
    StoryCatalogVariant,
    StoryFragment,
    StoryNarrationTrack,
    StoryPlacement,
    TriggerRegion,
)
from multi_city_import import (
    PackageValidationError,
    build_preview,
    confirm_preview,
    normalize_package,
    parse_package,
    persist_preview,
)
from narration import (
    DeterministicNarrationSynthesizer,
    MiniMaxNarrationSynthesizer,
    NarrationRequest,
    NarrationSynthesisError,
)
from object_storage import AlibabaOssObjectStorage, InMemoryObjectStorage, StoredObject
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from runtime_logs.docker_source import DockerLogSource
from runtime_logs.normalization import (
    NormalizationLimits,
    normalize_event,
    normalize_level,
)
from runtime_logs.storage import (
    cleanup_client_logs,
    ensure_client_log_schema,
    persist_client_events,
    query_client_events,
)
from runtime_logs.streaming import StreamLimiter, limited_stream, sse_message
from schemas import ChallengeInput, CityInput, ClientLogBatch, RouteInput, StopInput
from sqlalchemy import create_engine, delete, func, inspect, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "mysql+pymysql://jiandi:jiandi_dev@127.0.0.1:3307/jiandi?charset=utf8mb4"
    )
    testing: bool = False
    admin_token: str = "dev-only-change-me"
    cors_origins: str = "http://localhost:3000"
    max_upload_mb: int = 30
    object_storage_provider: str = "oss"
    oss_region: str = ""
    oss_endpoint: str = ""
    oss_public_bucket: str = ""
    oss_private_bucket: str = ""
    oss_public_base_url: str = ""
    oss_access_key_id: str = ""
    oss_access_key_secret: str = ""
    oss_signed_url_ttl_seconds: int = 300
    narration_provider: str = "minimax"
    minimax_api_key: str = ""
    minimax_t2a_endpoint: str = "https://api.minimaxi.com/v1/t2a_v2"
    minimax_t2a_model: str = "speech-2.8-hd"
    minimax_voice_id: str = "Chinese (Mandarin)_Gentleman"
    minimax_timeout_seconds: float = 45.0
    narration_preview_ttl_hours: int = 24
    client_log_ingest_token: str = "dev-client-logs-change-me"
    client_log_max_request_kb: int = 128
    client_log_max_batch: int = 50
    client_log_retention_days: int = 1
    client_log_max_rows: int = 2_000
    client_log_cleanup_batch: int = 1_000
    backend_logs_enabled: bool = False
    docker_socket_path: str = "/var/run/docker.sock"
    docker_api_version: str = "v1.41"
    log_sources: str = (
        "travel-api=deeptravel-api-1,admin-api=deeptravel-admin-admin-api-1"
    )
    log_tail_limit: int = 300
    log_line_max_chars: int = 8_000
    log_context_max_chars: int = 1_000
    log_heartbeat_seconds: float = 12.0
    log_client_poll_seconds: float = 1.0
    log_stream_batch: int = 200
    log_max_streams: int = 6


def parse_log_sources(value: str) -> dict[str, str]:
    sources: dict[str, str] = {}
    for item in value.split(","):
        if not item.strip():
            continue
        alias, separator, target = item.partition("=")
        alias = alias.strip()
        target = target.strip()
        if (
            not separator
            or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", alias)
            or not target
        ):
            raise ValueError(f"非法 LOG_SOURCES 项：{item}")
        sources[alias] = target
    return sources


settings = Settings()
engine = create_engine(settings.database_url, pool_pre_ping=True, pool_recycle=1800)
SessionLocal = sessionmaker(engine, expire_on_commit=False)
if settings.testing:
    public_object_storage = InMemoryObjectStorage()
    private_object_storage = InMemoryObjectStorage("https://private.test.invalid")
elif settings.object_storage_provider == "oss":
    if (
        not settings.oss_region
        or not settings.oss_public_bucket
        or not settings.oss_private_bucket
        or not settings.oss_public_base_url
        or not settings.oss_access_key_id
        or not settings.oss_access_key_secret
    ):
        raise RuntimeError("OSS 运行时必须完整配置区域、公私 Bucket、CDN 与访问凭据")
    public_object_storage = AlibabaOssObjectStorage(
        region=settings.oss_region,
        bucket=settings.oss_public_bucket,
        endpoint=settings.oss_endpoint,
        public_base_url=settings.oss_public_base_url,
        access_key_id=settings.oss_access_key_id,
        access_key_secret=settings.oss_access_key_secret,
    )
    private_object_storage = AlibabaOssObjectStorage(
        region=settings.oss_region,
        bucket=settings.oss_private_bucket,
        endpoint=settings.oss_endpoint,
        public_base_url=settings.oss_public_base_url,
        access_key_id=settings.oss_access_key_id,
        access_key_secret=settings.oss_access_key_secret,
    )
else:
    raise RuntimeError(
        "OBJECT_STORAGE_PROVIDER 运行时仅支持 oss；unit test 请注入内存 fake"
    )
if settings.narration_provider == "fake":
    narration_synthesizer = DeterministicNarrationSynthesizer()
elif settings.narration_provider == "minimax":
    narration_synthesizer = MiniMaxNarrationSynthesizer(
        api_key=settings.minimax_api_key,
        endpoint=settings.minimax_t2a_endpoint,
        model=settings.minimax_t2a_model,
        timeout_seconds=settings.minimax_timeout_seconds,
    )
else:
    raise RuntimeError("NARRATION_PROVIDER 仅支持 minimax 或 fake")
normalization_limits = NormalizationLimits(
    message_chars=max(256, settings.log_line_max_chars),
    context_string_chars=max(128, settings.log_context_max_chars),
)
configured_log_sources = parse_log_sources(settings.log_sources)
docker_log_source = DockerLogSource(
    socket_path=settings.docker_socket_path,
    sources=configured_log_sources,
    api_version=settings.docker_api_version,
    limits=normalization_limits,
)
stream_limiter = StreamLimiter(settings.log_max_streams)


def run_log_retention() -> int:
    with SessionLocal() as db:
        removed = cleanup_client_logs(
            db,
            retention_days=max(1, settings.client_log_retention_days),
            max_rows=max(100, settings.client_log_max_rows),
            batch_size=max(1, settings.client_log_cleanup_batch),
        )
        db.commit()
        return removed


@asynccontextmanager
async def lifespan(_: FastAPI):
    if hmac.compare_digest(settings.admin_token, settings.client_log_ingest_token):
        raise RuntimeError("CLIENT_LOG_INGEST_TOKEN 必须与 ADMIN_TOKEN 不同")
    ensure_client_log_schema(engine)
    ensure_photo_mission_guidance_schema(engine)
    ensure_footprint_content_schema(engine)
    await asyncio.to_thread(run_log_retention)
    yield


app = FastAPI(title="简地内容中台 API", version="1.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        item.strip() for item in settings.cors_origins.split(",") if item.strip()
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
    expected = f"Bearer {settings.admin_token}"
    if not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="管理令牌无效")


def authorize_client_ingest(
    x_client_log_token: Annotated[str | None, Header()] = None,
) -> None:
    if not x_client_log_token or not hmac.compare_digest(
        x_client_log_token, settings.client_log_ingest_token
    ):
        raise HTTPException(status_code=401, detail="客户端日志令牌无效")


Db = Annotated[Session, Depends(get_db)]
Auth = Annotated[None, Depends(authorize)]
ClientLogAuth = Annotated[None, Depends(authorize_client_ingest)]


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def city_dict(item: City) -> dict[str, Any]:
    return {
        "id": item.id,
        "slug": item.slug,
        "name": item.name,
        "subtitle": item.subtitle,
        "hero_image": item.hero_image,
        "latitude": item.latitude,
        "longitude": item.longitude,
    }


def route_dict(
    item: Route, city_name: str | None = None, stop_count: int = 0
) -> dict[str, Any]:
    return {
        "id": item.id,
        "city_id": item.city_id,
        "city_name": city_name,
        "slug": item.slug,
        "title": item.title,
        "subtitle": item.subtitle,
        "description": item.description,
        "duration_minutes": item.duration_minutes,
        "distance_km": item.distance_km,
        "difficulty": item.difficulty,
        "theme": item.theme,
        "hero_image": item.hero_image,
        "is_featured": item.is_featured,
        "content_status": item.content_status,
        "published_at": iso(item.published_at),
        "is_public_visible": item.content_status == "published"
        and item.published_at is not None,
        "managed_package_id": item.managed_package_id,
        "managed_package_version": item.managed_package_version,
        "stop_count": stop_count,
    }


def stop_dict(
    item: Stop, route_title: str | None = None, has_challenge: bool = False
) -> dict[str, Any]:
    return {
        "id": item.id,
        "route_id": item.route_id,
        "route_title": route_title,
        "position": item.position,
        "title": item.title,
        "kicker": item.kicker,
        "address": item.address,
        "latitude": item.latitude,
        "longitude": item.longitude,
        "arrival_radius_m": item.arrival_radius_m,
        "story_title": item.story_title,
        "story_body": item.story_body,
        "audio_url": item.audio_url,
        "image": item.image,
        "insight": item.insight,
        "experience_tags": normalize_experience_tags(item.experience_tags_json or []),
        "has_challenge": has_challenge,
    }


def stop_values(payload: StopInput) -> dict[str, Any]:
    values = payload.model_dump()
    values["experience_tags_json"] = values.pop("experience_tags")
    return values


def challenge_dict(
    item: Challenge, stop_title: str | None = None, route_title: str | None = None
) -> dict[str, Any]:
    return {
        "id": item.id,
        "stop_id": item.stop_id,
        "stop_title": stop_title,
        "route_title": route_title,
        "prompt": item.prompt,
        "hint": item.hint,
        "options": item.options_json,
        "correct_option": item.correct_option,
        "explanation": item.explanation,
    }


def commit_or_conflict(db: Session, message: str = "数据与现有内容冲突") -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=message) from exc


@app.get("/api/admin/health")
def health(_: Auth, db: Db):
    db.execute(select(func.count()).select_from(City)).scalar_one()
    return {
        "status": "ok",
        "database": "connected",
        "media_storage": public_object_storage.provider,
        "media_readiness": _media_readiness(db),
        "client_log_storage": "connected",
        "backend_logs": "available"
        if settings.backend_logs_enabled and docker_log_source.available
        else "unavailable",
    }


REQUIRED_CITY_STORY_TABLES = {
    "story_catalog_items",
    "story_catalog_variants",
    "story_placements",
    "route_pretrip_guidance",
    "route_predeparture_tracks",
    "content_import_previews",
    "content_import_batches",
}
HOME_MODULES = (
    ("today_city_story", "今天听一段城市故事"),
    ("street_corner_3min", "3 分钟了解一个街角"),
    ("city_small_thing", "一座城市的一件小事"),
    ("overlooked_detail", "你路过但没注意的细节"),
    ("today_destination", "今天适合去哪儿"),
)


def require_city_story_schema() -> None:
    missing = REQUIRED_CITY_STORY_TABLES - set(inspect(engine).get_table_names())
    if missing:
        raise HTTPException(
            503,
            "主服务数据库尚未升级到 20260825_0015；缺少：" + "、".join(sorted(missing)),
        )
    required_columns = {
        "introduction_text",
        "introduction_transcript_hash",
        "introduction_script_version",
        "selected_intro_track_id",
    }
    missing_columns = required_columns - {
        column["name"]
        for column in inspect(engine).get_columns("route_pretrip_guidance")
    }
    if missing_columns:
        raise HTTPException(
            503, "主服务出发前字段未升级：" + "、".join(sorted(missing_columns))
        )


def _source_context(db: Session, source_kind: str, source_id: str) -> dict[str, Any]:
    if source_kind == "story_arc":
        source = db.get(StoryArc, source_id)
        if source is None:
            raise HTTPException(422, "完整故事来源不存在")
        transcript = source.complete_story.strip()
        tracks = list(
            db.scalars(
                select(StoryNarrationTrack).where(
                    StoryNarrationTrack.arc_id == source.id
                )
            )
        )
        return {
            "source_kind": source_kind,
            "source_id": source.id,
            "title": source.title,
            "transcript": transcript,
            "canonical_revision": hashlib.sha256(transcript.encode()).hexdigest(),
            "script_version": source.script_version,
            "review_status": source.review_state,
            "tracks": [
                {
                    "id": track.id,
                    "kind": "story",
                    "transcript_hash": track.transcript_hash,
                    "script_version": track.script_version,
                    "duration_ms": track.duration_ms,
                    "status": track.status,
                    "media_path": track.media_path,
                }
                for track in tracks
            ],
        }
    if source_kind == "story_fragment":
        source = db.get(StoryFragment, source_id)
        if source is None:
            raise HTTPException(422, "现场故事来源不存在")
        transcript = source.narration_script.strip()
        tracks = list(
            db.scalars(
                select(FragmentNarrationTrack).where(
                    FragmentNarrationTrack.fragment_id == source.id
                )
            )
        )
        return {
            "source_kind": source_kind,
            "source_id": source.id,
            "title": source.title,
            "transcript": transcript,
            "canonical_revision": hashlib.sha256(transcript.encode()).hexdigest(),
            "script_version": source.script_version,
            "review_status": source.review_state,
            "tracks": [
                {
                    "id": track.id,
                    "kind": "fragment",
                    "transcript_hash": track.transcript_hash,
                    "script_version": track.script_version,
                    "duration_ms": 0,
                    "status": "published" if track.published_at else "approved",
                    "media_path": track.media_path,
                }
                for track in tracks
            ],
        }
    raise HTTPException(422, "source_kind 仅支持 story_arc 或 story_fragment")


def _catalog_payload(db: Session, item: StoryCatalogItem) -> dict[str, Any]:
    source = _source_context(db, item.source_kind, item.source_id)
    city = db.get(City, item.city_id)
    variants = list(
        db.scalars(
            select(StoryCatalogVariant)
            .where(StoryCatalogVariant.catalog_item_id == item.id)
            .order_by(StoryCatalogVariant.role)
        )
    )
    placements = list(
        db.scalars(
            select(StoryPlacement)
            .where(StoryPlacement.catalog_item_id == item.id)
            .order_by(StoryPlacement.channel, StoryPlacement.display_order)
        )
    )
    blockers: list[str] = []
    if source["canonical_revision"] != item.canonical_revision:
        blockers.append("来源正文已变化，需要重新审核变体")
    if source["review_status"] != "reviewed":
        blockers.append("规范故事尚未审核")
    if item.review_status != "reviewed":
        blockers.append("目录元数据尚未审核")
    if not item.title.strip() or not source["transcript"].strip():
        blockers.append("标题和故事内容不能为空")
    track_map = {track["id"]: track for track in source["tracks"]}
    variant_payloads: list[dict[str, Any]] = []
    durations: list[int] = []
    for variant in variants:
        track = track_map.get(variant.track_id)
        stale = (
            track is None
            or variant.transcript_hash != source["canonical_revision"]
            or variant.script_version != source["script_version"]
            or track["transcript_hash"] != source["canonical_revision"]
            or track["status"] not in {"approved", "published"}
        )
        if stale:
            blockers.append(f"{variant.role} 变体与当前正文或音频不一致")
        if track and track["duration_ms"]:
            durations.append(int(track["duration_ms"]))
        variant_payloads.append(
            {
                "id": variant.id,
                "role": variant.role,
                "source_kind": variant.source_kind,
                "source_id": variant.source_id,
                "track_kind": variant.track_kind,
                "track_id": variant.track_id,
                "transcript_hash": variant.transcript_hash,
                "script_version": variant.script_version,
                "status": variant.status,
                "stale": stale,
            }
        )
    if not variants:
        blockers.append("至少需要一个已审核的展示变体")
    duration_ms = (
        min(durations) if durations else max(1, len(source["transcript"]) // 4) * 1000
    )
    warnings = []
    if duration_ms < 180_000 or duration_ms > 480_000:
        warnings.append("建议将短故事控制在 3–8 分钟；此项不阻止发布")
    return {
        "id": item.id,
        "city_id": item.city_id,
        "city_name": city.name if city else "",
        "source_kind": item.source_kind,
        "source_id": item.source_id,
        "canonical_revision": item.canonical_revision,
        "title": item.title,
        "summary": item.summary,
        "cover_image": item.cover_image,
        "district": item.district,
        "themes": item.themes_json,
        "point_ids": item.point_ids_json,
        "related_stories": item.related_stories_json,
        "content_type": item.content_type,
        "place_context": item.place_context,
        "observable_detail": item.observable_detail,
        "attention_hint": item.attention_hint,
        "sources": item.sources_json,
        "fact_status": item.fact_status,
        "review_status": item.review_status,
        "status": item.status,
        "version": item.version,
        "source": source,
        "story_content": source["transcript"],
        "variants": variant_payloads,
        "placements": [
            {
                "id": row.id,
                "channel": row.channel,
                "module_key": row.module_key,
                "route_id": row.route_id,
                "variant_role": row.variant_role,
                "display_order": row.display_order,
                "weight": row.weight,
                "status": row.status,
                "starts_at": iso(row.starts_at),
                "ends_at": iso(row.ends_at),
            }
            for row in placements
        ],
        "duration_ms": duration_ms,
        "warnings": warnings,
        "blockers": sorted(set(blockers)),
        "ready_to_publish": not blockers,
        "updated_at": iso(item.updated_at),
    }


def _save_catalog_item(
    db: Session, payload: dict[str, Any], item: StoryCatalogItem | None = None
) -> StoryCatalogItem:
    forbidden = {
        "transcript",
        "audio",
        "audio_path",
        "narration_script",
    } & payload.keys()
    if forbidden:
        raise HTTPException(422, "目录只引用规范故事，不能复制正文或音频字段")
    now = datetime.now(UTC)
    if item is not None and item.status == "published":
        raise HTTPException(409, "已发布故事请先撤回再修改")
    simple_create = item is None and not payload.get("source_kind") and not payload.get("source_id")
    city_id = str(payload.get("city_id") or (item.city_id if item else ""))
    city = db.get(City, city_id)
    if city is None:
        raise HTTPException(422, "所属城市不存在")
    source_kind = str(payload.get("source_kind") or (item.source_kind if item else ""))
    source_id = str(payload.get("source_id") or (item.source_id if item else ""))
    if simple_create:
        used_sources = select(StoryCatalogItem.source_id).where(
            StoryCatalogItem.source_kind == "story_arc"
        )
        candidate = db.scalar(
            select(StoryArc)
            .join(Route, Route.id == StoryArc.route_id)
            .where(Route.city_id == city_id, ~StoryArc.id.in_(used_sources))
            .order_by(StoryArc.id)
        )
        if candidate is None:
            raise HTTPException(409, "这个城市没有可添加的景点完整故事，请先在景点内容中添加故事")
        source_kind = "story_arc"
        source_id = candidate.id

    title = str(payload.get("title") or "").strip()
    story_content = str(payload.get("story_content") or "").strip()
    if "story_content" in payload:
        if not title or not story_content:
            raise HTTPException(422, "标题和故事内容不能为空")
        if source_kind == "story_arc":
            canonical = db.get(StoryArc, source_id)
            if canonical is None:
                raise HTTPException(422, "完整故事来源不存在")
            transcript_changed = canonical.complete_story.strip() != story_content
            canonical.title = title
            canonical.complete_story = story_content
            if transcript_changed:
                canonical.review_state = "in_review"
        elif source_kind == "story_fragment":
            canonical_fragment = db.get(StoryFragment, source_id)
            if canonical_fragment is None:
                raise HTTPException(422, "现场故事来源不存在")
            transcript_changed = canonical_fragment.narration_script.strip() != story_content
            canonical_fragment.title = title
            canonical_fragment.narration_script = story_content
            canonical_fragment.transcript = story_content
            if transcript_changed:
                canonical_fragment.review_state = "in_review"
        db.flush()
    source = _source_context(db, source_kind, source_id)
    if item is None:
        route = (
            db.scalar(select(Route).join(StoryArc, StoryArc.route_id == Route.id).where(StoryArc.id == source_id))
            if source_kind == "story_arc"
            else None
        )
        fallback_summary = (story_content or source["transcript"]).strip()[:160]
        item = StoryCatalogItem(
            id=str(payload.get("id") or uuid4()),
            source_kind=source_kind,
            source_id=source_id,
            canonical_revision=source["canonical_revision"],
            city_id=city_id,
            title=title or source["title"],
            summary=str(payload.get("summary") or fallback_summary),
            cover_image=str(payload.get("cover_image") or (route.hero_image if route else city.hero_image)),
            content_type=str(payload.get("content_type") or "城市故事"),
            place_context=str(payload.get("place_context") or city.name),
            observable_detail=str(payload.get("observable_detail") or (route.title if route else title or source["title"])),
            status="draft",
            review_status="in_review",
            version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(item)
    elif source_kind != item.source_kind or source_id != item.source_id:
        item.source_kind = source_kind
        item.source_id = source_id
        item.canonical_revision = source["canonical_revision"]
        item.review_status = "in_review"
    if "story_content" in payload:
        item.title = title
        item.summary = story_content[:160]
        item.canonical_revision = source["canonical_revision"]
        if transcript_changed:
            item.review_status = "in_review"
    mappings = {
        "city_id": "city_id",
        "title": "title",
        "summary": "summary",
        "cover_image": "cover_image",
        "district": "district",
        "themes": "themes_json",
        "point_ids": "point_ids_json",
        "related_stories": "related_stories_json",
        "content_type": "content_type",
        "place_context": "place_context",
        "observable_detail": "observable_detail",
        "attention_hint": "attention_hint",
        "sources": "sources_json",
        "fact_status": "fact_status",
        "review_status": "review_status",
    }
    for source_field, target_field in mappings.items():
        if source_field in payload:
            setattr(item, target_field, payload[source_field])
    if simple_create and not item.sources_json:
        item.sources_json = [{"kind": "canonical_story", "source_id": source_id}]
    item.version += 1 if item.created_at != now else 0
    item.updated_at = now
    db.flush()
    if simple_create and "variants" not in payload:
        approved_track = next(
            (track for track in source["tracks"] if track["status"] in {"approved", "published"}),
            None,
        )
        if approved_track:
            payload["variants"] = [{"role": "short_preview", "track_id": approved_track["id"]}]
    if simple_create and "placements" not in payload:
        payload["placements"] = [{"channel": "home", "module_key": "today_city_story", "display_order": 0}]
    if "variants" in payload:
        db.execute(
            delete(StoryCatalogVariant).where(
                StoryCatalogVariant.catalog_item_id == item.id
            )
        )
        for raw in payload["variants"]:
            role = str(raw.get("role") or "")
            if role not in {"short_preview", "on_site_complete"}:
                raise HTTPException(
                    422, "变体 role 仅支持 short_preview/on_site_complete"
                )
            track_id = str(raw.get("track_id") or "")
            track = next(
                (row for row in source["tracks"] if row["id"] == track_id), None
            )
            if track is None:
                raise HTTPException(422, f"变体音频 {track_id} 不属于当前规范故事")
            db.add(
                StoryCatalogVariant(
                    id=str(raw.get("id") or uuid4()),
                    catalog_item_id=item.id,
                    role=role,
                    source_kind=item.source_kind,
                    source_id=item.source_id,
                    track_kind=track["kind"],
                    track_id=track_id,
                    transcript_hash=source["canonical_revision"],
                    script_version=source["script_version"],
                    status="draft",
                    created_at=now,
                    updated_at=now,
                )
            )
    if "placements" in payload:
        db.execute(
            delete(StoryPlacement).where(StoryPlacement.catalog_item_id == item.id)
        )
        for raw in payload["placements"]:
            module_key = raw.get("module_key")
            if raw.get("channel") == "home" and module_key not in dict(HOME_MODULES):
                raise HTTPException(
                    422, "首页 placement 必须使用五个固定 module_key 之一"
                )
            db.add(
                StoryPlacement(
                    id=str(raw.get("id") or uuid4()),
                    catalog_item_id=item.id,
                    channel=str(raw.get("channel") or "home"),
                    module_key=module_key,
                    route_id=raw.get("route_id"),
                    variant_role=str(raw.get("variant_role") or "short_preview"),
                    display_order=int(raw.get("display_order") or 0),
                    weight=max(1, int(raw.get("weight") or 1)),
                    status="draft",
                    starts_at=_parse_datetime(raw.get("starts_at")),
                    ends_at=_parse_datetime(raw.get("ends_at")),
                    created_at=now,
                    updated_at=now,
                )
            )
    return item


@app.get("/api/admin/schema/city-stories")
def city_story_schema_status(_: Auth):
    require_city_story_schema()
    return {"status": "compatible", "required_migration": "20260823_0013"}


@app.get("/api/admin/story-catalog")
def list_story_catalog(_: Auth, db: Db, city_id: str | None = None):
    require_city_story_schema()
    query = select(StoryCatalogItem).order_by(StoryCatalogItem.updated_at.desc())
    if city_id:
        query = query.where(StoryCatalogItem.city_id == city_id)
    return [_catalog_payload(db, item) for item in db.scalars(query)]


@app.get("/api/admin/story-catalog/{item_id}")
def get_story_catalog(item_id: str, _: Auth, db: Db):
    require_city_story_schema()
    item = db.get(StoryCatalogItem, item_id)
    if item is None:
        raise HTTPException(404, "城市故事不存在")
    return _catalog_payload(db, item)


@app.post("/api/admin/story-catalog", status_code=201)
def create_story_catalog(payload: dict[str, Any], _: Auth, db: Db):
    require_city_story_schema()
    try:
        item = _save_catalog_item(db, payload)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "同一规范故事只能建立一个目录项") from exc
    return _catalog_payload(db, item)


@app.put("/api/admin/story-catalog/{item_id}")
def update_story_catalog(item_id: str, payload: dict[str, Any], _: Auth, db: Db):
    require_city_story_schema()
    item = db.get(StoryCatalogItem, item_id)
    if item is None:
        raise HTTPException(404, "城市故事不存在")
    expected_version = payload.pop("expected_version", None)
    if expected_version is not None and int(expected_version) != item.version:
        raise HTTPException(409, "内容已被其他编辑更新，请刷新后重试")
    item = _save_catalog_item(db, payload, item)
    db.commit()
    return _catalog_payload(db, item)


@app.post("/api/admin/story-catalog/{item_id}/{action}")
def transition_story_catalog(item_id: str, action: str, _: Auth, db: Db):
    require_city_story_schema()
    item = db.get(StoryCatalogItem, item_id)
    if item is None:
        raise HTTPException(404, "城市故事不存在")
    now = datetime.now(UTC)
    if action == "submit-review":
        item.status = "in_review"
    elif action == "verify":
        item.status = "verified"
        item.review_status = "reviewed"
        item.reviewed_at = now
    elif action == "publish":
        projection = _catalog_payload(db, item)
        if projection["blockers"]:
            raise HTTPException(
                422, {"message": "仍有发布阻塞项", "blockers": projection["blockers"]}
            )
        item.status = "published"
        item.published_at = now
        for row in db.scalars(
            select(StoryCatalogVariant).where(
                StoryCatalogVariant.catalog_item_id == item.id
            )
        ):
            row.status = "published"
            row.published_at = now
        for row in db.scalars(
            select(StoryPlacement).where(StoryPlacement.catalog_item_id == item.id)
        ):
            row.status = "published"
            row.published_at = now
    elif action == "withdraw":
        item.status = "draft"
        item.published_at = None
        for model in (StoryCatalogVariant, StoryPlacement):
            for row in db.scalars(
                select(model).where(model.catalog_item_id == item.id)
            ):
                row.status = "draft"
                row.published_at = None
    else:
        raise HTTPException(404, "未知生命周期操作")
    item.updated_at = now
    db.commit()
    return _catalog_payload(db, item)


@app.get("/api/admin/cities/{city_id}/home-story-preview")
def preview_city_home(city_id: str, _: Auth, db: Db):
    require_city_story_schema()
    if db.get(City, city_id) is None:
        raise HTTPException(404, "城市不存在")
    modules = []
    for key, label in HOME_MODULES:
        placements = list(
            db.scalars(
                select(StoryPlacement)
                .join(
                    StoryCatalogItem,
                    StoryCatalogItem.id == StoryPlacement.catalog_item_id,
                )
                .where(
                    StoryCatalogItem.city_id == city_id,
                    StoryPlacement.channel == "home",
                    StoryPlacement.module_key == key,
                )
                .order_by(StoryPlacement.display_order, StoryPlacement.weight.desc())
            )
        )
        modules.append(
            {
                "key": key,
                "label": label,
                "items": [
                    _catalog_payload(db, db.get(StoryCatalogItem, row.catalog_item_id))
                    for row in placements
                ],
                "empty": not placements,
            }
        )
    return {"city_id": city_id, "modules": modules}


def _pretrip_payload(
    item: RoutePretripGuidance | None, route_id: str, db: Session | None = None
) -> dict[str, Any]:
    tracks = []
    if db is not None:
        tracks = [
            {
                "id": track.id,
                "profile_id": track.profile_id,
                "script_version": track.script_version,
                "transcript_hash": track.transcript_hash,
                "media_path": track.media_path,
                "mime_type": track.mime_type,
                "size_bytes": track.size_bytes,
                "duration_ms": track.duration_ms,
                "status": track.status,
                "matches_current_text": bool(
                    item and track.transcript_hash == item.introduction_transcript_hash
                ),
            }
            for track in db.scalars(
                select(RoutePredepartureTrack)
                .where(RoutePredepartureTrack.route_id == route_id)
                .order_by(RoutePredepartureTrack.updated_at.desc())
            )
        ]
    if item is None:
        return {
            "route_id": route_id,
            "theme_story_catalog_id": None,
            "story_directions": [],
            "companion_tags": [],
            "safety_tips": [],
            "rest_tips": [],
            "accessibility_tips": [],
            "weather_tips": [],
            "offline_roles": [],
            "introduction_text": "",
            "introduction_transcript_hash": None,
            "introduction_script_version": "1",
            "selected_intro_track_id": None,
            "tracks": tracks,
            "status": "draft",
            "version": 0,
        }
    return {
        "route_id": item.route_id,
        "theme_story_catalog_id": item.theme_story_catalog_id,
        "story_directions": item.story_directions_json,
        "companion_tags": item.companion_tags_json,
        "safety_tips": item.safety_tips_json,
        "rest_tips": item.rest_tips_json,
        "accessibility_tips": item.accessibility_tips_json,
        "weather_tips": item.weather_tips_json,
        "offline_roles": item.offline_roles_json,
        "introduction_text": item.introduction_text or "",
        "introduction_transcript_hash": item.introduction_transcript_hash,
        "introduction_script_version": item.introduction_script_version or "1",
        "selected_intro_track_id": item.selected_intro_track_id,
        "tracks": tracks,
        "status": item.status,
        "version": item.version,
        "updated_at": iso(item.updated_at),
    }


@app.get("/api/admin/routes/{route_id}/pretrip")
def get_route_pretrip(route_id: str, _: Auth, db: Db):
    require_city_story_schema()
    if db.get(Route, route_id) is None:
        raise HTTPException(404, "路线不存在")
    return _pretrip_payload(db.get(RoutePretripGuidance, route_id), route_id, db)


@app.put("/api/admin/routes/{route_id}/pretrip")
def save_route_pretrip(route_id: str, payload: dict[str, Any], _: Auth, db: Db):
    require_city_story_schema()
    if db.get(Route, route_id) is None:
        raise HTTPException(404, "路线不存在")
    item = db.get(RoutePretripGuidance, route_id)
    if item and item.status == "published":
        raise HTTPException(409, "已发布的出发前内容请先撤回")
    expected_version = payload.pop("expected_version", None)
    if item and expected_version is not None and int(expected_version) != item.version:
        raise HTTPException(409, "内容已被其他编辑更新，请刷新后重试")
    now = datetime.now(UTC)
    if item is None:
        item = RoutePretripGuidance(
            route_id=route_id, status="draft", version=0, updated_at=now
        )
        db.add(item)
    theme_id = payload.get("theme_story_catalog_id", item.theme_story_catalog_id)
    if theme_id and db.get(StoryCatalogItem, str(theme_id)) is None:
        raise HTTPException(422, "主题故事不存在")
    item.theme_story_catalog_id = theme_id or None
    if "introduction_text" in payload:
        introduction = "\n".join(
            line.strip()
            for line in str(payload["introduction_text"]).splitlines()
            if line.strip()
        )
        if len(introduction) > 1200:
            raise HTTPException(422, "出发前介绍不能超过 1200 字")
        digest = (
            hashlib.sha256(introduction.encode("utf-8")).hexdigest()
            if introduction
            else None
        )
        if digest != item.introduction_transcript_hash:
            item.selected_intro_track_id = None
            item.published_at = None
        item.introduction_text = introduction or None
        item.introduction_transcript_hash = digest
        item.introduction_script_version = str(
            payload.get("introduction_script_version")
            or item.introduction_script_version
            or "1"
        )[:40]
    if "selected_intro_track_id" in payload:
        track_id = str(payload.get("selected_intro_track_id") or "") or None
        track = db.get(RoutePredepartureTrack, track_id) if track_id else None
        if track and (
            track.route_id != route_id
            or track.status != "published"
            or track.transcript_hash != item.introduction_transcript_hash
            or track.script_version != item.introduction_script_version
        ):
            raise HTTPException(422, "只能选择当前文字版本对应的已审核音频")
        item.selected_intro_track_id = track_id
    for source_field, target_field in {
        "story_directions": "story_directions_json",
        "companion_tags": "companion_tags_json",
        "safety_tips": "safety_tips_json",
        "rest_tips": "rest_tips_json",
        "accessibility_tips": "accessibility_tips_json",
        "weather_tips": "weather_tips_json",
        "offline_roles": "offline_roles_json",
    }.items():
        if source_field in payload:
            setattr(item, target_field, payload[source_field])
    item.status = "in_review" if payload.get("submit_review") else "draft"
    item.version += 1
    item.updated_at = now
    db.commit()
    return _pretrip_payload(item, route_id, db)


@app.post("/api/admin/routes/{route_id}/pretrip/{action}")
def transition_route_pretrip(route_id: str, action: str, _: Auth, db: Db):
    require_city_story_schema()
    item = db.get(RoutePretripGuidance, route_id)
    if item is None:
        raise HTTPException(404, "出发前内容不存在")
    now = datetime.now(UTC)
    if action == "publish":
        if not item.introduction_text or not item.introduction_transcript_hash:
            raise HTTPException(422, "发布前必须填写出发前介绍")
        track = (
            db.get(RoutePredepartureTrack, item.selected_intro_track_id)
            if item.selected_intro_track_id
            else None
        )
        if not track or track.status != "published" or track.route_id != route_id:
            raise HTTPException(422, "发布前必须选择已审核音频")
        if (
            track.transcript_hash != item.introduction_transcript_hash
            or track.script_version != item.introduction_script_version
        ):
            raise HTTPException(422, "文字已变化，请重新审核匹配音频")
        item.status = "published"
        item.reviewed_at = now
        item.published_at = now
    elif action == "withdraw":
        item.status = "draft"
        item.published_at = None
    else:
        raise HTTPException(404, "未知生命周期操作")
    item.version += 1
    item.updated_at = now
    db.commit()
    return _pretrip_payload(item, route_id, db)


@app.post("/api/admin/routes/{route_id}/pretrip/audio", status_code=201)
def upload_route_predeparture_audio(
    route_id: str,
    _: Auth,
    db: Db,
    file: Annotated[UploadFile, File()],
    profile_id: Annotated[str, Form()],
    duration_ms: Annotated[int, Form()] = 0,
):
    item = db.get(RoutePretripGuidance, route_id)
    if (
        item is None
        or not item.introduction_transcript_hash
        or not item.introduction_script_version
    ):
        raise HTTPException(422, "请先保存出发前介绍文字")
    if db.get(NarrationVoiceProfile, profile_id) is None:
        raise HTTPException(422, "旁白音色不存在")
    existing_track = db.scalar(
        select(RoutePredepartureTrack).where(
            RoutePredepartureTrack.route_id == route_id,
            RoutePredepartureTrack.profile_id == profile_id,
            RoutePredepartureTrack.transcript_hash == item.introduction_transcript_hash,
            RoutePredepartureTrack.script_version == item.introduction_script_version,
        )
    )
    if existing_track is not None:
        return {"track": next(
            row for row in _pretrip_payload(item, route_id, db)["tracks"]
            if row["id"] == existing_track.id
        ), "idempotent": True}
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(415, "请选择音频文件")
    payload = file.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if not payload or len(payload) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"音频不能为空且不能超过 {settings.max_upload_mb}MB")
    checksum = hashlib.sha256(payload).hexdigest()
    suffix = Path(file.filename or "intro.mp3").suffix.lower() or ".mp3"
    object_key = (
        f"public/predeparture/{route_id}/"
        f"{item.introduction_transcript_hash}/{checksum}{suffix}"
    )
    uploaded_now = not public_object_storage.exists(object_key)
    if uploaded_now:
        public_object_storage.put(object_key, payload, file.content_type)
    now = datetime.now(UTC)
    track = RoutePredepartureTrack(
        id=str(uuid4()),
        route_id=route_id,
        profile_id=profile_id,
        transcript_hash=item.introduction_transcript_hash,
        script_version=item.introduction_script_version,
        media_path=public_object_storage.public_url(object_key),
        mime_type=file.content_type,
        size_bytes=len(payload),
        duration_ms=max(1, duration_ms),
        checksum_sha256=checksum,
        generation_metadata_json={
            "source": "operator_upload",
            "object_key": object_key,
        },
        status="published",
        reviewed_at=now,
        published_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(track)
    db.add(MediaAsset(
        key=f"predeparture-{track.id}", storage_path=object_key,
        mime_type=file.content_type, storage_provider="oss", object_key=object_key,
        canonical_url=track.media_path, visibility="public", size_bytes=len(payload),
        checksum_sha256=checksum,
        metadata_json={"usage": "predeparture", "route_id": route_id},
        created_at=now, updated_at=now,
    ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if uploaded_now:
            public_object_storage.delete(object_key)
        raise
    return {"track": next(
        row for row in _pretrip_payload(item, route_id, db)["tracks"]
        if row["id"] == track.id
    ), "idempotent": False}


def _package_error(exc: PackageValidationError) -> HTTPException:
    return HTTPException(
        422, {"message": str(exc), "problems": [x.as_dict() for x in exc.problems]}
    )


@app.post("/api/admin/multi-city-import/preview", status_code=201)
async def preview_multi_city_import(file: UploadFile, _: Auth, db: Db):
    require_city_story_schema()
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(422, "请选择 JSON 文件")
    try:
        package = normalize_package(parse_package(await file.read(2 * 1024 * 1024 + 1)))
        plan = build_preview(db, package)
        preview, token = persist_preview(
            db, plan, editor_id="admin-token", secret=settings.admin_token
        )
        db.commit()
    except PackageValidationError as exc:
        db.rollback()
        raise _package_error(exc) from exc
    return {
        "preview_id": preview.id,
        "confirmation_token": token if plan["can_confirm"] else None,
        "expires_at": iso(preview.expires_at),
        **{
            key: value
            for key, value in plan.items()
            if key not in {"package", "target_revisions"}
        },
    }


@app.post("/api/admin/multi-city-import/confirm")
def confirm_multi_city_import(payload: dict[str, Any], _: Auth, db: Db):
    require_city_story_schema()
    token = str(payload.get("confirmation_token") or "")
    if not token:
        raise HTTPException(422, "confirmation_token 不能为空")
    try:
        result = confirm_preview(
            db, token=token, editor_id="admin-token", secret=settings.admin_token
        )
        db.commit()
    except PackageValidationError as exc:
        db.rollback()
        raise _package_error(exc) from exc
    except Exception:
        db.rollback()
        raise
    return result


def _query_client_events(**kwargs: Any):
    with SessionLocal() as db:
        return query_client_events(db, **kwargs)


def _parse_levels(value: str) -> set[str]:
    return {normalize_level(item) for item in value.split(",") if item.strip()}


@app.post("/api/runtime/client-logs", status_code=202)
async def ingest_client_logs(request: Request, _: ClientLogAuth, db: Db):
    content_length = request.headers.get("content-length")
    max_bytes = max(1, settings.client_log_max_request_kb) * 1024
    if content_length and content_length.isdigit() and int(content_length) > max_bytes:
        raise HTTPException(413, "客户端日志请求过大")
    body = await request.body()
    if len(body) > max_bytes:
        raise HTTPException(413, "客户端日志请求过大")
    try:
        payload = ClientLogBatch.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(
            422, exc.errors(include_input=False, include_url=False)
        ) from exc
    if len(payload.events) > min(50, max(1, settings.client_log_max_batch)):
        raise HTTPException(422, "单批客户端日志数量超出限制")

    received_at = datetime.now(UTC)
    normalized = []
    for index, item in enumerate(payload.events):
        context = {
            **item.context,
            "_session_id": item.session_id,
            "_app_version": item.app_version,
            "_platform": item.platform,
        }
        normalized.append(
            normalize_event(
                cursor=f"pending:{index}",
                occurred_at=item.occurred_at,
                received_at=received_at,
                source_type="client",
                source=item.source,
                level=item.level,
                category=item.category,
                message=item.message,
                context=context,
                limits=normalization_limits,
            )
        )
    try:
        rows = persist_client_events(db, normalized)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to persist client runtime logs")
        raise HTTPException(503, "客户端日志暂时无法写入") from None

    try:
        run_log_retention()
    except Exception:
        logger.exception("Client log retention cleanup failed")
    return {
        "accepted": len(rows),
        "first_cursor": rows[0].id if rows else None,
        "last_cursor": rows[-1].id if rows else None,
    }


@app.get("/api/admin/logs/sources")
def list_log_sources(_: Auth):
    backend_available = settings.backend_logs_enabled and docker_log_source.available
    return {
        "client": {"id": "client", "label": "客户端", "available": True},
        "backend": [
            {
                "id": alias,
                "label": alias.replace("-", " "),
                "available": backend_available,
            }
            for alias in configured_log_sources
        ],
        "limits": {
            "tail": settings.log_tail_limit,
            "max_streams": settings.log_max_streams,
            "retention_days": settings.client_log_retention_days,
        },
    }


@app.get("/api/admin/logs/client/history")
def client_log_history(
    _: Auth,
    db: Db,
    after: int | None = None,
    before: int | None = None,
    levels: str = "",
    keyword: str = "",
    session_id: str = "",
    source: str = "",
    limit: int = 200,
):
    events = query_client_events(
        db,
        after_cursor=after,
        before_cursor=before,
        levels=_parse_levels(levels),
        keyword=keyword[:200],
        session_id=session_id[:120],
        source=source[:120],
        limit=min(max(limit, 1), settings.log_tail_limit),
    )
    return {"events": [event.to_dict() for event in events]}


async def client_log_stream(request: Request, *, after: int | None, tail: int):
    yield sse_message(
        "metadata",
        {
            "source_type": "client",
            "source": "client",
            "heartbeat_seconds": settings.log_heartbeat_seconds,
        },
    )
    cursor = after
    initial = await asyncio.to_thread(
        _query_client_events,
        after_cursor=after,
        limit=min(max(1, tail), settings.log_tail_limit),
    )
    for event in initial:
        cursor = int(event.cursor)
        yield sse_message("log", event.to_dict(), cursor=event.cursor)

    last_heartbeat = time.monotonic()
    while not await request.is_disconnected():
        await asyncio.sleep(max(0.2, settings.log_client_poll_seconds))
        events = await asyncio.to_thread(
            _query_client_events,
            after_cursor=cursor if cursor is not None else 0,
            limit=max(1, settings.log_stream_batch),
        )
        for event in events:
            cursor = int(event.cursor)
            yield sse_message("log", event.to_dict(), cursor=event.cursor)
            last_heartbeat = time.monotonic()
        if time.monotonic() - last_heartbeat >= max(
            2.0, settings.log_heartbeat_seconds
        ):
            yield sse_message("heartbeat", {"at": datetime.now(UTC).isoformat()})
            last_heartbeat = time.monotonic()


@app.get("/api/admin/logs/client/stream")
async def stream_client_logs(
    request: Request, _: Auth, after: int | None = None, tail: int = 200
):
    if not await stream_limiter.acquire():
        raise HTTPException(429, "实时日志连接数已达上限")
    source = client_log_stream(request, after=after, tail=tail)
    return StreamingResponse(
        limited_stream(source, stream_limiter),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, no-transform",
            "Pragma": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )


async def backend_log_stream(request: Request, *, source: str, tail: int):
    yield sse_message(
        "metadata",
        {
            "source_type": "backend",
            "source": source,
            "heartbeat_seconds": settings.log_heartbeat_seconds,
        },
    )
    iterator = docker_log_source.follow(source, tail=tail).__aiter__()
    pending: asyncio.Task | None = None
    try:
        while not await request.is_disconnected():
            if pending is None:
                pending = asyncio.create_task(anext(iterator))
            done, _ = await asyncio.wait(
                {pending}, timeout=max(2.0, settings.log_heartbeat_seconds)
            )
            if not done:
                yield sse_message("heartbeat", {"at": datetime.now(UTC).isoformat()})
                continue
            try:
                event = pending.result()
            except StopAsyncIteration:
                yield sse_message(
                    "source_status", {"status": "ended", "source": source}
                )
                break
            pending = None
            yield sse_message("log", event.to_dict(), cursor=event.cursor)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(
            "Backend log source %s unavailable: %s", source, type(exc).__name__
        )
        yield sse_message(
            "source_status",
            {
                "status": "unavailable",
                "source": source,
                "message": "后端日志源暂不可用",
            },
        )
    finally:
        if pending and not pending.done():
            pending.cancel()
        await iterator.aclose()


@app.get("/api/admin/logs/backend/stream")
async def stream_backend_logs(request: Request, _: Auth, source: str, tail: int = 200):
    if source not in configured_log_sources:
        raise HTTPException(404, "日志来源不存在")
    if not settings.backend_logs_enabled or not docker_log_source.available:
        raise HTTPException(503, "后端日志读取尚未启用或 Docker socket 不可用")
    if not await stream_limiter.acquire():
        raise HTTPException(429, "实时日志连接数已达上限")
    stream = backend_log_stream(
        request, source=source, tail=min(max(tail, 1), settings.log_tail_limit)
    )
    return StreamingResponse(
        limited_stream(stream, stream_limiter),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, no-transform",
            "Pragma": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/api/admin/dashboard")
def dashboard(_: Auth, db: Db):
    counts = {
        "cities": db.scalar(select(func.count()).select_from(City)) or 0,
        "routes": db.scalar(select(func.count()).select_from(Route)) or 0,
        "published_routes": db.scalar(
            select(func.count())
            .select_from(Route)
            .where(Route.content_status == "published", Route.published_at.is_not(None))
        )
        or 0,
        "stops": db.scalar(select(func.count()).select_from(Stop)) or 0,
        "challenges": db.scalar(select(func.count()).select_from(Challenge)) or 0,
        "media": db.scalar(select(func.count()).select_from(MediaAsset)) or 0,
        "journeys": db.scalar(select(func.count()).select_from(Journey)) or 0,
    }
    missing_challenges = (
        db.scalar(
            select(func.count())
            .select_from(Stop)
            .outerjoin(Challenge, Challenge.stop_id == Stop.id)
            .where(Challenge.id.is_(None))
        )
        or 0
    )
    recent_rows = db.execute(
        select(Route, City.name, func.count(Stop.id))
        .join(City, City.id == Route.city_id)
        .outerjoin(Stop, Stop.route_id == Route.id)
        .group_by(Route.id, City.name)
        .order_by(Route.published_at.desc(), Route.title)
        .limit(5)
    ).all()
    return {
        **counts,
        "missing_challenges": missing_challenges,
        "recent_routes": [
            route_dict(route, city_name, stop_count)
            for route, city_name, stop_count in recent_rows
        ],
    }


@app.get("/api/admin/cities")
def list_cities(_: Auth, db: Db, q: str = ""):
    statement = select(City).order_by(City.name)
    if q:
        statement = statement.where(or_(City.name.contains(q), City.slug.contains(q)))
    return [city_dict(item) for item in db.scalars(statement)]


@app.post("/api/admin/cities", status_code=201)
def create_city(payload: CityInput, _: Auth, db: Db):
    item = City(id=str(uuid4()), **payload.model_dump())
    db.add(item)
    commit_or_conflict(db, "城市标识已存在")
    return city_dict(item)


@app.put("/api/admin/cities/{item_id}")
def update_city(item_id: str, payload: CityInput, _: Auth, db: Db):
    item = db.get(City, item_id)
    if not item:
        raise HTTPException(404, "城市不存在")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    commit_or_conflict(db, "城市标识已存在")
    return city_dict(item)


@app.delete("/api/admin/cities/{item_id}", status_code=204)
def delete_city(item_id: str, _: Auth, db: Db):
    item = db.get(City, item_id)
    if not item:
        raise HTTPException(404, "城市不存在")
    if db.scalar(
        select(func.count()).select_from(Route).where(Route.city_id == item_id)
    ):
        raise HTTPException(409, "请先删除或迁移该城市下的路线")
    db.delete(item)
    db.commit()


@app.get("/api/admin/routes")
def list_routes(_: Auth, db: Db, city_id: str | None = None, q: str = ""):
    statement = (
        select(Route, City.name, func.count(Stop.id))
        .join(City, City.id == Route.city_id)
        .outerjoin(Stop, Stop.route_id == Route.id)
        .group_by(Route.id, City.name)
        .order_by(Route.is_featured.desc(), Route.title)
    )
    if city_id:
        statement = statement.where(Route.city_id == city_id)
    if q:
        statement = statement.where(
            or_(Route.title.contains(q), Route.slug.contains(q))
        )
    return [
        route_dict(route, city_name, stop_count)
        for route, city_name, stop_count in db.execute(statement)
    ]


@app.post("/api/admin/routes", status_code=201)
def create_route(payload: RouteInput, _: Auth, db: Db):
    if not db.get(City, payload.city_id):
        raise HTTPException(400, "所选城市不存在")
    values = payload.model_dump()
    values["content_status"] = "draft"
    values["published_at"] = None
    item = Route(id=str(uuid4()), **values)
    db.add(item)
    commit_or_conflict(db, "路线标识已存在")
    return route_dict(item)


@app.put("/api/admin/routes/{item_id}")
def update_route(item_id: str, payload: RouteInput, _: Auth, db: Db):
    item = db.get(Route, item_id)
    if not item:
        raise HTTPException(404, "路线不存在")
    if item.managed_package_id and _published_route_locked(db, item):
        raise HTTPException(409, "published_route_locked")
    values = payload.model_dump()
    values["content_status"] = item.content_status
    values["published_at"] = item.published_at
    for key, value in values.items():
        setattr(item, key, value)
    commit_or_conflict(db, "路线标识或字段与现有内容冲突")
    return route_dict(item)


@app.delete("/api/admin/routes/{item_id}", status_code=204)
def delete_route(item_id: str, _: Auth, db: Db):
    item = db.get(Route, item_id)
    if not item:
        raise HTTPException(404, "路线不存在")
    if db.scalar(
        select(func.count()).select_from(Journey).where(Journey.route_id == item_id)
    ):
        raise HTTPException(409, "该路线已有用户行程记录，不能删除；可改为草稿状态")
    stop_ids = list(db.scalars(select(Stop.id).where(Stop.route_id == item_id)))
    if stop_ids:
        db.execute(delete(Challenge).where(Challenge.stop_id.in_(stop_ids)))
        db.execute(delete(Stop).where(Stop.id.in_(stop_ids)))
    db.delete(item)
    db.commit()


@app.get("/api/admin/stops")
def list_stops(_: Auth, db: Db, route_id: str | None = None, q: str = ""):
    statement = (
        select(Stop, Route.title, Challenge.id)
        .join(Route, Route.id == Stop.route_id)
        .outerjoin(Challenge, Challenge.stop_id == Stop.id)
        .order_by(Route.title, Stop.position)
    )
    if route_id:
        statement = statement.where(Stop.route_id == route_id)
    if q:
        statement = statement.where(
            or_(Stop.title.contains(q), Stop.story_title.contains(q))
        )
    return [
        stop_dict(stop, route_title, bool(challenge_id))
        for stop, route_title, challenge_id in db.execute(statement)
    ]


@app.post("/api/admin/stops", status_code=201)
def create_stop(payload: StopInput, _: Auth, db: Db):
    if not db.get(Route, payload.route_id):
        raise HTTPException(400, "所选路线不存在")
    item = Stop(id=str(uuid4()), **stop_values(payload))
    db.add(item)
    commit_or_conflict(db, "同一路线中的站点序号不能重复")
    return stop_dict(item)


@app.put("/api/admin/stops/{item_id}")
def update_stop(item_id: str, payload: StopInput, _: Auth, db: Db):
    item = db.get(Stop, item_id)
    if not item:
        raise HTTPException(404, "站点不存在")
    for key, value in stop_values(payload).items():
        setattr(item, key, value)
    commit_or_conflict(db, "同一路线中的站点序号不能重复")
    return stop_dict(item)


@app.delete("/api/admin/stops/{item_id}", status_code=204)
def delete_stop(item_id: str, _: Auth, db: Db):
    item = db.get(Stop, item_id)
    if not item:
        raise HTTPException(404, "站点不存在")
    if db.scalar(
        select(func.count())
        .select_from(JourneyAnswer)
        .where(JourneyAnswer.stop_id == item_id)
    ):
        raise HTTPException(409, "该站点已有用户答题记录，不能删除")
    db.execute(delete(Challenge).where(Challenge.stop_id == item_id))
    db.delete(item)
    db.commit()


@app.get("/api/admin/challenges")
def list_challenges(_: Auth, db: Db, route_id: str | None = None):
    statement = (
        select(Challenge, Stop.title, Route.title)
        .join(Stop, Stop.id == Challenge.stop_id)
        .join(Route, Route.id == Stop.route_id)
        .order_by(Route.title, Stop.position)
    )
    if route_id:
        statement = statement.where(Route.id == route_id)
    return [
        challenge_dict(item, stop_title, route_title)
        for item, stop_title, route_title in db.execute(statement)
    ]


@app.post("/api/admin/challenges", status_code=201)
def create_challenge(payload: ChallengeInput, _: Auth, db: Db):
    if payload.correct_option >= len(payload.options):
        raise HTTPException(422, "正确答案序号超出选项范围")
    if not db.get(Stop, payload.stop_id):
        raise HTTPException(400, "所选站点不存在")
    values = payload.model_dump()
    values["options_json"] = values.pop("options")
    item = Challenge(id=str(uuid4()), **values)
    db.add(item)
    commit_or_conflict(db, "每个站点只能配置一道问题")
    return challenge_dict(item)


@app.put("/api/admin/challenges/{item_id}")
def update_challenge(item_id: str, payload: ChallengeInput, _: Auth, db: Db):
    if payload.correct_option >= len(payload.options):
        raise HTTPException(422, "正确答案序号超出选项范围")
    item = db.get(Challenge, item_id)
    if not item:
        raise HTTPException(404, "问题不存在")
    values = payload.model_dump()
    values["options_json"] = values.pop("options")
    for key, value in values.items():
        setattr(item, key, value)
    commit_or_conflict(db, "每个站点只能配置一道问题")
    return challenge_dict(item)


@app.delete("/api/admin/challenges/{item_id}", status_code=204)
def delete_challenge(item_id: str, _: Auth, db: Db):
    item = db.get(Challenge, item_id)
    if not item:
        raise HTTPException(404, "问题不存在")
    db.delete(item)
    db.commit()


@app.get("/api/admin/media")
def list_media(request: Request, _: Auth, db: Db, q: str = ""):
    statement = select(MediaAsset).order_by(MediaAsset.updated_at.desc())
    if q:
        statement = statement.where(
            or_(MediaAsset.key.contains(q), MediaAsset.storage_path.contains(q))
        )
    base = str(request.base_url).rstrip("/")
    return [
        {
            "key": item.key,
            "storage_path": item.storage_path,
            "mime_type": item.mime_type,
            "storage_provider": item.storage_provider,
            "object_key": item.object_key,
            "canonical_url": item.canonical_url,
            "size_bytes": item.size_bytes,
            "checksum_sha256": item.checksum_sha256,
            "created_at": iso(item.created_at),
            "updated_at": iso(item.updated_at),
            "preview_url": item.canonical_url
            or f"{base}/media/{item.object_key or item.storage_path}",
        }
        for item in db.scalars(statement)
    ]


def _safe_identity(value: str) -> str:
    return (
        hashlib.sha256(value.encode("utf-8")).hexdigest()[:12] if value else "missing"
    )


def _media_readiness(db: Session) -> dict[str, Any]:
    local_assets = (
        db.scalar(
            select(func.count())
            .select_from(MediaAsset)
            .where(MediaAsset.storage_provider != "oss")
        )
        or 0
    )
    public_count = (
        db.scalar(
            select(func.count())
            .select_from(MediaAsset)
            .where(MediaAsset.visibility == "public")
        )
        or 0
    )
    private_tracks = db.scalar(select(func.count()).select_from(NarrationPreview)) or 0
    blockers = []
    if (
        public_object_storage.provider != "oss"
        or private_object_storage.provider != "oss"
    ):
        blockers.append("runtime_provider_not_oss")
    if local_assets:
        blockers.append(f"local_media_references:{local_assets}")
    return {
        "ready": not blockers,
        "environment": "shared-production-test-resources",
        "provider": "oss",
        "public_bucket_identity": _safe_identity(settings.oss_public_bucket),
        "private_bucket_identity": _safe_identity(settings.oss_private_bucket),
        "cdn_base": settings.oss_public_base_url.rstrip("/"),
        "public_count": public_count,
        "private_count": private_tracks,
        "canonical_resource_set": "identical-for-production-and-test",
        "private_delivery": "authorized-signed-get",
        "local_blockers": local_assets,
        "blockers": blockers,
        "audit_time": datetime.now(UTC).isoformat(),
    }


@app.get("/api/admin/media/readiness")
def media_readiness(_: Auth, db: Db):
    return _media_readiness(db)


@app.get("/api/admin/media/hierarchy")
def media_hierarchy(_: Auth, db: Db):
    assets = {item.storage_path: item for item in db.scalars(select(MediaAsset))}
    aliases = {
        alias: path
        for path, asset in assets.items()
        for alias in (path, asset.object_key, asset.canonical_url)
        if alias
    }
    groups: dict[str, dict[str, Any]] = {}
    usages: dict[str, list[dict[str, str]]] = {path: [] for path in assets}
    for city in db.scalars(select(City)):
        groups[city.id] = {"id": city.id, "name": city.name, "scenics": []}
        city_asset = aliases.get(city.hero_image)
        if city_asset:
            usages[city_asset].append(
                {"city_id": city.id, "scenic_id": "", "role": "城市封面"}
            )
    for route, city_name in db.execute(
        select(Route, City.name).join(City, City.id == Route.city_id)
    ):
        scenic = {
            "id": route.id,
            "title": route.title,
            "cover": route.hero_image,
            "status": route.content_status,
            "assets": [],
        }
        groups[route.city_id]["scenics"].append(scenic)
        refs: list[tuple[str | None, str]] = [(route.hero_image, "景点封面")]
        refs.extend(
            (stop.image, f"{stop.title} · 图片")
            for stop in db.scalars(select(Stop).where(Stop.route_id == route.id))
        )
        refs.extend(
            (stop.audio_url, f"{stop.title} · 旁白")
            for stop in db.scalars(select(Stop).where(Stop.route_id == route.id))
        )
        refs.extend(
            (track.media_path, "出发前音频")
            for track in db.scalars(
                select(RoutePredepartureTrack).where(
                    RoutePredepartureTrack.route_id == route.id
                )
            )
        )
        seen: set[str] = set()
        for reference, role in refs:
            path = aliases.get(reference or "")
            if not path:
                continue
            usages[path].append(
                {"city_id": route.city_id, "scenic_id": route.id, "role": role}
            )
            if path not in seen:
                scenic["assets"].append(path)
                seen.add(path)
    serialized = {
        path: {
            "key": asset.key,
            "object_key": asset.object_key or path,
            "mime_type": asset.mime_type,
            "size_bytes": asset.size_bytes,
            "checksum_sha256": asset.checksum_sha256,
            "scope": asset.visibility,
            "delivery": asset.canonical_url
            if asset.visibility == "public"
            else "protected-signed-get",
            "reference_count": len(usages[path]),
            "usages": usages[path],
        }
        for path, asset in assets.items()
    }
    return {
        "cities": list(groups.values()),
        "assets": serialized,
        "unassigned": [path for path, refs in usages.items() if not refs],
        "readiness": _media_readiness(db),
    }


@app.post("/api/admin/media", status_code=201)
def upload_media(
    _: Auth,
    db: Db,
    file: Annotated[UploadFile, File()],
    key: Annotated[str, Form()] = "",
):
    if not file.filename or not file.content_type:
        raise HTTPException(400, "请选择有效文件")
    allowed_prefixes = ("image/", "audio/")
    if not file.content_type.startswith(allowed_prefixes):
        raise HTTPException(415, "仅支持图片和音频文件")
    payload = file.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(payload) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"文件不能超过 {settings.max_upload_mb}MB")
    safe_name = (
        re.sub(r"[^a-zA-Z0-9._-]", "-", Path(file.filename).name).strip(".-") or "asset"
    )
    asset_key = (
        re.sub(r"[^a-zA-Z0-9_-]", "-", key.strip()).strip("-") or Path(safe_name).stem
    )
    checksum = hashlib.sha256(payload).hexdigest()
    existing = db.get(MediaAsset, asset_key)
    if existing:
        if existing.checksum_sha256 == checksum:
            return {
                "key": existing.key,
                "storage_path": existing.storage_path,
                "mime_type": existing.mime_type,
                "idempotent": True,
            }
        raise HTTPException(
            409, "资源标识已存在；请更换标识，避免已发布内容引用被静默替换"
        )
    now = datetime.now(UTC)
    suffix = Path(safe_name).suffix.lower()
    object_key = f"public/content/{now:%Y/%m}/{checksum}{suffix}"
    uploaded_now = False
    if not public_object_storage.exists(object_key):
        stored = public_object_storage.put(object_key, payload, file.content_type)
        uploaded_now = True
    else:
        canonical = public_object_storage.public_url(object_key)
        stored = StoredObject(public_object_storage.provider, object_key, canonical)
    storage_path = object_key
    item = MediaAsset(
        key=asset_key,
        storage_path=storage_path,
        mime_type=file.content_type,
        storage_provider=stored.provider,
        object_key=stored.object_key,
        canonical_url=stored.canonical_url if stored.provider == "oss" else None,
        visibility="public",
        size_bytes=len(payload),
        checksum_sha256=checksum,
        metadata_json={"original_filename": safe_name},
        created_at=now,
        updated_at=now,
    )
    db.add(item)
    try:
        commit_or_conflict(db, "资源标识或存储路径冲突")
    except Exception:
        if uploaded_now:
            public_object_storage.delete(object_key)
        raise
    return {
        "key": item.key,
        "storage_path": item.storage_path,
        "mime_type": item.mime_type,
        "storage_provider": item.storage_provider,
        "canonical_url": item.canonical_url,
    }


@app.delete("/api/admin/media/{asset_key}", status_code=204)
def delete_media(asset_key: str, _: Auth, db: Db):
    item = db.get(MediaAsset, asset_key)
    if not item:
        raise HTTPException(404, "媒体资源不存在")
    references = (
        (
            db.scalar(
                select(func.count())
                .select_from(City)
                .where(City.hero_image == item.storage_path)
            )
            or 0
        )
        + (
            db.scalar(
                select(func.count())
                .select_from(Route)
                .where(Route.hero_image == item.storage_path)
            )
            or 0
        )
        + (
            db.scalar(
                select(func.count())
                .select_from(Stop)
                .where(
                    or_(
                        Stop.image == item.storage_path,
                        Stop.audio_url == item.storage_path,
                    )
                )
            )
            or 0
        )
        + (
            db.scalar(
                select(func.count())
                .select_from(StoryFragment)
                .where(StoryFragment.audio_path == item.storage_path)
            )
            or 0
        )
        + (
            db.scalar(
                select(func.count())
                .select_from(HomeStoryPublication)
                .where(HomeStoryPublication.cover_image == item.storage_path)
            )
            or 0
        )
        + (
            db.scalar(
                select(func.count())
                .select_from(StoryNarrationTrack)
                .where(StoryNarrationTrack.media_path == item.storage_path)
            )
            or 0
        )
    )
    if references:
        raise HTTPException(409, f"该资源正在被 {references} 处内容使用，不能删除")
    shared_object = (
        db.scalar(
            select(func.count())
            .select_from(MediaAsset)
            .where(
                MediaAsset.object_key == item.object_key,
                MediaAsset.key != item.key,
            )
        )
        or 0
    )
    if item.object_key and not shared_object:
        public_object_storage.delete(item.object_key)
    db.delete(item)
    db.commit()


@app.get("/media/{asset_path:path}")
def serve_media(asset_path: str):
    return RedirectResponse(
        public_object_storage.public_url(asset_path), status_code=308
    )


def narration_preview_dict(item: NarrationPreview) -> dict[str, Any]:
    return {
        "id": item.id,
        "fragment_id": item.fragment_id,
        "profile_id": item.profile_id,
        "transcript_hash": item.transcript_hash,
        "provider": item.provider,
        "model": item.model,
        "voice_id": item.voice_id,
        "emotion": item.emotion,
        "speed": item.speed,
        "pitch": item.pitch,
        "pronunciation": item.pronunciation_json,
        "status": item.status,
        "error_code": item.error_code,
        "metadata": item.metadata_json,
        "created_at": iso(item.created_at),
        "expires_at": iso(item.expires_at),
        "approved_at": iso(item.approved_at),
        "playback_path": f"/narration/previews/{item.id}/audio"
        if item.status in {"ready", "approved"}
        else None,
    }


def narration_default_variants() -> list[dict[str, Any]]:
    return [
        {"label": "沉静纪实", "emotion": "neutral", "speed": 0.92, "pitch": -1},
        {"label": "温和导览", "emotion": "neutral", "speed": 1.0, "pitch": 0},
        {"label": "故事张力", "emotion": "happy", "speed": 0.96, "pitch": 1},
    ]


DEFAULT_NARRATION_PROFILE_ID = "default-narration-voice"
SHENZHEN_WARM_PROFILE_ID = "shenzhen-warm-female-voice"


def narration_profile_dict(item: NarrationVoiceProfile) -> dict[str, Any]:
    return {
        "id": item.id,
        "slug": item.slug,
        "display_name": item.display_name,
        "description": item.description,
        "provider": item.provider,
        "model": item.model,
        "voice_id": item.voice_id,
        "emotion": item.emotion,
        "speed": item.speed,
        "pitch": item.pitch,
        "preview_media_path": item.preview_media_path,
        "display_order": item.display_order,
        "status": item.status,
        "is_default": item.is_default,
        "published_at": iso(item.published_at),
        "updated_at": iso(item.updated_at),
    }


def ensure_default_narration_profile(db: Session) -> NarrationVoiceProfile:
    profile = db.get(NarrationVoiceProfile, DEFAULT_NARRATION_PROFILE_ID)
    now = datetime.now(UTC)
    if profile is None:
        profile = NarrationVoiceProfile(
            id=DEFAULT_NARRATION_PROFILE_ID,
            slug="default",
            display_name="原声导览",
            description="路线编辑审核通过的默认旁白",
            provider="legacy",
            model="approved-audio",
            voice_id=settings.minimax_voice_id,
            emotion="neutral",
            speed=1.0,
            pitch=0,
            display_order=0,
            status="published",
            is_default=True,
            created_at=now,
            updated_at=now,
            published_at=now,
        )
        db.add(profile)
        db.flush()
    fragments = list(db.scalars(select(StoryFragment)))
    for fragment in fragments:
        transcript_hash = hashlib.sha256(
            fragment.narration_script.strip().encode()
        ).hexdigest()
        track = db.scalar(
            select(FragmentNarrationTrack).where(
                FragmentNarrationTrack.fragment_id == fragment.id,
                FragmentNarrationTrack.profile_id == profile.id,
                FragmentNarrationTrack.transcript_hash == transcript_hash,
                FragmentNarrationTrack.script_version == fragment.script_version,
            )
        )
        if track is None and fragment.audio_path:
            db.add(
                FragmentNarrationTrack(
                    id=str(uuid4()),
                    fragment_id=fragment.id,
                    profile_id=profile.id,
                    transcript_hash=transcript_hash,
                    script_version=fragment.script_version,
                    media_path=fragment.audio_path,
                    mime_type=fragment.audio_mime_type,
                    size_bytes=fragment.audio_size_bytes,
                    generation_metadata_json={"backfilled": True},
                    approved_at=now,
                    published_at=now,
                )
            )
    db.flush()
    return profile


def ensure_shenzhen_warm_profile(db: Session) -> NarrationVoiceProfile:
    profile = db.get(NarrationVoiceProfile, SHENZHEN_WARM_PROFILE_ID)
    if profile is not None:
        return profile
    now = datetime.now(UTC)
    profile = NarrationVoiceProfile(
        id=SHENZHEN_WARM_PROFILE_ID,
        slug="shenzhen-warm-companion",
        display_name="温柔同行者",
        description="亲切、轻盈，像熟悉深圳的朋友陪你边走边聊",
        provider=narration_synthesizer.provider,
        model=narration_synthesizer.model,
        voice_id="Chinese (Mandarin)_Warm_HeartedGirl",
        emotion="calm",
        speed=0.94,
        pitch=0,
        display_order=10,
        status="draft",
        is_default=False,
        created_at=now,
        updated_at=now,
    )
    db.add(profile)
    db.flush()
    return profile


def narration_profile_coverage(
    db: Session, route_id: str, profile_id: str
) -> dict[str, Any]:
    route = db.get(Route, route_id)
    profile = db.get(NarrationVoiceProfile, profile_id)
    if route is None or profile is None:
        raise HTTPException(404, "路线或音色不存在")
    arc = db.scalar(select(StoryArc).where(StoryArc.route_id == route_id))
    fragments = (
        list(
            db.scalars(
                select(StoryFragment)
                .where(StoryFragment.arc_id == arc.id)
                .order_by(StoryFragment.position)
            )
        )
        if arc
        else []
    )
    rows = (
        list(
            db.scalars(
                select(FragmentNarrationTrack).where(
                    FragmentNarrationTrack.profile_id == profile_id,
                    FragmentNarrationTrack.fragment_id.in_(
                        [item.id for item in fragments]
                    ),
                )
            )
        )
        if fragments
        else []
    )
    by_fragment: dict[str, list[FragmentNarrationTrack]] = {}
    for row in rows:
        by_fragment.setdefault(row.fragment_id, []).append(row)
    missing: list[dict[str, str]] = []
    stale: list[dict[str, str]] = []
    complete: list[str] = []
    for fragment in fragments:
        expected_hash = hashlib.sha256(
            fragment.narration_script.strip().encode()
        ).hexdigest()
        current = next(
            (
                row
                for row in by_fragment.get(fragment.id, [])
                if row.transcript_hash == expected_hash
                and row.script_version == fragment.script_version
            ),
            None,
        )
        if current is not None:
            complete.append(fragment.id)
        elif by_fragment.get(fragment.id):
            stale.append({"id": fragment.id, "title": fragment.title})
        else:
            missing.append({"id": fragment.id, "title": fragment.title})
    return {
        "route_id": route_id,
        "profile_id": profile_id,
        "total": len(fragments),
        "complete_count": len(complete),
        "complete_fragment_ids": complete,
        "missing": missing,
        "stale": stale,
        "ready": bool(fragments) and not missing and not stale,
    }


def persist_formal_narration_track(
    db: Session,
    *,
    fragment: StoryFragment,
    profile: NarrationVoiceProfile,
    audio: bytes,
    provider: str,
    model: str,
    voice_id: str,
    emotion: str,
    speed: float,
    pitch: int,
    source_preview_id: str | None = None,
) -> tuple[FragmentNarrationTrack, MediaAsset, str, bool]:
    """Promote generated bytes through the single immutable formal-track path."""
    transcript_hash = hashlib.sha256(
        fragment.narration_script.strip().encode()
    ).hexdigest()
    audio_hash = hashlib.sha256(audio).hexdigest()
    version = re.sub(r"[^a-zA-Z0-9._-]", "-", fragment.script_version) or "v1"
    settings_hash = hashlib.sha256(
        f"{voice_id}|{emotion}|{speed}|{pitch}".encode()
    ).hexdigest()[:12]
    profile_slug = re.sub(r"[^a-z0-9-]", "-", profile.slug.lower()) or "voice"
    object_key = (
        f"public/narration/{fragment.id}/{profile_slug}/"
        f"{transcript_hash[:16]}-{version}-{settings_hash}-{audio_hash[:12]}.mp3"
    )
    uploaded = False
    if not public_object_storage.exists(object_key):
        public_object_storage.put(object_key, audio, "audio/mpeg")
        uploaded = True
    try:
        canonical_url = public_object_storage.public_url(object_key)
        asset = db.scalar(select(MediaAsset).where(MediaAsset.object_key == object_key))
        now = datetime.now(UTC)
        metadata = {
            "narration": {
                "preview_id": source_preview_id,
                "provider": provider,
                "model": model,
                "voice_id": voice_id,
                "emotion": emotion,
                "speed": speed,
                "pitch": pitch,
                "transcript_hash": transcript_hash,
            }
        }
        if asset is None:
            asset = MediaAsset(
                key=(
                    f"narration-{fragment.id[:24]}-{profile.slug[:18]}-"
                    f"{transcript_hash[:10]}-{audio_hash[:12]}"
                ),
                storage_path=object_key,
                mime_type="audio/mpeg",
                storage_provider=public_object_storage.provider,
                object_key=object_key,
                canonical_url=canonical_url
                if public_object_storage.provider == "oss"
                else None,
                visibility="public",
                size_bytes=len(audio),
                checksum_sha256=audio_hash,
                metadata_json=metadata,
                created_at=now,
                updated_at=now,
            )
            db.add(asset)
        track = db.scalar(
            select(FragmentNarrationTrack).where(
                FragmentNarrationTrack.fragment_id == fragment.id,
                FragmentNarrationTrack.profile_id == profile.id,
                FragmentNarrationTrack.transcript_hash == transcript_hash,
                FragmentNarrationTrack.script_version == fragment.script_version,
            )
        )
        if track is None:
            track = FragmentNarrationTrack(
                id=str(uuid4()),
                fragment_id=fragment.id,
                profile_id=profile.id,
                transcript_hash=transcript_hash,
                script_version=fragment.script_version,
                media_path=object_key,
                mime_type="audio/mpeg",
                size_bytes=len(audio),
                checksum_sha256=audio_hash,
                generation_metadata_json={},
                approved_at=now,
                published_at=now if profile.status == "published" else None,
            )
            db.add(track)
        track.media_path = object_key
        track.mime_type = "audio/mpeg"
        track.size_bytes = len(audio)
        track.checksum_sha256 = audio_hash
        track.generation_metadata_json = metadata["narration"]
        track.approved_at = now
        track.published_at = now if profile.status == "published" else None
        if profile.preview_media_path is None:
            profile.preview_media_path = object_key
        if profile.is_default:
            fragment.audio_path = object_key
            fragment.audio_mime_type = "audio/mpeg"
            fragment.audio_size_bytes = len(audio)
        return track, asset, object_key, uploaded
    except Exception:
        if uploaded:
            try:
                public_object_storage.delete(object_key)
            except Exception:
                logger.exception(
                    "Failed to clean orphaned narration object %s", object_key
                )
        raise


def story_transcript_hash(arc: StoryArc) -> str:
    return hashlib.sha256(arc.complete_story.strip().encode()).hexdigest()


def home_story_defaults(arc: StoryArc, route: Route | None) -> tuple[str, str]:
    introduction = (
        str(route.subtitle or "").strip() if route is not None else ""
    ) or f"戴上耳机，听听「{arc.title}」的完整故事。"
    cover_image = str(route.hero_image or "").strip() if route is not None else ""
    return introduction, cover_image


def home_story_dict(db: Session, arc: StoryArc) -> dict[str, Any]:
    route = db.get(Route, arc.route_id)
    city = db.get(City, route.city_id) if route else None
    default_introduction, default_cover_image = home_story_defaults(arc, route)
    publication = db.scalar(
        select(HomeStoryPublication).where(HomeStoryPublication.arc_id == arc.id)
    )
    tracks = list(
        db.scalars(
            select(StoryNarrationTrack)
            .where(StoryNarrationTrack.arc_id == arc.id)
            .order_by(StoryNarrationTrack.updated_at.desc())
        )
    )
    expected_hash = story_transcript_hash(arc)
    track_payloads: list[dict[str, Any]] = []
    for track in tracks:
        profile = db.get(NarrationVoiceProfile, track.profile_id)
        track_payloads.append(
            {
                "id": track.id,
                "profile_id": track.profile_id,
                "profile_name": profile.display_name if profile else "未知音色",
                "transcript_hash": track.transcript_hash,
                "script_version": track.script_version,
                "status": track.status,
                "duration_ms": track.duration_ms,
                "size_bytes": track.size_bytes,
                "is_current": (
                    track.transcript_hash == expected_hash
                    and track.script_version == arc.script_version
                ),
                "playback_path": f"/home-stories/tracks/{track.id}/audio",
                "reviewed_at": iso(track.reviewed_at),
                "published_at": iso(track.published_at),
                "updated_at": iso(track.updated_at),
            }
        )
    selected = next(
        (
            item
            for item in track_payloads
            if publication and item["id"] == publication.selected_track_id
        ),
        None,
    )
    blockers: list[str] = []
    if not arc.complete_story.strip():
        blockers.append("完整故事正文为空")
    if not publication:
        blockers.append("尚未创建首页故事卡片")
    else:
        if not publication.title.strip():
            blockers.append("标题为空")
        if not (publication.introduction.strip() or default_introduction):
            blockers.append("简介为空")
        if not (publication.cover_image.strip() or default_cover_image):
            blockers.append("封面为空")
        if publication.selection_weight <= 0:
            blockers.append("随机权重必须大于 0")
        if selected is None:
            blockers.append("尚未选择完整故事音频")
        elif not selected["is_current"]:
            blockers.append("已选音频与当前正文不一致，请重新生成")
        elif selected["status"] not in {"approved", "published"}:
            blockers.append("已选音频尚未审核通过")
    if route is None or route.content_status != "published":
        blockers.append("所属路线尚未发布")
    return {
        "arc_id": arc.id,
        "arc_title": arc.title,
        "route_id": route.id if route else None,
        "route_title": route.title if route else "路线已删除",
        "route_status": route.content_status if route else "missing",
        "city_id": city.id if city else None,
        "city_name": city.name if city else "未知城市",
        "transcript": arc.complete_story,
        "transcript_hash": expected_hash,
        "script_version": arc.script_version,
        "pronunciation_notes": arc.pronunciation_notes_json,
        "publication": (
            {
                "id": publication.id,
                "title": publication.title,
                "introduction": publication.introduction.strip()
                or default_introduction,
                "cover_image": publication.cover_image.strip() or default_cover_image,
                "selection_weight": publication.selection_weight,
                "status": publication.status,
                "selected_track_id": publication.selected_track_id,
                "reviewed_at": iso(publication.reviewed_at),
                "published_at": iso(publication.published_at),
                "updated_at": iso(publication.updated_at),
            }
            if publication
            else None
        ),
        "tracks": track_payloads,
        "blockers": blockers,
        "ready_to_publish": not blockers,
    }


def require_story_arc(db: Session, arc_id: str) -> StoryArc:
    arc = db.get(StoryArc, arc_id)
    if arc is None:
        raise HTTPException(404, "完整故事不存在")
    return arc


@app.get("/api/admin/home-stories")
def list_home_stories(_: Auth, db: Db):
    arcs = list(db.scalars(select(StoryArc).order_by(StoryArc.title)))
    return [home_story_dict(db, arc) for arc in arcs]


@app.put("/api/admin/home-stories/{arc_id}")
def save_home_story(arc_id: str, payload: dict[str, Any], _: Auth, db: Db):
    arc = require_story_arc(db, arc_id)
    route = db.get(Route, arc.route_id)
    default_introduction, default_cover_image = home_story_defaults(arc, route)
    item = db.scalar(
        select(HomeStoryPublication).where(HomeStoryPublication.arc_id == arc.id)
    )
    now = datetime.now(UTC)
    if item is None:
        item = HomeStoryPublication(
            id=str(uuid4()),
            arc_id=arc.id,
            title=arc.title,
            introduction=default_introduction,
            cover_image=default_cover_image,
            selection_weight=1,
            status="draft",
            created_at=now,
            updated_at=now,
        )
        db.add(item)
    if item.status == "published":
        raise HTTPException(409, "已发布故事请先撤回，再修改")
    title = str(payload.get("title", item.title)).strip()
    introduction = (
        str(payload.get("introduction", item.introduction)).strip()
        or default_introduction
    )
    cover_image = (
        str(payload.get("cover_image", item.cover_image)).strip() or default_cover_image
    )
    try:
        selection_weight = int(payload.get("selection_weight", item.selection_weight))
    except (TypeError, ValueError) as error:
        raise HTTPException(422, "随机权重必须是整数") from error
    if len(title) > 255 or len(introduction) > 2000 or len(cover_image) > 500:
        raise HTTPException(422, "标题、简介或封面地址过长")
    if selection_weight < 0 or selection_weight > 100:
        raise HTTPException(422, "随机权重须在 0 到 100 之间")
    selected_track_id = payload.get("selected_track_id", item.selected_track_id)
    if selected_track_id:
        selected_track = db.get(StoryNarrationTrack, str(selected_track_id))
        if selected_track is None or selected_track.arc_id != arc.id:
            raise HTTPException(422, "所选音频不属于当前完整故事")
        item.selected_track_id = selected_track.id
    else:
        item.selected_track_id = None
    item.title = title
    item.introduction = introduction
    item.cover_image = cover_image
    item.selection_weight = selection_weight
    item.updated_at = now
    db.commit()
    return home_story_dict(db, arc)


@app.post("/api/admin/home-stories/{arc_id}/generate", status_code=201)
def generate_home_story_track(arc_id: str, payload: dict[str, Any], _: Auth, db: Db):
    arc = require_story_arc(db, arc_id)
    transcript = arc.complete_story.strip()
    if not transcript:
        raise HTTPException(422, "完整故事正文为空")
    ensure_default_narration_profile(db)
    profile_id = str(payload.get("profile_id") or DEFAULT_NARRATION_PROFILE_ID)
    profile = db.get(NarrationVoiceProfile, profile_id)
    if profile is None or profile.status == "archived":
        raise HTTPException(404, "音色档案不存在")
    if (
        settings.narration_provider == "minimax"
        and not settings.minimax_api_key.strip()
    ):
        raise HTTPException(503, "尚未配置 MiniMax 语音凭证")
    try:
        result = narration_synthesizer.synthesize(
            NarrationRequest(
                transcript,
                profile.voice_id,
                profile.emotion,
                profile.speed,
                profile.pitch,
                tuple(arc.pronunciation_notes_json or []),
            )
        )
    except NarrationSynthesisError as error:
        raise HTTPException(503, {"code": error.code, "message": str(error)}) from error
    transcript_hash = story_transcript_hash(arc)
    audio_hash = hashlib.sha256(result.payload).hexdigest()
    profile_slug = re.sub(r"[^a-z0-9-]", "-", profile.slug.lower()) or "voice"
    version = re.sub(r"[^a-zA-Z0-9._-]", "-", arc.script_version) or "v1"
    object_key = (
        f"public/home-stories/{arc.id}/{profile_slug}/"
        f"{transcript_hash[:16]}-{version}-{audio_hash[:12]}.mp3"
    )
    uploaded = False
    if not public_object_storage.exists(object_key):
        public_object_storage.put(object_key, result.payload, result.mime_type)
        uploaded = True
    now = datetime.now(UTC)
    try:
        asset = db.scalar(select(MediaAsset).where(MediaAsset.object_key == object_key))
        if asset is None:
            asset = MediaAsset(
                key=f"home-story-{arc.id[:20]}-{audio_hash[:12]}",
                storage_path=object_key,
                mime_type=result.mime_type,
                storage_provider=public_object_storage.provider,
                object_key=object_key,
                canonical_url=(
                    public_object_storage.public_url(object_key)
                    if public_object_storage.provider == "oss"
                    else None
                ),
                visibility="public",
                size_bytes=len(result.payload),
                checksum_sha256=audio_hash,
                metadata_json={"kind": "home_story", "arc_id": arc.id},
                created_at=now,
                updated_at=now,
            )
            db.add(asset)
        track = db.scalar(
            select(StoryNarrationTrack).where(
                StoryNarrationTrack.arc_id == arc.id,
                StoryNarrationTrack.profile_id == profile.id,
                StoryNarrationTrack.transcript_hash == transcript_hash,
                StoryNarrationTrack.script_version == arc.script_version,
            )
        )
        if track is None:
            track = StoryNarrationTrack(
                id=str(uuid4()),
                arc_id=arc.id,
                profile_id=profile.id,
                transcript_hash=transcript_hash,
                script_version=arc.script_version,
                media_path=object_key,
                mime_type=result.mime_type,
                size_bytes=len(result.payload),
                duration_ms=max(1000, len(transcript) * 230),
                checksum_sha256=audio_hash,
                generation_metadata_json={},
                status="in_review",
                created_at=now,
                updated_at=now,
            )
            db.add(track)
        track.media_path = object_key
        track.mime_type = result.mime_type
        track.size_bytes = len(result.payload)
        track.duration_ms = max(1000, len(transcript) * 230)
        track.checksum_sha256 = audio_hash
        track.generation_metadata_json = {
            "provider": result.provider,
            "model": result.model,
            "voice_id": profile.voice_id,
            "emotion": profile.emotion,
            "speed": profile.speed,
            "pitch": profile.pitch,
            "request_id": result.request_id,
        }
        track.status = "in_review"
        track.reviewed_by = None
        track.reviewed_at = None
        track.published_at = None
        track.updated_at = now
        publication = db.scalar(
            select(HomeStoryPublication).where(HomeStoryPublication.arc_id == arc.id)
        )
        if publication is None:
            default_introduction, default_cover_image = home_story_defaults(
                arc, db.get(Route, arc.route_id)
            )
            publication = HomeStoryPublication(
                id=str(uuid4()),
                arc_id=arc.id,
                title=arc.title,
                introduction=default_introduction,
                cover_image=default_cover_image,
                selection_weight=1,
                status="draft",
                created_at=now,
                updated_at=now,
            )
            db.add(publication)
        publication.selected_track_id = track.id
        publication.updated_at = now
        db.commit()
    except Exception:
        db.rollback()
        if uploaded:
            public_object_storage.delete(object_key)
        raise
    return home_story_dict(db, arc)


@app.post("/api/admin/home-stories/{arc_id}/upload", status_code=201)
def upload_home_story_track(
    arc_id: str,
    _: Auth,
    db: Db,
    profile_id: Annotated[str, Form()],
    duration_ms: Annotated[int, Form()],
    file: Annotated[UploadFile, File()],
):
    arc = require_story_arc(db, arc_id)
    profile = db.get(NarrationVoiceProfile, profile_id)
    if profile is None or profile.status == "archived":
        raise HTTPException(404, "音色档案不存在")
    mime_type = (file.content_type or "").lower()
    extensions = {
        "audio/mpeg": "mp3",
        "audio/mp4": "m4a",
        "audio/x-m4a": "m4a",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
    }
    if mime_type not in extensions:
        raise HTTPException(422, "仅支持 MP3、M4A 或 WAV 完整故事音频")
    if duration_ms <= 0 or duration_ms > 24 * 60 * 60 * 1000:
        raise HTTPException(422, "请填写有效的音频时长（毫秒）")
    payload = file.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if not payload:
        raise HTTPException(422, "音频文件为空")
    if len(payload) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"音频不能超过 {settings.max_upload_mb} MB")
    transcript_hash = story_transcript_hash(arc)
    checksum = hashlib.sha256(payload).hexdigest()
    version = re.sub(r"[^a-zA-Z0-9._-]", "-", arc.script_version) or "v1"
    object_key = (
        f"public/home-stories/{arc.id}/manual/"
        f"{transcript_hash[:16]}-{version}-{checksum[:12]}.{extensions[mime_type]}"
    )
    uploaded = False
    if not public_object_storage.exists(object_key):
        public_object_storage.put(object_key, payload, mime_type)
        uploaded = True
    now = datetime.now(UTC)
    try:
        asset = db.scalar(select(MediaAsset).where(MediaAsset.object_key == object_key))
        if asset is None:
            db.add(
                MediaAsset(
                    key=f"home-story-manual-{arc.id[:16]}-{checksum[:12]}",
                    storage_path=object_key,
                    mime_type=mime_type,
                    storage_provider=public_object_storage.provider,
                    object_key=object_key,
                    canonical_url=(
                        public_object_storage.public_url(object_key)
                        if public_object_storage.provider == "oss"
                        else None
                    ),
                    visibility="public",
                    size_bytes=len(payload),
                    checksum_sha256=checksum,
                    metadata_json={
                        "kind": "home_story",
                        "arc_id": arc.id,
                        "source": "manual",
                    },
                    created_at=now,
                    updated_at=now,
                )
            )
        track = db.scalar(
            select(StoryNarrationTrack).where(
                StoryNarrationTrack.arc_id == arc.id,
                StoryNarrationTrack.profile_id == profile.id,
                StoryNarrationTrack.transcript_hash == transcript_hash,
                StoryNarrationTrack.script_version == arc.script_version,
            )
        )
        if track is None:
            track = StoryNarrationTrack(
                id=str(uuid4()),
                arc_id=arc.id,
                profile_id=profile.id,
                transcript_hash=transcript_hash,
                script_version=arc.script_version,
                media_path=object_key,
                mime_type=mime_type,
                size_bytes=len(payload),
                duration_ms=duration_ms,
                status="in_review",
                created_at=now,
                updated_at=now,
            )
            db.add(track)
        track.media_path = object_key
        track.mime_type = mime_type
        track.size_bytes = len(payload)
        track.duration_ms = duration_ms
        track.checksum_sha256 = checksum
        track.generation_metadata_json = {
            "source": "manual_upload",
            "filename": file.filename,
        }
        track.status = "in_review"
        track.reviewed_by = None
        track.reviewed_at = None
        track.published_at = None
        track.updated_at = now
        publication = db.scalar(
            select(HomeStoryPublication).where(HomeStoryPublication.arc_id == arc.id)
        )
        if publication is None:
            default_introduction, default_cover_image = home_story_defaults(
                arc, db.get(Route, arc.route_id)
            )
            publication = HomeStoryPublication(
                id=str(uuid4()),
                arc_id=arc.id,
                title=arc.title,
                introduction=default_introduction,
                cover_image=default_cover_image,
                selection_weight=1,
                status="draft",
                created_at=now,
                updated_at=now,
            )
            db.add(publication)
        publication.selected_track_id = track.id
        publication.updated_at = now
        db.commit()
    except Exception:
        db.rollback()
        if uploaded:
            public_object_storage.delete(object_key)
        raise
    return home_story_dict(db, arc)


@app.get("/api/admin/home-stories/tracks/{track_id}/audio")
def stream_home_story_track(track_id: str, _: Auth, db: Db):
    track = db.get(StoryNarrationTrack, track_id)
    if track is None:
        raise HTTPException(404, "完整故事音频不存在")
    try:
        stream = public_object_storage.open(track.media_path)
    except FileNotFoundError as error:
        raise HTTPException(404, "音频文件不存在") from error

    def chunks():
        with stream:
            while payload := stream.read(64 * 1024):
                yield payload

    return StreamingResponse(chunks(), media_type=track.mime_type)


@app.post("/api/admin/home-stories/{arc_id}/{action}")
def transition_home_story(arc_id: str, action: str, _: Auth, db: Db):
    arc = require_story_arc(db, arc_id)
    item = db.scalar(
        select(HomeStoryPublication).where(HomeStoryPublication.arc_id == arc.id)
    )
    if item is None:
        raise HTTPException(409, "请先保存首页故事卡片")
    track = (
        db.get(StoryNarrationTrack, item.selected_track_id)
        if item.selected_track_id
        else None
    )
    now = datetime.now(UTC)
    if action == "submit-review":
        if item.status not in {"draft", "withdrawn"}:
            raise HTTPException(409, "当前状态不能提交审核")
        route = db.get(Route, arc.route_id)
        default_introduction, default_cover_image = home_story_defaults(arc, route)
        item.introduction = item.introduction.strip() or default_introduction
        item.cover_image = item.cover_image.strip() or default_cover_image
        if not item.title.strip():
            raise HTTPException(422, "请先补齐标题")
        item.status = "in_review"
    elif action == "approve":
        if item.status != "in_review":
            raise HTTPException(409, "请先提交审核")
        if track is None or track.arc_id != arc.id:
            raise HTTPException(422, "请先选择完整故事音频")
        if (
            track.transcript_hash != story_transcript_hash(arc)
            or track.script_version != arc.script_version
        ):
            raise HTTPException(409, "音频已过期，请按当前正文重新生成")
        item.status = "approved"
        item.reviewed_by = "admin"
        item.reviewed_at = now
        track.status = "approved"
        track.reviewed_by = "admin"
        track.reviewed_at = now
        track.updated_at = now
    elif action == "publish":
        if item.status != "approved":
            raise HTTPException(409, "故事尚未审核通过")
        route = db.get(Route, arc.route_id)
        if route is None or route.content_status != "published":
            raise HTTPException(409, "所属路线尚未发布")
        if track is None or track.status != "approved":
            raise HTTPException(409, "完整故事音频尚未审核通过")
        if (
            track.transcript_hash != story_transcript_hash(arc)
            or track.script_version != arc.script_version
        ):
            raise HTTPException(409, "音频已过期，请按当前正文重新生成")
        if item.selection_weight <= 0:
            raise HTTPException(422, "随机权重必须大于 0")
        item.status = "published"
        item.published_at = now
        track.status = "published"
        track.published_at = now
        track.updated_at = now
    elif action == "withdraw":
        if item.status != "published":
            raise HTTPException(409, "只有已发布故事可以撤回")
        item.status = "withdrawn"
        item.published_at = None
        if track and track.status == "published":
            track.status = "approved"
            track.published_at = None
            track.updated_at = now
    elif action == "archive":
        if item.status == "published":
            raise HTTPException(409, "请先撤回已发布故事")
        item.status = "archived"
        item.published_at = None
    else:
        raise HTTPException(404, "未知故事流转操作")
    item.updated_at = now
    db.commit()
    return home_story_dict(db, arc)


@app.get("/api/admin/narration/profiles")
def list_narration_profiles(_: Auth, db: Db):
    ensure_default_narration_profile(db)
    ensure_shenzhen_warm_profile(db)
    db.commit()
    rows = list(
        db.scalars(
            select(NarrationVoiceProfile).order_by(
                NarrationVoiceProfile.display_order,
                NarrationVoiceProfile.display_name,
            )
        )
    )
    return [narration_profile_dict(item) for item in rows]


@app.post("/api/admin/narration/profiles", status_code=201)
def create_narration_profile(payload: dict[str, Any], _: Auth, db: Db):
    slug = str(payload.get("slug") or "").strip().lower()
    name = str(payload.get("display_name") or "").strip()
    voice_id = str(payload.get("voice_id") or "").strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,78}", slug) or not name or not voice_id:
        raise HTTPException(422, "slug、显示名称和 Voice ID 格式不正确")
    if db.scalar(
        select(NarrationVoiceProfile).where(NarrationVoiceProfile.slug == slug)
    ):
        raise HTTPException(409, "音色 slug 已存在")
    now = datetime.now(UTC)
    item = NarrationVoiceProfile(
        id=str(uuid4()),
        slug=slug,
        display_name=name,
        description=str(payload.get("description") or "").strip(),
        provider=str(payload.get("provider") or narration_synthesizer.provider),
        model=str(payload.get("model") or narration_synthesizer.model),
        voice_id=voice_id,
        emotion=str(payload.get("emotion") or "neutral"),
        speed=min(max(float(payload.get("speed", 1.0)), 0.5), 2.0),
        pitch=min(max(int(payload.get("pitch", 0)), -12), 12),
        display_order=int(payload.get("display_order", 10)),
        status="draft",
        is_default=False,
        created_at=now,
        updated_at=now,
    )
    db.add(item)
    db.commit()
    return narration_profile_dict(item)


@app.put("/api/admin/narration/profiles/{profile_id}")
def update_narration_profile(profile_id: str, payload: dict[str, Any], _: Auth, db: Db):
    item = db.get(NarrationVoiceProfile, profile_id)
    if item is None:
        raise HTTPException(404, "音色不存在")
    for key in (
        "display_name",
        "description",
        "provider",
        "model",
        "voice_id",
        "emotion",
    ):
        if key in payload:
            setattr(item, key, str(payload[key]).strip())
    if "speed" in payload:
        item.speed = min(max(float(payload["speed"]), 0.5), 2.0)
    if "pitch" in payload:
        item.pitch = min(max(int(payload["pitch"]), -12), 12)
    if "display_order" in payload:
        item.display_order = int(payload["display_order"])
    if "preview_media_path" in payload:
        item.preview_media_path = (
            str(payload["preview_media_path"] or "").strip() or None
        )
    if (
        not item.is_default
        and item.status == "published"
        and any(
            key in payload
            for key in ("provider", "model", "voice_id", "emotion", "speed", "pitch")
        )
    ):
        item.status = "draft"
        item.published_at = None
    item.updated_at = datetime.now(UTC)
    db.commit()
    return narration_profile_dict(item)


@app.get("/api/admin/routes/{route_id}/narration/coverage")
def get_narration_coverage(route_id: str, profile_id: str, _: Auth, db: Db):
    ensure_default_narration_profile(db)
    return narration_profile_coverage(db, route_id, profile_id)


@app.post("/api/admin/routes/{route_id}/narration/generate", status_code=201)
def generate_route_narration(route_id: str, payload: dict[str, Any], _: Auth, db: Db):
    default_profile = ensure_default_narration_profile(db)
    profile_id = str(payload.get("profile_id") or default_profile.id)
    profile = db.get(NarrationVoiceProfile, profile_id)
    route = db.get(Route, route_id)
    if route is None:
        raise HTTPException(404, "路线不存在")
    if profile is None or profile.status == "archived":
        raise HTTPException(422, "请选择可编辑的音色档案")
    if (
        settings.narration_provider == "minimax"
        and not settings.minimax_api_key.strip()
    ):
        raise HTTPException(503, "MiniMax 凭证未配置，无法生成路线旁白")
    arc = db.scalar(select(StoryArc).where(StoryArc.route_id == route_id))
    fragments = (
        list(
            db.scalars(
                select(StoryFragment)
                .where(StoryFragment.arc_id == arc.id)
                .order_by(StoryFragment.position)
            )
        )
        if arc
        else []
    )
    if not fragments:
        raise HTTPException(422, "路线没有可生成的故事节点")
    coverage_before = narration_profile_coverage(db, route_id, profile.id)
    regenerate_all = bool(payload.get("regenerate_all", False))
    target_ids = (
        {item.id for item in fragments}
        if regenerate_all
        else {
            item["id"] for item in coverage_before["missing"] + coverage_before["stale"]
        }
    )
    targets = [item for item in fragments if item.id in target_ids]
    skipped = [item for item in fragments if item.id not in target_ids]

    def synthesize(fragment: StoryFragment):
        if not fragment.narration_script.strip():
            return fragment, None, "empty_transcript"
        try:
            result = narration_synthesizer.synthesize(
                NarrationRequest(
                    fragment.narration_script.strip(),
                    profile.voice_id,
                    profile.emotion,
                    profile.speed,
                    profile.pitch,
                )
            )
            return fragment, result, None
        except NarrationSynthesisError as error:
            return fragment, None, error.code
        except Exception:
            logger.exception(
                "Route narration generation failed for fragment %s", fragment.id
            )
            return fragment, None, "provider_error"

    generated = []
    if targets:
        with ThreadPoolExecutor(max_workers=min(4, len(targets))) as executor:
            generated = list(executor.map(synthesize, targets))

    results: list[dict[str, Any]] = [
        {"fragment_id": item.id, "title": item.title, "status": "skipped"}
        for item in skipped
    ]
    for fragment, synthesis, error_code in generated:
        if synthesis is None:
            results.append(
                {
                    "fragment_id": fragment.id,
                    "title": fragment.title,
                    "status": "failed",
                    "error_code": error_code,
                }
            )
            continue
        uploaded_key = None
        uploaded = False
        try:
            track, _, uploaded_key, uploaded = persist_formal_narration_track(
                db,
                fragment=fragment,
                profile=profile,
                audio=synthesis.payload,
                provider=synthesis.provider,
                model=synthesis.model,
                voice_id=profile.voice_id,
                emotion=profile.emotion,
                speed=profile.speed,
                pitch=profile.pitch,
            )
            profile.provider = synthesis.provider
            profile.model = synthesis.model
            profile.updated_at = datetime.now(UTC)
            db.commit()
            results.append(
                {
                    "fragment_id": fragment.id,
                    "title": fragment.title,
                    "status": "saved",
                    "track_id": track.id,
                    "media_path": track.media_path,
                }
            )
        except Exception:
            db.rollback()
            if uploaded and uploaded_key:
                public_object_storage.delete(uploaded_key)
            logger.exception(
                "Route narration storage failed for fragment %s", fragment.id
            )
            results.append(
                {
                    "fragment_id": fragment.id,
                    "title": fragment.title,
                    "status": "failed",
                    "error_code": "storage_unavailable",
                }
            )
    coverage = narration_profile_coverage(db, route_id, profile.id)
    if profile.is_default and coverage["ready"]:
        now = datetime.now(UTC)
        profile.status = "published"
        profile.published_at = profile.published_at or now
        profile.updated_at = now
        for fragment_id in coverage["complete_fragment_ids"]:
            fragment = db.get(StoryFragment, fragment_id)
            transcript_hash = hashlib.sha256(
                fragment.narration_script.strip().encode()
            ).hexdigest()
            track = db.scalar(
                select(FragmentNarrationTrack).where(
                    FragmentNarrationTrack.fragment_id == fragment_id,
                    FragmentNarrationTrack.profile_id == profile.id,
                    FragmentNarrationTrack.transcript_hash == transcript_hash,
                    FragmentNarrationTrack.script_version == fragment.script_version,
                )
            )
            track.published_at = now
        db.commit()
    saved_count = sum(item["status"] == "saved" for item in results)
    failed_count = sum(item["status"] == "failed" for item in results)
    logger.info(
        "Route narration batch route=%s profile=%s saved=%s failed=%s skipped=%s",
        route_id,
        profile.id,
        saved_count,
        failed_count,
        len(skipped),
    )
    return {
        "route_id": route_id,
        "profile": narration_profile_dict(profile),
        "generated_count": saved_count,
        "failed_count": failed_count,
        "skipped_count": len(skipped),
        "results": results,
        "coverage": coverage,
    }


@app.post("/api/admin/narration/profiles/{profile_id}/publish")
def publish_narration_profile(
    profile_id: str, payload: dict[str, Any], _: Auth, db: Db
):
    item = db.get(NarrationVoiceProfile, profile_id)
    route_id = str(payload.get("route_id") or "")
    if item is None:
        raise HTTPException(404, "音色不存在")
    coverage = narration_profile_coverage(db, route_id, profile_id)
    if not coverage["ready"]:
        raise HTTPException(
            409, {"message": "音色尚未覆盖整条路线", "coverage": coverage}
        )
    now = datetime.now(UTC)
    item.status = "published"
    item.published_at = now
    item.updated_at = now
    for fragment_id in coverage["complete_fragment_ids"]:
        fragment = db.get(StoryFragment, fragment_id)
        transcript_hash = hashlib.sha256(
            fragment.narration_script.strip().encode()
        ).hexdigest()
        track = db.scalar(
            select(FragmentNarrationTrack).where(
                FragmentNarrationTrack.fragment_id == fragment_id,
                FragmentNarrationTrack.profile_id == profile_id,
                FragmentNarrationTrack.transcript_hash == transcript_hash,
                FragmentNarrationTrack.script_version == fragment.script_version,
            )
        )
        track.published_at = now
    db.commit()
    return {"profile": narration_profile_dict(item), "coverage": coverage}


@app.post("/api/admin/narration/profiles/{profile_id}/archive")
def archive_narration_profile(profile_id: str, _: Auth, db: Db):
    item = db.get(NarrationVoiceProfile, profile_id)
    if item is None:
        raise HTTPException(404, "音色不存在")
    if item.is_default:
        raise HTTPException(409, "默认音色不能归档，请先设置另一个默认音色")
    item.status = "archived"
    item.updated_at = datetime.now(UTC)
    db.commit()
    return narration_profile_dict(item)


@app.post("/api/admin/narration/profiles/{profile_id}/set-default")
def set_default_narration_profile(profile_id: str, _: Auth, db: Db):
    item = db.get(NarrationVoiceProfile, profile_id)
    if item is None or item.status != "published" or item.published_at is None:
        raise HTTPException(409, "只有已发布音色可以设为默认")
    now = datetime.now(UTC)
    for profile in db.scalars(select(NarrationVoiceProfile)):
        profile.is_default = profile.id == profile_id
        profile.updated_at = now
    tracks = list(
        db.scalars(
            select(FragmentNarrationTrack).where(
                FragmentNarrationTrack.profile_id == profile_id,
                FragmentNarrationTrack.published_at.is_not(None),
            )
        )
    )
    for track in tracks:
        fragment = db.get(StoryFragment, track.fragment_id)
        expected_hash = hashlib.sha256(
            fragment.narration_script.strip().encode()
        ).hexdigest()
        if (
            track.transcript_hash == expected_hash
            and track.script_version == fragment.script_version
        ):
            fragment.audio_path = track.media_path
            fragment.audio_mime_type = track.mime_type
            fragment.audio_size_bytes = track.size_bytes
    db.commit()
    return narration_profile_dict(item)


@app.get("/api/admin/narration/config")
def narration_config(_: Auth):
    return {
        "provider": narration_synthesizer.provider,
        "model": narration_synthesizer.model,
        "default_voice_id": settings.minimax_voice_id,
        "credentials_configured": (
            settings.narration_provider == "fake"
            or bool(settings.minimax_api_key.strip())
        ),
        "supported_emotions": [
            "neutral",
            "happy",
            "sad",
            "angry",
            "fearful",
            "disgusted",
            "surprised",
        ],
        "presets": narration_default_variants(),
    }


@app.post("/api/admin/fragments/{fragment_id}/narration/previews", status_code=201)
def generate_narration_previews(
    fragment_id: str, payload: dict[str, Any], _: Auth, db: Db
):
    fragment = db.get(StoryFragment, fragment_id)
    if fragment is None:
        raise HTTPException(404, "故事碎片不存在")
    transcript = fragment.narration_script.strip()
    if not transcript:
        raise HTTPException(422, "旁白文字稿不能为空")
    default_profile = ensure_default_narration_profile(db)
    profile_id = str(payload.get("profile_id") or default_profile.id)
    profile = db.get(NarrationVoiceProfile, profile_id)
    if profile is None or profile.status == "archived":
        raise HTTPException(422, "请选择可编辑的音色档案")
    variants = payload.get("variants") or narration_default_variants()
    if not isinstance(variants, list) or not 3 <= len(variants) <= 5:
        raise HTTPException(422, "一次需要生成 3 到 5 个试听版本")
    pronunciation = tuple(str(item) for item in payload.get("pronunciation") or [])
    transcript_hash = hashlib.sha256(transcript.encode()).hexdigest()
    now = datetime.now(UTC)
    previews: list[NarrationPreview] = []
    for raw in variants:
        variant = dict(raw)
        preview_id = str(uuid4())
        voice_id = str(variant.get("voice_id") or profile.voice_id)
        emotion = str(variant.get("emotion") or profile.emotion)
        speed = min(max(float(variant.get("speed", profile.speed)), 0.5), 2.0)
        pitch = min(max(int(variant.get("pitch", profile.pitch)), -12), 12)
        preview = NarrationPreview(
            id=preview_id,
            fragment_id=fragment.id,
            profile_id=profile.id,
            transcript_hash=transcript_hash,
            provider=narration_synthesizer.provider,
            model=narration_synthesizer.model,
            voice_id=voice_id,
            emotion=emotion,
            speed=speed,
            pitch=pitch,
            pronunciation_json=list(pronunciation),
            status="pending",
            metadata_json={"label": str(variant.get("label") or emotion)},
            created_at=now,
            expires_at=now
            + timedelta(hours=max(1, settings.narration_preview_ttl_hours)),
        )
        try:
            result = narration_synthesizer.synthesize(
                NarrationRequest(
                    transcript, voice_id, emotion, speed, pitch, pronunciation
                )
            )
            object_key = f"private/narration-previews/{fragment.id}/{preview_id}.mp3"
            private_object_storage.put(object_key, result.payload, result.mime_type)
            preview.object_key = object_key
            preview.status = "ready"
            preview.metadata_json = {
                **preview.metadata_json,
                "mime_type": result.mime_type,
                "size_bytes": len(result.payload),
                "request_id": result.request_id,
            }
        except NarrationSynthesisError as error:
            preview.status = "failed"
            preview.error_code = error.code
        except Exception:
            logger.exception(
                "Narration preview storage failed for fragment %s", fragment.id
            )
            preview.status = "failed"
            preview.error_code = "storage_unavailable"
        db.add(preview)
        previews.append(preview)
    db.commit()
    return {"previews": [narration_preview_dict(item) for item in previews]}


@app.get("/api/admin/narration/previews/{preview_id}/audio")
def stream_narration_preview(preview_id: str, _: Auth, db: Db):
    preview = db.get(NarrationPreview, preview_id)
    if (
        preview is None
        or preview.status not in {"ready", "approved"}
        or not preview.object_key
    ):
        raise HTTPException(404, "试听音频不存在或已过期")
    now = datetime.now(UTC)
    if preview.expires_at.tzinfo is None:
        now = now.replace(tzinfo=None)
    if preview.expires_at < now and preview.status != "approved":
        raise HTTPException(410, "试听音频已过期")
    mime_type = str(preview.metadata_json.get("mime_type") or "audio/mpeg")

    def chunks():
        with private_object_storage.open(preview.object_key) as source:
            while payload := source.read(64 * 1024):
                yield payload

    return StreamingResponse(chunks(), media_type=mime_type)


@app.post("/api/admin/narration/previews/{preview_id}/approve")
def approve_narration_preview(preview_id: str, _: Auth, db: Db):
    preview = db.get(NarrationPreview, preview_id)
    if preview is None or preview.status != "ready" or not preview.object_key:
        raise HTTPException(409, "只有可试听版本能够批准")
    fragment = db.get(StoryFragment, preview.fragment_id)
    if fragment is None:
        raise HTTPException(404, "故事碎片不存在")
    transcript_hash = hashlib.sha256(
        fragment.narration_script.strip().encode()
    ).hexdigest()
    if transcript_hash != preview.transcript_hash:
        raise HTTPException(409, "文字稿已变化，请重新生成试听版本")
    profile = db.get(
        NarrationVoiceProfile,
        preview.profile_id or DEFAULT_NARRATION_PROFILE_ID,
    )
    if profile is None or profile.status == "archived":
        raise HTTPException(409, "试听对应的音色档案不存在或已归档")
    with private_object_storage.open(preview.object_key) as source:
        audio = source.read()
    object_key = None
    uploaded = False
    try:
        track, asset, object_key, uploaded = persist_formal_narration_track(
            db,
            fragment=fragment,
            profile=profile,
            audio=audio,
            provider=preview.provider,
            model=preview.model,
            voice_id=preview.voice_id,
            emotion=preview.emotion,
            speed=preview.speed,
            pitch=preview.pitch,
            source_preview_id=preview.id,
        )
        now = datetime.now(UTC)
        preview.status = "approved"
        preview.approved_at = now
        db.commit()
    except Exception:
        db.rollback()
        if uploaded and object_key:
            public_object_storage.delete(object_key)
        raise
    return {
        "preview": narration_preview_dict(preview),
        "profile": narration_profile_dict(profile),
        "track": {
            "id": track.id,
            "fragment_id": track.fragment_id,
            "profile_id": track.profile_id,
            "media_path": track.media_path,
        },
        "asset": {
            "key": asset.key,
            "storage_path": asset.storage_path,
            "canonical_url": asset.canonical_url,
        },
    }


@app.post("/api/admin/narration/previews/cleanup")
def cleanup_narration_previews(_: Auth, db: Db):
    rows = list(
        db.scalars(
            select(NarrationPreview).where(
                NarrationPreview.expires_at < datetime.now(UTC),
                NarrationPreview.status != "approved",
            )
        )
    )
    removed = 0
    for item in rows:
        if item.object_key:
            try:
                private_object_storage.delete(item.object_key)
            except Exception:
                logger.warning("Failed to delete expired narration preview %s", item.id)
                continue
        db.delete(item)
        removed += 1
    db.commit()
    return {"removed": removed}


def upsert(db: Session, model: type, identity: str, values: dict[str, Any]):
    item = db.get(model, identity)
    if item:
        for key, value in values.items():
            setattr(item, key, value)
        return item, False
    item = model(id=identity, **values)
    db.add(item)
    return item, True


@app.post("/api/admin/import")
def import_content(payload: dict[str, Any], _: Auth, db: Db):
    counts = {"cities": 0, "routes": 0, "stops": 0, "challenges": 0}
    try:
        city_ids: dict[str, str] = {}
        for raw_city in payload.get("cities", []):
            raw = dict(raw_city)
            supplied_city_id = raw.pop("id", None)
            data = CityInput.model_validate(raw)
            city_id = (
                supplied_city_id
                or db.scalar(select(City.id).where(City.slug == data.slug))
                or str(uuid4())
            )
            upsert(db, City, city_id, data.model_dump())
            city_ids[data.slug] = city_id
            counts["cities"] += 1

        route_ids: dict[str, str] = {}
        pending_stops: list[dict[str, Any]] = list(payload.get("stops", []))
        for raw_route in payload.get("routes", []):
            raw = dict(raw_route)
            nested_stops = raw.pop("stops", [])
            supplied_route_id = raw.pop("id", None)
            city_slug = raw.pop("city_slug", None)
            if city_slug and not raw.get("city_id"):
                raw["city_id"] = city_ids.get(city_slug) or db.scalar(
                    select(City.id).where(City.slug == city_slug)
                )
            data = RouteInput.model_validate(raw)
            route_id = (
                supplied_route_id
                or db.scalar(select(Route.id).where(Route.slug == data.slug))
                or str(uuid4())
            )
            values = data.model_dump()
            values["content_status"] = "draft"
            values["published_at"] = None
            upsert(db, Route, route_id, values)
            route_ids[data.slug] = route_id
            for nested in nested_stops:
                pending_stops.append({**nested, "route_id": route_id})
            counts["routes"] += 1

        stop_ids: dict[str, str] = {}
        pending_challenges: list[dict[str, Any]] = list(payload.get("challenges", []))
        for raw_stop in pending_stops:
            raw = dict(raw_stop)
            nested_challenge = raw.pop("challenge", None)
            supplied_stop_id = raw.pop("id", None)
            route_slug = raw.pop("route_slug", None)
            if route_slug and not raw.get("route_id"):
                raw["route_id"] = route_ids.get(route_slug) or db.scalar(
                    select(Route.id).where(Route.slug == route_slug)
                )
            data = StopInput.model_validate(raw)
            stop_id = (
                supplied_stop_id
                or db.scalar(
                    select(Stop.id).where(
                        Stop.route_id == data.route_id, Stop.position == data.position
                    )
                )
                or str(uuid4())
            )
            upsert(db, Stop, stop_id, stop_values(data))
            stop_ids[f"{data.route_id}:{data.position}"] = stop_id
            if nested_challenge:
                pending_challenges.append({**nested_challenge, "stop_id": stop_id})
            counts["stops"] += 1

        for raw_challenge in pending_challenges:
            raw = dict(raw_challenge)
            challenge_id = raw.pop("id", None) or str(uuid4())
            stop_ref = raw.pop("stop_ref", None)
            if stop_ref and not raw.get("stop_id"):
                raw["stop_id"] = stop_ids.get(stop_ref)
            data = ChallengeInput.model_validate(raw)
            if data.correct_option >= len(data.options):
                raise ValueError("正确答案序号超出选项范围")
            values = data.model_dump()
            values["options_json"] = values.pop("options")
            existing_id = db.scalar(
                select(Challenge.id).where(Challenge.stop_id == data.stop_id)
            )
            upsert(db, Challenge, existing_id or challenge_id, values)
            counts["challenges"] += 1

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(422, f"导入失败：{exc}") from exc
    return {"message": "内容已写入数据库", "imported": counts}


def _media_catalog(db: Session) -> dict[str, str]:
    catalog: dict[str, str] = {}
    for item in db.scalars(select(MediaAsset)):
        for reference in (item.storage_path, item.object_key, item.canonical_url):
            if reference:
                catalog[reference] = item.mime_type
    return catalog


def _published_route_locked(db: Session, route: Route) -> bool:
    if route.content_status != "published" or route.published_at is None:
        return False
    return bool(
        db.scalar(
            select(func.count())
            .select_from(Journey)
            .where(Journey.route_id == route.id)
        )
    )


def _route_content(db: Session, route: Route) -> dict[str, Any]:
    arc = db.scalar(select(StoryArc).where(StoryArc.route_id == route.id))
    if arc is None:
        return {
            "package_id": route.managed_package_id,
            "package_version": route.managed_package_version,
            "route": route_dict(route),
            "story_arc": None,
            "home_story": None,
            "fragments": [],
            "sources": [],
            "claims": [],
            "required_photo_mission_count": 0,
        }
    fragments = list(
        db.scalars(
            select(StoryFragment)
            .where(StoryFragment.arc_id == arc.id)
            .order_by(StoryFragment.position)
        )
    )
    fragment_ids = [item.id for item in fragments]
    stops = {
        item.id: item
        for item in db.scalars(
            select(Stop).where(Stop.id.in_([x.stop_id for x in fragments if x.stop_id]))
        )
    }
    regions = {
        item.fragment_id: item
        for item in db.scalars(
            select(TriggerRegion).where(TriggerRegion.fragment_id.in_(fragment_ids))
        )
    }
    missions = {
        item.fragment_id: item
        for item in db.scalars(
            select(PhotoMission).where(PhotoMission.fragment_id.in_(fragment_ids))
        )
    }
    dependency_map: dict[str, list[str]] = {}
    for row in db.scalars(
        select(FragmentDependency).where(
            FragmentDependency.fragment_id.in_(fragment_ids)
        )
    ):
        dependency_map.setdefault(row.fragment_id, []).append(row.required_fragment_id)
    claim_map: dict[str, list[str]] = {}
    for row in db.scalars(
        select(FragmentClaim).where(FragmentClaim.fragment_id.in_(fragment_ids))
    ):
        claim_map.setdefault(row.fragment_id, []).append(row.claim_id)
    route_claim_ids = sorted(
        {value for values in claim_map.values() for value in values}
    )
    claims = list(
        db.scalars(
            select(HistoricalClaim).where(HistoricalClaim.id.in_(route_claim_ids))
        )
    )
    support_map: dict[str, list[ClaimSource]] = {}
    support_rows = list(
        db.scalars(select(ClaimSource).where(ClaimSource.claim_id.in_(route_claim_ids)))
    )
    for row in support_rows:
        support_map.setdefault(row.claim_id, []).append(row)
    source_ids = sorted({row.source_id for row in support_rows})
    sources = list(
        db.scalars(select(HistoricalSource).where(HistoricalSource.id.in_(source_ids)))
    )
    home_publication = db.scalar(
        select(HomeStoryPublication).where(HomeStoryPublication.arc_id == arc.id)
    )
    story_tracks = list(
        db.scalars(
            select(StoryNarrationTrack).where(StoryNarrationTrack.arc_id == arc.id)
        )
    )

    def stop_payload(stop: Stop | None) -> dict[str, Any] | None:
        if stop is None:
            return None
        return {
            "id": stop.id,
            "title": stop.title,
            "kicker": stop.kicker,
            "address": stop.address,
            "latitude": stop.latitude,
            "longitude": stop.longitude,
            "arrival_radius_m": stop.arrival_radius_m,
            "story_title": stop.story_title,
            "story_body": stop.story_body,
            "audio_url": stop.audio_url,
            "image": stop.image,
            "insight": stop.insight,
            "experience_tags": normalize_experience_tags(
                stop.experience_tags_json or []
            ),
        }

    fragment_payloads = []
    for fragment in fragments:
        region = regions.get(fragment.id)
        mission = missions.get(fragment.id)
        fragment_payloads.append(
            {
                "id": fragment.id,
                "position": fragment.position,
                "title": fragment.title,
                "safe_preview": fragment.safe_preview,
                "narration_script": fragment.narration_script,
                "transcript": fragment.transcript,
                "audio_path": fragment.audio_path,
                "audio_mime_type": fragment.audio_mime_type,
                "audio_size_bytes": fragment.audio_size_bytes,
                "script_version": fragment.script_version,
                "interaction_type": fragment.interaction_type,
                "completion_threshold": fragment.completion_threshold,
                "key_claim": fragment.key_claim,
                "answers_question": fragment.answers_question,
                "raises_question": fragment.raises_question,
                "authenticity_label": fragment.authenticity_label,
                "review_state": fragment.review_state,
                "experience_tags": normalize_experience_tags(
                    fragment.experience_tags_json or []
                ),
                "footprint_editorial_summary": fragment.footprint_editorial_summary,
                "footprint_summary_options": normalize_footprint_summary_options(
                    fragment.footprint_summary_options_json or []
                ),
                "dependency_ids": dependency_map.get(fragment.id, []),
                "claim_ids": claim_map.get(fragment.id, []),
                "stop": stop_payload(stops.get(fragment.stop_id or "")),
                "trigger_region": {
                    "id": region.id,
                    "latitude": region.latitude,
                    "longitude": region.longitude,
                    "entry_radius_m": region.entry_radius_m,
                    "exit_radius_m": region.exit_radius_m,
                    "max_accuracy_m": region.max_accuracy_m,
                    "qualifying_samples": region.qualifying_samples,
                    "sample_window_seconds": region.sample_window_seconds,
                    "cooldown_seconds": region.cooldown_seconds,
                    "audit_state": region.audit_state,
                    "coordinate_system": region.coordinate_system,
                    "source_coordinate_system": region.source_coordinate_system,
                    "coordinate_source": region.coordinate_source,
                    "field_notes": region.field_notes,
                }
                if region
                else None,
                "photo_mission": {
                    "id": mission.id,
                    "prompt": mission.prompt,
                    "field_subject": mission.field_subject,
                    "vantage_point": mission.vantage_point,
                    "shooting_direction": mission.shooting_direction,
                    "composition_tip": mission.composition_tip,
                    "safety_copy": mission.safety_copy,
                    "accessibility_alternative": mission.accessibility_alternative,
                    "authenticity_label": mission.authenticity_label,
                    "required": mission.required,
                    "audit_state": mission.audit_state,
                }
                if mission
                else None,
            }
        )
    return {
        "package_id": route.managed_package_id,
        "package_version": route.managed_package_version,
        "route": {
            **route_dict(route),
            "id": route.id,
        },
        "story_arc": {
            "id": arc.id,
            "title": arc.title,
            "central_question": arc.central_question,
            "complete_story": arc.complete_story,
            "causal_model": arc.causal_model_json,
            "pronunciation_notes": arc.pronunciation_notes_json,
            "script_version": arc.script_version,
            "review_state": arc.review_state,
            "field_audit_state": arc.field_audit_state,
            "reviewed_by": arc.reviewed_by,
            "reviewed_at": iso(arc.reviewed_at),
            "source_version": arc.source_version,
            "publication_decision": arc.publication_decision,
        },
        "home_story": (
            {
                "id": home_publication.id,
                "title": home_publication.title,
                "introduction": home_publication.introduction,
                "cover_image": home_publication.cover_image,
                "selection_weight": home_publication.selection_weight,
                "status": home_publication.status,
                "selected_track_id": home_publication.selected_track_id,
                "reviewed_by": home_publication.reviewed_by,
                "reviewed_at": iso(home_publication.reviewed_at),
                "published_at": iso(home_publication.published_at),
                "tracks": [
                    {
                        "id": track.id,
                        "profile_id": track.profile_id,
                        "transcript_hash": track.transcript_hash,
                        "script_version": track.script_version,
                        "media_path": track.media_path,
                        "mime_type": track.mime_type,
                        "size_bytes": track.size_bytes,
                        "duration_ms": track.duration_ms,
                        "checksum_sha256": track.checksum_sha256,
                        "generation_metadata": track.generation_metadata_json,
                        "status": track.status,
                        "reviewed_by": track.reviewed_by,
                        "reviewed_at": iso(track.reviewed_at),
                        "published_at": iso(track.published_at),
                    }
                    for track in story_tracks
                ],
            }
            if home_publication
            else None
        ),
        "fragments": fragment_payloads,
        "sources": [
            {
                "id": item.id,
                "title": item.title,
                "publisher": item.publisher,
                "url": item.url,
                "source_type": item.source_type,
                "accessed_at": iso(item.accessed_at),
                "review_state": item.review_state,
                "summary": item.summary,
            }
            for item in sources
        ],
        "claims": [
            {
                "id": item.id,
                "canonical_text": item.canonical_text,
                "claim_kind": item.claim_kind,
                "certainty": item.certainty,
                "review_state": item.review_state,
                "boundary_note": item.boundary_note,
                "supersedes_claim_id": item.supersedes_claim_id,
                "reviewed_by": item.reviewed_by,
                "reviewed_at": iso(item.reviewed_at),
                "source_ids": [row.source_id for row in support_map.get(item.id, [])],
                "support_notes": {
                    row.source_id: row.support_note
                    for row in support_map.get(item.id, [])
                },
            }
            for item in claims
        ],
        "required_photo_mission_count": sum(
            1 for item in missions.values() if item.required
        ),
    }


def _replace_route_content(db: Session, route: Route, graph: dict[str, Any]) -> None:
    if _published_route_locked(db, route):
        raise HTTPException(409, "published_route_locked")
    route_data = dict(graph.get("route") or {})
    for key in (
        "slug",
        "title",
        "subtitle",
        "description",
        "duration_minutes",
        "distance_km",
        "difficulty",
        "theme",
        "hero_image",
        "is_featured",
    ):
        if key in route_data:
            setattr(route, key, route_data[key])
    route.managed_package_id = (
        str(graph.get("package_id") or route.managed_package_id or "") or None
    )
    route.managed_package_version = (
        str(graph.get("package_version") or route.managed_package_version or "") or None
    )
    route.content_status = "draft"
    route.published_at = None

    old_arc = db.scalar(select(StoryArc).where(StoryArc.route_id == route.id))
    old_fragment_ids: list[str] = []
    if old_arc:
        old_fragment_ids = list(
            db.scalars(
                select(StoryFragment.id).where(StoryFragment.arc_id == old_arc.id)
            )
        )
    incoming_fragments = {
        str(item.get("id") or ""): item for item in graph.get("fragments") or []
    }
    preserved_narration_tracks: list[dict[str, Any]] = []
    if old_fragment_ids:
        for track in db.scalars(
            select(FragmentNarrationTrack).where(
                FragmentNarrationTrack.fragment_id.in_(old_fragment_ids)
            )
        ):
            fragment = incoming_fragments.get(track.fragment_id)
            if fragment is None:
                continue
            expected_hash = hashlib.sha256(
                str(fragment.get("narration_script") or "").strip().encode()
            ).hexdigest()
            expected_version = str(fragment.get("script_version") or "")
            if (
                track.transcript_hash != expected_hash
                or track.script_version != expected_version
            ):
                continue
            preserved_narration_tracks.append(
                {
                    "id": track.id,
                    "fragment_id": track.fragment_id,
                    "profile_id": track.profile_id,
                    "transcript_hash": track.transcript_hash,
                    "script_version": track.script_version,
                    "media_path": track.media_path,
                    "mime_type": track.mime_type,
                    "size_bytes": track.size_bytes,
                    "checksum_sha256": track.checksum_sha256,
                    "generation_metadata_json": dict(
                        track.generation_metadata_json or {}
                    ),
                    "approved_at": track.approved_at,
                    "published_at": track.published_at,
                }
            )
        db.execute(
            delete(NarrationPreview).where(
                NarrationPreview.fragment_id.in_(old_fragment_ids)
            )
        )
        db.execute(
            delete(FragmentNarrationTrack).where(
                FragmentNarrationTrack.fragment_id.in_(old_fragment_ids)
            )
        )
        db.execute(
            delete(FragmentClaim).where(FragmentClaim.fragment_id.in_(old_fragment_ids))
        )
        db.execute(
            delete(FragmentDependency).where(
                FragmentDependency.fragment_id.in_(old_fragment_ids)
            )
        )
        db.execute(
            delete(TriggerRegion).where(TriggerRegion.fragment_id.in_(old_fragment_ids))
        )
        db.execute(
            delete(PhotoMission).where(PhotoMission.fragment_id.in_(old_fragment_ids))
        )
        db.execute(delete(StoryFragment).where(StoryFragment.id.in_(old_fragment_ids)))
    if old_arc:
        db.execute(
            delete(HomeStoryPublication).where(
                HomeStoryPublication.arc_id == old_arc.id
            )
        )
        db.execute(
            delete(StoryNarrationTrack).where(StoryNarrationTrack.arc_id == old_arc.id)
        )
        db.delete(old_arc)
    stop_ids = list(db.scalars(select(Stop.id).where(Stop.route_id == route.id)))
    if stop_ids:
        db.execute(delete(Challenge).where(Challenge.stop_id.in_(stop_ids)))
        db.execute(delete(Stop).where(Stop.id.in_(stop_ids)))
    db.flush()

    for raw in graph.get("sources") or []:
        values = dict(raw)
        identity = str(values.pop("id"))
        values["accessed_at"] = _parse_datetime(
            values.get("accessed_at")
        ) or datetime.now(UTC)
        item = db.get(HistoricalSource, identity)
        if item is None:
            db.add(HistoricalSource(id=identity, **values))
        else:
            for key, value in values.items():
                setattr(item, key, value)
    for raw in graph.get("claims") or []:
        values = dict(raw)
        identity = str(values.pop("id"))
        source_ids = list(map(str, values.pop("source_ids", [])))
        support_notes = dict(values.pop("support_notes", {}))
        values["reviewed_at"] = _parse_datetime(values.get("reviewed_at"))
        item = db.get(HistoricalClaim, identity)
        if item is None:
            db.add(HistoricalClaim(id=identity, **values))
        else:
            for key, value in values.items():
                setattr(item, key, value)
        db.execute(delete(ClaimSource).where(ClaimSource.claim_id == identity))
        for source_id in source_ids:
            db.add(
                ClaimSource(
                    claim_id=identity,
                    source_id=source_id,
                    support_note=str(
                        support_notes.get(source_id) or "支持该线索中的事实表述"
                    ),
                )
            )

    arc_data = dict(graph.get("story_arc") or {})
    arc_id = str(arc_data.pop("id"))
    arc = StoryArc(
        id=arc_id,
        route_id=route.id,
        title=str(arc_data.get("title") or ""),
        central_question=str(arc_data.get("central_question") or ""),
        complete_story=str(arc_data.get("complete_story") or ""),
        causal_model_json=list(arc_data.get("causal_model") or []),
        pronunciation_notes_json=list(arc_data.get("pronunciation_notes") or []),
        script_version=str(arc_data.get("script_version") or ""),
        review_state=str(arc_data.get("review_state") or "in_review"),
        field_audit_state=str(arc_data.get("field_audit_state") or "required"),
        reviewed_by=arc_data.get("reviewed_by"),
        reviewed_at=_parse_datetime(arc_data.get("reviewed_at")),
        source_version=arc_data.get("source_version"),
        publication_decision=arc_data.get("publication_decision"),
    )
    db.add(arc)
    db.flush()
    for raw in graph.get("fragments") or []:
        values = dict(raw)
        fragment_id = str(values["id"])
        stop_data = dict(values.get("stop") or {})
        region_data = dict(values.get("trigger_region") or {})
        stop_id = str(stop_data.get("id") or f"{fragment_id}-stop")
        stop = Stop(
            id=stop_id,
            route_id=route.id,
            position=int(values["position"]),
            title=str(stop_data.get("title") or values.get("title") or ""),
            kicker=str(
                stop_data.get("kicker") or values.get("safe_preview") or "现场线索"
            ),
            address=str(stop_data.get("address") or "公共步行区域"),
            latitude=float(stop_data.get("latitude", region_data.get("latitude"))),
            longitude=float(stop_data.get("longitude", region_data.get("longitude"))),
            arrival_radius_m=int(
                stop_data.get("arrival_radius_m", region_data.get("entry_radius_m", 60))
            ),
            story_title=str(stop_data.get("story_title") or values.get("title") or ""),
            story_body=str(
                stop_data.get("story_body") or values.get("transcript") or ""
            ),
            audio_url=stop_data.get("audio_url") or values.get("audio_path"),
            image=str(stop_data.get("image") or route.hero_image),
            insight=str(stop_data.get("insight") or values.get("key_claim") or ""),
            experience_tags_json=normalize_experience_tags(
                stop_data.get("experience_tags")
            ),
        )
        db.add(stop)
        db.flush()
        fragment = StoryFragment(
            id=fragment_id,
            arc_id=arc.id,
            stop_id=stop.id,
            position=int(values["position"]),
            title=str(values.get("title") or ""),
            safe_preview=str(values.get("safe_preview") or ""),
            narration_script=str(values.get("narration_script") or ""),
            transcript=str(values.get("transcript") or ""),
            audio_path=str(values.get("audio_path") or ""),
            audio_mime_type=str(values.get("audio_mime_type") or "audio/mp4"),
            audio_size_bytes=int(values.get("audio_size_bytes") or 0),
            script_version=str(values.get("script_version") or ""),
            interaction_type=str(values.get("interaction_type") or "passive"),
            completion_threshold=float(values.get("completion_threshold") or 0.9),
            key_claim=str(values.get("key_claim") or ""),
            answers_question=str(values.get("answers_question") or ""),
            raises_question=str(values.get("raises_question") or ""),
            authenticity_label=str(values.get("authenticity_label") or "interpretive"),
            review_state=str(values.get("review_state") or "in_review"),
            experience_tags_json=normalize_experience_tags(
                values.get("experience_tags")
            ),
            footprint_editorial_summary=str(
                values.get("footprint_editorial_summary") or ""
            ).strip()
            or None,
            footprint_summary_options_json=normalize_footprint_summary_options(
                values.get("footprint_summary_options")
            ),
        )
        db.add(fragment)
        db.flush()
        db.add(
            TriggerRegion(
                id=str(region_data.get("id") or f"{fragment_id}-trigger"),
                fragment_id=fragment_id,
                latitude=float(region_data["latitude"]),
                longitude=float(region_data["longitude"]),
                entry_radius_m=int(region_data.get("entry_radius_m", 60)),
                exit_radius_m=int(region_data.get("exit_radius_m", 90)),
                max_accuracy_m=int(region_data.get("max_accuracy_m", 35)),
                qualifying_samples=int(region_data.get("qualifying_samples", 2)),
                sample_window_seconds=int(region_data.get("sample_window_seconds", 15)),
                cooldown_seconds=int(region_data.get("cooldown_seconds", 120)),
                audit_state=str(region_data.get("audit_state") or "in_review"),
                coordinate_system=str(region_data.get("coordinate_system") or "WGS84"),
                source_coordinate_system=region_data.get("source_coordinate_system"),
                coordinate_source=region_data.get("coordinate_source"),
                field_notes=region_data.get("field_notes"),
            )
        )
        mission = values.get("photo_mission")
        if mission:
            db.add(
                PhotoMission(
                    id=str(mission.get("id") or f"{fragment_id}-mission"),
                    fragment_id=fragment_id,
                    prompt=str(mission.get("prompt") or ""),
                    field_subject=str(mission.get("field_subject") or ""),
                    vantage_point=mission.get("vantage_point"),
                    shooting_direction=mission.get("shooting_direction"),
                    composition_tip=mission.get("composition_tip"),
                    safety_copy=str(mission.get("safety_copy") or ""),
                    accessibility_alternative=str(
                        mission.get("accessibility_alternative") or ""
                    ),
                    authenticity_label=str(
                        mission.get("authenticity_label") or "interpretive"
                    ),
                    required=bool(mission.get("required", True)),
                    audit_state=str(mission.get("audit_state") or "in_review"),
                )
            )
        for claim_id in values.get("claim_ids") or []:
            db.add(FragmentClaim(fragment_id=fragment_id, claim_id=str(claim_id)))
        for required_id in values.get("dependency_ids") or []:
            db.add(
                FragmentDependency(
                    fragment_id=fragment_id, required_fragment_id=str(required_id)
                )
            )
    db.flush()
    for track in preserved_narration_tracks:
        db.add(FragmentNarrationTrack(**track))
    home_story_data = dict(graph.get("home_story") or {})
    if home_story_data:
        now = datetime.now(UTC)
        track_ids: set[str] = set()
        for raw_track in home_story_data.pop("tracks", []) or []:
            track_data = dict(raw_track)
            track_id = str(track_data.pop("id"))
            track_ids.add(track_id)
            db.add(
                StoryNarrationTrack(
                    id=track_id,
                    arc_id=arc.id,
                    profile_id=str(track_data.get("profile_id") or ""),
                    transcript_hash=str(track_data.get("transcript_hash") or ""),
                    script_version=str(track_data.get("script_version") or ""),
                    media_path=str(track_data.get("media_path") or ""),
                    mime_type=str(track_data.get("mime_type") or "audio/mpeg"),
                    size_bytes=int(track_data.get("size_bytes") or 0),
                    duration_ms=int(track_data.get("duration_ms") or 0),
                    checksum_sha256=track_data.get("checksum_sha256"),
                    generation_metadata_json=dict(
                        track_data.get("generation_metadata") or {}
                    ),
                    status=str(track_data.get("status") or "draft"),
                    reviewed_by=track_data.get("reviewed_by"),
                    reviewed_at=_parse_datetime(track_data.get("reviewed_at")),
                    published_at=_parse_datetime(track_data.get("published_at")),
                    created_at=now,
                    updated_at=now,
                )
            )
        selected_track_id = home_story_data.get("selected_track_id")
        if selected_track_id and str(selected_track_id) not in track_ids:
            selected_track_id = None
        db.flush()
        db.add(
            HomeStoryPublication(
                id=str(home_story_data.get("id") or uuid4()),
                arc_id=arc.id,
                selected_track_id=(
                    str(selected_track_id) if selected_track_id else None
                ),
                title=str(home_story_data.get("title") or arc.title),
                introduction=str(
                    home_story_data.get("introduction")
                    or home_story_defaults(arc, route)[0]
                ),
                cover_image=str(
                    home_story_data.get("cover_image")
                    or home_story_defaults(arc, route)[1]
                ),
                selection_weight=int(home_story_data.get("selection_weight") or 1),
                status=str(home_story_data.get("status") or "draft"),
                reviewed_by=home_story_data.get("reviewed_by"),
                reviewed_at=_parse_datetime(home_story_data.get("reviewed_at")),
                published_at=_parse_datetime(home_story_data.get("published_at")),
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


@app.get("/api/admin/routes/{route_id}/content")
def get_route_content(route_id: str, _: Auth, db: Db):
    route = db.get(Route, route_id)
    if route is None:
        raise HTTPException(404, "路线不存在")
    return _route_content(db, route)


@app.put("/api/admin/routes/{route_id}/content")
def put_route_content(route_id: str, payload: dict[str, Any], _: Auth, db: Db):
    route = db.get(Route, route_id)
    if route is None:
        raise HTTPException(404, "路线不存在")
    try:
        _replace_route_content(db, route, payload)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(422, f"保存碎片路线失败：{exc}") from exc
    graph = _route_content(db, route)
    return {"content": graph, "validation": validate_graph(graph, _media_catalog(db))}


@app.post("/api/admin/routes/{route_id}/validate")
def validate_route_content(route_id: str, _: Auth, db: Db):
    route = db.get(Route, route_id)
    if route is None:
        raise HTTPException(404, "路线不存在")
    return _publication_validation(db, route)


@app.post("/api/admin/routes/{route_id}/submit-review")
def submit_route_review(route_id: str, _: Auth, db: Db):
    route = _route_for_transition(db, route_id, {"draft"}, "只有草稿可以提交审核")
    route.content_status = "in_review"
    route.published_at = None
    db.commit()
    return {
        "route": route_dict(route),
        "validation": _publication_validation(db, route),
    }


@app.post("/api/admin/routes/{route_id}/verify")
def verify_route_content(route_id: str, _: Auth, db: Db):
    route = _route_for_transition(
        db, route_id, {"in_review"}, "只有待审核路线可以通过审核"
    )
    result = _publication_validation(db, route)
    if not result["valid"]:
        raise HTTPException(422, detail={"code": "content_validation_failed", **result})
    route.content_status = "verified"
    route.published_at = None
    db.commit()
    return {"route": route_dict(route), "validation": result}


@app.post("/api/admin/routes/{route_id}/publish")
def publish_route_content(route_id: str, _: Auth, db: Db):
    route = _route_for_transition(db, route_id, {"verified"}, "只有已审核路线可以发布")
    result = _publication_validation(db, route)
    if not result["valid"]:
        raise HTTPException(422, detail={"code": "content_validation_failed", **result})
    route.content_status = "published"
    route.published_at = datetime.now(UTC)
    arc = db.scalar(select(StoryArc).where(StoryArc.route_id == route.id))
    if arc:
        arc.publication_decision = "field_test"
    db.commit()
    return {"route": route_dict(route), "validation": result}


@app.post("/api/admin/routes/{route_id}/archive")
def archive_route_content(route_id: str, _: Auth, db: Db):
    route = _route_for_transition(db, route_id, {"published"}, "只有已发布路线可以归档")
    route.content_status = "archived"
    db.commit()
    return {"route": route_dict(route)}


def _route_for_transition(
    db: Session, route_id: str, allowed: set[str], message: str
) -> Route:
    route = db.get(Route, route_id)
    if route is None:
        raise HTTPException(404, "路线不存在")
    if route.content_status not in allowed:
        raise HTTPException(
            409,
            detail={
                "code": "invalid_route_transition",
                "message": message,
                "current_status": route.content_status,
            },
        )
    return route


def _publication_validation(db: Session, route: Route) -> dict[str, Any]:
    graph = _route_content(db, route)
    if graph["story_arc"] is not None:
        result = validate_graph(graph, _media_catalog(db))
        fragments = list(
            db.scalars(
                select(StoryFragment).where(
                    StoryFragment.arc_id == graph["story_arc"]["id"]
                )
            )
        )
        for index, fragment in enumerate(fragments):
            has_candidates = (
                db.scalar(
                    select(func.count())
                    .select_from(NarrationPreview)
                    .where(
                        NarrationPreview.fragment_id == fragment.id,
                        NarrationPreview.status.in_(["ready", "approved"]),
                    )
                )
                or 0
            )
            if not has_candidates:
                continue
            transcript_hash = hashlib.sha256(
                fragment.narration_script.strip().encode()
            ).hexdigest()
            approved = db.scalar(
                select(NarrationPreview).where(
                    NarrationPreview.fragment_id == fragment.id,
                    NarrationPreview.status == "approved",
                    NarrationPreview.transcript_hash == transcript_hash,
                )
            )
            asset = db.scalar(
                select(MediaAsset).where(MediaAsset.storage_path == fragment.audio_path)
            )
            provenance = (
                asset.metadata_json.get("narration")
                if asset and isinstance(asset.metadata_json, dict)
                else None
            ) or {}
            if (
                approved is None
                or provenance.get("preview_id") != approved.id
                or provenance.get("transcript_hash") != transcript_hash
            ):
                result["errors"].append(
                    {
                        "path": f"fragments[{index}].audio_path",
                        "code": "narration_not_approved",
                        "message": (
                            "当前文字稿已有试听版本，发布前必须批准与文字稿一致的旁白"
                        ),
                    }
                )
        result["valid"] = not result["errors"]
        return result
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    stops = list(db.scalars(select(Stop).where(Stop.route_id == route.id)))
    if not stops:
        errors.append(
            {
                "path": "stops",
                "code": "stops_missing",
                "message": "路线至少需要一个站点",
            }
        )
    media = _media_catalog(db)
    if route.hero_image not in media and not route.hero_image.startswith(
        ("http://", "https://")
    ):
        errors.append(
            {
                "path": "route.hero_image",
                "code": "media_missing",
                "message": "路线封面未登记",
            }
        )
    for index, stop in enumerate(stops):
        if not stop.story_body.strip():
            errors.append(
                {
                    "path": f"stops[{index}].story_body",
                    "code": "story_missing",
                    "message": "站点故事不能为空",
                }
            )
    return {"valid": not errors, "errors": errors, "warnings": warnings}


@app.post("/api/admin/fragmented-routes/import", status_code=201)
def import_fragmented_route(payload: dict[str, Any], _: Auth, db: Db):
    package_id = str(payload.get("package_id") or "").strip()
    package_version = str(payload.get("package_version") or "").strip()
    if not package_id or not package_version:
        raise HTTPException(422, "package_id 和 package_version 必填")
    now = datetime.now(UTC)
    media_aliases: dict[str, str] = {}
    for raw in payload.get("media") or []:
        media_data = dict(raw)
        asset_key = str(media_data.get("key") or "").strip()
        storage_path = str(media_data.get("storage_path") or "").strip()
        mime_type = str(media_data.get("mime_type") or "").strip()
        checksum = str(media_data.get("sha256") or "").strip().lower()
        if (
            not asset_key
            or not storage_path
            or not mime_type.startswith(("image/", "audio/"))
        ):
            raise HTTPException(
                422, "media 中的 key、storage_path 和图片/音频 MIME 必填"
            )
        item = db.get(MediaAsset, asset_key)
        if item is None:
            item = db.scalar(
                select(MediaAsset).where(
                    or_(
                        MediaAsset.storage_path == storage_path,
                        MediaAsset.canonical_url == storage_path,
                    )
                )
            )
        if item is None and checksum:
            item = db.scalar(
                select(MediaAsset).where(MediaAsset.checksum_sha256 == checksum)
            )
        if item is None:
            if not settings.testing:
                raise HTTPException(422, f"请先将资源上传 OSS 并登记：{asset_key}")
            fake_payload = storage_path.encode("utf-8")
            object_key = f"unit-test/import/{hashlib.sha256(fake_payload).hexdigest()}"
            if not public_object_storage.exists(object_key):
                public_object_storage.put(object_key, fake_payload, mime_type)
            db.add(
                MediaAsset(
                    key=asset_key,
                    storage_path=storage_path,
                    mime_type=mime_type,
                    storage_provider="memory",
                    object_key=object_key,
                    canonical_url=public_object_storage.public_url(object_key),
                    visibility="public",
                    size_bytes=len(fake_payload),
                    checksum_sha256=(
                        checksum or hashlib.sha256(fake_payload).hexdigest()
                    ),
                    metadata_json={"unit_test_fake": True},
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            if checksum and item.checksum_sha256 and item.checksum_sha256 != checksum:
                raise HTTPException(409, f"媒体校验和与已登记资源不匹配：{asset_key}")
            item.mime_type = mime_type
            item.updated_at = now
            media_aliases[storage_path] = item.canonical_url or item.storage_path
    if media_aliases:
        payload = _replace_media_aliases(payload, media_aliases)
    existing = db.scalar(select(Route).where(Route.managed_package_id == package_id))
    if existing and existing.managed_package_version == package_version:
        db.commit()
        return {
            "idempotent": True,
            "route": route_dict(existing),
            "validation": validate_graph(
                _route_content(db, existing), _media_catalog(db)
            ),
        }
    if existing and _published_route_locked(db, existing):
        raise HTTPException(409, "published_route_locked")
    city_data = dict(payload.get("city") or {})
    city_id = str(city_data.pop("id", "")).strip()
    if not city_id:
        raise HTTPException(422, "city.id 必填")
    city = db.get(City, city_id)
    if city is None:
        city = City(id=city_id, **city_data)
        db.add(city)
    else:
        for key, value in city_data.items():
            setattr(city, key, value)
    route_data = dict(payload.get("route") or {})
    route_id = str(route_data.get("id") or "").strip()
    if not route_id:
        raise HTTPException(422, "route.id 必填")
    route = db.get(Route, route_id) or existing
    if route is None:
        route = Route(
            id=route_id,
            city_id=city_id,
            slug=str(route_data.get("slug") or ""),
            title=str(route_data.get("title") or ""),
            subtitle=str(route_data.get("subtitle") or ""),
            description=str(route_data.get("description") or ""),
            duration_minutes=int(route_data.get("duration_minutes") or 1),
            distance_km=float(route_data.get("distance_km") or 0.1),
            difficulty=str(route_data.get("difficulty") or "轻松"),
            theme=str(route_data.get("theme") or "文化漫游"),
            hero_image=str(route_data.get("hero_image") or ""),
            is_featured=bool(route_data.get("is_featured", False)),
            content_status="draft",
            published_at=None,
            managed_package_id=package_id,
            managed_package_version=package_version,
        )
        db.add(route)
        db.flush()
    payload = {**payload, "route": {**route_data, "id": route.id}}
    try:
        _replace_route_content(db, route, payload)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(422, f"导入碎片路线失败：{exc}") from exc
    graph = _route_content(db, route)
    return {
        "idempotent": False,
        "route": route_dict(route),
        "validation": validate_graph(graph, _media_catalog(db)),
    }


def _replace_media_aliases(value: Any, aliases: dict[str, str]) -> Any:
    if isinstance(value, str):
        return aliases.get(value, value)
    if isinstance(value, list):
        return [_replace_media_aliases(item, aliases) for item in value]
    if isinstance(value, dict):
        return {
            key: _replace_media_aliases(item, aliases) for key, item in value.items()
        }
    return value
