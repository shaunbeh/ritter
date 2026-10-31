import json
from typing import Any

from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

from app.config import settings

pool = ConnectionPool(
    conninfo=settings.database_url,
    min_size=1,
    max_size=5,
    kwargs={"autocommit": True},
    open=False,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY,
    status TEXT NOT NULL,
    filename TEXT,
    object_key TEXT NOT NULL,
    language TEXT,
    summarize BOOLEAN NOT NULL DEFAULT TRUE,
    diarize BOOLEAN NOT NULL DEFAULT TRUE,
    min_speakers INT,
    max_speakers INT,
    callback_url TEXT,
    result JSONB,
    error TEXT,
    progress INT NOT NULL DEFAULT 0,
    progress_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS jobs_status_idx ON jobs (status);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS progress INT NOT NULL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS progress_message TEXT;
"""


def open_pool() -> None:
    if pool.closed:
        pool.open()
    with pool.connection() as conn:
        conn.execute(SCHEMA)


def close_pool() -> None:
    if not pool.closed:
        pool.close()


def _json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def insert_job(
    job_id: str,
    filename: str,
    object_key: str,
    language: str | None,
    summarize: bool,
    diarize: bool,
    min_speakers: int | None,
    max_speakers: int | None,
    callback_url: str | None,
) -> None:
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                id, status, filename, object_key, language, summarize, diarize,
                min_speakers, max_speakers, callback_url
            )
            VALUES (%s, 'queued', %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                job_id,
                filename,
                object_key,
                language,
                summarize,
                diarize,
                min_speakers,
                max_speakers,
                callback_url,
            ),
        )


def count_active() -> int:
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status IN ('queued', 'processing')"
        ).fetchone()
    return int(row[0]) if row else 0


def get_job(job_id: str) -> dict[str, Any] | None:
    with pool.connection() as conn:
        row = conn.execute(
            """
            SELECT id::text, status, language, result, error, callback_url,
                   object_key, filename, summarize, diarize, min_speakers, max_speakers,
                   progress, progress_message
            FROM jobs
            WHERE id = %s
            """,
            (job_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "status": row[1],
        "language": row[2],
        "result": _json(row[3]),
        "error": row[4],
        "callback_url": row[5],
        "object_key": row[6],
        "filename": row[7],
        "summarize": row[8],
        "diarize": row[9],
        "min_speakers": row[10],
        "max_speakers": row[11],
        "progress": row[12],
        "progress_message": row[13],
    }


def mark_processing(job_id: str) -> bool:
    with pool.connection() as conn:
        row = conn.execute(
            """
            UPDATE jobs
            SET status = 'processing',
                progress = 5,
                progress_message = 'Starting',
                updated_at = now(),
                error = NULL
            WHERE id = %s AND status = 'queued'
            RETURNING id
            """,
            (job_id,),
        ).fetchone()
    return row is not None


def set_progress(job_id: str, progress: int, message: str) -> None:
    with pool.connection() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET progress = %s,
                progress_message = %s,
                updated_at = now()
            WHERE id = %s AND status = 'processing'
            """,
            (max(0, min(100, int(progress))), message[:240], job_id),
        )


def complete_job(job_id: str, result: dict[str, Any]) -> None:
    with pool.connection() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET status = 'completed',
                result = %s,
                error = NULL,
                progress = 100,
                progress_message = 'Completed',
                updated_at = now()
            WHERE id = %s
            """,
            (Json(result), job_id),
        )


def fail_job(job_id: str, error: str) -> None:
    with pool.connection() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET status = 'failed',
                error = %s,
                progress_message = 'Failed',
                updated_at = now()
            WHERE id = %s AND status <> 'completed'
            """,
            (error[:4000], job_id),
        )


def ids_with_status(status: str) -> list[str]:
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT id::text FROM jobs WHERE status = %s",
            (status,),
        ).fetchall()
    return [row[0] for row in rows]


def requeue_processing() -> list[str]:
    with pool.connection() as conn:
        rows = conn.execute(
            """
            UPDATE jobs
            SET status = 'queued', updated_at = now()
            WHERE status = 'processing'
            RETURNING id::text
            """
        ).fetchall()
    return [row[0] for row in rows]


def requeue_job(job_id: str) -> None:
    with pool.connection() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET status = 'queued', updated_at = now()
            WHERE id = %s AND status IN ('queued', 'processing')
            """,
            (job_id,),
        )
