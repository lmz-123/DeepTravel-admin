from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class MediaAsset(Base):
    __tablename__ = "media_assets"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    storage_path: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class City(Base):
    __tablename__ = "cities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    subtitle: Mapped[str] = mapped_column(String(160))
    hero_image: Mapped[str] = mapped_column(String(255))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    city_id: Mapped[str] = mapped_column(ForeignKey("cities.id"), index=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(160))
    subtitle: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    distance_km: Mapped[float] = mapped_column(Float)
    difficulty: Mapped[str] = mapped_column(String(40))
    theme: Mapped[str] = mapped_column(String(80))
    hero_image: Mapped[str] = mapped_column(String(255))
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    content_status: Mapped[str] = mapped_column(String(40), default="draft")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Stop(Base):
    __tablename__ = "stops"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    route_id: Mapped[str] = mapped_column(ForeignKey("routes.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(160))
    kicker: Mapped[str] = mapped_column(String(120))
    address: Mapped[str] = mapped_column(String(255))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    arrival_radius_m: Mapped[int] = mapped_column(Integer, default=80)
    story_title: Mapped[str] = mapped_column(String(200))
    story_body: Mapped[str] = mapped_column(Text)
    audio_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image: Mapped[str] = mapped_column(String(255))
    insight: Mapped[str] = mapped_column(Text)


class Challenge(Base):
    __tablename__ = "challenges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    stop_id: Mapped[str] = mapped_column(ForeignKey("stops.id"), unique=True, index=True)
    prompt: Mapped[str] = mapped_column(Text)
    hint: Mapped[str] = mapped_column(Text)
    options_json: Mapped[list[str]] = mapped_column(JSON)
    correct_option: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str] = mapped_column(Text)


class Journey(Base):
    __tablename__ = "journeys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    route_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)


class JourneyAnswer(Base):
    __tablename__ = "journey_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stop_id: Mapped[str] = mapped_column(String(36), index=True)
