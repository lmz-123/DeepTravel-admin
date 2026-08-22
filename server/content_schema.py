from __future__ import annotations

from sqlalchemy import Engine, inspect, text


PHOTO_GUIDANCE_COLUMNS = (
    "vantage_point",
    "shooting_direction",
    "composition_tip",
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
