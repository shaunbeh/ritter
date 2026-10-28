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
    import io

    client.put_object(
        settings.minio_bucket,
        object_key,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type or "application/octet-stream",
    )


def download_audio(object_key: str, dest_path: str) -> None:
    client.fget_object(settings.minio_bucket, object_key, dest_path)


def delete_audio(object_key: str) -> None:
    client.remove_object(settings.minio_bucket, object_key)
