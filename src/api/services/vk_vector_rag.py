from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Callable

import requests

from src.api.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

try:
    import chromadb  
except Exception:  
    chromadb = None

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except Exception: 
    RecursiveCharacterTextSplitter = None

try:
    from sentence_transformers import SentenceTransformer
except Exception: 
    SentenceTransformer = None


class VKVectorRAG:
    def __init__(
        self,
        *,
        tokenize: Callable[[str], list[str]],
        chunk_size: int = 1024,
        chunk_overlap: int = 80,
    ):
        self._tokenize = tokenize
        self._enabled = os.getenv("VK_VECTOR_RAG_ENABLED", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self._embeddings_url = (
            os.getenv("RAG_EMBEDDINGS_URL", "").strip()
            or os.getenv("HUGGINGFACE_SPACE_URL", "").strip()
            or os.getenv("HUGGINGFACE_SPACE_EMBEDDINGS_URL", "").strip()
        ).rstrip("/")
        self._backend = (os.getenv("RAG_EMBEDDINGS_BACKEND", "auto").strip().lower() or "auto")
        self._model_name = (
            os.getenv(
                "RAG_EMBEDDINGS_MODEL",
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            ).strip()
            or "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )
        self._device = (os.getenv("RAG_EMBEDDINGS_DEVICE", "cpu").strip().lower() or "cpu")
        self._timeout = int(os.getenv("RAG_EMBEDDINGS_TIMEOUT_SEC", "60"))
        self._batch_size = max(1, int(os.getenv("RAG_EMBEDDINGS_BATCH_SIZE", "16")))
        self._chroma_path = Path(
            os.getenv("RAG_CHROMA_PATH", str((PROJECT_ROOT / "db" / "vk_rag_chroma").resolve()))
        )
        self._lock = threading.Lock()
        self._known_signatures: dict[str, str] = {}
        self._splitter = (
            RecursiveCharacterTextSplitter(
                chunk_size=max(256, int(chunk_size)),
                chunk_overlap=max(24, min(int(chunk_overlap), int(chunk_size) // 2)),
                length_function=len,
            )
            if RecursiveCharacterTextSplitter
            else None
        )
        self._client = None
        self._model: SentenceTransformer | None = None

    def ready(self) -> bool:
        if not self._enabled or chromadb is None:
            return False
        if self._backend == "local":
            return SentenceTransformer is not None
        if self._backend == "remote":
            return bool(self._embeddings_url)
        # auto
        return (SentenceTransformer is not None) or bool(self._embeddings_url)

    def retrieve(
        self,
        *,
        knowledge_base_id: str,
        query: str,
        documents: list[dict[str, Any]],
        max_chunks: int | None,
        max_chars: int,
    ) -> list[dict[str, Any]]:
        if not self.ready():
            return []
        if not query.strip() or not documents:
            return []

        with self._lock:
            collection = self._sync_collection(
                knowledge_base_id=knowledge_base_id,
                documents=documents,
            )

        if collection is None:
            return []

        query_embedding = self._embed_texts([query])[0]
        candidate_count = max(8, min(48, (max_chunks or 8) * 4))
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=candidate_count,
            include=["documents", "metadatas", "distances"],
        )

        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        query_tokens = set(self._tokenize(query))
        query_signal = {token for token in query_tokens if len(token) >= 4}

        selected: list[dict[str, Any]] = []
        used_chars = 0
        seen: set[str] = set()
        for doc, meta, distance in zip(docs, metas, distances, strict=False):
            snippet = str(doc or "").strip()
            if not snippet:
                continue
            meta = meta or {}
            doc_tokens = set(self._tokenize(snippet))
            overlap = query_tokens & doc_tokens
            signal_overlap = query_signal & doc_tokens
            dist = float(distance or 0.0)

            # Guardrail: cut semantic false-positives with weak lexical overlap.
            if not overlap and dist > 0.55:
                continue
            if query_signal and not signal_overlap and dist > 0.35:
                continue

            key = snippet[:220].lower()
            if key in seen:
                continue

            score = round(1.0 / (1.0 + max(0.0, dist)), 4)
            projected = used_chars + len(snippet)
            if selected and projected > max_chars:
                continue

            selected.append(
                {
                    "title": str(meta.get("title") or meta.get("filename") or "Document"),
                    "source_type": meta.get("source_type"),
                    "filename": meta.get("filename"),
                    "snippet": snippet,
                    "score": score,
                    "matched_terms": sorted(list(overlap))[:12],
                    "relevance_explain": {
                        "distance": round(dist, 4),
                        "token_overlap": len(overlap),
                        "signal_overlap": len(signal_overlap),
                    },
                }
            )
            used_chars = projected
            seen.add(key)
            if max_chunks is not None and len(selected) >= max_chunks:
                break

        return selected

    def _sync_collection(
        self,
        *,
        knowledge_base_id: str,
        documents: list[dict[str, Any]],
    ):
        client = self._get_client()
        if client is None:
            return None

        collection_name = self._collection_name(knowledge_base_id)
        signature = self._documents_signature(documents)
        if self._known_signatures.get(collection_name) == signature:
            try:
                return client.get_collection(collection_name)
            except Exception:
                self._known_signatures.pop(collection_name, None)

        try:
            client.delete_collection(collection_name)
        except Exception:
            pass
        collection = client.get_or_create_collection(collection_name)
        chunks = self._build_chunks(documents)
        if not chunks:
            self._known_signatures[collection_name] = signature
            return collection

        embeddings = self._embed_texts([chunk["text"] for chunk in chunks])
        collection.add(
            ids=[chunk["id"] for chunk in chunks],
            documents=[chunk["text"] for chunk in chunks],
            embeddings=embeddings,
            metadatas=[chunk["metadata"] for chunk in chunks],
        )
        self._known_signatures[collection_name] = signature
        return collection

    def _get_client(self):
        if not self.ready():
            return None
        if self._client is None:
            self._chroma_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self._chroma_path))
        return self._client

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        backend = self._resolve_backend()
        if backend == "local":
            return self._embed_texts_local(texts)
        return self._embed_texts_remote(texts)

    def _resolve_backend(self) -> str:
        if self._backend == "local":
            if SentenceTransformer is None:
                raise RuntimeError("RAG local backend requires sentence-transformers")
            return "local"
        if self._backend == "remote":
            if not self._embeddings_url:
                raise RuntimeError("RAG remote backend requires RAG_EMBEDDINGS_URL")
            return "remote"
        # auto
        if SentenceTransformer is not None:
            return "local"
        if self._embeddings_url:
            return "remote"
        raise RuntimeError("No embeddings backend available for vector RAG")

    def _embed_texts_local(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._get_model()
        embeddings = model.encode(
            texts,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [embedding.tolist() for embedding in embeddings]

    def _get_model(self) -> SentenceTransformer:
        if self._model is None:
            if SentenceTransformer is None:  # pragma: no cover - guarded by ready()
                raise RuntimeError("sentence-transformers is not installed")
            logger.info("Loading local embeddings model: %s", self._model_name)
            self._model = SentenceTransformer(self._model_name, device=self._device)
        return self._model

    def _embed_texts_remote(self, texts: list[str]) -> list[list[float]]:
        all_embeddings: list[list[float]] = []
        if not texts:
            return all_embeddings
        headers = {"Content-Type": "application/json"}
        with requests.Session() as session:
            for idx in range(0, len(texts), self._batch_size):
                batch = texts[idx : idx + self._batch_size]
                response = session.post(
                    f"{self._embeddings_url}/embeddings",
                    json={"texts": batch},
                    headers=headers,
                    timeout=self._timeout,
                )
                response.raise_for_status()
                data = response.json()
                embeddings = data.get("embeddings")
                if not isinstance(embeddings, list):
                    raise ValueError("Embeddings response does not contain 'embeddings' list")
                all_embeddings.extend(embeddings)
        if len(all_embeddings) != len(texts):
            raise ValueError("Embeddings count mismatch")
        return all_embeddings

    def _build_chunks(self, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        for doc in documents:
            content = str(doc.get("content") or "").strip()
            if not content:
                continue
            doc_id = str(doc.get("id") or "")
            title = str(doc.get("title") or doc.get("filename") or "Document").strip() or "Document"
            parts = self._split_text(content)
            for part_idx, part in enumerate(parts):
                text = str(part or "").strip()
                if not text:
                    continue
                hash_src = f"{doc_id}:{part_idx}:{text[:240]}"
                chunk_id = hashlib.sha1(hash_src.encode("utf-8")).hexdigest()
                chunks.append(
                    {
                        "id": chunk_id,
                        "text": text,
                        "metadata": self._sanitize_metadata(
                            {
                                "doc_id": doc_id,
                                "title": title,
                                "filename": doc.get("filename"),
                                "source_type": doc.get("source_type"),
                            }
                        ),
                    }
                )
        return chunks

    def _split_text(self, text: str) -> list[str]:
        if self._splitter is not None:
            return self._splitter.split_text(text)
        size = 1000
        overlap = 80
        out: list[str] = []
        start = 0
        while start < len(text):
            end = min(len(text), start + size)
            out.append(text[start:end])
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
        return out

    @staticmethod
    def _collection_name(knowledge_base_id: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_-]", "", (knowledge_base_id or "").strip()) or "default"
        return f"vk_kb_{normalized[:48]}"

    @staticmethod
    def _documents_signature(documents: list[dict[str, Any]]) -> str:
        rows: list[str] = []
        for doc in documents:
            rows.append(
                ":".join(
                    [
                        str(doc.get("id") or ""),
                        str(doc.get("updated_at") or ""),
                        str(len(str(doc.get("content") or ""))),
                    ]
                )
            )
        return hashlib.sha1("|".join(rows).encode("utf-8")).hexdigest()

    @staticmethod
    def _sanitize_metadata(raw: dict[str, Any]) -> dict[str, str]:
        output: dict[str, str] = {}
        for key, value in raw.items():
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            output[str(key)] = text[:512]
        return output
