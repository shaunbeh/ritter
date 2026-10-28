import logging
import re
import secrets
import uuid
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import redis
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from app.config import settings
from app import db, storage
from app.contract import QUEUE_KEY, job_body

log = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".aac",
    ".ogg",
    ".opus",
    ".flac",
    ".webm",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".wma",
}
LANGUAGE_RE = re.compile(r"[a-z]{2,3}(-[a-z0-9]{2,8})?$")

redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not settings.api_keys:
        raise RuntimeError("API_KEY is required")
    db.open_pool()
    storage.ensure_bucket()
    yield
    db.close_pool()


app = FastAPI(title="Transcription", lifespan=lifespan)


def require_api_key(
    x_api_key: str | None = Depends(api_key_header),
    authorization: str | None = Header(default=None),
) -> None:
    token = x_api_key
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token or not any(secrets.compare_digest(token, key) for key in settings.api_keys):
        raise HTTPException(status_code=401, detail="Invalid API key")


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _optional_int(value: str | None, name: str) -> int | None:
    if value is None or value.strip() == "":
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{name} must be an integer") from exc
    if not 1 <= parsed <= 50:
        raise HTTPException(status_code=400, detail=f"{name} must be between 1 and 50")
    return parsed


def _language(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    code = value.strip().lower()
    if not LANGUAGE_RE.fullmatch(code):
        raise HTTPException(status_code=400, detail="language must be a short language code")
    return code


def _callback(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    url = value.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="callback_url must be an http(s) URL")
    if len(url) > 2000:
        raise HTTPException(status_code=400, detail="callback_url is too long")
    return url


def _extension(filename: str, content_type: str | None) -> str:
    suffix = ""
    if "." in filename:
        suffix = "." + filename.rsplit(".", 1)[-1].lower()
    if suffix in ALLOWED_EXTENSIONS:
        return suffix
    if content_type and (
        content_type.startswith("audio/") or content_type.startswith("video/")
    ):
        return suffix or ".audio"
    raise HTTPException(status_code=400, detail="Upload an audio or video file")


@app.get("/health")
def health() -> dict:
    with db.pool.connection() as conn:
        conn.execute("SELECT 1")
    if redis_client.ping() is not True:
        raise HTTPException(status_code=503, detail="redis unavailable")
    return {"status": "ok"}


@app.post("/v1/transcriptions", status_code=202)
async def create_transcription(
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
    summarize: str | None = Form(default=None),
    diarize: str | None = Form(default=None),
    min_speakers: str | None = Form(default=None),
    max_speakers: str | None = Form(default=None),
    callback_url: str | None = Form(default=None),
    _: None = Depends(require_api_key),
) -> JSONResponse:
    if db.count_active() >= settings.max_queue_depth:
        raise HTTPException(status_code=429, detail="Transcription queue is full")

    language_code = _language(language)
    do_summarize = _as_bool(summarize, True)
    do_diarize = _as_bool(diarize, True)
    min_count = _optional_int(min_speakers, "min_speakers")
    max_count = _optional_int(max_speakers, "max_speakers")
    if min_count is not None and max_count is not None and min_count > max_count:
        raise HTTPException(status_code=400, detail="min_speakers cannot exceed max_speakers")
    callback = _callback(callback_url)

    filename = (file.filename or "audio").replace("\\", "/").split("/")[-1][:200]
    suffix = _extension(filename, file.content_type)
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="File exceeds upload limit")
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise HTTPException(status_code=400, detail="File is empty")

    job_id = str(uuid.uuid4())
    object_key = f"audio/{job_id}{suffix}"
    storage.put_audio(object_key, data, file.content_type or "application/octet-stream")
    db.insert_job(
        job_id,
        filename,
        object_key,
        language_code,
        do_summarize,
        do_diarize,
        min_count,
        max_count,
        callback,
    )
    redis_client.rpush(QUEUE_KEY, job_id)
    log.info("Queued transcription %s (%s bytes)", job_id, len(data))
    return JSONResponse(status_code=202, content={"id": job_id, "status": "queued"})


@app.get("/v1/transcriptions/{job_id}")
def get_transcription(job_id: str, _: None = Depends(require_api_key)) -> dict:
    try:
        uuid.UUID(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid job id") from exc
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_body(job)
