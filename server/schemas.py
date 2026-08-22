from __future__ import annotations

from datetime import datetime

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CityInput(BaseModel):
    slug: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    subtitle: str = Field(min_length=1, max_length=160)
    hero_image: str = Field(min_length=1, max_length=255)
    latitude: float
    longitude: float


class RouteInput(BaseModel):
    city_id: str
    slug: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=160)
    subtitle: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    duration_minutes: int = Field(gt=0)
    distance_km: float = Field(gt=0)
    difficulty: str = Field(min_length=1, max_length=40)
    theme: str = Field(min_length=1, max_length=80)
    hero_image: str = Field(min_length=1, max_length=255)
    is_featured: bool = False
    content_status: Literal["draft", "in_review", "verified", "published", "archived"] = "draft"
    published_at: datetime | None = None


class StopInput(BaseModel):
    route_id: str
    position: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=160)
    kicker: str = Field(min_length=1, max_length=120)
    address: str = Field(min_length=1, max_length=255)
    latitude: float
    longitude: float
    arrival_radius_m: int = Field(default=80, gt=0)
    story_title: str = Field(min_length=1, max_length=200)
    story_body: str = Field(min_length=1)
    audio_url: str | None = Field(default=None, max_length=500)
    image: str = Field(min_length=1, max_length=255)
    insight: str = Field(min_length=1)


class ChallengeInput(BaseModel):
    stop_id: str
    prompt: str = Field(min_length=1)
    hint: str = Field(min_length=1)
    options: list[str]
    correct_option: int = Field(ge=0)
    explanation: str = Field(min_length=1)

    @field_validator("options")
    @classmethod
    def validate_options(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if len(cleaned) < 2:
            raise ValueError("至少需要两个选项")
        return cleaned


class ImportBundle(BaseModel):
    cities: list[dict] = []
    routes: list[dict] = []
    stops: list[dict] = []
    challenges: list[dict] = []


class ClientLogInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurred_at: datetime
    level: str = Field(default="info", min_length=1, max_length=20)
    category: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=32_000)
    session_id: str = Field(min_length=1, max_length=120)
    app_version: str = Field(min_length=1, max_length=80)
    platform: str = Field(min_length=1, max_length=40)
    source: str = Field(default="deeptravel-flutter", min_length=1, max_length=120)
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at 必须包含时区")
        return value


class ClientLogBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[ClientLogInput] = Field(min_length=1, max_length=50)
