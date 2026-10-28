import logging
import os
from dataclasses import dataclass


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def redact(text: str) -> str:
    for secret in (
        os.getenv("HF_TOKEN", ""),
        os.getenv("LLM_API_KEY", ""),
        os.getenv("MINIO_SECRET_KEY", ""),
        os.getenv("MINIO_ROOT_PASSWORD", ""),
        os.getenv("API_KEY", ""),
    ):
        secret = secret.strip()
        if secret:
            text = text.replace(secret, "[redacted]")
    return text[:4000]


@dataclass(frozen=True)
class Settings:
    database_url: str
    redis_url: str
    api_keys: tuple[str, ...]
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    minio_secure: bool
    hf_token: str
    whisper_model: str
    whisper_device: str
    whisper_compute_type: str
    whisper_batch_size: int
    whisper_download_root: str
    min_free_vram_mb: int
    diarize_model: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    max_upload_bytes: int
    max_queue_depth: int
    summary_max_chars: int


def load_settings() -> Settings:
    keys = tuple(part.strip() for part in os.getenv("API_KEY", "").split(",") if part.strip())
    return Settings(
        database_url=_required("DATABASE_URL"),
        redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0"),
        api_keys=keys,
        minio_endpoint=os.getenv("MINIO_ENDPOINT", "minio:9000"),
        minio_access_key=_required("MINIO_ACCESS_KEY"),
        minio_secret_key=_required("MINIO_SECRET_KEY"),
        minio_bucket=os.getenv("MINIO_BUCKET", "transcriptions"),
        minio_secure=_bool("MINIO_SECURE", False),
        hf_token=os.getenv("HF_TOKEN", "").strip(),
        whisper_model=os.getenv("WHISPER_MODEL", "medium"),
        whisper_device=os.getenv("WHISPER_DEVICE", "cuda"),
        whisper_compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8_float16"),
        whisper_batch_size=_int("WHISPER_BATCH_SIZE", 4),
        whisper_download_root=os.getenv("WHISPER_DOWNLOAD_ROOT", "/cache/whisper"),
        min_free_vram_mb=_int("MIN_FREE_VRAM_MB", 4096),
        diarize_model=os.getenv("DIARIZE_MODEL", "").strip(),
        llm_base_url=os.getenv("LLM_BASE_URL", "").strip().rstrip("/"),
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_model=os.getenv("LLM_MODEL", "").strip(),
        max_upload_bytes=_int("MAX_UPLOAD_MB", 500) * 1024 * 1024,
        max_queue_depth=_int("MAX_QUEUE_DEPTH", 20),
        summary_max_chars=_int("SUMMARY_MAX_CHARS", 24000),
    )


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

settings = load_settings()
