from __future__ import annotations

import asyncio
import hmac
import logging
import re
import shutil
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from models import Challenge, City, Journey, JourneyAnswer, MediaAsset, Route, Stop
from runtime_logs.docker_source import DockerLogSource
from runtime_logs.normalization import NormalizationLimits, normalize_event, normalize_level
from runtime_logs.storage import (
    cleanup_client_logs,
    ensure_client_log_schema,
    persist_client_events,
    query_client_events,
)
from runtime_logs.streaming import StreamLimiter, limited_stream, sse_message
from schemas import ChallengeInput, CityInput, ClientLogBatch, RouteInput, StopInput

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "mysql+pymysql://jiandi:jiandi_dev@127.0.0.1:3307/jiandi?charset=utf8mb4"
    admin_token: str = "dev-only-change-me"
    media_root: str = "./media"
    cors_origins: str = "http://localhost:3000"
    max_upload_mb: int = 30
    client_log_ingest_token: str = "dev-client-logs-change-me"
    client_log_max_request_kb: int = 128
    client_log_max_batch: int = 50
    client_log_retention_days: int = 7
    client_log_max_rows: int = 20_000
    client_log_cleanup_batch: int = 1_000
    backend_logs_enabled: bool = False
    docker_socket_path: str = "/var/run/docker.sock"
    docker_api_version: str = "v1.41"
    log_sources: str = "travel-api=deeptravel-api-1,admin-api=deeptravel-admin-admin-api-1"
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
        if not separator or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", alias) or not target:
            raise ValueError(f"非法 LOG_SOURCES 项：{item}")
        sources[alias] = target
    return sources


settings = Settings()
engine = create_engine(settings.database_url, pool_pre_ping=True, pool_recycle=1800)
SessionLocal = sessionmaker(engine, expire_on_commit=False)
media_root = Path(settings.media_root).resolve()
media_root.mkdir(parents=True, exist_ok=True)
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
    await asyncio.to_thread(run_log_retention)
    yield


app = FastAPI(title="简地内容中台 API", version="1.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[item.strip() for item in settings.cors_origins.split(",") if item.strip()],
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


def authorize_client_ingest(x_client_log_token: Annotated[str | None, Header()] = None) -> None:
    if not x_client_log_token or not hmac.compare_digest(x_client_log_token, settings.client_log_ingest_token):
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


def route_dict(item: Route, city_name: str | None = None, stop_count: int = 0) -> dict[str, Any]:
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
        "stop_count": stop_count,
    }


def stop_dict(item: Stop, route_title: str | None = None, has_challenge: bool = False) -> dict[str, Any]:
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
        "has_challenge": has_challenge,
    }


def challenge_dict(item: Challenge, stop_title: str | None = None, route_title: str | None = None) -> dict[str, Any]:
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
        "media_root": str(media_root),
        "client_log_storage": "connected",
        "backend_logs": "available" if settings.backend_logs_enabled and docker_log_source.available else "unavailable",
    }


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
        raise HTTPException(422, exc.errors(include_input=False, include_url=False)) from exc
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
            {"id": alias, "label": alias.replace("-", " "), "available": backend_available}
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
        {"source_type": "client", "source": "client", "heartbeat_seconds": settings.log_heartbeat_seconds},
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
        if time.monotonic() - last_heartbeat >= max(2.0, settings.log_heartbeat_seconds):
            yield sse_message("heartbeat", {"at": datetime.now(UTC).isoformat()})
            last_heartbeat = time.monotonic()


@app.get("/api/admin/logs/client/stream")
async def stream_client_logs(request: Request, _: Auth, after: int | None = None, tail: int = 200):
    if not await stream_limiter.acquire():
        raise HTTPException(429, "实时日志连接数已达上限")
    source = client_log_stream(request, after=after, tail=tail)
    return StreamingResponse(
        limited_stream(source, stream_limiter),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


async def backend_log_stream(request: Request, *, source: str, tail: int):
    yield sse_message(
        "metadata",
        {"source_type": "backend", "source": source, "heartbeat_seconds": settings.log_heartbeat_seconds},
    )
    iterator = docker_log_source.follow(source, tail=tail).__aiter__()
    pending: asyncio.Task | None = None
    try:
        while not await request.is_disconnected():
            if pending is None:
                pending = asyncio.create_task(anext(iterator))
            done, _ = await asyncio.wait({pending}, timeout=max(2.0, settings.log_heartbeat_seconds))
            if not done:
                yield sse_message("heartbeat", {"at": datetime.now(UTC).isoformat()})
                continue
            try:
                event = pending.result()
            except StopAsyncIteration:
                yield sse_message("source_status", {"status": "ended", "source": source})
                break
            pending = None
            yield sse_message("log", event.to_dict(), cursor=event.cursor)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("Backend log source %s unavailable: %s", source, type(exc).__name__)
        yield sse_message(
            "source_status",
            {"status": "unavailable", "source": source, "message": "后端日志源暂不可用"},
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
    stream = backend_log_stream(request, source=source, tail=min(max(tail, 1), settings.log_tail_limit))
    return StreamingResponse(
        limited_stream(stream, stream_limiter),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@app.get("/api/admin/dashboard")
def dashboard(_: Auth, db: Db):
    counts = {
        "cities": db.scalar(select(func.count()).select_from(City)) or 0,
        "routes": db.scalar(select(func.count()).select_from(Route)) or 0,
        "published_routes": db.scalar(select(func.count()).select_from(Route).where(Route.content_status == "published")) or 0,
        "stops": db.scalar(select(func.count()).select_from(Stop)) or 0,
        "challenges": db.scalar(select(func.count()).select_from(Challenge)) or 0,
        "media": db.scalar(select(func.count()).select_from(MediaAsset)) or 0,
        "journeys": db.scalar(select(func.count()).select_from(Journey)) or 0,
    }
    missing_challenges = db.scalar(
        select(func.count()).select_from(Stop).outerjoin(Challenge, Challenge.stop_id == Stop.id).where(Challenge.id.is_(None))
    ) or 0
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
        "recent_routes": [route_dict(route, city_name, stop_count) for route, city_name, stop_count in recent_rows],
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
    if db.scalar(select(func.count()).select_from(Route).where(Route.city_id == item_id)):
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
        statement = statement.where(or_(Route.title.contains(q), Route.slug.contains(q)))
    return [route_dict(route, city_name, stop_count) for route, city_name, stop_count in db.execute(statement)]


@app.post("/api/admin/routes", status_code=201)
def create_route(payload: RouteInput, _: Auth, db: Db):
    if not db.get(City, payload.city_id):
        raise HTTPException(400, "所选城市不存在")
    values = payload.model_dump()
    if values["content_status"] == "published" and not values["published_at"]:
        values["published_at"] = datetime.now(UTC)
    item = Route(id=str(uuid4()), **values)
    db.add(item)
    commit_or_conflict(db, "路线标识已存在")
    return route_dict(item)


@app.put("/api/admin/routes/{item_id}")
def update_route(item_id: str, payload: RouteInput, _: Auth, db: Db):
    item = db.get(Route, item_id)
    if not item:
        raise HTTPException(404, "路线不存在")
    values = payload.model_dump()
    if values["content_status"] == "published" and not values["published_at"]:
        values["published_at"] = item.published_at or datetime.now(UTC)
    for key, value in values.items():
        setattr(item, key, value)
    commit_or_conflict(db, "路线标识或字段与现有内容冲突")
    return route_dict(item)


@app.delete("/api/admin/routes/{item_id}", status_code=204)
def delete_route(item_id: str, _: Auth, db: Db):
    item = db.get(Route, item_id)
    if not item:
        raise HTTPException(404, "路线不存在")
    if db.scalar(select(func.count()).select_from(Journey).where(Journey.route_id == item_id)):
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
        statement = statement.where(or_(Stop.title.contains(q), Stop.story_title.contains(q)))
    return [stop_dict(stop, route_title, bool(challenge_id)) for stop, route_title, challenge_id in db.execute(statement)]


@app.post("/api/admin/stops", status_code=201)
def create_stop(payload: StopInput, _: Auth, db: Db):
    if not db.get(Route, payload.route_id):
        raise HTTPException(400, "所选路线不存在")
    item = Stop(id=str(uuid4()), **payload.model_dump())
    db.add(item)
    commit_or_conflict(db, "同一路线中的站点序号不能重复")
    return stop_dict(item)


@app.put("/api/admin/stops/{item_id}")
def update_stop(item_id: str, payload: StopInput, _: Auth, db: Db):
    item = db.get(Stop, item_id)
    if not item:
        raise HTTPException(404, "站点不存在")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    commit_or_conflict(db, "同一路线中的站点序号不能重复")
    return stop_dict(item)


@app.delete("/api/admin/stops/{item_id}", status_code=204)
def delete_stop(item_id: str, _: Auth, db: Db):
    item = db.get(Stop, item_id)
    if not item:
        raise HTTPException(404, "站点不存在")
    if db.scalar(select(func.count()).select_from(JourneyAnswer).where(JourneyAnswer.stop_id == item_id)):
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
    return [challenge_dict(item, stop_title, route_title) for item, stop_title, route_title in db.execute(statement)]


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
        statement = statement.where(or_(MediaAsset.key.contains(q), MediaAsset.storage_path.contains(q)))
    base = str(request.base_url).rstrip("/")
    return [
        {
            "key": item.key,
            "storage_path": item.storage_path,
            "mime_type": item.mime_type,
            "created_at": iso(item.created_at),
            "updated_at": iso(item.updated_at),
            "preview_url": f"{base}/media/{item.storage_path}",
        }
        for item in db.scalars(statement)
    ]


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
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "-", Path(file.filename).name).strip(".-") or "asset"
    asset_key = re.sub(r"[^a-zA-Z0-9_-]", "-", key.strip()).strip("-") or Path(safe_name).stem
    now = datetime.now(UTC)
    folder = Path("uploads") / now.strftime("%Y") / now.strftime("%m")
    storage_path = (folder / f"{uuid4().hex[:10]}-{safe_name}").as_posix()
    destination = (media_root / storage_path).resolve()
    if media_root != destination and media_root not in destination.parents:
        raise HTTPException(400, "非法文件路径")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as target:
        shutil.copyfileobj(file.file, target)
    if destination.stat().st_size > settings.max_upload_mb * 1024 * 1024:
        destination.unlink(missing_ok=True)
        raise HTTPException(413, f"文件不能超过 {settings.max_upload_mb}MB")
    item = db.get(MediaAsset, asset_key)
    if item:
        item.storage_path = storage_path
        item.mime_type = file.content_type
        item.updated_at = now
    else:
        item = MediaAsset(
            key=asset_key,
            storage_path=storage_path,
            mime_type=file.content_type,
            created_at=now,
            updated_at=now,
        )
        db.add(item)
    commit_or_conflict(db, "资源标识或存储路径冲突")
    return {"key": item.key, "storage_path": item.storage_path, "mime_type": item.mime_type}


@app.delete("/api/admin/media/{asset_key}", status_code=204)
def delete_media(asset_key: str, _: Auth, db: Db):
    item = db.get(MediaAsset, asset_key)
    if not item:
        raise HTTPException(404, "媒体资源不存在")
    references = (
        (db.scalar(select(func.count()).select_from(City).where(City.hero_image == item.storage_path)) or 0)
        + (db.scalar(select(func.count()).select_from(Route).where(Route.hero_image == item.storage_path)) or 0)
        + (db.scalar(select(func.count()).select_from(Stop).where(or_(Stop.image == item.storage_path, Stop.audio_url == item.storage_path))) or 0)
    )
    if references:
        raise HTTPException(409, f"该资源正在被 {references} 处内容使用，不能删除")
    candidate = (media_root / item.storage_path).resolve()
    if media_root == candidate or media_root in candidate.parents:
        candidate.unlink(missing_ok=True)
    db.delete(item)
    db.commit()


@app.get("/media/{asset_path:path}")
def serve_media(asset_path: str):
    candidate = (media_root / asset_path).resolve()
    if media_root != candidate and media_root not in candidate.parents:
        raise HTTPException(404)
    if not candidate.is_file():
        raise HTTPException(404)
    return FileResponse(candidate)


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
            city_id = supplied_city_id or db.scalar(select(City.id).where(City.slug == data.slug)) or str(uuid4())
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
                raw["city_id"] = city_ids.get(city_slug) or db.scalar(select(City.id).where(City.slug == city_slug))
            data = RouteInput.model_validate(raw)
            route_id = supplied_route_id or db.scalar(select(Route.id).where(Route.slug == data.slug)) or str(uuid4())
            values = data.model_dump()
            if values["content_status"] == "published" and not values["published_at"]:
                values["published_at"] = datetime.now(UTC)
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
                raw["route_id"] = route_ids.get(route_slug) or db.scalar(select(Route.id).where(Route.slug == route_slug))
            data = StopInput.model_validate(raw)
            stop_id = supplied_stop_id or db.scalar(
                select(Stop.id).where(Stop.route_id == data.route_id, Stop.position == data.position)
            ) or str(uuid4())
            upsert(db, Stop, stop_id, data.model_dump())
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
            existing_id = db.scalar(select(Challenge.id).where(Challenge.stop_id == data.stop_id))
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
