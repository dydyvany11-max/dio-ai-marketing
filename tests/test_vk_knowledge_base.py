from pathlib import Path

from src.api.services.vk_knowledge import VKKnowledgeStore


def test_vk_knowledge_store_upsert_and_get(tmp_path: Path):
    store = VKKnowledgeStore(path=tmp_path / "vk_kb.db")

    created = store.upsert(
        name="Tonebook",
        content="Use short hooks. End with CTA.",
        language="ru",
    )
    assert created["id"]

    loaded = store.get(created["id"])
    assert loaded is not None
    assert loaded["name"] == "Tonebook"
    assert "Use short hooks. End with CTA." in loaded["content"]

    updated = store.upsert(
        name="Tonebook v2",
        content="Use short hooks. End with CTA and poll.",
        language="ru",
        knowledge_base_id=created["id"],
    )
    assert updated["id"] == created["id"]

    loaded_after = store.get(created["id"])
    assert loaded_after is not None
    assert loaded_after["name"] == "Tonebook v2"


def test_vk_knowledge_store_active_and_excerpt(tmp_path: Path):
    store = VKKnowledgeStore(path=tmp_path / "vk_kb.db")

    first = store.upsert(name="KB 1", content="A" * 100, language="ru")
    second = store.upsert(name="KB 2", content="B" * 9000, language="ru")

    active = store.get_active()
    assert active is not None
    assert active["id"] == second["id"]

    items = store.list_items()
    assert items
    assert any(item["id"] == second["id"] and item["is_active"] for item in items)
    assert any(item["id"] == first["id"] for item in items)

    excerpt = VKKnowledgeStore.build_excerpt(active["content"], max_chars=500)
    assert len(excerpt) <= 500
    assert excerpt.endswith("...")


def test_vk_knowledge_store_add_file_and_merge_content(tmp_path: Path):
    store = VKKnowledgeStore(path=tmp_path / "vk_kb.db")

    base = store.upsert(
        name="Regulations",
        content="Main style guide for posts",
        language="ru",
    )

    updated = store.add_file(
        filename="policy.txt",
        content="No aggressive claims. Keep legal wording.",
        mime_type="text/plain",
        language="ru",
        knowledge_base_id=base["id"],
    )

    assert updated["id"] == base["id"]
    merged = updated.get("content", "")
    assert "Main style guide for posts" in merged
    assert "No aggressive claims" in merged


def test_vk_knowledge_store_retrieve_relevant_chunks(tmp_path: Path):
    store = VKKnowledgeStore(path=tmp_path / "vk_kb.db")
    base = store.upsert(
        name="Brandbook",
        content=(
            "Пиши коротко и по делу. Избегай канцелярита.\n"
            "Для постов про скидки всегда добавляй срок действия акции.\n"
            "Используй мягкий CTA в конце публикации."
        ),
        language="ru",
    )
    store.add_file(
        filename="music_policy.txt",
        content=(
            "Музыкальные релизы: сначала артист, затем трек, затем контекст.\n"
            "Не использовать агрессивные обещания и кликбейт."
        ),
        language="ru",
        knowledge_base_id=base["id"],
    )

    snippets = store.retrieve_relevant(query="пост про скидки и срок акции", max_chunks=3)
    context = store.build_retrieved_context(snippets)

    assert snippets
    assert "скидки" in context.lower()
    assert "срок" in context.lower()



def test_vk_knowledge_store_retrieve_relevant_en_query(tmp_path: Path):
    store = VKKnowledgeStore(path=tmp_path / "vk_kb.db")
    base = store.upsert(
        name="Brandbook EN",
        content=(
            "Keep ad copy short and specific.\n"
            "For discount posts always mention start and end date.\n"
            "Finish with one clear CTA."
        ),
        language="en",
    )
    store.add_file(
        filename="tone.txt",
        content=(
            "Do not use aggressive claims.\n"
            "Avoid clickbait and fake urgency."
        ),
        language="en",
        knowledge_base_id=base["id"],
    )

    snippets = store.retrieve_relevant(
        query="write a discount post with promo period and CTA",
        knowledge_base_id=base["id"],
        max_chunks=3,
    )
    context = store.build_retrieved_context(snippets).lower()

    assert snippets
    assert "discount" in context
    assert "date" in context or "period" in context


def test_vk_knowledge_store_retrieval_diversifies_sources(tmp_path: Path):
    store = VKKnowledgeStore(path=tmp_path / "vk_kb.db")
    base = store.upsert(
        name="Launch Guide",
        content=(
            "Product launch checklist.\n"
            "Message structure: hook, value, CTA.\n"
            "Audience: beginners."
        ),
        language="en",
    )
    store.add_file(
        filename="faq.txt",
        content=(
            "FAQ for support team.\n"
            "Common objections and concise responses.\n"
            "Escalation path and SLA."
        ),
        language="en",
        knowledge_base_id=base["id"],
    )

    snippets = store.retrieve_relevant(
        query="need hook and CTA plus handling objections",
        knowledge_base_id=base["id"],
        max_chunks=2,
    )
    titles = {str(item.get("title") or "") for item in snippets}

    assert len(snippets) == 2
    assert len(titles) >= 2


def test_vk_knowledge_store_delete_document(tmp_path: Path):
    store = VKKnowledgeStore(path=tmp_path / "vk_kb.db")
    base = store.upsert(
        name="Docs",
        content="Root rules",
        language="ru",
    )
    loaded = store.get(base["id"])
    assert loaded is not None

    store.add_file(
        filename="extra.txt",
        content="Second doc",
        language="ru",
        knowledge_base_id=base["id"],
    )
    loaded = store.get(base["id"])
    assert loaded is not None
    docs = loaded.get("documents") or []
    file_doc = next(doc for doc in docs if doc.get("source_type") == "file")
    deleted = store.delete_document(document_id=str(file_doc["id"]), knowledge_base_id=base["id"])

    assert deleted["knowledge_base_id"] == base["id"]
    assert deleted["remaining_documents"] >= 1

    loaded_after = store.get(base["id"])
    assert loaded_after is not None
    ids = {str(doc.get("id")) for doc in loaded_after.get("documents") or []}
    assert str(file_doc["id"]) not in ids


def test_vk_knowledge_store_delete_document_by_filename(tmp_path: Path):
    store = VKKnowledgeStore(path=tmp_path / "vk_kb.db")
    base = store.upsert(name="Docs", content="base", language="ru")
    store.add_file(
        filename="to_delete.txt",
        content="remove me",
        language="ru",
        knowledge_base_id=base["id"],
    )

    result = store.delete_document_by_filename(
        filename="to_delete.txt",
        knowledge_base_id=base["id"],
    )
    assert result["knowledge_base_id"] == base["id"]
