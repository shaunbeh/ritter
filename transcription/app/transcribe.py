import gc
import logging
import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from pathlib import Path

from app.config import redact, settings

log = logging.getLogger(__name__)

ProgressFn = Callable[[int, str], None]

# Typical size of jonatasgrosman/wav2vec2-large-xlsr-53-persian weights.
ALIGN_MODEL_ESTIMATE_BYTES = int(os.getenv("ALIGN_MODEL_ESTIMATE_MB", "1260")) * 1024 * 1024


class LowVramError(RuntimeError):
    def __init__(self, free_mb: int, required_mb: int):
        super().__init__(
            f"GPU has {free_mb} MB free; waiting until {required_mb} MB is available"
        )
        self.free_mb = free_mb
        self.required_mb = required_mb


def ensure_vram() -> None:
    if settings.whisper_device != "cuda":
        return
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("WHISPER_DEVICE=cuda but this process cannot see a GPU")
    free, _total = torch.cuda.mem_get_info()
    free_mb = int(free / (1024 * 1024))
    if free_mb < settings.min_free_vram_mb:
        raise LowVramError(free_mb, settings.min_free_vram_mb)


def _release_cuda() -> None:
    if settings.whisper_device != "cuda":
        return
    import torch

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.synchronize()
        torch.cuda.empty_cache()


def _number(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return round(number, 3)


def _segments(raw_segments: list[dict]) -> list[dict]:
    segments = []
    for segment in raw_segments:
        text = (segment.get("text") or "").strip()
        start = _number(segment.get("start"))
        end = _number(segment.get("end"))
        if not text or start is None or end is None:
            continue
        segments.append(
            {
                "start": start,
                "end": end,
                "text": text,
                "speaker_id": segment.get("speaker"),
            }
        )
    return segments


def _report(progress: ProgressFn | None, value: int, message: str) -> None:
    if progress is None:
        return
    try:
        progress(value, message)
    except Exception:
        log.exception("Progress callback failed")


def _incomplete_bytes(root: Path) -> int:
    if not root.is_dir():
        return 0
    total = 0
    for path in root.rglob("*.incomplete"):
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total


def _watch_hub_download(
    stop: threading.Event,
    progress: ProgressFn | None,
    *,
    label: str,
    cache_root: str,
    base_pct: int,
    span_pct: int,
) -> None:
    """Poll HF cache incomplete files and push download progress to the session."""
    root = Path(cache_root)
    last_bytes = -1
    stalled_since: float | None = None
    while not stop.wait(2.0):
        size = _incomplete_bytes(root)
        if size <= 0:
            _report(progress, base_pct, f"{label} (آماده‌سازی کش…)")
            continue
        if size != last_bytes:
            last_bytes = size
            stalled_since = None
        elif stalled_since is None:
            stalled_since = time.monotonic()
        mb = size / (1024 * 1024)
        est_mb = ALIGN_MODEL_ESTIMATE_BYTES / (1024 * 1024)
        ratio = min(1.0, size / max(ALIGN_MODEL_ESTIMATE_BYTES, 1))
        pct = base_pct + int(span_pct * ratio)
        stall = ""
        if stalled_since is not None and time.monotonic() - stalled_since > 30:
            stall = " — کند یا متوقف؛ اگر ماند، «پردازش دوباره» را بزنید"
        _report(
            progress,
            min(base_pct + span_pct - 1, max(base_pct, pct)),
            f"{label} — {mb:.0f} / ~{est_mb:.0f} مگابایت{stall}",
        )


def _load_with_download_progress(
    loader: Callable[[], object],
    progress: ProgressFn | None,
    *,
    label: str,
    base_pct: int,
    span_pct: int,
    timeout_seconds: int,
    stall_seconds: int,
    should_abort: Callable[[], bool] | None = None,
) -> object:
    stop = threading.Event()
    watcher = threading.Thread(
        target=_watch_hub_download,
        kwargs={
            "stop": stop,
            "progress": progress,
            "label": label,
            "cache_root": settings.whisper_download_root,
            "base_pct": base_pct,
            "span_pct": span_pct,
        },
        daemon=True,
    )
    watcher.start()
    root = Path(settings.whisper_download_root)
    deadline = time.monotonic() + max(60, timeout_seconds)
    last_bytes = _incomplete_bytes(root)
    last_change = time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(loader)
            while True:
                if should_abort and should_abort():
                    raise TimeoutError(f"{label}: cancelled")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"{label}: overall timeout")
                size = _incomplete_bytes(root)
                if size != last_bytes:
                    last_bytes = size
                    last_change = time.monotonic()
                elif size > 0 and time.monotonic() - last_change >= stall_seconds:
                    raise TimeoutError(
                        f"{label}: stalled at {size / (1024 * 1024):.0f} MB"
                    )
                try:
                    return future.result(timeout=min(2.0, remaining))
                except FuturesTimeout:
                    continue
    finally:
        stop.set()


def transcribe_file(
    path: str,
    language: str | None,
    diarize: bool,
    min_speakers: int | None,
    max_speakers: int | None,
    progress: ProgressFn | None = None,
    should_abort: Callable[[], bool] | None = None,
) -> dict:
    import torch
    import whisperx
    from whisperx.diarize import DiarizationPipeline

    device = settings.whisper_device
    compute_type = settings.whisper_compute_type
    if device == "cpu" and compute_type == "int8_float16":
        compute_type = "int8"
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("WHISPER_DEVICE=cuda but this process cannot see a GPU")

    ensure_vram()
    _report(progress, 12, "بارگذاری صوت")
    audio = whisperx.load_audio(path)
    detected = language

    _report(progress, 20, f"بارگذاری مدل Whisper ({settings.whisper_model})")
    model = whisperx.load_model(
        settings.whisper_model,
        device,
        compute_type=compute_type,
        download_root=settings.whisper_download_root,
    )
    try:
        _report(progress, 45, "رونویسی گفتار")
        result = model.transcribe(
            audio,
            batch_size=settings.whisper_batch_size,
            language=language,
        )
    finally:
        del model
        _release_cuda()

    detected = result.get("language") or detected
    aligned_segments = result.get("segments") or []
    align_timeout = int(os.getenv("ALIGN_TIMEOUT_SECONDS", "1800"))
    align_stall_seconds = int(os.getenv("ALIGN_STALL_SECONDS", "180"))
    local_align = os.getenv("ALIGN_MODEL_DIR", "").strip()

    try:
        _report(
            progress,
            58,
            f"هم‌ترازی زمان‌ها ({detected or 'auto'}) — در صورت نیاز مدل دانلود می‌شود",
        )

        def _load_align():
            align_kwargs: dict = {
                "language_code": detected,
                "device": device,
                "model_dir": settings.whisper_download_root,
            }
            if local_align:
                align_kwargs["model_name"] = local_align
            return whisperx.load_align_model(**align_kwargs)

        align_model, metadata = _load_with_download_progress(
            _load_align,
            progress,
            label="دانلود مدل هم‌ترازی فارسی",
            base_pct=58,
            span_pct=14,
            timeout_seconds=align_timeout,
            stall_seconds=align_stall_seconds,
            should_abort=should_abort,
        )
        try:
            _report(progress, 72, "اعمال هم‌ترازی روی رونوشت")
            aligned = whisperx.align(
                aligned_segments,
                align_model,
                metadata,
                audio,
                device,
                return_char_alignments=False,
            )
            aligned_segments = aligned.get("segments") or aligned_segments
        finally:
            del align_model
            _release_cuda()
    except TimeoutError as exc:
        log.warning("Alignment skipped after timeout: %s", exc)
        _report(
            progress,
            65,
            "دانلود مدل هم‌ترازی کند/متوقف شد — ادامه بدون هم‌ترازی. برای تلاش دوباره «پردازش دوباره» را بزنید",
        )
    except Exception as exc:
        log.warning("Alignment skipped: %s", redact(str(exc)))
        _report(progress, 65, "هم‌ترازی در دسترس نیست؛ ادامه بدون آن")

    diarization_error = None
    if diarize and not settings.hf_token:
        diarization_error = (
            "HF_TOKEN تنظیم نشده؛ تشخیص گوینده رد شد. "
            "شرایط مدل pyannote را بپذیرید و HF_TOKEN را تنظیم کنید."
        )
    elif diarize:
        _report(progress, 75, "تشخیص گویندگان (ممکن است مدل دانلود شود)")
        diarize_model = None
        try:

            def _load_diarize():
                pipeline_kwargs = {}
                if settings.diarize_model:
                    pipeline_kwargs["model_name"] = settings.diarize_model
                return DiarizationPipeline(
                    token=settings.hf_token,
                    device=device,
                    cache_dir=settings.whisper_download_root,
                    **pipeline_kwargs,
                )

            diarize_model = _load_with_download_progress(
                _load_diarize,
                progress,
                label="دانلود مدل تشخیص گوینده",
                base_pct=75,
                span_pct=10,
                timeout_seconds=int(os.getenv("DIARIZE_TIMEOUT_SECONDS", "1800")),
                stall_seconds=int(os.getenv("DIARIZE_STALL_SECONDS", "180")),
                should_abort=should_abort,
            )
            call_kwargs = {}
            if min_speakers is not None:
                call_kwargs["min_speakers"] = min_speakers
            if max_speakers is not None:
                call_kwargs["max_speakers"] = max_speakers
            diarize_segments = diarize_model(audio, **call_kwargs)
            if isinstance(diarize_segments, tuple):
                diarize_segments = diarize_segments[0]
            assigned = whisperx.assign_word_speakers(
                diarize_segments,
                {"segments": aligned_segments, "language": detected},
            )
            aligned_segments = assigned.get("segments") or aligned_segments
        except Exception as exc:
            log.exception("Diarization failed")
            diarization_error = redact(str(exc))
        finally:
            if diarize_model is not None:
                del diarize_model
            _release_cuda()

    _report(progress, 88, "آماده‌سازی خروجی")
    payload = {
        "language": detected,
        "segments": _segments(aligned_segments),
        "summary": None,
    }
    if diarization_error:
        payload["diarization_error"] = diarization_error
    return payload
