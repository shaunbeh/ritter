QUEUE_KEY = "transcription:queue"

STATUS_LABELS = {
    "queued": "Queued — waiting for the GPU worker",
    "processing": "Processing",
    "completed": "Completed",
    "failed": "Failed",
}


def job_body(job: dict) -> dict:
    result = job.get("result") or {}
    status = job["status"]
    progress = job.get("progress")
    if progress is None:
        if status == "queued":
            progress = 0
        elif status == "completed":
            progress = 100
        elif status == "processing":
            progress = 10
        else:
            progress = 0
    message = job.get("progress_message") or STATUS_LABELS.get(status, status)
    body = {
        "id": job["id"],
        "status": status,
        "progress": progress,
        "progress_message": message,
        "language": result.get("language", job.get("language")),
        "segments": result.get("segments"),
        "summary": result.get("summary"),
    }
    if job.get("error"):
        body["error"] = job["error"]
    if result.get("diarization_error"):
        body["diarization_error"] = result["diarization_error"]
    if result.get("summary_error"):
        body["summary_error"] = result["summary_error"]
    return body
