from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

from src.api.config import PROJECT_ROOT


_DB_PATH = os.getenv(
    "VK_CONTENT_HISTORY_DB_PATH",
    str((PROJECT_ROOT / "db" / "vk_content_history.db").resolve()),
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _init_db() -> None:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    with sqlite3.connect(_DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS vk_post_generation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                prompt TEXT,
                theme TEXT,
                tone TEXT,
                content_type TEXT,
                publish_requested INTEGER NOT NULL DEFAULT 0,
                language TEXT,
                length TEXT,
                published INTEGER NOT NULL DEFAULT 0,
                post_id INTEGER,
                owner_id INTEGER,
                char_count INTEGER,
                word_count INTEGER,
                text_preview TEXT,
                response_json TEXT NOT NULL
            )
            """
        )
        conn.commit()


def save_generated_post(
    *,
    request_payload: dict,
    response_payload: dict,
) -> int:
    _init_db()
    request_data = dict(request_payload or {})
    response_data = dict(response_payload or {})
    text = str(response_data.get("text") or "").strip()
    preview = text[:220].strip()
    with sqlite3.connect(_DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO vk_post_generation_history (
                created_at, prompt, theme, tone, content_type,
                publish_requested, language, length,
                published, post_id, owner_id, char_count, word_count,
                text_preview, response_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _utc_now_iso(),
                str(request_data.get("prompt") or ""),
                str(request_data.get("theme") or "") or None,
                str(request_data.get("tone") or "") or None,
                str(response_data.get("content_type") or request_data.get("content_type") or "text"),
                1 if bool(request_data.get("publish")) else 0,
                str(request_data.get("language") or "ru"),
                str(request_data.get("length") or "medium"),
                1 if bool(response_data.get("published")) else 0,
                int(response_data.get("post_id") or 0) if response_data.get("post_id") is not None else None,
                int(response_data.get("owner_id") or 0) if response_data.get("owner_id") is not None else None,
                int(response_data.get("char_count") or 0),
                int(response_data.get("word_count") or 0),
                preview,
                json.dumps(response_data, ensure_ascii=False),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_generated_posts(limit: int = 30) -> list[dict]:
    _init_db()
    normalized_limit = max(1, min(int(limit or 30), 200))
    with sqlite3.connect(_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                id, created_at, prompt, theme, tone, content_type,
                publish_requested, language, length,
                published, post_id, owner_id, char_count, word_count, text_preview
            FROM vk_post_generation_history
            ORDER BY id DESC
            LIMIT ?
            """,
            (normalized_limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def get_generated_post(history_id: int) -> dict | None:
    _init_db()
    with sqlite3.connect(_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                id, created_at, prompt, theme, tone, content_type,
                publish_requested, language, length,
                published, post_id, owner_id, char_count, word_count, text_preview,
                response_json
            FROM vk_post_generation_history
            WHERE id = ?
            """,
            (int(history_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        data = dict(row)
        response_raw = data.pop("response_json", "")
        try:
            parsed = json.loads(response_raw) if response_raw else {}
        except Exception:
            parsed = {}
        data["report"] = parsed if isinstance(parsed, dict) else {}
        return data


def clear_generated_posts_history() -> int:
    _init_db()
    with sqlite3.connect(_DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(1) FROM vk_post_generation_history")
        row = cur.fetchone()
        total = int(row[0] or 0) if row else 0
        cur.execute("DELETE FROM vk_post_generation_history")
        conn.commit()
        return total


def delete_generated_post(history_id: int) -> bool:
    _init_db()
    with sqlite3.connect(_DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM vk_post_generation_history WHERE id = ?", (int(history_id),))
        conn.commit()
        return int(cur.rowcount or 0) > 0
