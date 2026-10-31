import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import redis
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

from app.config import settings
from app import db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)
redis_client = redis.Redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=10,
    health_check_interval=30,
    retry_on_timeout=True,
)

REFRESH_PREFIX = "auth:refresh:"
REFRESH_DENY = "auth:deny:"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def _encode(payload: dict[str, Any], expires: timedelta) -> str:
    body = dict(payload)
    now = datetime.now(timezone.utc)
    body["iat"] = int(now.timestamp())
    body["exp"] = int((now + expires).timestamp())
    return jwt.encode(body, settings.jwt_secret, algorithm="HS256")


def create_access_token(user: dict[str, Any]) -> str:
    return _encode(
        {"sub": user["id"], "email": user["email"], "role": user["role"], "typ": "access"},
        timedelta(minutes=settings.jwt_access_minutes),
    )


def create_refresh_token(user: dict[str, Any]) -> str:
    jti = str(uuid.uuid4())
    token = _encode(
        {
            "sub": user["id"],
            "email": user["email"],
            "role": user["role"],
            "typ": "refresh",
            "jti": jti,
        },
        timedelta(days=settings.jwt_refresh_days),
    )
    redis_client.setex(
        f"{REFRESH_PREFIX}{jti}",
        settings.jwt_refresh_days * 86400,
        user["id"],
    )
    return token


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="توکن نامعتبر است") from exc


def revoke_refresh(jti: str) -> None:
    redis_client.delete(f"{REFRESH_PREFIX}{jti}")
    redis_client.setex(f"{REFRESH_DENY}{jti}", settings.jwt_refresh_days * 86400, "1")


def refresh_is_valid(jti: str) -> bool:
    if redis_client.get(f"{REFRESH_DENY}{jti}"):
        return False
    return bool(redis_client.get(f"{REFRESH_PREFIX}{jti}"))


def bootstrap_admin() -> None:
    if db.count_users() > 0:
        return
    db.create_user(
        str(uuid.uuid4()),
        settings.admin_email,
        settings.admin_name,
        hash_password(settings.admin_password),
        role="admin",
        prefs={"language": "fa", "summarize": True, "diarize": True},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="ورود لازم است")
    payload = decode_token(credentials.credentials)
    if payload.get("typ") != "access":
        raise HTTPException(status_code=401, detail="توکن دسترسی نامعتبر است")
    user = db.get_user_by_id(payload["sub"])
    if user is None:
        raise HTTPException(status_code=401, detail="کاربر یافت نشد")
    return user


async def require_admin(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="دسترسی مدیر لازم است")
    return user
