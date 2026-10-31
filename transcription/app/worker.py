import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path

import redis

from app.config import redact, settings
from app import db, storage
from app.contract import CANCEL_PREFIX, GPU_LOCK, QUEUE_KEY
from app.summarize import summarize
from app.transcribe import LowVramError, ensure_vram, transcribe_file

log = logging.getLogger(__name__)

RECOVER_LOCK = "transcription:recover"
LOCK_TTL_SECONDS = 6 * 60 * 60


def _cancel_key(session_id: str) -> str:
    return f"{CANCEL_PREFIX}{session_id}"


def is_cancelled(session_id: str) -> bool:
    return bool(redis_client.get(_cancel_key(session_id)))


def clear_cancel(session_id: str) -> None:
    redis_client.delete(_cancel_key(session_id))

redis_client = redis.Redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=None,
    health_check_interval=30,
    retry_on_timeout=True,
)


def _run_ffmpeg(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "ffmpeg failed")[-1000:])


def _concat_assets(assets: list[dict], dest: str) -> None:
    if not assets:
        raise RuntimeError("no assets")
    if len(assets) == 1:
        storage.download_audio(assets[0]["object_key"], dest)
        return

    tmp_dir = tempfile.mkdtemp(prefix="tx-concat-")
    try:
        list_file = str(Path(tmp_dir) / "list.txt")
        with open(list_file, "w", encoding="utf-8") as handle:
            for index, asset in enumerate(assets):
                suffix = Path(asset.get("filename") or asset["object_key"]).suffix or ".webm"
                path = str(Path(tmp_dir) / f"part-{index:05d}{suffix}")
                storage.download_audio(asset["object_key"], path)
                escaped = path.replace("'", r"'\''")
                handle.write(f"file '{escaped}'\n")

        try:
            _run_ffmpeg(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", dest]
            )
        except RuntimeError:
            wav_dest = dest if dest.endswith(".wav") else f"{dest}.wav"
            _run_ffmpeg(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    list_file,
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    wav_dest,
                ]
            )
            if wav_dest != dest:
                os.replace(wav_dest, dest)
    finally:
        for root, _dirs, files in os.walk(tmp_dir, topdown=False):
            for name in files:
                try:
                    os.unlink(os.path.join(root, name))
                except OSError:
                    pass
            try:
                os.rmdir(root)
            except OSError:
                pass


class CancelledError(RuntimeError):
    pass


def process(session_id: str) -> None:
    session = db.get_session(session_id)
    if session is None or session["status"] in {"completed", "failed"}:
        return
    # Skip stale queue copies while this id is already running.
    if session["status"] == "processing":
        return

    if not redis_client.set(GPU_LOCK, session_id, nx=True, ex=LOCK_TTL_SECONDS):
        # Avoid duplicate flood when another job holds the GPU.
        if redis_client.llen(QUEUE_KEY) < 3:
            redis_client.rpush(QUEUE_KEY, session_id)
        time.sleep(5)
        return

    path = None
    retry_delay = 0
    clear_cancel(session_id)
    try:
        ensure_vram()
        if not db.mark_session_processing(session_id):
            return

        assets = [
            asset
            for asset in db.list_assets(session_id)
            if asset["kind"] in {"chunk", "source"}
        ]
        if not assets:
            raise RuntimeError("هیچ فایلی برای پردازش نیست")

        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        db.set_session_progress(session_id, 8, "ادغام فایل‌های صوتی")
        _concat_assets(assets, path)

        log.info(
            "Transcribing session %s with %s on %s",
            session_id,
            settings.whisper_model,
            settings.whisper_device,
        )

        def on_progress(value: int, message: str) -> None:
            if is_cancelled(session_id):
                raise CancelledError("پردازش توسط کاربر لغو شد")
            db.set_session_progress(session_id, value, message)

        result = transcribe_file(
            path,
            session["language"],
            session["diarize"],
            session["min_speakers"],
            session["max_speakers"],
            progress=on_progress,
            should_abort=lambda: is_cancelled(session_id),
        )
        if is_cancelled(session_id):
            raise CancelledError("پردازش توسط کاربر لغو شد")
        live = db.get_session(session_id)
        if live is None or live["status"] != "processing":
            raise CancelledError("پردازش لغو یا جایگزین شد")
        if session["summarize"]:
            db.set_session_progress(session_id, 92, "در حال خلاصه‌سازی با مدل زبانی")
            summary, summary_error = summarize(result["segments"], result.get("language"))
            result["summary"] = summary
            if summary_error:
                result["summary_error"] = summary_error
        db.complete_session(session_id, result)
        log.info("Completed session %s", session_id)
    except CancelledError as exc:
        log.warning("Session %s cancelled: %s", session_id, exc)
        # Force-retry already set status to queued; leave it for the next pop.
        live = db.get_session(session_id)
        if live and live["status"] == "processing":
            db.requeue_session(session_id)
            redis_client.rpush(QUEUE_KEY, session_id)
    except LowVramError as exc:
        log.warning("%s; session %s stays queued", exc, session_id)
        db.requeue_session(session_id)
        redis_client.rpush(QUEUE_KEY, session_id)
        retry_delay = 15
    except Exception as exc:
        log.exception("Session %s failed", session_id)
        db.fail_session(session_id, redact(str(exc)))
    finally:
        clear_cancel(session_id)
        if path and os.path.exists(path):
            os.unlink(path)
        current = redis_client.get(GPU_LOCK)
        if current == session_id:
            redis_client.delete(GPU_LOCK)
    if retry_delay:
        time.sleep(retry_delay)


def recover() -> None:
    if not redis_client.set(RECOVER_LOCK, "1", nx=True, ex=60):
        return
    redis_client.delete(GPU_LOCK)
    db.requeue_processing_sessions()
    present = set(redis_client.lrange(QUEUE_KEY, 0, -1))
    for session_id in db.ids_with_session_status("queued"):
        if session_id not in present:
            redis_client.rpush(QUEUE_KEY, session_id)
            log.warning("Requeued session %s", session_id)


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
    log.info("Worker waiting for sessions")
    while True:
        try:
            item = redis_client.blpop(QUEUE_KEY, timeout=5)
        except redis.TimeoutError:
            continue
        except redis.RedisError:
            log.exception("Redis queue wait failed; retrying")
            time.sleep(2)
            continue
        if not item:
            continue
        _key, session_id = item
        process(session_id)


if __name__ == "__main__":
    main()
