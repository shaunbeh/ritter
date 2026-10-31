import json
from typing import Any

from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

from app.config import settings

pool = ConnectionPool(
    conninfo=settings.database_url,
    min_size=1,
    max_size=8,
    kwargs={"autocommit": True},
    open=False,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    prefs JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    language TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    summarize BOOLEAN NOT NULL DEFAULT TRUE,
    diarize BOOLEAN NOT NULL DEFAULT TRUE,
    min_speakers INT,
    max_speakers INT,
    progress INT NOT NULL DEFAULT 0,
    progress_message TEXT,
    result JSONB,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS sessions_status_idx ON sessions (status);

CREATE TABLE IF NOT EXISTS session_assets (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    object_key TEXT NOT NULL,
    filename TEXT,
    bytes INT NOT NULL DEFAULT 0,
    duration_ms INT,
    sort_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS session_assets_session_idx ON session_assets (session_id, sort_order);
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
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value


def _user_row(row) -> dict[str, Any]:
    return {
        "id": row[0],
        "email": row[1],
        "name": row[2],
        "password_hash": row[3],
        "role": row[4],
        "prefs": _json(row[5]) or {},
        "created_at": row[6].isoformat() if row[6] else None,
    }


def count_users() -> int:
    with pool.connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
    return int(row[0]) if row else 0


def create_user(
    user_id: str,
    email: str,
    name: str,
    password_hash: str,
    role: str = "user",
    prefs: dict | None = None,
) -> dict[str, Any]:
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, email, name, password_hash, role, prefs)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (user_id, email.lower(), name, password_hash, role, Json(prefs or {})),
        )
    user = get_user_by_id(user_id)
    assert user is not None
    return user


def get_user_by_email(email: str) -> dict[str, Any] | None:
    with pool.connection() as conn:
        row = conn.execute(
            """
            SELECT id::text, email, name, password_hash, role, prefs, created_at
            FROM users WHERE email = %s
            """,
            (email.lower(),),
        ).fetchone()
    return _user_row(row) if row else None


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    with pool.connection() as conn:
        row = conn.execute(
            """
            SELECT id::text, email, name, password_hash, role, prefs, created_at
            FROM users WHERE id = %s
            """,
            (user_id,),
        ).fetchone()
    return _user_row(row) if row else None


def list_users() -> list[dict[str, Any]]:
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT id::text, email, name, password_hash, role, prefs, created_at
            FROM users ORDER BY created_at ASC
            """
        ).fetchall()
    return [_user_row(row) for row in rows]


def update_user(
    user_id: str,
    *,
    name: str | None = None,
    password_hash: str | None = None,
    prefs: dict | None = None,
) -> dict[str, Any] | None:
    sets: list[str] = []
    args: list[Any] = []
    if name is not None:
        sets.append("name = %s")
        args.append(name)
    if password_hash is not None:
        sets.append("password_hash = %s")
        args.append(password_hash)
    if prefs is not None:
        sets.append("prefs = %s")
        args.append(Json(prefs))
    if not sets:
        return get_user_by_id(user_id)
    args.append(user_id)
    with pool.connection() as conn:
        conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = %s", args)
    return get_user_by_id(user_id)


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "prefs": user.get("prefs") or {},
        "created_at": user.get("created_at"),
    }


def _session_row(row) -> dict[str, Any]:
    return {
        "id": row[0],
        "user_id": row[1],
        "title": row[2],
        "language": row[3],
        "status": row[4],
        "summarize": row[5],
        "diarize": row[6],
        "min_speakers": row[7],
        "max_speakers": row[8],
        "progress": row[9],
        "progress_message": row[10],
        "result": _json(row[11]),
        "error": row[12],
        "created_at": row[13].isoformat() if row[13] else None,
        "updated_at": row[14].isoformat() if row[14] else None,
    }


def create_session(
    session_id: str,
    user_id: str,
    title: str,
    language: str | None,
    summarize: bool,
    diarize: bool,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> dict[str, Any]:
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO sessions (
                id, user_id, title, language, status, summarize, diarize,
                min_speakers, max_speakers, progress, progress_message
            )
            VALUES (%s, %s, %s, %s, 'draft', %s, %s, %s, %s, 0, 'پیش‌نویس')
            """,
            (
                session_id,
                user_id,
                title,
                language,
                summarize,
                diarize,
                min_speakers,
                max_speakers,
            ),
        )
    session = get_session(session_id)
    assert session is not None
    return session


def get_session(session_id: str) -> dict[str, Any] | None:
    with pool.connection() as conn:
        row = conn.execute(
            """
            SELECT id::text, user_id::text, title, language, status, summarize, diarize,
                   min_speakers, max_speakers, progress, progress_message, result, error,
                   created_at, updated_at
            FROM sessions WHERE id = %s
            """,
            (session_id,),
        ).fetchone()
    return _session_row(row) if row else None


def list_sessions(user_id: str, q: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    clauses = ["user_id = %s"]
    args: list[Any] = [user_id]
    if status:
        clauses.append("status = %s")
        args.append(status)
    if q:
        clauses.append("(title ILIKE %s OR COALESCE(language,'') ILIKE %s)")
        like = f"%{q}%"
        args.extend([like, like])
    where = " AND ".join(clauses)
    with pool.connection() as conn:
        rows = conn.execute(
            f"""
            SELECT id::text, user_id::text, title, language, status, summarize, diarize,
                   min_speakers, max_speakers, progress, progress_message, result, error,
                   created_at, updated_at
            FROM sessions
            WHERE {where}
            ORDER BY updated_at DESC
            LIMIT 200
            """,
            args,
        ).fetchall()
    return [_session_row(row) for row in rows]


def update_session(session_id: str, **fields: Any) -> dict[str, Any] | None:
    allowed = {
        "title",
        "language",
        "status",
        "summarize",
        "diarize",
        "min_speakers",
        "max_speakers",
        "progress",
        "progress_message",
        "result",
        "error",
    }
    sets: list[str] = []
    args: list[Any] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "result":
            sets.append("result = %s")
            args.append(Json(value) if value is not None else None)
        else:
            sets.append(f"{key} = %s")
            args.append(value)
    if not sets:
        return get_session(session_id)
    sets.append("updated_at = now()")
    args.append(session_id)
    with pool.connection() as conn:
        conn.execute(f"UPDATE sessions SET {', '.join(sets)} WHERE id = %s", args)
    return get_session(session_id)


def delete_session(session_id: str) -> bool:
    with pool.connection() as conn:
        row = conn.execute(
            "DELETE FROM sessions WHERE id = %s RETURNING id",
            (session_id,),
        ).fetchone()
    return row is not None


def count_active_sessions() -> int:
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE status IN ('queued', 'processing')"
        ).fetchone()
    return int(row[0]) if row else 0


def set_session_progress(session_id: str, progress: int, message: str) -> None:
    with pool.connection() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET progress = %s, progress_message = %s, updated_at = now()
            WHERE id = %s AND status = 'processing'
            """,
            (max(0, min(100, int(progress))), message[:240], session_id),
        )


def mark_session_processing(session_id: str) -> bool:
    with pool.connection() as conn:
        row = conn.execute(
            """
            UPDATE sessions
            SET status = 'processing', progress = 5, progress_message = 'شروع پردازش',
                error = NULL, updated_at = now()
            WHERE id = %s AND status = 'queued'
            RETURNING id
            """,
            (session_id,),
        ).fetchone()
    return row is not None


def complete_session(session_id: str, result: dict[str, Any]) -> None:
    with pool.connection() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET status = 'completed', result = %s, error = NULL,
                progress = 100, progress_message = 'تمام شد', updated_at = now()
            WHERE id = %s
            """,
            (Json(result), session_id),
        )


def fail_session(session_id: str, error: str) -> None:
    with pool.connection() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET status = 'failed', error = %s, progress_message = 'ناموفق',
                updated_at = now()
            WHERE id = %s AND status <> 'completed'
            """,
            (error[:4000], session_id),
        )


def requeue_processing_sessions() -> list[str]:
    with pool.connection() as conn:
        rows = conn.execute(
            """
            UPDATE sessions
            SET status = 'queued', updated_at = now()
            WHERE status = 'processing'
            RETURNING id::text
            """
        ).fetchall()
    return [row[0] for row in rows]


def ids_with_session_status(status: str) -> list[str]:
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT id::text FROM sessions WHERE status = %s",
            (status,),
        ).fetchall()
    return [row[0] for row in rows]


def requeue_session(session_id: str) -> None:
    with pool.connection() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET status = 'queued', updated_at = now()
            WHERE id = %s AND status IN ('queued', 'processing')
            """,
            (session_id,),
        )


def add_asset(
    asset_id: str,
    session_id: str,
    kind: str,
    object_key: str,
    filename: str | None,
    size: int,
    sort_order: int,
    duration_ms: int | None = None,
) -> dict[str, Any]:
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO session_assets (
                id, session_id, kind, object_key, filename, bytes, duration_ms, sort_order
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (asset_id, session_id, kind, object_key, filename, size, duration_ms, sort_order),
        )
    assets = list_assets(session_id)
    return next(a for a in assets if a["id"] == asset_id)


def list_assets(session_id: str) -> list[dict[str, Any]]:
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT id::text, session_id::text, kind, object_key, filename, bytes,
                   duration_ms, sort_order, created_at
            FROM session_assets
            WHERE session_id = %s
            ORDER BY sort_order ASC, created_at ASC
            """,
            (session_id,),
        ).fetchall()
    return [
        {
            "id": row[0],
            "session_id": row[1],
            "kind": row[2],
            "object_key": row[3],
            "filename": row[4],
            "bytes": row[5],
            "duration_ms": row[6],
            "sort_order": row[7],
            "created_at": row[8].isoformat() if row[8] else None,
        }
        for row in rows
    ]


def next_asset_sort(session_id: str) -> int:
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM session_assets WHERE session_id = %s",
            (session_id,),
        ).fetchone()
    return int(row[0]) if row else 0
