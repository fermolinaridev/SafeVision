from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .rules import Equipment


EventStatus = Literal["open", "reviewed", "dismissed"]
Bucket = Literal["day", "week", "month"]


class CameraInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    location: str
    last_seen: datetime | None = None


class CameraCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    location: str = Field(min_length=2, max_length=120)


class Credentials(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class VideoInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    camera_id: str
    filename: str
    status: Literal["pending", "running", "completed", "failed"]
    progress: int
    error: str | None
    created_at: datetime
    recorded_at: datetime
    processed_frames: int
    processing_seconds: float | None


class EventInfo(BaseModel):
    id: str
    video_id: str | None = None
    camera_id: str
    camera_name: str
    occurred_at: datetime
    equipment: Equipment
    track_id: int
    confidence: float
    duration: float
    status: EventStatus
    evidence_url: str | None
    frame_seconds: float
    reviewed_at: datetime | None = None


class EventPage(BaseModel):
    items: list[EventInfo]
    total: int


class Review(BaseModel):
    status: EventStatus


class PeriodPoint(BaseModel):
    date: str
    helmet: int = 0
    vest: int = 0


class CameraCount(BaseModel):
    id: str
    name: str
    count: int


class HourCount(BaseModel):
    hour: int
    count: int


class Summary(BaseModel):
    total: int
    previous_total: int
    helmet: int
    vest: int
    open: int
    cameras_total: int
    cameras_active: int
    timeline: list[PeriodPoint]
    cameras: list[CameraCount]
    hours: list[HourCount]
    timezone: str
