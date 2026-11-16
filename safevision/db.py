from datetime import UTC, datetime
from functools import lru_cache

from sqlalchemy import DateTime, ForeignKey, Index, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import settings


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    location: Mapped[str] = mapped_column(String(120))
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VideoJob(Base):
    __tablename__ = "video_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"))
    filename: Mapped[str] = mapped_column(String(160))
    object_key: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    progress: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(String(280))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processed_frames: Mapped[int] = mapped_column(default=0)
    processing_seconds: Mapped[float | None]


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_camera_time", "camera_id", "occurred_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    stream_id: Mapped[str] = mapped_column(String(36))
    video_id: Mapped[str | None] = mapped_column(ForeignKey("video_jobs.id"), index=True)
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    equipment: Mapped[str] = mapped_column(String(12))
    track_id: Mapped[int]
    confidence: Mapped[float]
    duration: Mapped[float]
    status: Mapped[str] = mapped_column(String(16), default="open")
    evidence_key: Mapped[str | None] = mapped_column(String(160))
    frame_seconds: Mapped[float]
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Audit(Base):
    __tablename__ = "audit"

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(48))
    target: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(32), default="admin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


@lru_cache
def engine():
    return create_engine(
        settings().database_url, pool_pre_ping=True,
        connect_args={"connect_timeout": 4} if settings().database_url.startswith("postgresql") else {},
    )


@lru_cache
def sessions():
    return sessionmaker(engine(), expire_on_commit=False)


def session_dependency():
    with sessions()() as db:
        yield db
