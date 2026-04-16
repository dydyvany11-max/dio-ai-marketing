from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timezone

from src.api.config import PROJECT_ROOT


_DB_PATH = os.getenv(
    "VK_ANALYSIS_HISTORY_DB_PATH",
    str((PROJECT_ROOT / "db" / "vk_analysis_history.db").resolve()),
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _init_db() -> None:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    with sqlite3.connect(_DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS vk_group_analysis_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                source_input TEXT,
                post_limit INTEGER,
                language TEXT,
                group_id INTEGER,
                group_name TEXT,
                screen_name TEXT,
                members_count INTEGER,
                total_posts_analyzed INTEGER,
                average_likes INTEGER,
                average_comments INTEGER,
                ai_summary TEXT,
                chat_json TEXT NOT NULL DEFAULT '[]',
                report_json TEXT NOT NULL
            )
            """
        )
        # Lightweight migration for older DBs created before chat persistence.
        cur.execute("PRAGMA table_info(vk_group_analysis_history)")
        columns = {str(row[1]) for row in cur.fetchall()}
        if "chat_json" not in columns:
            cur.execute(
                "ALTER TABLE vk_group_analysis_history ADD COLUMN chat_json TEXT NOT NULL DEFAULT '[]'"
            )
        conn.commit()


def save_analysis_report(
    *,
    source_input: str,
    post_limit: int,
    language: str,
    report: dict,
) -> int:
    _init_db()
    source = report.get("source") or {}
    metrics = report.get("metrics") or {}
    ai = report.get("ai") or {}
    with sqlite3.connect(_DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO vk_group_analysis_history (
                created_at, source_input, post_limit, language,
                group_id, group_name, screen_name, members_count,
                total_posts_analyzed, average_likes, average_comments,
                ai_summary, chat_json, report_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _utc_now_iso(),
                source_input,
                int(post_limit or 0),
                str(language or "ru"),
                int(source.get("group_id") or 0),
                str(source.get("name") or ""),
                str(source.get("screen_name") or ""),
                int(source.get("members_count") or 0) if source.get("members_count") is not None else None,
                int(metrics.get("total_posts_analyzed") or 0),
                int(metrics.get("average_likes") or 0),
                int(metrics.get("average_comments") or 0),
                str(ai.get("summary") or ""),
                "[]",
                json.dumps(report, ensure_ascii=False),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_analysis_history(limit: int = 30) -> list[dict]:
    _init_db()
    normalized_limit = max(1, min(int(limit or 30), 200))
    with sqlite3.connect(_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                id, created_at, source_input, post_limit, language,
                group_id, group_name, screen_name, members_count,
                total_posts_analyzed, average_likes, average_comments, ai_summary
            FROM vk_group_analysis_history
            ORDER BY id DESC
            LIMIT ?
            """,
            (normalized_limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def get_analysis_history_item(history_id: int) -> dict | None:
    _init_db()
    with sqlite3.connect(_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                id, created_at, source_input, post_limit, language,
                group_id, group_name, screen_name, members_count,
                total_posts_analyzed, average_likes, average_comments, ai_summary,
                chat_json, report_json
            FROM vk_group_analysis_history
            WHERE id = ?
            """,
            (int(history_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        data = dict(row)
        report_raw = data.pop("report_json", "")
        chat_raw = data.pop("chat_json", "[]")
        try:
            data["report"] = json.loads(report_raw) if report_raw else {}
        except Exception:
            data["report"] = {}
        try:
            parsed_chat = json.loads(chat_raw) if chat_raw else []
            if isinstance(parsed_chat, list):
                data["chat_messages"] = parsed_chat
            else:
                data["chat_messages"] = []
        except Exception:
            data["chat_messages"] = []
        return data


def append_analysis_chat_messages(history_id: int, messages: list[dict]) -> list[dict]:
    _init_db()
    normalized_new: list[dict] = []
    for item in messages or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        text = _normalize_chat_text(str(item.get("text") or ""))
        if not text:
            continue
        normalized_new.append(
            {
                "role": role,
                "text": text[:5000],
                "created_at": str(item.get("created_at") or _utc_now_iso()),
            }
        )
    if not normalized_new:
        return []

    with sqlite3.connect(_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT chat_json FROM vk_group_analysis_history WHERE id = ?",
            (int(history_id),),
        )
        row = cur.fetchone()
        if row is None:
            return []
        chat_raw = str(row["chat_json"] or "[]")
        try:
            existing = json.loads(chat_raw)
            if not isinstance(existing, list):
                existing = []
        except Exception:
            existing = []
        merged = (existing + normalized_new)[-120:]
        cur.execute(
            "UPDATE vk_group_analysis_history SET chat_json = ? WHERE id = ?",
            (json.dumps(merged, ensure_ascii=False), int(history_id)),
        )
        conn.commit()
        return merged


def _normalize_chat_text(text: str) -> str:
    value = str(text or "")
    value = value.replace("\\r\\n", "\n").replace("\\n", "\n")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.split()) for line in value.split("\n")]
    value = "\n".join(lines)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def clear_analysis_history() -> int:
    _init_db()
    with sqlite3.connect(_DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(1) FROM vk_group_analysis_history")
        row = cur.fetchone()
        total = int(row[0] or 0) if row else 0
        cur.execute("DELETE FROM vk_group_analysis_history")
        conn.commit()
        return total


def delete_analysis_history_item(history_id: int) -> bool:
    _init_db()
    with sqlite3.connect(_DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM vk_group_analysis_history WHERE id = ?", (int(history_id),))
        conn.commit()
        return int(cur.rowcount or 0) > 0
