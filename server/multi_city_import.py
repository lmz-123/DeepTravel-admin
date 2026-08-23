from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from content_schema import normalize_footprint_summary_options
from models import (
    City,
    ContentImportBatch,
    ContentImportPreview,
    MediaAsset,
    Route,
    RoutePretripGuidance,
    Stop,
    StoryArc,
    StoryCatalogItem,
    StoryCatalogVariant,
    StoryFragment,
    StoryPlacement,
)
from schemas import CityInput, RouteInput, StopInput

SCHEMA_VERSION = "1.0"
MAX_PACKAGE_BYTES = 2 * 1024 * 1024
MAX_ENTITIES = 5_000
PREVIEW_TTL_MINUTES = 15
COLLECTIONS = (
    "cities",
    "routes",
    "stops",
    "story_arcs",
    "story_fragments",
    "catalog_items",
    "variants",
    "placements",
    "pretrip_guidance",
    "media",
)


@dataclass(frozen=True)
class PackageProblem:
    path: str
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "code": self.code, "message": self.message}


class PackageValidationError(ValueError):
    def __init__(self, problems: list[PackageProblem]):
        super().__init__("内容包校验失败")
        self.problems = problems


MODEL_BY_COLLECTION = {
    "cities": City,
    "routes": Route,
    "stops": Stop,
    "story_arcs": StoryArc,
    "story_fragments": StoryFragment,
    "catalog_items": StoryCatalogItem,
    "variants": StoryCatalogVariant,
    "placements": StoryPlacement,
    "pretrip_guidance": RoutePretripGuidance,
}

IDENTITY_FIELD = {
    "cities": "id",
    "routes": "id",
    "stops": "id",
    "story_arcs": "id",
    "story_fragments": "id",
    "catalog_items": "id",
    "variants": "id",
    "placements": "id",
    "pretrip_guidance": "route_id",
}

REQUIRED_FIELDS = {
    "cities": ("id", "slug", "name", "subtitle", "hero_image", "latitude", "longitude"),
    "routes": (
        "id",
        "city_id",
        "slug",
        "title",
        "subtitle",
        "description",
        "duration_minutes",
        "distance_km",
        "difficulty",
        "theme",
        "hero_image",
    ),
    "stops": (
        "id",
        "route_id",
        "position",
        "title",
        "kicker",
        "address",
        "latitude",
        "longitude",
        "story_title",
        "story_body",
        "image",
        "insight",
    ),
    "story_arcs": (
        "id",
        "route_id",
        "title",
        "central_question",
        "complete_story",
        "script_version",
    ),
    "story_fragments": (
        "id",
        "arc_id",
        "position",
        "title",
        "narration_script",
        "transcript",
        "audio_path",
        "script_version",
    ),
    "catalog_items": (
        "id",
        "city_id",
        "source_kind",
        "source_id",
        "canonical_revision",
        "title",
        "summary",
        "cover_image",
        "content_type",
        "place_context",
        "observable_detail",
        "sources",
    ),
    "variants": (
        "id",
        "catalog_item_id",
        "role",
        "source_kind",
        "source_id",
        "track_kind",
        "track_id",
        "transcript_hash",
        "script_version",
    ),
    "placements": ("id", "catalog_item_id", "channel", "variant_role"),
    "pretrip_guidance": ("route_id",),
}


def canonical_checksum(package: dict[str, Any]) -> str:
    canonical = dict(package)
    canonical.pop("package_checksum", None)
    encoded = json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def parse_package(payload: bytes) -> dict[str, Any]:
    if len(payload) > MAX_PACKAGE_BYTES:
        raise PackageValidationError(
            [PackageProblem("/", "package_too_large", "JSON 文件不能超过 2 MB")]
        )
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackageValidationError(
            [PackageProblem("/", "invalid_json", f"JSON 无法解析：{exc}")]
        ) from exc
    if not isinstance(value, dict):
        raise PackageValidationError(
            [PackageProblem("/", "invalid_type", "内容包根节点必须是对象")]
        )
    return value


def normalize_package(package: dict[str, Any]) -> dict[str, Any]:
    problems: list[PackageProblem] = []
    normalized: dict[str, Any] = {
        "schema_version": str(package.get("schema_version") or ""),
        "package_id": str(package.get("package_id") or "").strip(),
        "package_version": str(package.get("package_version") or "").strip(),
    }
    if normalized["schema_version"] != SCHEMA_VERSION:
        problems.append(
            PackageProblem(
                "/schema_version",
                "unsupported_schema",
                f"仅支持 schema_version={SCHEMA_VERSION}",
            )
        )
    for field in ("package_id", "package_version"):
        if not normalized[field]:
            problems.append(PackageProblem(f"/{field}", "required", "字段不能为空"))

    entities = package.get("entities", package)
    if not isinstance(entities, dict):
        problems.append(
            PackageProblem("/entities", "invalid_type", "entities 必须是对象")
        )
        entities = {}
    total = 0
    for collection in COLLECTIONS:
        raw_items = entities.get(collection, [])
        if not isinstance(raw_items, list):
            problems.append(
                PackageProblem(
                    f"/entities/{collection}", "invalid_type", "字段必须是数组"
                )
            )
            raw_items = []
        total += len(raw_items)
        normalized[collection] = []
        for index, raw in enumerate(raw_items):
            path = f"/entities/{collection}/{index}"
            if not isinstance(raw, dict):
                problems.append(PackageProblem(path, "invalid_type", "记录必须是对象"))
                continue
            if _contains_embedded_media(raw):
                problems.append(
                    PackageProblem(
                        path, "embedded_media", "不允许 base64、data URI 或二进制媒体"
                    )
                )
                continue
            if collection == "media" and any(
                isinstance(raw.get(field), str)
                and str(raw[field]).lower().startswith(("http://", "https://"))
                for field in ("url", "storage_path", "object_key")
            ):
                problems.append(
                    PackageProblem(
                        path,
                        "remote_media",
                        "媒体描述只能引用已上传的受管媒体 key，不能请求远程下载",
                    )
                )
                continue
            normalized[collection].append(dict(raw))
    if total > MAX_ENTITIES:
        problems.append(
            PackageProblem(
                "/entities", "too_many_entities", f"记录总数不能超过 {MAX_ENTITIES}"
            )
        )

    supplied = str(package.get("package_checksum") or "").strip()
    calculated = canonical_checksum(package)
    if supplied and not hmac.compare_digest(supplied, calculated):
        problems.append(
            PackageProblem(
                "/package_checksum", "checksum_mismatch", "内容包校验和不匹配"
            )
        )
    normalized["package_checksum"] = calculated
    if problems:
        raise PackageValidationError(problems)
    return normalized


def build_preview(db: Session, normalized: dict[str, Any]) -> dict[str, Any]:
    problems = _validate_graph(db, normalized)
    changes: list[dict[str, Any]] = []
    target_revisions: dict[str, str] = {}
    counts = {
        key: 0 for key in ("new", "updated", "unchanged", "conflicted", "invalid")
    }

    imported = db.scalar(
        select(ContentImportBatch).where(
            ContentImportBatch.package_id == normalized["package_id"],
            ContentImportBatch.package_version == normalized["package_version"],
        )
    )
    if (
        imported is not None
        and imported.package_checksum != normalized["package_checksum"]
    ):
        problems.append(
            PackageProblem(
                "/package_checksum",
                "package_conflict",
                "相同 package_id/package_version 已用于不同内容",
            )
        )
        counts["conflicted"] += 1

    for collection, model in MODEL_BY_COLLECTION.items():
        identity_field = IDENTITY_FIELD[collection]
        for index, record in enumerate(normalized[collection]):
            path = f"/entities/{collection}/{index}"
            record_problems = _record_problems(collection, record, path)
            if record_problems:
                problems.extend(record_problems)
                changes.append(
                    _change(
                        collection,
                        str(record.get(identity_field) or ""),
                        "invalid",
                        path,
                        record_problems,
                    )
                )
                counts["invalid"] += 1
                continue
            identity = str(record.get(identity_field) or "").strip()
            if not identity:
                problem = PackageProblem(
                    f"{path}/{identity_field}", "required", "稳定标识不能为空"
                )
                problems.append(problem)
                changes.append(
                    _change(collection, identity, "invalid", path, [problem])
                )
                counts["invalid"] += 1
                continue
            existing = db.get(model, identity)
            revision_key = f"{collection}:{identity}"
            revision = _revision(existing)
            target_revisions[revision_key] = revision
            if existing is None:
                status = "new"
                fields = sorted(record)
            else:
                fields = _changed_fields(existing, record)
                status = "updated" if fields else "unchanged"
            changes.append(_change(collection, identity, status, path, [], fields))
            counts[status] += 1

    for index, media in enumerate(normalized["media"]):
        path = f"/entities/media/{index}"
        key = str(media.get("key") or "").strip()
        existing = db.get(MediaAsset, key) if key else None
        media_problems: list[PackageProblem] = []
        if not key:
            media_problems.append(
                PackageProblem(f"{path}/key", "required", "媒体 key 不能为空")
            )
        elif existing is None:
            media_problems.append(
                PackageProblem(
                    f"{path}/key", "missing_media", "媒体必须先上传到受管媒体库"
                )
            )
        elif (
            media.get("checksum_sha256")
            and media["checksum_sha256"] != existing.checksum_sha256
        ):
            media_problems.append(
                PackageProblem(
                    f"{path}/checksum_sha256", "media_checksum", "媒体校验和不一致"
                )
            )
        status = "invalid" if media_problems else "unchanged"
        counts[status] += 1
        changes.append(_change("media", key, status, path, media_problems))
        problems.extend(media_problems)

    return {
        "package": normalized,
        "counts": counts,
        "changes": changes,
        "problems": [item.as_dict() for item in problems],
        "target_revisions": target_revisions,
        "can_confirm": not problems,
    }


def persist_preview(
    db: Session, plan: dict[str, Any], *, editor_id: str, secret: str
) -> tuple[ContentImportPreview, str]:
    now = datetime.now(UTC)
    preview = ContentImportPreview(
        id=str(uuid4()),
        package_id=plan["package"]["package_id"],
        package_version=plan["package"]["package_version"],
        package_checksum=plan["package"]["package_checksum"],
        editor_id=editor_id,
        status="ready" if plan["can_confirm"] else "invalid",
        plan_json={
            key: value for key, value in plan.items() if key != "target_revisions"
        },
        target_revisions_json=plan["target_revisions"],
        expires_at=now + timedelta(minutes=PREVIEW_TTL_MINUTES),
        created_at=now,
    )
    db.add(preview)
    db.flush()
    return preview, _token(preview, secret)


def confirm_preview(
    db: Session, *, token: str, editor_id: str, secret: str
) -> dict[str, Any]:
    preview_id = token.split(".", 1)[0]
    preview = db.get(ContentImportPreview, preview_id)
    if preview is None or not hmac.compare_digest(token, _token(preview, secret)):
        raise PackageValidationError(
            [PackageProblem("/confirmation_token", "invalid_token", "确认令牌无效")]
        )
    now = datetime.now(UTC)
    expires_at = preview.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if preview.editor_id != editor_id or preview.status != "ready" or expires_at <= now:
        raise PackageValidationError(
            [
                PackageProblem(
                    "/confirmation_token",
                    "expired_or_forbidden",
                    "确认令牌已过期或不可用",
                )
            ]
        )

    existing_batch = db.scalar(
        select(ContentImportBatch).where(
            ContentImportBatch.package_id == preview.package_id,
            ContentImportBatch.package_version == preview.package_version,
        )
    )
    if existing_batch is not None:
        if existing_batch.package_checksum != preview.package_checksum:
            raise PackageValidationError(
                [
                    PackageProblem(
                        "/package_checksum",
                        "package_conflict",
                        "相同版本已导入不同内容",
                    )
                ]
            )
        preview.status = "confirmed"
        return {**existing_batch.result_json, "replayed": True}

    stale = _stale_targets(db, preview.target_revisions_json)
    if stale:
        raise PackageValidationError(
            [
                PackageProblem(path, "stale_target", "预检后目标内容已发生变化")
                for path in stale
            ]
        )

    package = preview.plan_json["package"]
    result = _apply_package(db, package)
    batch = ContentImportBatch(
        id=str(uuid4()),
        package_id=preview.package_id,
        package_version=preview.package_version,
        package_checksum=preview.package_checksum,
        editor_id=editor_id,
        status="completed",
        result_json=result,
        created_at=now,
        completed_at=now,
    )
    preview.status = "confirmed"
    db.add(batch)
    db.flush()
    return result


def _validate_graph(db: Session, package: dict[str, Any]) -> list[PackageProblem]:
    problems: list[PackageProblem] = []
    ids = {
        collection: {
            str(item.get(IDENTITY_FIELD[collection]) or "")
            for item in package[collection]
        }
        for collection in MODEL_BY_COLLECTION
    }
    city_ids = ids["cities"] | set(db.scalars(select(City.id)))
    route_ids = ids["routes"] | set(db.scalars(select(Route.id)))
    arc_ids = ids["story_arcs"] | set(db.scalars(select(StoryArc.id)))
    catalog_ids = ids["catalog_items"] | set(db.scalars(select(StoryCatalogItem.id)))

    for index, item in enumerate(package["routes"]):
        if item.get("city_id") not in city_ids:
            problems.append(_missing_relation("routes", index, "city_id"))
    for index, item in enumerate(package["stops"]):
        if item.get("route_id") not in route_ids:
            problems.append(_missing_relation("stops", index, "route_id"))
    for index, item in enumerate(package["story_arcs"]):
        if item.get("route_id") not in route_ids:
            problems.append(_missing_relation("story_arcs", index, "route_id"))
    for index, item in enumerate(package["story_fragments"]):
        if item.get("arc_id") not in arc_ids:
            problems.append(_missing_relation("story_fragments", index, "arc_id"))
    for index, item in enumerate(package["catalog_items"]):
        if item.get("city_id") not in city_ids:
            problems.append(_missing_relation("catalog_items", index, "city_id"))
        if item.get("source_kind") not in {"story_arc", "story_fragment"}:
            problems.append(
                PackageProblem(
                    f"/entities/catalog_items/{index}/source_kind",
                    "invalid_source_kind",
                    "仅支持 story_arc 或 story_fragment",
                )
            )
    for collection in ("variants", "placements"):
        for index, item in enumerate(package[collection]):
            if item.get("catalog_item_id") not in catalog_ids:
                problems.append(_missing_relation(collection, index, "catalog_item_id"))
    for index, item in enumerate(package["pretrip_guidance"]):
        if item.get("route_id") not in route_ids:
            problems.append(_missing_relation("pretrip_guidance", index, "route_id"))
        theme_id = item.get("theme_story_catalog_id")
        if theme_id and theme_id not in catalog_ids:
            problems.append(
                _missing_relation("pretrip_guidance", index, "theme_story_catalog_id")
            )
    return problems


def _apply_package(db: Session, package: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for collection, model in MODEL_BY_COLLECTION.items():
        count = 0
        for raw in package[collection]:
            values = _values(collection, raw)
            identity_field = IDENTITY_FIELD[collection]
            identity = str(values[identity_field])
            item = db.get(model, identity)
            if item is None:
                item = model(**values)
                db.add(item)
            else:
                for key, value in values.items():
                    if key == "created_at":
                        continue
                    setattr(item, key, value)
            count += 1
        counts[collection] = count
        db.flush()
    return {"message": "内容包已写入草稿区", "imported": counts, "replayed": False}


def _values(collection: str, raw: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(UTC)
    values = dict(raw)
    if collection == "cities":
        identity = values.pop("id")
        return {"id": identity, **CityInput.model_validate(values).model_dump()}
    if collection == "routes":
        identity = values.pop("id")
        validated = RouteInput.model_validate(values).model_dump()
        return {
            "id": identity,
            **validated,
            "content_status": "draft",
            "published_at": None,
        }
    if collection == "stops":
        identity = values.pop("id")
        validated = StopInput.model_validate(values).model_dump()
        validated["experience_tags_json"] = validated.pop("experience_tags")
        return {"id": identity, **validated}
    if collection == "story_fragments":
        values["footprint_summary_options"] = normalize_footprint_summary_options(
            values.get("footprint_summary_options")
        )

    aliases = {
        "catalog_items": {
            "themes": "themes_json",
            "point_ids": "point_ids_json",
            "related_stories": "related_stories_json",
            "sources": "sources_json",
        },
        "pretrip_guidance": {
            "story_directions": "story_directions_json",
            "companion_tags": "companion_tags_json",
            "safety_tips": "safety_tips_json",
            "rest_tips": "rest_tips_json",
            "accessibility_tips": "accessibility_tips_json",
            "weather_tips": "weather_tips_json",
            "offline_roles": "offline_roles_json",
        },
        "story_arcs": {
            "causal_model": "causal_model_json",
            "pronunciation_notes": "pronunciation_notes_json",
        },
        "story_fragments": {
            "experience_tags": "experience_tags_json",
            "footprint_summary_options": "footprint_summary_options_json",
        },
    }
    for source, target in aliases.get(collection, {}).items():
        if source in values:
            values[target] = values.pop(source)
    for key in ("status", "review_status", "review_state", "publication_decision"):
        if key in values:
            values[key] = "draft" if key == "status" else "in_review"
    if collection == "catalog_items":
        values.update(
            status="draft",
            review_status="in_review",
            published_at=None,
            reviewed_at=None,
            updated_at=now,
            created_at=values.get("created_at") or now,
        )
    elif collection in {"variants", "placements"}:
        if collection == "placements":
            values["starts_at"] = _datetime(values.get("starts_at"))
            values["ends_at"] = _datetime(values.get("ends_at"))
        values.update(
            status="draft",
            published_at=None,
            reviewed_at=None,
            updated_at=now,
            created_at=values.get("created_at") or now,
        )
    elif collection == "pretrip_guidance":
        values.update(
            status="draft", published_at=None, reviewed_at=None, updated_at=now
        )
    elif collection == "story_arcs":
        values.update(review_state="in_review", publication_decision=None)
    elif collection == "story_fragments":
        values.update(review_state="in_review")
    return values


def _contains_embedded_media(value: Any) -> bool:
    if isinstance(value, str):
        lowered = value.lower()
        return lowered.startswith("data:") or "base64," in lowered
    if isinstance(value, list):
        return any(_contains_embedded_media(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_embedded_media(item) for item in value.values())
    return isinstance(value, (bytes, bytearray))


def _datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise ValueError("时间字段必须是 ISO 8601 字符串")


def _record_problems(
    collection: str, record: dict[str, Any], path: str
) -> list[PackageProblem]:
    problems = [
        PackageProblem(f"{path}/{field}", "required", "字段不能为空")
        for field in REQUIRED_FIELDS[collection]
        if field not in record
        or record[field] is None
        or (isinstance(record[field], (str, list, dict)) and not record[field])
    ]
    if problems:
        return problems
    try:
        _values(collection, record)
    except (KeyError, TypeError, ValueError) as exc:
        problems.append(PackageProblem(path, "invalid_record", str(exc)))
    return problems


def _revision(item: Any | None) -> str:
    if item is None:
        return "missing"
    value = getattr(item, "updated_at", None) or getattr(item, "version", None)
    if isinstance(value, datetime):
        return value.isoformat()
    payload = {
        column.name: getattr(item, column.name)
        for column in item.__table__.columns
        if column.name not in {"created_at", "updated_at"}
    }
    return hashlib.sha256(
        json.dumps(payload, default=str, sort_keys=True).encode()
    ).hexdigest()


def _stale_targets(db: Session, snapshots: dict[str, str]) -> list[str]:
    stale: list[str] = []
    for key, expected in snapshots.items():
        collection, identity = key.split(":", 1)
        current = _revision(db.get(MODEL_BY_COLLECTION[collection], identity))
        if not hmac.compare_digest(current, expected):
            stale.append(f"/entities/{collection}/{identity}")
    return stale


def _changed_fields(item: Any, record: dict[str, Any]) -> list[str]:
    comparable = _values_preview(item.__tablename__, record)
    return sorted(
        key
        for key, value in comparable.items()
        if hasattr(item, key) and getattr(item, key) != value
    )


def _values_preview(table_name: str, record: dict[str, Any]) -> dict[str, Any]:
    collection = {
        "story_catalog_items": "catalog_items",
        "story_catalog_variants": "variants",
        "story_placements": "placements",
        "route_pretrip_guidance": "pretrip_guidance",
    }.get(table_name, table_name)
    values = dict(record)
    aliases = {
        "catalog_items": {"themes": "themes_json", "point_ids": "point_ids_json"},
        "pretrip_guidance": {"companion_tags": "companion_tags_json"},
        "stops": {"experience_tags": "experience_tags_json"},
        "story_fragments": {
            "experience_tags": "experience_tags_json",
            "footprint_summary_options": "footprint_summary_options_json",
        },
    }
    for source, target in aliases.get(collection, {}).items():
        if source in values:
            values[target] = values.pop(source)
    return values


def _token(preview: ContentImportPreview, secret: str) -> str:
    expires_at = preview.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    message = ":".join(
        (
            preview.id,
            preview.editor_id,
            preview.package_checksum,
            expires_at.isoformat(),
        )
    )
    signature = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return f"{preview.id}.{signature}"


def _change(
    collection: str,
    identity: str,
    status: str,
    path: str,
    problems: list[PackageProblem],
    fields: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "entity": collection,
        "id": identity,
        "status": status,
        "path": path,
        "changed_fields": fields or [],
        "problems": [item.as_dict() for item in problems],
    }


def _missing_relation(collection: str, index: int, field: str) -> PackageProblem:
    return PackageProblem(
        f"/entities/{collection}/{index}/{field}",
        "missing_relation",
        "关联记录不存在于内容包或数据库",
    )
