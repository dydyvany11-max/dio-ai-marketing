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
