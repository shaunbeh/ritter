import gc
import logging
from collections.abc import Callable

from app.config import redact, settings

log = logging.getLogger(__name__)

ProgressFn = Callable[[int, str], None]


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


def transcribe_file(
    path: str,
    language: str | None,
    diarize: bool,
    min_speakers: int | None,
    max_speakers: int | None,
    progress: ProgressFn | None = None,
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
    _report(progress, 12, "Loading audio")
    audio = whisperx.load_audio(path)
    detected = language

    _report(
        progress,
        20,
        f"Loading Whisper model ({settings.whisper_model}) — first run downloads weights",
    )
    model = whisperx.load_model(
        settings.whisper_model,
        device,
        compute_type=compute_type,
        download_root=settings.whisper_download_root,
    )
    try:
        _report(progress, 45, "Transcribing speech")
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
    try:
        _report(progress, 60, f"Aligning timestamps ({detected or 'auto'})")
        align_model, metadata = whisperx.load_align_model(
            language_code=detected,
            device=device,
            model_dir=settings.whisper_download_root,
        )
        try:
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
    except ValueError as exc:
        log.warning("Alignment skipped: %s", exc)
        _report(progress, 65, "Alignment unavailable for this language; continuing")

    diarization_error = None
    if diarize and not settings.hf_token:
        diarization_error = (
            "HF_TOKEN is not set, so speaker diarization was skipped. "
            "Accept the pyannote model terms and set HF_TOKEN."
        )
    elif diarize:
        _report(progress, 75, "Identifying speakers (may download diarization models)")
        pipeline_kwargs = {}
        if settings.diarize_model:
            pipeline_kwargs["model_name"] = settings.diarize_model
        diarize_model = DiarizationPipeline(
            token=settings.hf_token,
            device=device,
            cache_dir=settings.whisper_download_root,
            **pipeline_kwargs,
        )
        try:
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
            del diarize_model
            _release_cuda()

    _report(progress, 88, "Packaging transcript")
    payload = {
        "language": detected,
        "segments": _segments(aligned_segments),
        "summary": None,
    }
    if diarization_error:
        payload["diarization_error"] = diarization_error
    return payload
