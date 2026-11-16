import logging
import math
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from uuid import UUID, uuid5

from sqlalchemy import select, text

from . import storage
from .config import settings
from .db import Camera, Event, VideoJob, engine, sessions, utcnow
from .rules import ViolationEngine
from .vision import MediaError, PersonTracker, detector


logger = logging.getLogger(__name__)


def video_type(header: bytes) -> str:
    if header[4:8] == b"ftyp":
        return ".mp4"
    if header.startswith(b"\x1a\x45\xdf\xa3") and b"webm" in header:
        return ".webm"
    raise MediaError("Envie um vídeo MP4, MOV ou WebM válido.")


@contextmanager
def open_video(path: Path):
    import cv2

    cfg = settings()
    capture = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 2])
    try:
        fps = capture.get(cv2.CAP_PROP_FPS)
        count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        width = capture.get(cv2.CAP_PROP_FRAME_WIDTH)
        height = capture.get(cv2.CAP_PROP_FRAME_HEIGHT)
        if (not capture.isOpened() or not all(map(math.isfinite, (fps, count, width, height)))
                or not 1 <= fps <= 240 or width < 16 or height < 16
                or width * height > 9_000_000 or count < 1):
            raise MediaError("O vídeo não pôde ser lido ou excede o limite de resolução.")
        if count / fps > cfg.max_video_seconds:
            raise MediaError(f"O vídeo excede o limite de {cfg.max_video_seconds} segundos.")
        yield capture, fps, int(count)
    finally:
        capture.release()


def evidence_jpeg(frame, analysis):
    import cv2

    frame = frame.copy()
    colors = {"person": (224, 140, 19), "helmet": (174, 170, 8), "vest": (174, 170, 8)}
    for detection in analysis.detections:
        x1, y1, x2, y2 = (int(value) for value in detection.box)
        color = colors.get(detection.label, (74, 109, 250))
        label = f"{detection.label} {detection.confidence:.0%}"
        if detection.track_id is not None:
            label += f" #{detection.track_id}"
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, label, (x1, max(16, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, color, 2, cv2.LINE_AA)
    if frame.shape[1] > 1280:
        ratio = 1280 / frame.shape[1]
        frame = cv2.resize(frame, (1280, round(frame.shape[0] * ratio)))
    ok, image = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
    if not ok:
        raise MediaError("Não foi possível gerar a evidência.")
    return image.tobytes()


class Stream:
    def __init__(self, stream_id, camera_id, base_time, fps, video_id=None):
        cfg = settings()
        self.stream_id = stream_id
        self.camera_id = camera_id
        self.base_time = base_time
        self.video_id = video_id
        self.tracker = PersonTracker(fps)
        self.rules = ViolationEngine(cfg.violation_seconds, cfg.gap_seconds, cfg.recovery_seconds)
        self.saved = set()
        self.durations = {}
        self.last_flush = None

    def analyze(self, frame, timestamp):
        analysis = detector.analyze(frame, self.tracker)
        for report in self.rules.update(analysis.people, timestamp):
            event_id = str(uuid5(UUID(self.stream_id), f"{report.track_id}:{report.equipment}:{report.started:.6f}"))
            self.durations[event_id] = report.duration
            if event_id in self.saved:
                continue
            with sessions()() as db:
                if db.get(Event, event_id) is None:
                    key = f"evidence/{event_id}.jpg"
                    storage.put_evidence(key, evidence_jpeg(frame, analysis))
                    db.add(Event(
                        id=event_id, camera_id=self.camera_id, stream_id=self.stream_id, video_id=self.video_id,
                        occurred_at=self.base_time + timedelta(seconds=timestamp),
                        equipment=report.equipment, track_id=report.track_id, confidence=report.confidence,
                        duration=report.duration, evidence_key=key, frame_seconds=timestamp,
                    ))
                    db.commit()
            self.saved.add(event_id)
        if self.last_flush is None or timestamp - self.last_flush >= 1:
            self.flush()
            self.last_flush = timestamp
        return analysis

    def flush(self):
        with sessions()() as db:
            for event_id, duration in self.durations.items():
                event = db.get(Event, event_id, with_for_update=True)
                if event and duration > event.duration:
                    event.duration = duration
            if self.video_id is None:
                camera = db.get(Camera, self.camera_id)
                if camera:
                    camera.last_seen = utcnow()
            db.commit()
        self.durations.clear()


@contextmanager
def job_lock(job_id):
    # Session-level lock across progress commits, released even if the worker dies.
    key = int.from_bytes(UUID(job_id).bytes[:8], byteorder="big", signed=True)
    with engine().connect() as connection:
        acquired = connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
        connection.commit()
        try:
            yield acquired
        finally:
            if acquired:
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                connection.commit()


def video_job(job_id):
    import cv2

    with sessions()() as db:
        job = db.get(VideoJob, job_id, with_for_update=True)
        if not job or job.status in ("completed", "failed"):
            return
        job.status, job.progress, job.processed_frames, job.error = "running", 0, 0, None
        db.commit()

    cfg = settings()
    started = monotonic()
    with TemporaryDirectory(prefix="safevision-") as temporary:
        if not job.object_key:
            raise MediaError("O vídeo original expirou.")
        path = Path(temporary, "input")
        storage.get_file(job.object_key, path)
        with open_video(path) as (capture, fps, count):
            stream = Stream(job.id, job.camera_id, job.recorded_at, min(fps, cfg.sample_fps), job.id)
            samples, decoded, next_sample, last_timestamp, last_progress = 0, 0, 0.0, -1.0, started
            while capture.grab():
                media_time = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000
                timestamp = media_time if math.isfinite(media_time) and media_time > last_timestamp else last_timestamp + 1 / fps
                last_timestamp = timestamp
                if timestamp > cfg.max_video_seconds or decoded > cfg.max_video_seconds * 240:
                    raise MediaError("O vídeo excede o limite de duração.")
                decoded += 1
                if timestamp + 1e-6 < next_sample:
                    continue
                ok, frame = capture.retrieve()
                if not ok or frame.size == 0 or frame.shape[0] * frame.shape[1] > 9_000_000:
                    raise MediaError("O vídeo contém frames inválidos.")
                stream.analyze(frame, timestamp)
                next_sample += 1 / min(fps, cfg.sample_fps)
                if next_sample <= timestamp:
                    next_sample = timestamp + 1 / min(fps, cfg.sample_fps)
                samples += 1
                if monotonic() - last_progress >= 1:
                    update_job(job_id, progress=min(99, round(decoded / count * 100)), processed_frames=samples)
                    last_progress = monotonic()
            if not samples or decoded < count * 0.9:
                raise MediaError("O vídeo está vazio ou incompleto.")
            stream.flush()
    update_job(job_id, status="completed", progress=100, processed_frames=samples,
               processing_seconds=round(monotonic() - started, 3))


def update_job(job_id, **fields):
    with sessions()() as db:
        job = db.get(VideoJob, job_id, with_for_update=True)
        if job is not None:
            for key, value in fields.items():
                setattr(job, key, value)
            db.commit()


def enforce_retention():
    cfg = settings()
    now = utcnow()
    specs = (
        (Event, Event.evidence_key, Event.created_at, cfg.evidence_days, "evidence_key"),
        (VideoJob, VideoJob.object_key, VideoJob.updated_at, cfg.upload_days, "object_key"),
    )
    for model, object_key, when, days, field in specs:
        criteria = [object_key.is_not(None), when < now - timedelta(days=days)]
        if model is VideoJob:
            criteria.append(VideoJob.status.in_(["completed", "failed"]))
        with sessions()() as db:
            rows = db.scalars(
                select(model).where(*criteria).limit(250).with_for_update(skip_locked=True)
            ).all()
            for row in rows:
                storage.delete(getattr(row, field))
                setattr(row, field, None)
            db.commit()
