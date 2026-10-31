QUEUE_KEY = "transcription:sessions"

STATUS_LABELS = {
    "draft": "پیش‌نویس",
    "recording": "در حال ضبط",
    "queued": "در صف",
    "processing": "در حال پردازش",
    "completed": "تمام‌شده",
    "failed": "ناموفق",
}


def session_body(session: dict, assets: list[dict] | None = None) -> dict:
    result = session.get("result") or {}
    status = session["status"]
    progress = session.get("progress")
    if progress is None:
        progress = 100 if status == "completed" else 0 if status in {"draft", "recording"} else 10
    message = session.get("progress_message") or STATUS_LABELS.get(status, status)
    body = {
        "id": session["id"],
        "user_id": session["user_id"],
        "title": session["title"],
        "language": result.get("language", session.get("language")),
        "status": status,
        "summarize": session.get("summarize", True),
        "diarize": session.get("diarize", True),
        "min_speakers": session.get("min_speakers"),
        "max_speakers": session.get("max_speakers"),
        "progress": progress,
        "progress_message": message,
        "segments": result.get("segments"),
        "summary": result.get("summary"),
        "error": session.get("error"),
        "created_at": session.get("created_at"),
        "updated_at": session.get("updated_at"),
        "assets": assets or [],
    }
    if result.get("diarization_error"):
        body["diarization_error"] = result["diarization_error"]
    if result.get("summary_error"):
        body["summary_error"] = result["summary_error"]
    return body


def format_timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_srt_timestamp(seconds: float) -> str:
    total_ms = max(0, int(float(seconds) * 1000))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def export_txt(session: dict) -> str:
    result = session.get("result") or {}
    lines = []
    if result.get("summary"):
        lines.append("خلاصه:")
        lines.append(result["summary"])
        lines.append("")
        lines.append("متن:")
    for segment in result.get("segments") or []:
        speaker = segment.get("speaker_id") or "SPEAKER"
        lines.append(f"{speaker}: {segment.get('text', '')}")
    return "\n".join(lines).strip() + "\n"


def export_srt(session: dict) -> str:
    result = session.get("result") or {}
    blocks = []
    for idx, segment in enumerate(result.get("segments") or [], start=1):
        start = format_srt_timestamp(float(segment.get("start") or 0))
        end = format_srt_timestamp(float(segment.get("end") or 0))
        speaker = segment.get("speaker_id") or "SPEAKER"
        text = segment.get("text") or ""
        blocks.append(f"{idx}\n{start} --> {end}\n{speaker}: {text}\n")
    return "\n".join(blocks)
