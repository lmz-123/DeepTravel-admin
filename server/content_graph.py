from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Any

from content_schema import normalize_experience_tags


def validate_graph(graph: dict[str, Any], media_assets: dict[str, str]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    route = graph.get("route") or {}
    arc = graph.get("story_arc") or {}
    fragments = list(graph.get("fragments") or [])
    sources = list(graph.get("sources") or [])
    claims = list(graph.get("claims") or [])

    def error(path: str, code: str, message: str) -> None:
        errors.append({"path": path, "code": code, "message": message})

    def warning(path: str, code: str, message: str) -> None:
        warnings.append({"path": path, "code": code, "message": message})

    for key in ("id", "slug", "title", "hero_image"):
        if not str(route.get(key) or "").strip():
            error(f"route.{key}", "required", "缺少必填路线字段")
    for key in ("id", "title", "central_question", "complete_story", "script_version"):
        if not str(arc.get(key) or "").strip():
            error(f"story_arc.{key}", "required", "缺少必填故事弧字段")
    if not fragments:
        error("fragments", "required", "碎片路线至少需要一个线索")

    positions = [item.get("position") for item in fragments]
    if positions != list(range(1, len(fragments) + 1)):
        error("fragments", "positions_not_contiguous", "线索顺序必须从 1 连续递增")
    fragment_ids = [str(item.get("id") or "") for item in fragments]
    if any(not item for item in fragment_ids) or len(set(fragment_ids)) != len(fragment_ids):
        error("fragments", "fragment_ids_invalid", "线索标识必须填写且不能重复")

    source_ids = {str(item.get("id") or "") for item in sources}
    claim_ids = {str(item.get("id") or "") for item in claims}
    if len(source_ids) != len(sources) or "" in source_ids:
        error("sources", "source_ids_invalid", "来源标识必须填写且不能重复")
    if len(claim_ids) != len(claims) or "" in claim_ids:
        error("claims", "claim_ids_invalid", "主张标识必须填写且不能重复")
    for index, source in enumerate(sources):
        for key in ("title", "publisher", "url"):
            if not str(source.get(key) or "").strip():
                error(f"sources[{index}].{key}", "required", "来源缺少标题、发布机构或链接")
    for index, claim in enumerate(claims):
        linked = set(map(str, claim.get("source_ids") or []))
        if not str(claim.get("id") or "") or not str(claim.get("canonical_text") or ""):
            error(f"claims[{index}]", "claim_invalid", "史实主张缺少标识或正文")
        if not linked or not linked.issubset(source_ids):
            error(f"claims[{index}].source_ids", "claim_source_missing", "每条主张必须关联有效来源")

    required_missions = int(graph.get("required_photo_mission_count", 0))
    actual_missions = 0
    previous: dict[str, Any] | None = None
    for index, fragment in enumerate(fragments):
        path = f"fragments[{index}]"
        try:
            fragment["experience_tags"] = normalize_experience_tags(
                fragment.get("experience_tags")
            )
        except ValueError as exc:
            error(f"{path}.experience_tags", "experience_tags_invalid", str(exc))
        stop = fragment.get("stop")
        if isinstance(stop, dict):
            try:
                stop["experience_tags"] = normalize_experience_tags(
                    stop.get("experience_tags")
                )
            except ValueError as exc:
                error(
                    f"{path}.stop.experience_tags",
                    "experience_tags_invalid",
                    str(exc),
                )
        for key in ("title", "narration_script", "transcript", "audio_path", "script_version"):
            if not str(fragment.get(key) or "").strip():
                error(f"{path}.{key}", "required", "线索缺少必填内容")
        if fragment.get("narration_script") != fragment.get("transcript"):
            error(f"{path}.transcript", "transcript_mismatch", "旁白必须与文字稿一致")
        if fragment.get("script_version") != arc.get("script_version"):
            error(f"{path}.script_version", "script_version_mismatch", "脚本版本不一致")
        audio = str(fragment.get("audio_path") or "")
        if audio and media_assets.get(audio) is None:
            error(f"{path}.audio_path", "media_missing", "音频资源未登记")
        elif audio and not media_assets[audio].startswith("audio/"):
            error(f"{path}.audio_path", "media_type_invalid", "旁白必须是音频")
        linked_claims = set(map(str, fragment.get("claim_ids") or []))
        if not linked_claims or not linked_claims.issubset(claim_ids):
            error(f"{path}.claim_ids", "fragment_claims_missing", "线索必须关联有效主张")
        for dependency in map(str, fragment.get("dependency_ids") or []):
            if dependency not in fragment_ids[:index]:
                error(f"{path}.dependency_ids", "dependency_invalid", "依赖必须指向前序线索")

        region = fragment.get("trigger_region") or {}
        lat = _number(region.get("latitude"))
        lon = _number(region.get("longitude"))
        entry = _number(region.get("entry_radius_m"))
        exit_radius = _number(region.get("exit_radius_m"))
        max_accuracy = _number(region.get("max_accuracy_m"))
        qualifying_samples = _number(region.get("qualifying_samples"))
        sample_window = _number(region.get("sample_window_seconds"))
        if lat is None or not -90 <= lat <= 90:
            error(f"{path}.trigger_region.latitude", "wgs84_invalid", "纬度无效")
        if lon is None or not -180 <= lon <= 180:
            error(f"{path}.trigger_region.longitude", "wgs84_invalid", "经度无效")
        if entry is None or entry <= 0 or exit_radius is None or exit_radius <= entry:
            error(f"{path}.trigger_region.exit_radius_m", "hysteresis_invalid", "离开半径必须更大")
        if max_accuracy is None or max_accuracy <= 0:
            error(f"{path}.trigger_region.max_accuracy_m", "sampling_invalid", "定位精度阈值必须大于零")
        if qualifying_samples is None or qualifying_samples < 1 or sample_window is None or sample_window <= 0:
            error(f"{path}.trigger_region.qualifying_samples", "sampling_invalid", "定位采样策略无效")
        if str(region.get("coordinate_system") or "").upper().replace("-", "") != "WGS84":
            error(f"{path}.trigger_region.coordinate_system", "coordinate_system_invalid", "运行坐标必须为 WGS-84")
        if not str(region.get("coordinate_source") or "").strip():
            error(f"{path}.trigger_region.coordinate_source", "coordinate_source_missing", "缺少坐标来源")
        if region.get("audit_state") != "reviewed":
            warning(f"{path}.trigger_region.audit_state", "field_review_required", "坐标仍需现场复核")
        if previous and None not in (lat, lon, entry):
            previous_lat = _number(previous.get("latitude"))
            previous_lon = _number(previous.get("longitude"))
            previous_entry = _number(previous.get("entry_radius_m"))
            if None not in (previous_lat, previous_lon, previous_entry):
                if _distance_m(lat, lon, previous_lat, previous_lon) <= entry + previous_entry + 30:
                    error(f"{path}.trigger_region", "trigger_regions_overlap", "相邻触发范围安全间距不足")
        previous = region

        mission = fragment.get("photo_mission")
        if mission:
            actual_missions += int(bool(mission.get("required")))
            for key in ("prompt", "field_subject", "safety_copy", "accessibility_alternative"):
                if not str(mission.get(key) or "").strip():
                    error(f"{path}.photo_mission.{key}", "required", "照片任务缺少安全说明")
            guidance_labels = {
                "vantage_point": "安全站位 / 经典机位",
                "shooting_direction": "拍摄朝向",
                "composition_tip": "构图建议",
            }
            for key, label in guidance_labels.items():
                if not str(mission.get(key) or "").strip():
                    error(
                        f"{path}.photo_mission.{key}",
                        "photo_guidance_required",
                        f"照片留念缺少{label}",
                    )

    if actual_missions != required_missions:
        error("required_photo_mission_count", "mission_count_mismatch", "必做照片任务数量不匹配")
    cover = str(route.get("hero_image") or "")
    if cover and media_assets.get(cover) is None:
        error("route.hero_image", "media_missing", "路线封面未登记")
    elif cover and not media_assets[cover].startswith("image/"):
        error("route.hero_image", "media_type_invalid", "路线封面必须是图片")

    causal = list(arc.get("causal_model") or [])
    causal_ids = [str(item.get("id") or "") if isinstance(item, dict) else "" for item in causal]
    causal_text = [str(item.get("text") or "") if isinstance(item, dict) else str(item) for item in causal]
    if len(causal) != len(fragments):
        error("story_arc.causal_model", "causal_count_mismatch", "因果项数量必须与线索一致")
    if any(not value for value in causal_ids + causal_text) or len(set(causal_ids)) != len(causal_ids) or len(set(causal_text)) != len(causal_text):
        error("story_arc.causal_model", "causal_items_invalid", "因果项标识与文字必须唯一")
    if arc.get("review_state") != "reviewed":
        warning("story_arc.review_state", "editorial_review_required", "故事内容仍待审核")
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth = 6_371_000.0
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    value = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * earth * asin(sqrt(value))
