from __future__ import annotations

from sqlalchemy import Engine, inspect, text


PHOTO_GUIDANCE_COLUMNS = (
    "vantage_point",
    "shooting_direction",
    "composition_tip",
)

MAX_EXPERIENCE_TAGS = 8
MAX_EXPERIENCE_TAG_LENGTH = 24


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
