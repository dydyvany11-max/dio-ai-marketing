from pathlib import Path

from src.api.services import vk_content_history as history


def test_vk_content_generation_history_roundtrip(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "vk_content_history.db"
    monkeypatch.setattr(history, "_DB_PATH", str(db_path))

    history_id = history.save_generated_post(
        request_payload={
            "prompt": "Напиши пост про автоматизацию",
            "theme": "автоматизация",
            "tone": "деловой",
            "content_type": "image",
            "publish": False,
            "language": "ru",
            "length": "short",
        },
        response_payload={
            "text": "Короткий пост",
            "content_type": "image",
            "published": False,
            "char_count": 14,
            "word_count": 2,
            "token_estimate": 4,
            "token_estimate_method": "chars/4",
            "generated_image_base64": "AAAABBBB",
        },
    )

    assert history_id > 0

    rows = history.list_generated_posts(limit=10)
    assert rows
    assert rows[0]["id"] == history_id
    assert rows[0]["prompt"] == "Напиши пост про автоматизацию"
    assert rows[0]["content_type"] == "image"

    item = history.get_generated_post(history_id)
    assert item is not None
    assert item["id"] == history_id
    assert item["report"]["text"] == "Короткий пост"
    assert item["report"]["generated_image_base64"] == "AAAABBBB"

    deleted = history.delete_generated_post(history_id)
    assert deleted is True
    assert history.get_generated_post(history_id) is None

    cleared = history.clear_generated_posts_history()
    assert cleared == 0
    assert history.list_generated_posts(limit=10) == []
