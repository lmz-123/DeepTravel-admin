from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Double,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class MediaAsset(Base):
    __tablename__ = "media_assets"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    storage_path: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    storage_provider: Mapped[str] = mapped_column(String(20), default="local")
    object_key: Mapped[str | None] = mapped_column(
        String(500), nullable=True, index=True
    )
    canonical_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    visibility: Mapped[str] = mapped_column(String(20), default="public")
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NarrationPreview(Base):
    __tablename__ = "narration_previews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fragment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("story_fragments.id"), index=True
    )
    profile_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("narration_voice_profiles.id"), nullable=True, index=True
    )
    transcript_hash: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(80))
    voice_id: Mapped[str] = mapped_column(String(120))
    emotion: Mapped[str] = mapped_column(String(40), default="neutral")
    speed: Mapped[float] = mapped_column(Float, default=1.0)
    pitch: Mapped[int] = mapped_column(Integer, default=0)
    pronunciation_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class City(Base):
    __tablename__ = "cities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    subtitle: Mapped[str] = mapped_column(String(160))
    hero_image: Mapped[str] = mapped_column(String(255))
    latitude: Mapped[float] = mapped_column(Double)
    longitude: Mapped[float] = mapped_column(Double)


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
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    managed_package_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True, index=True
    )
    managed_package_version: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )


class Stop(Base):
    __tablename__ = "stops"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    route_id: Mapped[str] = mapped_column(ForeignKey("routes.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(160))
    kicker: Mapped[str] = mapped_column(String(120))
    address: Mapped[str] = mapped_column(String(255))
    latitude: Mapped[float] = mapped_column(Double)
    longitude: Mapped[float] = mapped_column(Double)
    arrival_radius_m: Mapped[int] = mapped_column(Integer, default=80)
    story_title: Mapped[str] = mapped_column(String(200))
    story_body: Mapped[str] = mapped_column(Text)
    audio_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image: Mapped[str] = mapped_column(String(255))
    insight: Mapped[str] = mapped_column(Text)
    experience_tags_json: Mapped[list[str]] = mapped_column(JSON, default=list)


class Challenge(Base):
    __tablename__ = "challenges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    stop_id: Mapped[str] = mapped_column(
        ForeignKey("stops.id"), unique=True, index=True
    )
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


class HistoricalSource(Base):
    __tablename__ = "historical_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    publisher: Mapped[str] = mapped_column(String(160))
    url: Mapped[str] = mapped_column(String(800))
    source_type: Mapped[str] = mapped_column(String(40), default="government")
    accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    review_state: Mapped[str] = mapped_column(String(40), default="in_review")
    summary: Mapped[str] = mapped_column(Text)


class HistoricalClaim(Base):
    __tablename__ = "historical_claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    canonical_text: Mapped[str] = mapped_column(Text)
    claim_kind: Mapped[str] = mapped_column(String(40))
    certainty: Mapped[str] = mapped_column(String(40), default="documented")
    review_state: Mapped[str] = mapped_column(String(40), default="in_review")
    boundary_note: Mapped[str] = mapped_column(Text, default="")
    supersedes_claim_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ClaimSource(Base):
    __tablename__ = "claim_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claim_id: Mapped[str] = mapped_column(String(36), index=True)
    source_id: Mapped[str] = mapped_column(String(36), index=True)
    support_note: Mapped[str] = mapped_column(Text)


class StoryArc(Base):
    __tablename__ = "story_arcs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    route_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    central_question: Mapped[str] = mapped_column(Text)
    complete_story: Mapped[str] = mapped_column(Text)
    causal_model_json: Mapped[list[dict | str]] = mapped_column(JSON)
    pronunciation_notes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    script_version: Mapped[str] = mapped_column(String(40))
    review_state: Mapped[str] = mapped_column(String(40), default="in_review")
    field_audit_state: Mapped[str] = mapped_column(String(40), default="required")
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    publication_decision: Mapped[str | None] = mapped_column(String(40), nullable=True)

    story_narration_tracks: Mapped[list[StoryNarrationTrack]] = relationship(
        back_populates="arc", cascade="all, delete-orphan"
    )
    home_story_publication: Mapped[HomeStoryPublication | None] = relationship(
        back_populates="arc", cascade="all, delete-orphan", uselist=False
    )


class StoryFragment(Base):
    __tablename__ = "story_fragments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    arc_id: Mapped[str] = mapped_column(String(36), index=True)
    stop_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    safe_preview: Mapped[str] = mapped_column(Text)
    narration_script: Mapped[str] = mapped_column(Text)
    transcript: Mapped[str] = mapped_column(Text)
    audio_path: Mapped[str] = mapped_column(String(500))
    audio_mime_type: Mapped[str] = mapped_column(String(80), default="audio/mpeg")
    audio_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    script_version: Mapped[str] = mapped_column(String(40))
    interaction_type: Mapped[str] = mapped_column(String(40))
    completion_threshold: Mapped[float] = mapped_column(Float, default=0.9)
    key_claim: Mapped[str] = mapped_column(Text)
    answers_question: Mapped[str] = mapped_column(Text)
    raises_question: Mapped[str] = mapped_column(Text)
    authenticity_label: Mapped[str] = mapped_column(String(80), default="interpretive")
    review_state: Mapped[str] = mapped_column(String(40), default="in_review")
    experience_tags_json: Mapped[list[str]] = mapped_column(JSON, default=list)


class NarrationVoiceProfile(Base):
    __tablename__ = "narration_voice_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(500), default="")
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(80))
    voice_id: Mapped[str] = mapped_column(String(120))
    emotion: Mapped[str] = mapped_column(String(40), default="neutral")
    speed: Mapped[float] = mapped_column(Float, default=1.0)
    pitch: Mapped[int] = mapped_column(Integer, default=0)
    preview_media_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class FragmentNarrationTrack(Base):
    __tablename__ = "fragment_narration_tracks"
    __table_args__ = (
        UniqueConstraint(
            "fragment_id",
            "profile_id",
            "transcript_hash",
            "script_version",
            name="uq_fragment_voice_script",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fragment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("story_fragments.id"), index=True
    )
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("narration_voice_profiles.id"), index=True
    )
    transcript_hash: Mapped[str] = mapped_column(String(64), index=True)
    script_version: Mapped[str] = mapped_column(String(40))
    media_path: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(80), default="audio/mpeg")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generation_metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class StoryNarrationTrack(Base):
    __tablename__ = "story_narration_tracks"
    __table_args__ = (
        UniqueConstraint(
            "arc_id",
            "profile_id",
            "transcript_hash",
            "script_version",
            name="uq_story_voice_script",
        ),
        Index("ix_story_narration_tracks_hash_status", "transcript_hash", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    arc_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("story_arcs.id"), index=True
    )
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("narration_voice_profiles.id"), index=True
    )
    transcript_hash: Mapped[str] = mapped_column(String(64), index=True)
    script_version: Mapped[str] = mapped_column(String(40))
    media_path: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(80), default="audio/mpeg")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generation_metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    arc: Mapped[StoryArc] = relationship(back_populates="story_narration_tracks")


class HomeStoryPublication(Base):
    __tablename__ = "home_story_publications"
    __table_args__ = (
        Index(
            "ix_home_story_publications_status_weight",
            "status",
            "selection_weight",
            "published_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    arc_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("story_arcs.id"), unique=True, index=True
    )
    selected_track_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("story_narration_tracks.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    introduction: Mapped[str] = mapped_column(Text)
    cover_image: Mapped[str] = mapped_column(String(500))
    selection_weight: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    arc: Mapped[StoryArc] = relationship(back_populates="home_story_publication")
    selected_track: Mapped[StoryNarrationTrack | None] = relationship(
        foreign_keys=[selected_track_id]
    )


class StoryCatalogItem(Base):
    __tablename__ = "story_catalog_items"
    __table_args__ = (
        UniqueConstraint("source_kind", "source_id", name="uq_story_catalog_source"),
        Index("ix_story_catalog_city_status", "city_id", "status", "published_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    city_id: Mapped[str] = mapped_column(ForeignKey("cities.id"), index=True)
    source_kind: Mapped[str] = mapped_column(String(30))
    source_id: Mapped[str] = mapped_column(String(36), index=True)
    canonical_revision: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text)
    cover_image: Mapped[str] = mapped_column(String(500), default="")
    district: Mapped[str | None] = mapped_column(String(120), nullable=True)
    themes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    point_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    related_stories_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    content_type: Mapped[str] = mapped_column(String(80))
    place_context: Mapped[str] = mapped_column(Text)
    observable_detail: Mapped[str] = mapped_column(Text)
    attention_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    sources_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    fact_status: Mapped[str] = mapped_column(String(40), default="documented")
    review_status: Mapped[str] = mapped_column(String(40), default="in_review")
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StoryCatalogVariant(Base):
    __tablename__ = "story_catalog_variants"
    __table_args__ = (
        UniqueConstraint(
            "catalog_item_id", "role", name="uq_story_catalog_variant_role"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    catalog_item_id: Mapped[str] = mapped_column(
        ForeignKey("story_catalog_items.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(30))
    source_kind: Mapped[str] = mapped_column(String(30))
    source_id: Mapped[str] = mapped_column(String(36), index=True)
    track_kind: Mapped[str] = mapped_column(String(30))
    track_id: Mapped[str] = mapped_column(String(36), index=True)
    transcript_hash: Mapped[str] = mapped_column(String(64))
    script_version: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StoryPlacement(Base):
    __tablename__ = "story_placements"
    __table_args__ = (
        UniqueConstraint(
            "catalog_item_id",
            "channel",
            "module_key",
            "route_id",
            name="uq_story_catalog_placement",
        ),
        Index("ix_story_placement_public", "channel", "module_key", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    catalog_item_id: Mapped[str] = mapped_column(
        ForeignKey("story_catalog_items.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[str] = mapped_column(String(30), index=True)
    module_key: Mapped[str | None] = mapped_column(
        String(80), nullable=True, index=True
    )
    route_id: Mapped[str | None] = mapped_column(
        ForeignKey("routes.id"), nullable=True, index=True
    )
    variant_role: Mapped[str] = mapped_column(String(30), default="short_preview")
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    weight: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    starts_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RoutePretripGuidance(Base):
    __tablename__ = "route_pretrip_guidance"

    route_id: Mapped[str] = mapped_column(ForeignKey("routes.id"), primary_key=True)
    theme_story_catalog_id: Mapped[str | None] = mapped_column(
        ForeignKey("story_catalog_items.id"), nullable=True, index=True
    )
    story_directions_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    companion_tags_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    safety_tips_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    rest_tips_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    accessibility_tips_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    weather_tips_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    offline_roles_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ContentImportPreview(Base):
    __tablename__ = "content_import_previews"
    __table_args__ = (
        Index("ix_content_import_preview_expiry", "status", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    package_id: Mapped[str] = mapped_column(String(120), index=True)
    package_version: Mapped[str] = mapped_column(String(80))
    package_checksum: Mapped[str] = mapped_column(String(64))
    editor_id: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(20), default="ready", index=True)
    plan_json: Mapped[dict] = mapped_column(JSON)
    target_revisions_json: Mapped[dict] = mapped_column(JSON, default=dict)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ContentImportBatch(Base):
    __tablename__ = "content_import_batches"
    __table_args__ = (
        UniqueConstraint(
            "package_id", "package_version", name="uq_content_import_package_version"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    package_id: Mapped[str] = mapped_column(String(120), index=True)
    package_version: Mapped[str] = mapped_column(String(80))
    package_checksum: Mapped[str] = mapped_column(String(64))
    editor_id: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(20), default="completed", index=True)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class FragmentClaim(Base):
    __tablename__ = "fragment_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fragment_id: Mapped[str] = mapped_column(String(36), index=True)
    claim_id: Mapped[str] = mapped_column(String(36), index=True)


class FragmentDependency(Base):
    __tablename__ = "fragment_dependencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fragment_id: Mapped[str] = mapped_column(String(36), index=True)
    required_fragment_id: Mapped[str] = mapped_column(String(36), index=True)


class TriggerRegion(Base):
    __tablename__ = "trigger_regions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fragment_id: Mapped[str] = mapped_column(String(36), unique=True)
    latitude: Mapped[float] = mapped_column(Double)
    longitude: Mapped[float] = mapped_column(Double)
    entry_radius_m: Mapped[int] = mapped_column(Integer, default=60)
    exit_radius_m: Mapped[int] = mapped_column(Integer, default=90)
    max_accuracy_m: Mapped[int] = mapped_column(Integer, default=50)
    qualifying_samples: Mapped[int] = mapped_column(Integer, default=2)
    sample_window_seconds: Mapped[int] = mapped_column(Integer, default=15)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=120)
    audit_state: Mapped[str] = mapped_column(String(40), default="in_review")
    coordinate_system: Mapped[str] = mapped_column(String(20), default="WGS84")
    source_coordinate_system: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    coordinate_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class PhotoMission(Base):
    __tablename__ = "photo_missions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fragment_id: Mapped[str] = mapped_column(String(36), unique=True)
    prompt: Mapped[str] = mapped_column(Text)
    field_subject: Mapped[str] = mapped_column(Text)
    vantage_point: Mapped[str | None] = mapped_column(Text, nullable=True)
    shooting_direction: Mapped[str | None] = mapped_column(Text, nullable=True)
    composition_tip: Mapped[str | None] = mapped_column(Text, nullable=True)
    safety_copy: Mapped[str] = mapped_column(Text)
    accessibility_alternative: Mapped[str] = mapped_column(Text)
    authenticity_label: Mapped[str] = mapped_column(String(80), default="interpretive")
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    audit_state: Mapped[str] = mapped_column(String(40), default="in_review")


class JourneyFragment(Base):
    __tablename__ = "journey_fragments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    journey_id: Mapped[str] = mapped_column(String(36), index=True)
    fragment_id: Mapped[str] = mapped_column(String(36), index=True)


class ClientRuntimeLog(Base):
    __tablename__ = "client_runtime_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    level: Mapped[str] = mapped_column(String(16), index=True)
    category: Mapped[str] = mapped_column(String(120), index=True)
    message: Mapped[str] = mapped_column(Text)
    session_id: Mapped[str] = mapped_column(String(120), index=True)
    app_version: Mapped[str] = mapped_column(String(80))
    platform: Mapped[str] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(120), index=True)
    context_json: Mapped[dict] = mapped_column(JSON)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
