from __future__ import annotations

from sqlalchemy import Engine, inspect, text


PHOTO_GUIDANCE_COLUMNS = (
    "vantage_point",
    "shooting_direction",
    "composition_tip",
)

MAX_EXPERIENCE_TAGS = 8
MAX_EXPERIENCE_TAG_LENGTH = 24
MAX_FOOTPRINT_SUMMARY_OPTIONS = 8
MAX_FOOTPRINT_SUMMARY_OPTION_LENGTH = 160
MAX_FOOTPRINT_EDITORIAL_SUMMARY_LENGTH = 600


def normalize_experience_tags(values: object) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list | tuple):
        raise ValueError("体验标签必须是字符串数组")
    result: list[str] = []
    for raw in values:
        if not isinstance(raw, str):
            raise ValueError("体验标签必须是字符串数组")
        value = raw.strip()
        if not value or value in result:
            continue
        if len(value) > MAX_EXPERIENCE_TAG_LENGTH:
            raise ValueError(f"每个体验标签最多 {MAX_EXPERIENCE_TAG_LENGTH} 个字符")
        result.append(value)
    if len(result) > MAX_EXPERIENCE_TAGS:
        raise ValueError(f"体验标签最多 {MAX_EXPERIENCE_TAGS} 个")
    return result


def normalize_footprint_summary_options(values: object) -> list[dict[str, str]]:
    if values is None:
        return []
    if not isinstance(values, list | tuple):
        raise ValueError("足迹概括选项必须是对象数组")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, raw in enumerate(values):
        if isinstance(raw, str):
            identity = f"option-{index + 1}"
            text_value = raw
        elif isinstance(raw, dict):
            identity = str(raw.get("id") or "").strip()
            text_value = raw.get("text")
        else:
            raise ValueError("每个足迹概括选项必须包含稳定 id 和文字")
        text_value = str(text_value or "").strip()
        if not identity or not text_value:
            raise ValueError("每个足迹概括选项必须包含稳定 id 和文字")
        if identity in seen:
            raise ValueError("足迹概括选项 id 不能重复")
        if len(identity) > 80:
            raise ValueError("足迹概括选项 id 最多 80 个字符")
        if len(text_value) > MAX_FOOTPRINT_SUMMARY_OPTION_LENGTH:
            raise ValueError(
                f"每个足迹概括选项最多 {MAX_FOOTPRINT_SUMMARY_OPTION_LENGTH} 个字符"
            )
        seen.add(identity)
        result.append({"id": identity, "text": text_value})
    if len(result) > MAX_FOOTPRINT_SUMMARY_OPTIONS:
        raise ValueError(f"足迹概括选项最多 {MAX_FOOTPRINT_SUMMARY_OPTIONS} 个")
    return result


def ensure_footprint_content_schema(engine: Engine) -> None:
    """Keep local admin development compatible before the API migration is applied."""
    inspector = inspect(engine)
    if "story_fragments" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("story_fragments")}
    with engine.begin() as connection:
        if "footprint_editorial_summary" not in existing:
            connection.execute(
                text(
                    "ALTER TABLE story_fragments ADD COLUMN footprint_editorial_summary TEXT NULL"
                )
            )
        if "footprint_summary_options_json" not in existing:
            connection.execute(
                text(
                    "ALTER TABLE story_fragments ADD COLUMN footprint_summary_options_json JSON NULL"
                )
            )


def ensure_photo_mission_guidance_schema(engine: Engine) -> None:
    """Add nullable guidance fields without blocking legacy content rows."""
    inspector = inspect(engine)
    if "photo_missions" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("photo_missions")}
    missing = [name for name in PHOTO_GUIDANCE_COLUMNS if name not in existing]
    if not missing:
        return
    with engine.begin() as connection:
        for column in missing:
            connection.execute(
                text(f"ALTER TABLE photo_missions ADD COLUMN {column} TEXT NULL")
            )
