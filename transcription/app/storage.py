import io
from datetime import timedelta
from typing import Any
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error

from app.config import settings

client = Minio(
    settings.minio_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=settings.minio_secure,
)


def ensure_bucket() -> None:
    try:
        if not client.bucket_exists(settings.minio_bucket):
            client.make_bucket(settings.minio_bucket)
    except S3Error as exc:
        if exc.code not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
            raise


def put_audio(object_key: str, data: bytes, content_type: str) -> None:
    client.put_object(
        settings.minio_bucket,
        object_key,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type or "application/octet-stream",
    )


def download_audio(object_key: str, dest_path: str) -> None:
    client.fget_object(settings.minio_bucket, object_key, dest_path)


def get_bytes(object_key: str) -> bytes:
    response = client.get_object(settings.minio_bucket, object_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def delete_audio(object_key: str) -> None:
    client.remove_object(settings.minio_bucket, object_key)


def list_prefix(prefix: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for obj in client.list_objects(settings.minio_bucket, prefix=prefix, recursive=True):
        if obj.is_dir:
            continue
        items.append(
            {
                "key": obj.object_name,
                "size": obj.size or 0,
                "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
                "etag": obj.etag,
            }
        )
    items.sort(key=lambda item: item.get("last_modified") or "", reverse=True)
    return items


def presigned_get(object_key: str, expires_seconds: int = 600) -> str:
    url = client.presigned_get_object(
        settings.minio_bucket,
        object_key,
        expires=timedelta(seconds=expires_seconds),
    )
    # Inside Docker, endpoint is minio:9000. Rewrite for browser via nginx optional later.
    parsed = urlparse(url)
    return url if parsed.netloc else url


def user_prefix(user_id: str) -> str:
    return f"users/{user_id}/"


def session_prefix(user_id: str, session_id: str) -> str:
    return f"users/{user_id}/sessions/{session_id}/"
