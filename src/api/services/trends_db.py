import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable


@dataclass
class Article:
    source_id: int | None
    source: str
    url: str
    title: str
    content: str
    published_at: str | None
    fetched_at: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db(db_path: str) -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                type TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                meta_json TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER,
                source TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                title TEXT,
                content TEXT,
                published_at TEXT,
                fetched_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS term_counts (
                term TEXT NOT NULL,
                bucket_start TEXT NOT NULL,
                count INTEGER NOT NULL,
                PRIMARY KEY (term, bucket_start)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS trends (
                term TEXT PRIMARY KEY,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                count_now INTEGER NOT NULL,
                count_prev INTEGER NOT NULL,
                growth REAL NOT NULL,
                score REAL NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def add_source(db_path: str, name: str, url: str, source_type: str, enabled: bool = True, meta_json: str | None = None) -> int:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO sources (name, url, type, enabled, meta_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, url, source_type, 1 if enabled else 0, meta_json, _utc_now()),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_sources(db_path: str, enabled_only: bool = False) -> list[dict]:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        if enabled_only:
            cur.execute("SELECT * FROM sources WHERE enabled = 1 ORDER BY id ASC")
        else:
            cur.execute("SELECT * FROM sources ORDER BY id ASC")
        return [dict(row) for row in cur.fetchall()]


def set_source_enabled(db_path: str, source_id: int, enabled: bool) -> None:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE sources SET enabled = ? WHERE id = ?", (1 if enabled else 0, source_id))
        conn.commit()


def store_articles(db_path: str, articles: Iterable[Article]) -> int:
    init_db(db_path)
    inserted = 0
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        for article in articles:
            try:
                cur.execute(
                    """
                    INSERT INTO articles (source_id, source, url, title, content, published_at, fetched_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        article.source_id,
                        article.source,
                        article.url,
                        article.title,
                        article.content,
                        article.published_at,
                        article.fetched_at,
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                continue
        conn.commit()
    return inserted


def list_recent_articles(db_path: str, limit: int = 100) -> list[dict]:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM articles ORDER BY fetched_at DESC LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def upsert_term_counts(db_path: str, counts: dict[str, dict[str, int]]) -> None:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        for bucket_start, terms in counts.items():
            for term, count in terms.items():
                cur.execute(
                    """
                    INSERT INTO term_counts (term, bucket_start, count)
                    VALUES (?, ?, ?)
                    ON CONFLICT(term, bucket_start) DO UPDATE SET count = count + excluded.count
                    """,
                    (term, bucket_start, count),
                )
        conn.commit()


def save_trends(db_path: str, trends: list[dict]) -> None:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM trends")
        for item in trends:
            cur.execute(
                """
                INSERT INTO trends (term, window_start, window_end, count_now, count_prev, growth, score, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["term"],
                    item["window_start"],
                    item["window_end"],
                    item["count_now"],
                    item["count_prev"],
                    item["growth"],
                    item["score"],
                    item["updated_at"],
                ),
            )
        conn.commit()


def list_trends(db_path: str, limit: int = 50) -> list[dict]:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM trends ORDER BY score DESC LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def clear_trends(db_path: str) -> None:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM articles")
        cur.execute("DELETE FROM term_counts")
        cur.execute("DELETE FROM trends")
        conn.commit()
