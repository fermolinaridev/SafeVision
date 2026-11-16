import asyncio
import logging
import re
from datetime import UTC, date, datetime, timedelta
from hmac import compare_digest
from pathlib import Path
from threading import Lock
from time import monotonic, perf_counter
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, URLSafeTimedSerializer
from redis import Redis
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.websockets import WebSocketDisconnect

from . import demo, storage
from .config import settings
from .db import Audit, Camera, Event, VideoJob, session_dependency, sessions, utcnow
from .processing import Stream, video_type
from .reporting import Filters, day_zone, event_info, grouped_rows, summarize
from .rules import Equipment
from .schemas import (
    Bucket, CameraCreate, CameraInfo, Credentials, EventInfo, EventPage, EventStatus, Review,
    Summary, VideoInfo,
)
from .vision import Analysis, FORMATS, MediaError, ModelError, decode_image, detector


logger = logging.getLogger(__name__)
COOKIE = "safevision_session"
FRONTEND = Path("frontend/dist")
Db = Annotated[Session, Depends(session_dependency)]
Upload = Annotated[UploadFile, File()]
app = FastAPI(
    title="SafeVision API", version="0.3.0",
    description="Detecção visual de EPIs, processamento de vídeos e acompanhamento de ocorrências.",
)
public_inference = Lock()


def error_response(status, message, code="http_error", details=None):
    return JSONResponse({"error": {"code": code, "message": message, "details": details}}, status)


@app.exception_handler(StarletteHTTPException)
async def http_error(request, exc):
    response = error_response(exc.status_code, str(exc.detail))
    response.headers.update(exc.headers or {})
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    details = [{"field": ".".join(map(str, item["loc"])), "message": item["msg"]} for item in exc.errors()]
    return error_response(422, "Revise os campos enviados.", "validation_error", details)


@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    logger.exception("Erro na rota %s", request.url.path, exc_info=exc)
    return error_response(500, "O serviço encontrou um erro.", "internal_error")


def same_origin(headers):
    origin = headers.get("origin")
    return not origin or (
        urlsplit(origin).scheme in {"http", "https"} and urlsplit(origin).netloc == headers.get("host")
    )


@app.middleware("http")
async def protect_request(request: Request, call_next):
    start = perf_counter()
    if request.method in {"POST", "PATCH", "DELETE", "PUT"} and not same_origin(request.headers):
        return error_response(403, "Origem da requisição inválida.")
    if request.method == "POST":
        cfg = settings()
        multipart = request.url.path in {"/detect", "/videos"}
        limit = (cfg.image_mb if request.url.path == "/detect" else cfg.video_mb) * 1024 * 1024 + 65536
        if request.url.path == "/auth/login":
            limit = 4096
        if multipart or request.url.path == "/auth/login":
            lengths = request.headers.getlist("content-length")
            if len(lengths) != 1 or not lengths[0].isdigit() or "transfer-encoding" in request.headers:
                return error_response(411, "Informe o tamanho do arquivo.")
            if int(lengths[0]) > limit:
                return error_response(413, "O arquivo excede o tamanho permitido.")
    limit_public_work = request.method == "POST" and request.url.path == "/detect" and settings().demo
    if limit_public_work and not public_inference.acquire(blocking=False):
        return error_response(429, "A demonstração está ocupada. Tente novamente em instantes.")
    try:
        response = await call_next(request)
    finally:
        if limit_public_work:
            public_inference.release()
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Response-Time-Ms"] = f"{(perf_counter() - start) * 1000:.2f}"
    if request.url.path.startswith(("/events", "/analytics", "/videos", "/cameras", "/auth", "/detect")):
        response.headers["Cache-Control"] = "private, no-store"
    return response


def signer():
    return URLSafeTimedSerializer(settings().session_secret.get_secret_value(), salt="safevision-admin-v1")


def signed_in(token):
    if not token:
        return False
    try:
        return signer().loads(token, max_age=settings().session_seconds) == "admin"
    except BadSignature:
        return False


def viewer(request: Request):
    if not settings().demo and not signed_in(request.cookies.get(COOKIE)):
        raise HTTPException(401, "Entre para acessar o SafeVision.")


def admin(request: Request):
    if settings().demo:
        raise HTTPException(403, "A demonstração pública oferece análise de imagens e webcam.")
    viewer(request)


def redis_client():
    return Redis.from_url(settings().redis_url, socket_timeout=2, socket_connect_timeout=2)


@app.get("/auth/session")
def current_session(request: Request):
    cfg = settings()
    return {
        "demo": cfg.demo, "authenticated": cfg.demo or signed_in(request.cookies.get(COOKIE)),
        "timezone": cfg.timezone, "image_mb": cfg.image_mb, "video_mb": cfg.video_mb,
        "max_video_seconds": cfg.max_video_seconds,
    }


@app.post("/auth/login")
def login(body: Credentials, request: Request, response: Response, db: Db):
    cfg = settings()
    if cfg.demo:
        raise HTTPException(403, "A demonstração já está disponível.")
    addr = request.client.host if request.client else "unknown"
    with redis_client() as redis, redis.pipeline(transaction=True) as pipe:
        attempts, _ = pipe.incr(f"safevision:login:{addr}").expire(
            f"safevision:login:{addr}", 60, nx=True
        ).execute()
        if attempts > 8:
            raise HTTPException(429, "Aguarde um minuto antes de tentar novamente.")
        if not compare_digest(body.password.encode(), cfg.admin_password.get_secret_value().encode()):
            raise HTTPException(401, "Senha inválida.")
        redis.delete(f"safevision:login:{addr}")
    db.add(Audit(action="login", target="session"))
    db.commit()
    response.set_cookie(COOKIE, signer().dumps("admin"), max_age=cfg.session_seconds,
                        httponly=True, secure=cfg.cookie_secure, samesite="strict")
    return {"authenticated": True}


@app.post("/auth/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(COOKIE, secure=settings().cookie_secure, httponly=True, samesite="strict")


@app.get("/health", dependencies=[Depends(viewer)])
def health():
    cfg = settings()
    services = {"api": True, "database": None, "queue": None, "storage": None}
    if not cfg.demo:
        def database_ready():
            with sessions()() as db:
                db.execute(text("SELECT 1 FROM cameras LIMIT 1"))

        def queue_ready():
            with redis_client() as redis:
                redis.ping()

        for name, check in (
            ("database", database_ready), ("queue", queue_ready),
            ("storage", lambda: storage.client().head_bucket(Bucket=cfg.s3_bucket)),
        ):
            try:
                check()
                services[name] = True
            except Exception:
                services[name] = False
    return {"services": services, **detector.metrics(), "device": cfg.device}


@app.post("/detect", response_model=Analysis, dependencies=[Depends(viewer)])
def detect(file: Upload):
    cfg = settings()
    if file.content_type not in FORMATS.values():
        raise HTTPException(415, "Use uma imagem JPG, PNG ou WebP.")
    data = file.file.read(cfg.image_mb * 1024 * 1024 + 1)
    if len(data) > cfg.image_mb * 1024 * 1024:
        raise HTTPException(413, "A imagem excede o tamanho permitido.")
    try:
        return detector.analyze(decode_image(data, file.content_type), wait=False)
    except MediaError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ModelError as exc:
        raise HTTPException(503, str(exc)) from exc


def camera_or_404(db, camera_id):
    camera = db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(404, "Câmera não encontrada.")
    return camera


@app.get("/cameras", response_model=list[CameraInfo], dependencies=[Depends(viewer)])
def cameras(db: Db):
    return demo.cameras() if settings().demo else db.scalars(select(Camera).order_by(Camera.name)).all()


@app.post("/cameras", response_model=CameraInfo, status_code=201, dependencies=[Depends(admin)])
def add_camera(body: CameraCreate, db: Db):
    name, location = body.name.strip(), body.location.strip()
    if len(name) < 2 or len(location) < 2:
        raise HTTPException(422, "Preencha o nome e o local da câmera.")
    camera = Camera(id=str(uuid4()), name=name, location=location)
    db.add_all([camera, Audit(action="camera_created", target=camera.id)])
    try:
        db.commit()
    except IntegrityError as exc:
        raise HTTPException(409, "Já existe uma câmera com esse nome.") from exc
    return camera


def queue_job(db, job):
    from .tasks import process

    try:
        process.apply_async(args=[job.id], task_id=job.id, retry=False)
    except Exception:
        logger.exception("Não foi possível enviar %s à fila", job.id)
        db.refresh(job, with_for_update=True)
        if job.status == "pending":
            job.status = "failed"
            job.error = "Fila indisponível. Repita a tarefa mais tarde."
            db.commit()


@app.post("/videos", response_model=VideoInfo, status_code=202, dependencies=[Depends(admin)])
def upload_video(file: Upload, db: Db, camera_id: Annotated[str, Form(max_length=40)] = "cam-01",
                 recorded_at: Annotated[datetime | None, Form()] = None):
    cfg = settings()
    camera_or_404(db, camera_id)
    if file.content_type not in {"video/mp4", "video/quicktime", "video/webm", "application/octet-stream"}:
        raise HTTPException(415, "Use um vídeo MP4, MOV ou WebM.")
    if file.size is None or file.size > cfg.video_mb * 1024 * 1024:
        raise HTTPException(413, "O vídeo excede o tamanho permitido.")
    if recorded_at and (recorded_at.utcoffset() is None or not 2000 <= recorded_at.year <= 2100):
        raise HTTPException(422, "Informe a data de gravação com fuso horário.")
    try:
        suffix = video_type(file.file.read(4096))
    except MediaError as exc:
        raise HTTPException(422, str(exc)) from exc
    file.file.seek(0)
    job_id = str(uuid4())
    key = f"uploads/{job_id}{suffix}"
    filename = re.sub(r"[\x00-\x1f\x7f]", "", file.filename or "").replace("\\", "/").split("/")[-1]
    job = VideoJob(id=job_id, camera_id=camera_id, filename=filename[:160] or f"video{suffix}",
                   object_key=key, recorded_at=recorded_at or utcnow())
    storage.put_file(key, file.file)
    try:
        db.add_all([job, Audit(action="video_uploaded", target=job_id)])
        db.commit()
    except Exception:
        storage.delete(key)
        raise
    queue_job(db, job)
    return job


@app.get("/videos", response_model=list[VideoInfo], dependencies=[Depends(admin)])
def videos(db: Db):
    return db.scalars(select(VideoJob).order_by(VideoJob.created_at.desc()).limit(30)).all()


@app.get("/videos/{job_id}/status", response_model=VideoInfo, dependencies=[Depends(admin)])
def video_status(job_id: UUID, db: Db):
    job = db.get(VideoJob, str(job_id))
    if job is None:
        raise HTTPException(404, "Processamento não encontrado.")
    return job


@app.post("/videos/{job_id}/retry", response_model=VideoInfo, status_code=202, dependencies=[Depends(admin)])
def retry_video(job_id: UUID, db: Db):
    job = db.get(VideoJob, str(job_id), with_for_update=True)
    if job is None:
        raise HTTPException(404, "Processamento não encontrado.")
    if job.status != "failed" or job.object_key is None:
        raise HTTPException(409, "A tarefa não pode ser repetida.")
    job.status, job.error, job.progress, job.processed_frames, job.processing_seconds = "pending", None, 0, 0, None
    db.add(Audit(action="video_retried", target=job.id))
    db.commit()
    queue_job(db, job)
    return job


def filters(
    start: date | None = None, end: date | None = None, camera_id: Annotated[str | None, Query(max_length=40)] = None,
    equipment: Equipment | None = None, status: EventStatus | None = None,
):
    zone = day_zone()
    end = end or utcnow().astimezone(zone).date()
    start = start or end - timedelta(days=6)
    if start > end or (end - start).days > 365 or not 2000 <= start.year <= end.year <= 2100:
        raise HTTPException(422, "Escolha um período válido de até 366 dias.")
    return Filters(start, end, camera_id, equipment, status, zone)


Criteria = Annotated[Filters, Depends(filters)]


@app.get("/events", response_model=EventPage, dependencies=[Depends(viewer)])
def events(criteria: Criteria, db: Db, offset: Annotated[int, Query(ge=0)] = 0,
           limit: Annotated[int, Query(ge=1, le=100)] = 20):
    if settings().demo:
        items = demo.filtered(criteria)
        return EventPage(items=items[offset:offset + limit], total=len(items))
    predicates = criteria.predicates()
    rows = db.execute(
        select(Event, Camera.name).join(Camera).where(*predicates)
        .order_by(Event.occurred_at.desc(), Event.id).offset(offset).limit(limit)
    )
    return EventPage(
        items=[event_info(event, name) for event, name in rows],
        total=db.scalar(select(func.count()).select_from(Event).where(*predicates)),
    )


@app.get("/events/{event_id}", response_model=EventInfo, dependencies=[Depends(viewer)])
def event_detail(event_id: UUID, db: Db):
    if settings().demo:
        item = next((e for e in demo.events() if e.id == str(event_id)), None)
        if item:
            return item
    else:
        row = db.execute(select(Event, Camera.name).join(Camera).where(Event.id == str(event_id))).one_or_none()
        if row:
            return event_info(*row)
    raise HTTPException(404, "Ocorrência não encontrada.")


@app.patch("/events/{event_id}", response_model=EventInfo, dependencies=[Depends(admin)])
def review_event(event_id: UUID, body: Review, db: Db):
    event = db.get(Event, str(event_id), with_for_update=True)
    if event is None:
        raise HTTPException(404, "Ocorrência não encontrada.")
    if event.status != body.status:
        event.status = body.status
        event.reviewed_at = None if body.status == "open" else utcnow()
        db.add(Audit(action=f"event_{body.status}", target=event.id))
        db.commit()
    return event_info(event, db.get(Camera, event.camera_id).name)


@app.get("/events/{event_id}/evidence", dependencies=[Depends(admin)])
def evidence(event_id: UUID, db: Db):
    event = db.get(Event, str(event_id))
    if event is None or not event.evidence_key:
        raise HTTPException(404, "Evidência indisponível.")
    from botocore.exceptions import ClientError

    try:
        stream = storage.read_evidence(event.evidence_key)
    except ClientError as exc:
        if exc.response["Error"]["Code"] in {"NoSuchKey", "404"}:
            raise HTTPException(404, "Evidência indisponível.") from exc
        raise

    def chunks():
        with stream:
            yield from stream.iter_chunks(65536)

    return StreamingResponse(chunks(), media_type="image/jpeg")


@app.delete("/events/{event_id}/evidence", status_code=204, dependencies=[Depends(admin)])
def delete_evidence(event_id: UUID, db: Db):
    event = db.get(Event, str(event_id), with_for_update=True)
    if event is None:
        raise HTTPException(404, "Ocorrência não encontrada.")
    if event.evidence_key:
        storage.delete(event.evidence_key)
        event.evidence_key = None
        db.add(Audit(action="evidence_deleted", target=event.id))
        db.commit()


@app.get("/analytics/summary", response_model=Summary, dependencies=[Depends(viewer)])
def analytics(criteria: Criteria, db: Db, bucket: Bucket = "day"):
    previous = criteria.previous()
    if settings().demo:
        return summarize(criteria, bucket, demo.groups(criteria), len(demo.filtered(previous)), demo.cameras())
    prior_count = db.scalar(select(func.count()).select_from(Event).where(*previous.predicates()))
    return summarize(criteria, bucket, grouped_rows(db, criteria), prior_count, db.scalars(select(Camera)).all())


def recent_events():
    with sessions()() as db:
        rows = db.execute(select(Event, Camera.name).join(Camera).order_by(
            Event.created_at.desc(), Event.id
        ).limit(250))
        return [event_info(*row) for row in rows]


@app.websocket("/events/live")
async def live_events(ws: WebSocket):
    demo_mode = settings().demo
    token = ws.cookies.get(COOKIE)
    if not same_origin(ws.headers) or (not demo_mode and not signed_in(token)):
        await ws.close(1008)
        return
    await ws.accept()
    try:
        previous = set() if demo_mode else {event.id for event in await run_in_threadpool(recent_events)}
        await ws.send_json({"type": "ready"})
        while True:
            if not demo_mode and not signed_in(token):
                await ws.close(1008)
                return
            try:
                message = await asyncio.wait_for(ws.receive(), timeout=1.5)
                if message["type"] == "websocket.disconnect":
                    return
            except TimeoutError:
                if not demo_mode:
                    current = await run_in_threadpool(recent_events)
                    for event in reversed(current):
                        if event.id not in previous:
                            await ws.send_json({"type": "event", "event": event.model_dump(mode="json")})
                    previous = {event.id for event in current}
    except WebSocketDisconnect:
        pass


def open_stream(camera_id):
    with sessions()() as db:
        if db.get(Camera, camera_id):
            return Stream(str(uuid4()), camera_id, utcnow(), settings().sample_fps)
    return None


@app.websocket("/cameras/{camera_id}/live")
async def webcam(ws: WebSocket, camera_id: str):
    cfg = settings()
    token = ws.cookies.get(COOKIE)
    if cfg.demo or not same_origin(ws.headers) or not signed_in(token):
        await ws.close(1008)
        return
    stream = await run_in_threadpool(open_stream, camera_id)
    if stream is None:
        await ws.close(1008)
        return
    start, last = monotonic(), float("-inf")
    await ws.accept()
    try:
        while monotonic() - start < 7200:
            data = await asyncio.wait_for(ws.receive_bytes(), timeout=30)
            if not signed_in(token):
                await ws.close(1008)
                return
            elapsed = monotonic() - start
            if len(data) > min(cfg.image_mb * 1024 * 1024, 1024 * 1024):
                await ws.close(1009)
                return
            if elapsed - last < 0.9 / cfg.sample_fps:
                await ws.send_json({"type": "skip"})
                continue
            last = elapsed
            try:
                frame = await run_in_threadpool(decode_image, data, "image/jpeg")
                analysis = await run_in_threadpool(stream.analyze, frame, elapsed)
                await ws.send_json({"type": "analysis", "analysis": analysis.model_dump(mode="json")})
            except (MediaError, ModelError) as exc:
                await ws.send_json({"type": "error", "message": str(exc)})
        await ws.close(1000)
    except TimeoutError:
        await ws.close(1000)
    except WebSocketDisconnect:
        pass
    finally:
        await run_in_threadpool(stream.flush)


@app.get("/", include_in_schema=False)
def dashboard():
    path = FRONTEND / "index.html"
    if not path.is_file():
        raise HTTPException(503, "Compile o dashboard com npm --prefix frontend run build.")
    return FileResponse(path)


@app.get("/favicon.svg", include_in_schema=False)
def favicon():
    path = FRONTEND / "favicon.svg"
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path)


@app.get("/creditos", include_in_schema=False)
def credits():
    return FileResponse("docs/ASSETS.md", media_type="text/plain")


app.mount("/assets", StaticFiles(directory=FRONTEND / "assets", check_dir=False), name="assets")
app.mount("/examples", StaticFiles(directory="frontend/public/examples"), name="examples")
