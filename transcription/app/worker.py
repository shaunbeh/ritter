import logging
import os
import tempfile
import time
from pathlib import Path

import httpx
import redis

from app.config import redact, settings
from app import db, storage
from app.contract import QUEUE_KEY, job_body
from app.summarize import summarize
from app.transcribe import LowVramError, ensure_vram, transcribe_file

log = logging.getLogger(__name__)

GPU_LOCK = "transcription:gpu"
RECOVER_LOCK = "transcription:recover"
LOCK_TTL_SECONDS = 6 * 60 * 60

redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _notify(job: dict) -> None:
    callback = job.get("callback_url")
    if not callback:
        return
    try:
        with httpx.Client(timeout=15, follow_redirects=False) as client:
            response = client.post(callback, json=job_body(job))
            response.raise_for_status()
    except Exception:
        log.exception("Callback failed for %s", job["id"])


def _finish(job_id: str, delete_audio: bool, object_key: str) -> None:
    if delete_audio:
        try:
            storage.delete_audio(object_key)
        except Exception:
            log.exception("Could not delete audio for %s", job_id)
    job = db.get_job(job_id)
    if job is not None and job["status"] in {"completed", "failed"}:
        _notify(job)


def process(job_id: str) -> None:
    job = db.get_job(job_id)
    if job is None or job["status"] in {"completed", "failed", "processing"}:
        return

    if not redis_client.set(GPU_LOCK, job_id, nx=True, ex=LOCK_TTL_SECONDS):
        redis_client.rpush(QUEUE_KEY, job_id)
        time.sleep(5)
        return

    path = None
    delete_audio = False
    retry_delay = 0
    try:
        ensure_vram()
        if not db.mark_processing(job_id):
            return

        suffix = Path(job["filename"] or "audio").suffix or ".audio"
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        storage.download_audio(job["object_key"], path)
        log.info(
            "Transcribing %s with %s on %s",
            job_id,
            settings.whisper_model,
            settings.whisper_device,
        )
        result = transcribe_file(
            path,
            job["language"],
            job["diarize"],
            job["min_speakers"],
            job["max_speakers"],
        )
        if job["summarize"]:
            summary, summary_error = summarize(result["segments"], result.get("language"))
            result["summary"] = summary
            if summary_error:
                result["summary_error"] = summary_error
        db.complete_job(job_id, result)
        delete_audio = True
        log.info("Completed transcription %s", job_id)
    except LowVramError as exc:
        log.warning("%s; job %s stays queued", exc, job_id)
        db.requeue_job(job_id)
        redis_client.rpush(QUEUE_KEY, job_id)
        retry_delay = 15
    except Exception as exc:
        log.exception("Transcription %s failed", job_id)
        db.fail_job(job_id, redact(str(exc)))
        delete_audio = True
    finally:
        if path and os.path.exists(path):
            os.unlink(path)
        current = redis_client.get(GPU_LOCK)
        if current == job_id:
            redis_client.delete(GPU_LOCK)
        _finish(job_id, delete_audio, job["object_key"])
    if retry_delay:
        time.sleep(retry_delay)


def recover() -> None:
    if not redis_client.set(RECOVER_LOCK, "1", nx=True, ex=60):
        return
    # This service runs a single worker. A lock left by a dead process would
    # block the queue until its TTL, so drop it on startup.
    redis_client.delete(GPU_LOCK)
    db.requeue_processing()
    present = set(redis_client.lrange(QUEUE_KEY, 0, -1))
    for job_id in db.ids_with_status("queued"):
        if job_id not in present:
            redis_client.rpush(QUEUE_KEY, job_id)
            log.warning("Requeued job %s", job_id)


def check_gpu() -> None:
    if settings.whisper_device != "cuda":
        log.info("Transcription device is %s", settings.whisper_device)
        return
    import torch

    if not torch.cuda.is_available():
        raise SystemExit("WHISPER_DEVICE=cuda but no GPU is visible. Check the NVIDIA runtime.")
    free, total = torch.cuda.mem_get_info()
    log.info(
        "GPU %s free %.1f GiB / %.1f GiB; model %s (%s), one job at a time",
        torch.cuda.get_device_name(0),
        free / 2**30,
        total / 2**30,
        settings.whisper_model,
        settings.whisper_compute_type,
    )


def main() -> None:
    db.open_pool()
    storage.ensure_bucket()
    check_gpu()
    recover()
    log.info("Worker waiting for jobs")
    while True:
        item = redis_client.blpop(QUEUE_KEY, timeout=5)
        if not item:
            continue
        _key, job_id = item
        process(job_id)


if __name__ == "__main__":
    main()
