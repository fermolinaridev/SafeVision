from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Date, Integer, cast, extract, func, select

from .config import settings
from .db import Camera, Event, utcnow
from .rules import Equipment
from .schemas import Bucket, CameraCount, EventInfo, EventStatus, HourCount, PeriodPoint, Summary


@dataclass
class Filters:
    start: date
    end: date
    camera_id: str | None
    equipment: Equipment | None
    status: EventStatus | None
    zone: ZoneInfo

    def bounds(self):
        return (
            datetime.combine(self.start, time.min, self.zone),
            datetime.combine(self.end + timedelta(days=1), time.min, self.zone),
        )

    def predicates(self):
        start, end = self.bounds()
        clauses = [Event.occurred_at >= start, Event.occurred_at < end]
        if self.camera_id:
            clauses.append(Event.camera_id == self.camera_id)
        if self.equipment:
            clauses.append(Event.equipment == self.equipment)
        if self.status:
            clauses.append(Event.status == self.status)
        return clauses

    def previous(self):
        period = self.end - self.start + timedelta(days=1)
        return Filters(self.start - period, self.end - period, self.camera_id,
                       self.equipment, self.status, self.zone)


def day_zone():
    return ZoneInfo(settings().timezone)


def event_info(event: Event, name: str) -> EventInfo:
    return EventInfo(
        id=event.id, video_id=event.video_id, camera_id=event.camera_id, camera_name=name,
        occurred_at=event.occurred_at, equipment=event.equipment, track_id=event.track_id,
        confidence=event.confidence, duration=event.duration, status=event.status,
        evidence_url=f"/events/{event.id}/evidence" if event.evidence_key else None,
        frame_seconds=event.frame_seconds, reviewed_at=event.reviewed_at,
    )


def grouped_rows(db, criteria):
    local_time = func.timezone(criteria.zone.key, Event.occurred_at)
    event_date = cast(local_time, Date)
    hour = cast(extract("hour", local_time), Integer)
    groups = (event_date, hour, Event.camera_id, Event.equipment, Event.status)
    return db.execute(
        select(*groups, func.count()).where(*criteria.predicates()).group_by(*groups),
    )


def bucket_start(day: date, bucket: Bucket):
    if bucket == "week":
        return day - timedelta(days=day.weekday())
    if bucket == "month":
        return day.replace(day=1)
    return day


def summarize(criteria, bucket, groups, previous, cameras):
    categories, by_camera, hours, dates = Counter(), Counter(), Counter(), Counter()
    open_count = 0
    for day, hour, camera, equipment, status, count in groups:
        categories[equipment] += count
        by_camera[camera] += count
        hours[hour] += count
        dates[(bucket_start(day, bucket), equipment)] += count
        if status == "open":
            open_count += count
    buckets = dict.fromkeys(
        bucket_start(criteria.start + timedelta(days=i), bucket)
        for i in range((criteria.end - criteria.start).days + 1)
    )
    active_cutoff = utcnow() - timedelta(minutes=2)
    return Summary(
        total=categories.total(), previous_total=previous, helmet=categories["helmet"],
        vest=categories["vest"], open=open_count, cameras_total=len(cameras),
        cameras_active=sum(
            c.last_seen is not None and c.last_seen >= active_cutoff
            for c in cameras
        ),
        timeline=[PeriodPoint(date=day.isoformat(), helmet=dates[(day, "helmet")],
                              vest=dates[(day, "vest")]) for day in buckets],
        cameras=sorted(
            (CameraCount(id=c.id, name=c.name, count=by_camera[c.id]) for c in cameras
             if not criteria.camera_id or criteria.camera_id == c.id),
            key=lambda c: (-c.count, c.name),
        ),
        hours=[HourCount(hour=hour, count=hours[hour]) for hour in range(24)],
        timezone=criteria.zone.key,
    )
