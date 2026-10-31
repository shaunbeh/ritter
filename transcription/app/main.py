import logging
import re
import uuid
from contextlib import asynccontextmanager
from typing import Any
import redis
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, EmailStr, Field

from app import db, storage
from app.auth import (
    bootstrap_admin,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    refresh_is_valid,
    require_admin,
    revoke_refresh,
    verify_password,
)
from app.config import settings
from app.contract import QUEUE_KEY, export_srt, export_txt, session_body

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

redis_client = redis.Redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=10,
    health_check_interval=30,
    retry_on_timeout=True,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.open_pool()
    storage.ensure_bucket()
    bootstrap_admin()
    yield
    db.close_pool()


app = FastAPI(title="Transcription Panel API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class RefreshBody(BaseModel):
    refresh_token: str


class UserCreateBody(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    role: str = "user"


class MeUpdateBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    prefs: dict[str, Any] | None = None


class SessionCreateBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    language: str | None = None
    summarize: bool = True
    diarize: bool = True
    min_speakers: int | None = None
    max_speakers: int | None = None


class SessionUpdateBody(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    language: str | None = None
    summarize: bool | None = None
    diarize: bool | None = None
    status: str | None = None
    min_speakers: int | None = None
    max_speakers: int | None = None


def _language(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    code = value.strip().lower()
    if not LANGUAGE_RE.fullmatch(code):
        raise HTTPException(status_code=400, detail="کد زبان نامعتبر است")
    return code


def _extension(filename: str, content_type: str | None) -> str:
    suffix = ""
    if "." in filename:
        suffix = "." + filename.rsplit(".", 1)[-1].lower()
    if suffix in ALLOWED_EXTENSIONS:
        return suffix
    if content_type and (
        content_type.startswith("audio/") or content_type.startswith("video/")
    ):
        return suffix or ".webm"
    raise HTTPException(status_code=400, detail="فایل صوتی یا ویدیویی ارسال کنید")


async def _read_upload(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="حجم فایل بیش از حد مجاز است")
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise HTTPException(status_code=400, detail="فایل خالی است")
    return data


def _owned_session(session_id: str, user: dict) -> dict:
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="نشست یافت نشد")
    if session["user_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="دسترسی ندارید")
    return session


def _enqueue(session_id: str) -> None:
    redis_client.rpush(QUEUE_KEY, session_id)


@app.get("/health")
def health() -> dict:
    with db.pool.connection() as conn:
        conn.execute("SELECT 1")
    if redis_client.ping() is not True:
        raise HTTPException(status_code=503, detail="redis unavailable")
    return {"status": "ok"}


@app.post("/auth/login")
def login(body: LoginBody) -> dict:
    user = db.get_user_by_email(str(body.email))
    if user is None or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="ایمیل یا رمز عبور نادرست است")
    return {
        "access_token": create_access_token(user),
        "refresh_token": create_refresh_token(user),
        "token_type": "bearer",
        "user": db.public_user(user),
    }


@app.post("/auth/refresh")
def refresh(body: RefreshBody) -> dict:
    payload = decode_token(body.refresh_token)
    if payload.get("typ") != "refresh":
        raise HTTPException(status_code=401, detail="توکن تازه‌سازی نامعتبر است")
    jti = payload.get("jti")
    if not jti or not refresh_is_valid(jti):
        raise HTTPException(status_code=401, detail="توکن تازه‌سازی باطل شده است")
    user = db.get_user_by_id(payload["sub"])
    if user is None:
        raise HTTPException(status_code=401, detail="کاربر یافت نشد")
    revoke_refresh(jti)
    return {
        "access_token": create_access_token(user),
        "refresh_token": create_refresh_token(user),
        "token_type": "bearer",
        "user": db.public_user(user),
    }


@app.post("/auth/logout")
def logout(body: RefreshBody, user: dict = Depends(get_current_user)) -> dict:
    payload = decode_token(body.refresh_token)
    if payload.get("sub") != user["id"]:
        raise HTTPException(status_code=403, detail="دسترسی ندارید")
    jti = payload.get("jti")
    if jti:
        revoke_refresh(jti)
    return {"ok": True}


@app.get("/auth/me")
def me(user: dict = Depends(get_current_user)) -> dict:
    return db.public_user(user)


@app.patch("/auth/me")
def update_me(body: MeUpdateBody, user: dict = Depends(get_current_user)) -> dict:
    password_hash = hash_password(body.password) if body.password else None
    updated = db.update_user(
        user["id"],
        name=body.name,
        password_hash=password_hash,
        prefs=body.prefs,
    )
    assert updated is not None
    return db.public_user(updated)


@app.get("/auth/users")
def list_users(_admin: dict = Depends(require_admin)) -> dict:
    return {"users": [db.public_user(u) for u in db.list_users()]}


@app.post("/auth/users", status_code=201)
def create_user(body: UserCreateBody, _admin: dict = Depends(require_admin)) -> dict:
    if body.role not in {"admin", "user"}:
        raise HTTPException(status_code=400, detail="نقش نامعتبر است")
    if db.get_user_by_email(str(body.email)):
        raise HTTPException(status_code=409, detail="این ایمیل قبلا ثبت شده است")
    user = db.create_user(
        str(uuid.uuid4()),
        str(body.email),
        body.name.strip(),
        hash_password(body.password),
        role=body.role,
    )
    return db.public_user(user)


@app.get("/v1/sessions")
def list_sessions(
    q: str | None = None,
    status: str | None = None,
    user: dict = Depends(get_current_user),
) -> dict:
    sessions = db.list_sessions(user["id"], q=q, status=status)
    return {"sessions": [session_body(s) for s in sessions]}


@app.post("/v1/sessions", status_code=201)
def create_session(body: SessionCreateBody, user: dict = Depends(get_current_user)) -> dict:
    language = _language(body.language)
    if body.min_speakers is not None and body.max_speakers is not None:
        if body.min_speakers > body.max_speakers:
            raise HTTPException(status_code=400, detail="min_speakers بزرگ‌تر از max است")
    session = db.create_session(
        str(uuid.uuid4()),
        user["id"],
        body.title.strip(),
        language,
        body.summarize,
        body.diarize,
        body.min_speakers,
        body.max_speakers,
    )
    return session_body(session, [])


@app.get("/v1/sessions/{session_id}")
def get_session(session_id: str, user: dict = Depends(get_current_user)) -> dict:
    session = _owned_session(session_id, user)
    return session_body(session, db.list_assets(session_id))


@app.patch("/v1/sessions/{session_id}")
def patch_session(
    session_id: str,
    body: SessionUpdateBody,
    user: dict = Depends(get_current_user),
) -> dict:
    session = _owned_session(session_id, user)
    fields: dict[str, Any] = {}
    if body.title is not None:
        fields["title"] = body.title.strip()
    if body.language is not None:
        fields["language"] = _language(body.language)
    if body.summarize is not None:
        fields["summarize"] = body.summarize
    if body.diarize is not None:
        fields["diarize"] = body.diarize
    if body.min_speakers is not None:
        fields["min_speakers"] = body.min_speakers
    if body.max_speakers is not None:
        fields["max_speakers"] = body.max_speakers
    if body.status is not None:
        if body.status not in {"draft", "recording"}:
            raise HTTPException(status_code=400, detail="وضعیت مجاز نیست")
        if session["status"] in {"queued", "processing", "completed"} and body.status == "recording":
            raise HTTPException(status_code=409, detail="این نشست قابل ادامه ضبط نیست")
        fields["status"] = body.status
        if body.status == "recording":
            fields["progress_message"] = "در حال ضبط"
    updated = db.update_session(session_id, **fields)
    assert updated is not None
    return session_body(updated, db.list_assets(session_id))


@app.delete("/v1/sessions/{session_id}")
def remove_session(session_id: str, user: dict = Depends(get_current_user)) -> dict:
    session = _owned_session(session_id, user)
    if session["status"] in {"queued", "processing"}:
        raise HTTPException(status_code=409, detail="نشست در حال پردازش است")
    for asset in db.list_assets(session_id):
        try:
            storage.delete_audio(asset["object_key"])
        except Exception:
            log.exception("delete asset failed")
    db.delete_session(session_id)
    return {"ok": True}


@app.post("/v1/sessions/{session_id}/chunks", status_code=201)
async def upload_chunk(
    session_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
) -> dict:
    session = _owned_session(session_id, user)
    if session["status"] not in {"draft", "recording"}:
        raise HTTPException(status_code=409, detail="امکان افزودن تکه وجود ندارد")
    data = await _read_upload(file)
    filename = (file.filename or "chunk.webm").replace("\\", "/").split("/")[-1][:200]
    suffix = _extension(filename, file.content_type)
    order = db.next_asset_sort(session_id)
    object_key = f"{storage.session_prefix(user['id'], session_id)}chunks/{order:05d}{suffix}"
    storage.put_audio(object_key, data, file.content_type or "audio/webm")
    asset = db.add_asset(
        str(uuid.uuid4()),
        session_id,
        "chunk",
        object_key,
        filename,
        len(data),
        order,
    )
    db.update_session(session_id, status="recording", progress_message="در حال ضبط")
    return {"asset": asset}


@app.post("/v1/sessions/{session_id}/upload", status_code=201)
async def upload_source(
    session_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
) -> dict:
    session = _owned_session(session_id, user)
    if session["status"] not in {"draft", "recording", "completed", "failed"}:
        raise HTTPException(status_code=409, detail="امکان آپلود وجود ندارد")
    data = await _read_upload(file)
    filename = (file.filename or "audio").replace("\\", "/").split("/")[-1][:200]
    suffix = _extension(filename, file.content_type)
    order = db.next_asset_sort(session_id)
    object_key = f"{storage.session_prefix(user['id'], session_id)}source/{order:05d}{suffix}"
    storage.put_audio(object_key, data, file.content_type or "application/octet-stream")
    asset = db.add_asset(
        str(uuid.uuid4()),
        session_id,
        "source",
        object_key,
        filename,
        len(data),
        order,
    )
    if session["status"] == "draft":
        db.update_session(session_id, status="draft", progress_message="فایل آماده است")
    return {"asset": asset, "session": session_body(db.get_session(session_id), db.list_assets(session_id))}


@app.post("/v1/sessions/{session_id}/finalize", status_code=202)
def finalize_session(session_id: str, user: dict = Depends(get_current_user)) -> JSONResponse:
    session = _owned_session(session_id, user)
    if session["status"] in {"queued", "processing"}:
        raise HTTPException(status_code=409, detail="قبلا در صف است")
    assets = db.list_assets(session_id)
    if not assets:
        raise HTTPException(status_code=400, detail="هیچ فایل یا تکه‌ای وجود ندارد")
    if db.count_active_sessions() >= settings.max_queue_depth:
        raise HTTPException(status_code=429, detail="صف پردازش پر است")
    db.update_session(
        session_id,
        status="queued",
        progress=0,
        progress_message="در صف پردازش",
        error=None,
    )
    _enqueue(session_id)
    updated = db.get_session(session_id)
    assert updated is not None
    return JSONResponse(status_code=202, content=session_body(updated, assets))


@app.get("/v1/sessions/{session_id}/export")
def export_session(
    session_id: str,
    format: str = Query(default="txt"),
    user: dict = Depends(get_current_user),
):
    session = _owned_session(session_id, user)
    if session["status"] != "completed" or not session.get("result"):
        raise HTTPException(status_code=409, detail="رونوشت آماده نیست")
    fmt = format.lower().strip()
    if fmt == "json":
        return session_body(session, db.list_assets(session_id))
    if fmt == "srt":
        return PlainTextResponse(export_srt(session), media_type="application/x-subrip")
    if fmt == "txt":
        return PlainTextResponse(export_txt(session), media_type="text/plain; charset=utf-8")
    raise HTTPException(status_code=400, detail="فرمت نامعتبر است")


@app.get("/v1/files")
def list_files(user: dict = Depends(get_current_user)) -> dict:
    items = storage.list_prefix(storage.user_prefix(user["id"]))
    return {"files": items}


@app.get("/v1/files/download")
def download_file(key: str = Query(...), user: dict = Depends(get_current_user)):
    from fastapi.responses import Response

    prefix = storage.user_prefix(user["id"])
    if not key.startswith(prefix) and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="دسترسی ندارید")
    if ".." in key or key.startswith("/"):
        raise HTTPException(status_code=400, detail="کلید نامعتبر است")
    try:
        data = storage.get_bytes(key)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="فایل یافت نشد") from exc
    filename = key.rsplit("/", 1)[-1]
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
