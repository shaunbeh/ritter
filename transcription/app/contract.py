QUEUE_KEY = "transcription:queue"


def job_body(job: dict) -> dict:
    result = job.get("result") or {}
    body = {
        "id": job["id"],
        "status": job["status"],
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
