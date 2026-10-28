import logging

import httpx

from app.config import redact, settings

log = logging.getLogger(__name__)


def _endpoint() -> str:
    base = settings.llm_base_url
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def summarize(segments: list[dict], language: str | None) -> tuple[str | None, str | None]:
    if not settings.llm_base_url:
        return None, None
    if not settings.llm_model:
        return None, "LLM_MODEL is not set"
    if not segments:
        return None, None

    lines = []
    for segment in segments:
        speaker = segment.get("speaker_id") or "SPEAKER"
        lines.append(f"{speaker}: {segment['text']}")
    transcript = "\n".join(lines)
    if len(transcript) > settings.summary_max_chars:
        transcript = transcript[: settings.summary_max_chars]

    language_hint = f" The transcript language code is {language}." if language else ""
    payload = {
        "model": settings.llm_model,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Summarize the transcript in a short paragraph, in the same language "
                    "as the transcript."
                    + language_hint
                ),
            },
            {"role": "user", "content": transcript},
        ],
    }
    headers = {"Content-Type": "application/json"}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"

    try:
        with httpx.Client(timeout=180) as client:
            response = client.post(_endpoint(), json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()
        content = body["choices"][0]["message"]["content"]
    except Exception as exc:
        log.exception("LLM summary failed")
        return None, redact(str(exc))
    text = (content or "").strip()
    return (text or None), None
