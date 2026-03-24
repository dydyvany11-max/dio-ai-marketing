from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.api.config import PROJECT_ROOT


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class VKKnowledgeStore:
    def __init__(self, path: Path | None = None):
        default_path = PROJECT_ROOT / "db" / "knowledge_base.db"
        env_path = (
            os.getenv("KNOWLEDGE_DB_PATH", "").strip()
            or os.getenv("VK_KNOWLEDGE_BASE_PATH", "").strip()
        )
        self._path = Path(env_path) if env_path else (path or default_path)
        self._lock = threading.Lock()
        self._init_db()

    def upsert(
        self,
        *,
        name: str,
        content: str,
        language: str = "ru",
        knowledge_base_id: str | None = None,
    ) -> dict[str, Any]:
        cleaned_name = (name or "").strip()
        cleaned_content = (content or "").strip()
        cleaned_language = (language or "ru").strip().lower() or "ru"

        if not cleaned_name:
            raise ValueError("Knowledge base name is required")
        if not cleaned_content:
            raise ValueError("Knowledge base content is required")

        with self._lock:
            kb_id = self._ensure_base(
                knowledge_base_id=knowledge_base_id,
                name=cleaned_name,
                language=cleaned_language,
            )
            self._upsert_manual_document(
                knowledge_base_id=kb_id,
                title=cleaned_name,
                content=cleaned_content,
            )
            self._set_active(kb_id)
            return self.get(kb_id) or {}

    def add_file(
        self,
        *,
        filename: str,
        content: str,
        mime_type: str | None = None,
        language: str = "ru",
        name: str | None = None,
        knowledge_base_id: str | None = None,
    ) -> dict[str, Any]:
        cleaned_filename = (filename or "").strip()
        cleaned_content = (content or "").strip()
        cleaned_language = (language or "ru").strip().lower() or "ru"
        cleaned_name = (name or "").strip()

        if not cleaned_filename:
            raise ValueError("Filename is required")
        if not cleaned_content:
            raise ValueError("File content is empty")

        base_name = cleaned_name or Path(cleaned_filename).stem or "Knowledge base"
        with self._lock:
            kb_id = self._ensure_base(
                knowledge_base_id=knowledge_base_id,
                name=base_name,
                language=cleaned_language,
            )
            now = _utc_now_iso()
            doc_id = uuid.uuid4().hex
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO knowledge_documents (
                        id, knowledge_base_id, source_type, title, filename, mime_type,
                        content, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        doc_id,
                        kb_id,
                        "file",
                        Path(cleaned_filename).stem,
                        cleaned_filename,
                        (mime_type or "").strip() or None,
                        cleaned_content,
                        now,
                        now,
                    ),
                )
                conn.execute(
                    """
                    UPDATE knowledge_bases
                    SET updated_at = ?, name = COALESCE(NULLIF(?, ''), name), language = ?
                    WHERE id = ?
                    """,
                    (now, cleaned_name, cleaned_language, kb_id),
                )
            self._set_active(kb_id)
            return self.get(kb_id) or {}

    def list_items(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    kb.id,
                    kb.name,
                    kb.language,
                    kb.created_at,
                    kb.updated_at,
                    kb.is_active,
                    COALESCE(SUM(LENGTH(COALESCE(d.content, ''))), 0) AS content_length
                FROM knowledge_bases kb
                LEFT JOIN knowledge_documents d ON d.knowledge_base_id = kb.id
                GROUP BY kb.id
                ORDER BY kb.updated_at DESC
                """
            ).fetchall()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "language": row["language"],
                "content_length": int(row["content_length"] or 0),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "is_active": bool(row["is_active"]),
            }
            for row in rows
        ]

    def get(self, knowledge_base_id: str) -> dict[str, Any] | None:
        kb_id = (knowledge_base_id or "").strip()
        if not kb_id:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, name, language, created_at, updated_at, is_active
                FROM knowledge_bases
                WHERE id = ?
                """,
                (kb_id,),
            ).fetchone()
            if row is None:
                return None
            docs = conn.execute(
                """
                SELECT id, source_type, title, filename, mime_type, content, created_at, updated_at
                FROM knowledge_documents
                WHERE knowledge_base_id = ?
                ORDER BY created_at ASC
                """,
                (kb_id,),
            ).fetchall()

        docs_payload = []
        for doc in docs:
            docs_payload.append(
                {
                    "id": doc["id"],
                    "source_type": doc["source_type"],
                    "title": doc["title"],
                    "filename": doc["filename"],
                    "mime_type": doc["mime_type"],
                    "content": doc["content"] or "",
                    "created_at": doc["created_at"],
                    "updated_at": doc["updated_at"],
                }
            )

        return {
            "id": row["id"],
            "name": row["name"],
            "language": row["language"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "is_active": bool(row["is_active"]),
            "documents": docs_payload,
            "content": self._merge_documents(docs_payload),
        }

    def get_active(self) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id
                FROM knowledge_bases
                ORDER BY is_active DESC, updated_at DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return self.get(str(row["id"]))

    @staticmethod
    def build_excerpt(content: str, max_chars: int = 6000) -> str:
        text = (content or "").strip()
        if len(text) <= max_chars:
            return text
        return text[: max(0, max_chars - 3)].rstrip() + "..."

    def _init_db(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_bases (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    language TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_documents (
                    id TEXT PRIMARY KEY,
                    knowledge_base_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    title TEXT,
                    filename TEXT,
                    mime_type TEXT,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_knowledge_documents_kb
                ON knowledge_documents(knowledge_base_id)
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_base(self, *, knowledge_base_id: str | None, name: str, language: str) -> str:
        kb_id = (knowledge_base_id or "").strip()
        now = _utc_now_iso()
        with self._connect() as conn:
            if kb_id:
                existing = conn.execute(
                    "SELECT id FROM knowledge_bases WHERE id = ?",
                    (kb_id,),
                ).fetchone()
                if existing:
                    conn.execute(
                        """
                        UPDATE knowledge_bases
                        SET name = ?, language = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (name, language, now, kb_id),
                    )
                    return kb_id
                raise ValueError("Knowledge base not found")

            kb_id = uuid.uuid4().hex
            conn.execute(
                """
                INSERT INTO knowledge_bases (id, name, language, created_at, updated_at, is_active)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (kb_id, name, language, now, now),
            )
            return kb_id

    def _set_active(self, knowledge_base_id: str) -> None:
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute("UPDATE knowledge_bases SET is_active = 0")
            conn.execute(
                "UPDATE knowledge_bases SET is_active = 1, updated_at = ? WHERE id = ?",
                (now, knowledge_base_id),
            )

    def _upsert_manual_document(self, *, knowledge_base_id: str, title: str, content: str) -> None:
        now = _utc_now_iso()
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT id
                FROM knowledge_documents
                WHERE knowledge_base_id = ? AND source_type = 'text'
                LIMIT 1
                """,
                (knowledge_base_id,),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE knowledge_documents
                    SET title = ?, content = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (title, content, now, existing["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO knowledge_documents (
                        id, knowledge_base_id, source_type, title, filename, mime_type,
                        content, created_at, updated_at
                    )
                    VALUES (?, ?, 'text', ?, NULL, 'text/plain', ?, ?, ?)
                    """,
                    (uuid.uuid4().hex, knowledge_base_id, title, content, now, now),
                )
            conn.execute(
                "UPDATE knowledge_bases SET updated_at = ? WHERE id = ?",
                (now, knowledge_base_id),
            )

    @staticmethod
    def _merge_documents(documents: list[dict[str, Any]]) -> str:
        chunks: list[str] = []
        for document in documents:
            content = (document.get("content") or "").strip()
            if not content:
                continue
            title = (
                str(document.get("title") or "").strip()
                or str(document.get("filename") or "").strip()
                or "Document"
            )
            chunks.append(f"[{title}]\n{content}")
        return "\n\n".join(chunks).strip()
