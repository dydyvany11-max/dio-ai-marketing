from __future__ import annotations

import os
import re
import sqlite3
import threading
import uuid
from collections import Counter
from datetime import datetime, timezone
import math
from pathlib import Path
from typing import Any

from src.api.config import PROJECT_ROOT
from src.api.services.vk_vector_rag import VKVectorRAG


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_GENERIC_STOPWORDS = {
    "and",
    "the",
    "for",
    "with",
    "this",
    "that",
    "from",
    "into",
    "about",
    "your",
    "you",
    "are",
    "\u043a\u0430\u043a",
    "\u0434\u043b\u044f",
    "\u044d\u0442\u043e",
    "\u0447\u0442\u043e",
    "\u0438\u043b\u0438",
    "\u043f\u0440\u0438",
    "\u043f\u043e\u0434",
    "\u043d\u0430\u0434",
    "\u0431\u0435\u0437",
    "\u0432\u0441\u0435",
    "\u0432\u0441\u0435\u0445",
    "\u0435\u0441\u043b\u0438",
    "\u0442\u0430\u043a\u0436\u0435",
    "\u0447\u0442\u043e\u0431\u044b",
    "\u0433\u0434\u0435",
    "\u043a\u043e\u0433\u0434\u0430",
    "\u043f\u043e\u0441\u043b\u0435",
    "\u043f\u0435\u0440\u0435\u0434",
    "\u0447\u0435\u0440\u0435\u0437",
    "\u0442\u0435\u043c\u0430",
    "\u0442\u043e\u043d",
    "\u043a\u043e\u043d\u0442\u0435\u043d\u0442",
    "\u043f\u043e\u0441\u0442",
    "\u0442\u0435\u043a\u0441\u0442",
    "\u0441\u0442\u0438\u043b\u044c",
    "\u043e\u0444\u0438\u0446\u0438\u0430\u043b\u044c\u043d\u044b\u0439",
    "\u0440\u0430\u0437\u0433\u043e\u0432\u043e\u0440\u043d\u044b\u0439",
    "\u0434\u0435\u043b\u043e\u0432\u043e\u0439",
    "\u0438\u043d\u0441\u0442\u0440\u0443\u043a\u0446\u0438\u044f",
    "\u0438\u043d\u0441\u0442\u0440\u0443\u043a\u0446",
    "\u0441\u043b\u043e\u0432\u043e",
    "\u0441\u043b\u043e\u0432\u0430",
    "\u0441\u043b\u043e\u0432",
}

_RU_SUFFIXES = (
    "\u0438\u044f\u043c\u0438",
    "\u044f\u043c\u0438",
    "\u0430\u043c\u0438",
    "\u043e\u0433\u043e",
    "\u0435\u043c\u0443",
    "\u043e\u043c\u0443",
    "\u0438\u043c\u0438",
    "\u044b\u043c\u0438",
    "\u0438\u044f\u0445",
    "\u0430\u0445",
    "\u044f\u0445",
    "\u0438\u044f",
    "\u044c\u044f",
    "\u0438\u0435",
    "\u044b\u0435",
    "\u0438\u0439",
    "\u044b\u0439",
    "\u043e\u0439",
    "\u0430\u044f",
    "\u043e\u0435",
    "\u0435\u0435",
    "\u0443\u044e",
    "\u044e\u044e",
    "\u043e\u0432",
    "\u0435\u0432",
    "\u043e\u043c",
    "\u0435\u043c",
    "\u0430\u043c",
    "\u044f\u043c",
    "\u044b",
    "\u0438",
    "\u0430",
    "\u044f",
    "\u043e",
    "\u0435",
    "\u0443",
    "\u044e",
)

_EN_SUFFIXES = (
    "ingly",
    "edly",
    "ization",
    "ation",
    "ments",
    "ment",
    "ingly",
    "edly",
    "ing",
    "edly",
    "edly",
    "ed",
    "ly",
    "es",
    "s",
)


class VKKnowledgeStore:
    def __init__(self, path: Path | None = None):
        default_path = PROJECT_ROOT / "db" / "knowledge_base.db"
        env_path = (
            os.getenv("KNOWLEDGE_DB_PATH", "").strip()
            or os.getenv("VK_KNOWLEDGE_BASE_PATH", "").strip()
        )
        self._path = Path(env_path) if env_path else (path or default_path)
        self._lock = threading.Lock()
        self._vector_rag = VKVectorRAG(tokenize=self._tokenize)
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

    def delete_document(
        self,
        *,
        document_id: str,
        knowledge_base_id: str | None = None,
    ) -> dict[str, Any]:
        cleaned_document_id = (document_id or "").strip()
        cleaned_kb_id = (knowledge_base_id or "").strip() or None
        if not cleaned_document_id:
            raise ValueError("Document id is required")

        with self._lock, self._connect() as conn:
            if cleaned_kb_id:
                row = conn.execute(
                    """
                    SELECT id, knowledge_base_id
                    FROM knowledge_documents
                    WHERE id = ? AND knowledge_base_id = ?
                    """,
                    (cleaned_document_id, cleaned_kb_id),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT id, knowledge_base_id
                    FROM knowledge_documents
                    WHERE id = ?
                    """,
                    (cleaned_document_id,),
                ).fetchone()

            if row is None:
                raise ValueError("Knowledge document not found")

            kb_id = str(row["knowledge_base_id"])
            conn.execute(
                "DELETE FROM knowledge_documents WHERE id = ?",
                (cleaned_document_id,),
            )
            now = _utc_now_iso()
            conn.execute(
                "UPDATE knowledge_bases SET updated_at = ? WHERE id = ?",
                (now, kb_id),
            )
            remaining = conn.execute(
                "SELECT COUNT(*) AS c FROM knowledge_documents WHERE knowledge_base_id = ?",
                (kb_id,),
            ).fetchone()
            remaining_docs = int((remaining["c"] if remaining else 0) or 0)

        return {
            "document_id": cleaned_document_id,
            "knowledge_base_id": kb_id,
            "remaining_documents": remaining_docs,
        }

    def delete_document_by_filename(
        self,
        *,
        filename: str,
        knowledge_base_id: str | None = None,
    ) -> dict[str, Any]:
        cleaned_filename = (filename or "").strip()
        cleaned_kb_id = (knowledge_base_id or "").strip() or None
        if not cleaned_filename:
            raise ValueError("Filename is required")

        with self._lock, self._connect() as conn:
            if cleaned_kb_id:
                row = conn.execute(
                    """
                    SELECT id
                    FROM knowledge_documents
                    WHERE knowledge_base_id = ? AND filename = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (cleaned_kb_id, cleaned_filename),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT id
                    FROM knowledge_documents
                    WHERE filename = ?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (cleaned_filename,),
                ).fetchone()

        if row is None:
            raise ValueError("Knowledge document not found")

        return self.delete_document(
            document_id=str(row["id"]),
            knowledge_base_id=cleaned_kb_id,
        )

    @staticmethod
    def build_excerpt(content: str, max_chars: int = 6000) -> str:
        text = (content or "").strip()
        if len(text) <= max_chars:
            return text
        return text[: max(0, max_chars - 3)].rstrip() + "..."

    def retrieve_relevant(
        self,
        *,
        query: str,
        knowledge_base_id: str | None = None,
        max_chunks: int | None = None,
        max_chars: int = 5000,
        chunk_size: int = 900,
        chunk_overlap: int = 160,
    ) -> list[dict[str, Any]]:
        normalized_query = " ".join((query or "").split()).strip()
        if not normalized_query:
            return []

        kb = self.get(knowledge_base_id) if knowledge_base_id else self.get_active()
        if not kb:
            return []

        documents = list(kb.get("documents") or [])
        if documents:
            try:
                vector_snippets = self._vector_rag.retrieve(
                    knowledge_base_id=str(kb.get("id") or ""),
                    query=normalized_query,
                    documents=documents,
                    max_chunks=max_chunks,
                    max_chars=max_chars,
                )
                if vector_snippets:
                    vector_snippets = self._filter_vector_snippets(vector_snippets)
                    if vector_snippets:
                        return vector_snippets
            except Exception:
                # Keep deterministic lexical fallback when vector backend is unavailable.
                pass

        chunks = self._build_chunks(
            documents=documents,
            chunk_size=max(300, chunk_size),
            chunk_overlap=max(40, min(chunk_overlap, chunk_size // 2)),
        )
        if not chunks:
            return []

        query_tokens = self._tokenize(normalized_query)
        raw_query_terms = self._raw_query_terms(normalized_query)
        query_phrases = self._query_phrases(query_tokens)
        query_char_ngrams = self._char_ngrams(normalized_query)
        query_token_set = set(query_tokens)
        query_signal_tokens = {
            token
            for token in query_token_set
            if len(token) >= 4 and token not in _GENERIC_STOPWORDS
        }
        required_token_overlap = 1 if len(query_signal_tokens) <= 4 else 2

        if not query_tokens and not raw_query_terms:
            return []

        token_doc_freq: Counter[str] = Counter()
        token_lengths: list[int] = []
        for chunk in chunks:
            tokens = list(chunk.get("tokens") or [])
            token_lengths.append(len(tokens))
            token_doc_freq.update(set(tokens))
        avg_len = (sum(token_lengths) / len(token_lengths)) if token_lengths else 1.0
        total_docs = max(1, len(chunks))

        scored: list[dict[str, Any]] = []
        query_counter = Counter(query_tokens)
        for chunk in chunks:
            token_counts = Counter(chunk.get("tokens") or [])
            chunk_token_set = set(token_counts.keys())
            token_overlap_count = len(query_token_set & chunk_token_set)
            signal_overlap_count = len(query_signal_tokens & chunk_token_set)
            bm25_score = self._bm25(
                token_counts=token_counts,
                query_counter=query_counter,
                token_doc_freq=token_doc_freq,
                total_docs=total_docs,
                chunk_len=max(1, len(chunk.get("tokens") or [])),
                avg_len=max(1.0, avg_len),
            )

            chunk_text_norm = str(chunk.get("normalized_text") or "")
            phrase_hits = sum(1 for phrase in query_phrases if phrase in chunk_text_norm)
            phrase_score = min(2.1, phrase_hits * 0.95)
            raw_term_score = 0.0
            raw_term_hits = 0
            for term in raw_query_terms:
                if term and term in chunk_text_norm:
                    raw_term_score += 1.45
                    raw_term_hits += 1

            char_overlap = self._jaccard(query_char_ngrams, chunk.get("char_ngrams") or set())
            char_score = char_overlap * 3.2

            lexical_hits = token_overlap_count + phrase_hits + raw_term_hits
            if lexical_hits == 0 and char_overlap < 0.28:
                continue
            if signal_overlap_count < required_token_overlap and phrase_hits == 0 and raw_term_hits == 0:
                continue

            overlap_bonus = min(1.8, token_overlap_count * 0.22) + min(0.9, phrase_hits * 0.35)
            total_score = bm25_score + phrase_score + raw_term_score + char_score
            total_score += overlap_bonus
            if total_score <= 0:
                continue

            scored.append(
                {
                    "title": chunk["title"],
                    "source_type": chunk["source_type"],
                    "filename": chunk["filename"],
                    "snippet": chunk["text"],
                    "score": round(total_score, 4),
                    "_score": float(total_score),
                    "_token_set": set(chunk.get("tokens") or []),
                    "_char_ngrams": set(chunk.get("char_ngrams") or set()),
                    "_token_overlap": token_overlap_count,
                    "_signal_overlap": signal_overlap_count,
                    "_phrase_hits": phrase_hits,
                    "_raw_term_hits": raw_term_hits,
                }
            )

        if not scored:
            return []

        scored.sort(key=lambda item: (item["_score"], len(item["snippet"])), reverse=True)
        top_score = float(scored[0]["_score"])
        min_keep_score = max(0.9, top_score * 0.38)
        relevance_filtered: list[dict[str, Any]] = []
        for item in scored:
            strong_lexical = (
                int(item.get("_signal_overlap") or 0) >= required_token_overlap
                or int(item.get("_phrase_hits") or 0) > 0
                or int(item.get("_raw_term_hits") or 0) > 0
            )
            if not strong_lexical:
                continue
            if float(item.get("_score") or 0.0) < min_keep_score:
                # allow a weaker chunk only when it still has clear lexical support
                if int(item.get("_signal_overlap") or 0) < (required_token_overlap + 1):
                    continue
            relevance_filtered.append(item)

        if relevance_filtered:
            scored = relevance_filtered

        scored = self._mmr_select(scored=scored, max_chunks=max_chunks)

        selected: list[dict[str, Any]] = []
        used_chars = 0
        seen_snippets: set[str] = set()
        for item in scored:
            snippet = str(item["snippet"]).strip()
            if not snippet:
                continue
            dedupe_key = snippet[:220].lower()
            if dedupe_key in seen_snippets:
                continue
            projected = used_chars + len(snippet)
            if selected and projected > max_chars:
                continue
            seen_snippets.add(dedupe_key)
            selected.append(
                {
                    "title": item["title"],
                    "source_type": item["source_type"],
                    "filename": item["filename"],
                    "snippet": snippet,
                    "score": round(float(item.get("_score") or item.get("score") or 0.0), 4),
                    "matched_terms": sorted(
                        list(query_token_set & set(item.get("_token_set") or set()))
                    )[:10],
                    "relevance_explain": {
                        "token_overlap": int(item.get("_token_overlap") or 0),
                        "phrase_hits": int(item.get("_phrase_hits") or 0),
                        "raw_term_hits": int(item.get("_raw_term_hits") or 0),
                    },
                }
            )
            used_chars = projected
            if max_chunks is not None and len(selected) >= max_chunks:
                break
        return self._filter_lexical_snippets(selected)

    @staticmethod
    def _filter_vector_snippets(snippets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not snippets:
            return []
        top_score = max(float(item.get("score") or 0.0) for item in snippets)
        min_keep_score = max(0.45, top_score * 0.72)

        filtered: list[dict[str, Any]] = []
        for item in snippets:
            score = float(item.get("score") or 0.0)
            explain = item.get("relevance_explain") or {}
            token_overlap = int(explain.get("token_overlap") or 0)
            signal_overlap = int(explain.get("signal_overlap") or 0)
            matched_terms = [str(term).strip().lower() for term in (item.get("matched_terms") or []) if str(term).strip()]
            informative_terms_count = len([term for term in matched_terms if term not in _GENERIC_STOPWORDS and len(term) >= 4])

            if score < min_keep_score and token_overlap < 2 and signal_overlap < 2:
                continue
            if score < 0.52 and token_overlap == 0:
                continue
            if informative_terms_count == 0 and score < 0.72:
                continue
            filtered.append(item)

        if filtered:
            return filtered
        return []

    @staticmethod
    def _filter_lexical_snippets(snippets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not snippets:
            return []
        top_score = max(float(item.get("score") or 0.0) for item in snippets)
        min_keep_score = max(1.15, top_score * 0.45)
        filtered: list[dict[str, Any]] = []
        for item in snippets:
            score = float(item.get("score") or 0.0)
            matched_terms_count = len([term for term in (item.get("matched_terms") or []) if str(term).strip()])
            explain = item.get("relevance_explain") or {}
            phrase_hits = int(explain.get("phrase_hits") or 0)
            raw_term_hits = int(explain.get("raw_term_hits") or 0)
            if score < min_keep_score and matched_terms_count < 2 and phrase_hits == 0 and raw_term_hits == 0:
                continue
            if matched_terms_count == 0 and phrase_hits == 0 and raw_term_hits == 0:
                continue
            filtered.append(item)
        return filtered

    @staticmethod
    def build_retrieved_context(snippets: list[dict[str, Any]], max_chars: int = 5000) -> str:
        if not snippets:
            return ""
        parts: list[str] = []
        used = 0
        for item in snippets:
            title = str(item.get("title") or item.get("filename") or "Document").strip() or "Document"
            snippet = str(item.get("snippet") or "").strip()
            if not snippet:
                continue
            block = f"[{title}]\n{snippet}"
            projected = used + len(block) + (2 if parts else 0)
            if parts and projected > max_chars:
                break
            parts.append(block)
            used = projected
        return "\n\n".join(parts).strip()

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

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        tokens: list[str] = []
        for raw in re.findall(r"\b\w+\b", text or "", flags=re.UNICODE):
            token = VKKnowledgeStore._normalize_token(raw)
            if token:
                tokens.append(token)
        return tokens

    @staticmethod
    def _normalize_token(raw: str) -> str:
        token = (raw or "").lower().replace("\u0451", "\u0435").strip("_-")
        if len(token) < 3:
            return ""
        if token in _GENERIC_STOPWORDS:
            return ""
        if not any(ch.isalpha() for ch in token):
            return ""
        if token.isdigit():
            return ""

        if re.search(r"[\u0430-\u044f]", token):
            for suffix in _RU_SUFFIXES:
                if token.endswith(suffix) and len(token) - len(suffix) >= 3:
                    token = token[: -len(suffix)]
                    break
        elif re.search(r"[a-z]", token):
            for suffix in _EN_SUFFIXES:
                if token.endswith(suffix) and len(token) - len(suffix) >= 3:
                    token = token[: -len(suffix)]
                    break

        if len(token) < 3 or token in _GENERIC_STOPWORDS:
            return ""
        return token

    @classmethod
    def _raw_query_terms(cls, query: str) -> list[str]:
        terms: list[str] = []
        seen: set[str] = set()
        for part in re.findall(r"[^\s,.;:!?()\[\]{}]+", query or ""):
            normalized = cls._normalize_for_search(part)
            if len(normalized) < 4:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            terms.append(normalized)
        return terms

    @classmethod
    def _query_phrases(cls, query_tokens: list[str]) -> list[str]:
        phrases: list[str] = []
        for idx in range(len(query_tokens) - 1):
            left = query_tokens[idx]
            right = query_tokens[idx + 1]
            if len(left) < 3 or len(right) < 3:
                continue
            phrases.append(f"{left} {right}")
        return phrases

    @staticmethod
    def _phrase_score(*, query_phrases: list[str], normalized_text: str) -> float:
        if not query_phrases or not normalized_text:
            return 0.0
        bonus = 0.0
        for phrase in query_phrases:
            if phrase in normalized_text:
                bonus += 0.95
        return bonus

    @staticmethod
    def _bm25(
        *,
        token_counts: Counter[str],
        query_counter: Counter[str],
        token_doc_freq: Counter[str],
        total_docs: int,
        chunk_len: int,
        avg_len: float,
    ) -> float:
        if not token_counts or not query_counter:
            return 0.0
        score = 0.0
        k1 = 1.4
        b = 0.75
        for token, q_tf in query_counter.items():
            tf = token_counts.get(token, 0)
            if tf <= 0:
                continue
            df = int(token_doc_freq.get(token, 0))
            idf = math.log(1.0 + ((total_docs - df + 0.5) / (df + 0.5)))
            denom = tf + k1 * (1.0 - b + b * (chunk_len / max(1.0, avg_len)))
            score += idf * ((tf * (k1 + 1.0)) / max(0.01, denom)) * (1.0 + 0.15 * (q_tf - 1))
        return score

    @classmethod
    def _normalize_for_search(cls, text: str) -> str:
        tokens = cls._tokenize(text)
        return " ".join(tokens)

    @staticmethod
    def _char_ngrams(text: str, *, min_n: int = 3, max_n: int = 5, limit: int = 1000) -> set[str]:
        base = re.sub(r"\s+", " ", (text or "").lower().replace("\u0451", "\u0435")).strip()
        if len(base) < min_n:
            return set()
        grams: set[str] = set()
        for n in range(min_n, max_n + 1):
            if len(base) < n:
                continue
            for idx in range(0, len(base) - n + 1):
                gram = base[idx : idx + n]
                if "  " in gram:
                    continue
                grams.add(gram)
                if len(grams) >= limit:
                    return grams
        return grams

    @staticmethod
    def _jaccard(left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        union_size = len(left | right)
        if union_size == 0:
            return 0.0
        return len(left & right) / union_size

    def _mmr_select(self, *, scored: list[dict[str, Any]], max_chunks: int | None) -> list[dict[str, Any]]:
        if max_chunks is None:
            max_chunks = len(scored)
        if len(scored) <= 1 or max_chunks <= 1:
            return scored[:max_chunks]

        remaining = list(scored)
        selected = [remaining.pop(0)]
        lambda_rel = 0.82

        while remaining and len(selected) < max_chunks:
            best_idx = 0
            best_score = float("-inf")
            for idx, candidate in enumerate(remaining):
                rel = float(candidate.get("_score") or 0.0)
                max_similarity = 0.0
                candidate_tokens = set(candidate.get("_token_set") or set())
                candidate_ngrams = set(candidate.get("_char_ngrams") or set())
                for picked in selected:
                    token_sim = self._jaccard(candidate_tokens, set(picked.get("_token_set") or set()))
                    char_sim = self._jaccard(candidate_ngrams, set(picked.get("_char_ngrams") or set()))
                    max_similarity = max(max_similarity, token_sim * 0.7 + char_sim * 0.3)
                mmr = lambda_rel * rel - (1.0 - lambda_rel) * max_similarity * rel
                if mmr > best_score:
                    best_score = mmr
                    best_idx = idx
            selected.append(remaining.pop(best_idx))

        return selected

    def _build_chunks(
        self,
        *,
        documents: list[dict[str, Any]],
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        for document in documents:
            content = str(document.get("content") or "").strip()
            if not content:
                continue
            title = (
                str(document.get("title") or "").strip()
                or str(document.get("filename") or "").strip()
                or "Document"
            )
            source_type = str(document.get("source_type") or "").strip() or None
            filename = str(document.get("filename") or "").strip() or None

            if len(content) <= chunk_size:
                tokens = self._tokenize(content)
                if tokens:
                    normalized_text = " ".join(tokens)
                    chunks.append(
                        {
                            "title": title,
                            "source_type": source_type,
                            "filename": filename,
                            "text": content,
                            "tokens": tokens,
                            "normalized_text": normalized_text,
                            "char_ngrams": self._char_ngrams(normalized_text),
                        }
                    )
                continue

            start = 0
            content_len = len(content)
            while start < content_len:
                end = min(content_len, start + chunk_size)
                if end < content_len:
                    boundary = content.rfind(" ", start, end)
                    if boundary > start + 120:
                        end = boundary
                chunk_text = content[start:end].strip()
                if chunk_text:
                    tokens = self._tokenize(chunk_text)
                    if tokens:
                        normalized_text = " ".join(tokens)
                        chunks.append(
                            {
                                "title": title,
                                "source_type": source_type,
                                "filename": filename,
                                "text": chunk_text,
                                "tokens": tokens,
                                "normalized_text": normalized_text,
                                "char_ngrams": self._char_ngrams(normalized_text),
                            }
                        )
                if end >= content_len:
                    break
                start = max(end - chunk_overlap, start + 1)
        return chunks

    @staticmethod
    def _fallback_chunks(
        chunks: list[dict[str, Any]],
        *,
        max_chunks: int | None,
        max_chars: int,
    ) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        used_chars = 0
        for chunk in chunks:
            snippet = str(chunk.get("text") or "").strip()
            if not snippet:
                continue
            projected = used_chars + len(snippet)
            if selected and projected > max_chars:
                continue
            selected.append(
                {
                    "title": chunk.get("title"),
                    "source_type": chunk.get("source_type"),
                    "filename": chunk.get("filename"),
                    "snippet": snippet,
                    "score": 0.0,
                }
            )
            used_chars = projected
            if max_chunks is not None and len(selected) >= max_chunks:
                break
        return selected
