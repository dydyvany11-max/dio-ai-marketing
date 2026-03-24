from src.api.config import GigaChatSettings
from src.api.services.vk_ai import GigaChatVKClient


def _fake_settings() -> GigaChatSettings:
    return GigaChatSettings(
        credentials=None,
        authorization_key="test",
        client_id=None,
        model="GigaChat",
        verify_ssl_certs=False,
        scope="GIGACHAT_API_PERS",
        auth_url="https://example.com/oauth",
        base_url="https://example.com/chat",
    )


def test_generate_story_content_parses_frames():
    client = GigaChatVKClient(_fake_settings())
    client._chat = lambda _prompt: (
        '{"content_type":"story","text":"Story caption","story_frames":["Frame 1","Frame 2"]}'
    )

    result = client.generate_post(
        prompt="make story",
        content_type="story",
        language="ru",
    )

    assert result.content_type == "story"
    assert result.text == "Story caption"
    assert result.story_frames == ["Frame 1", "Frame 2"]


def test_generate_image_content_parses_image_prompt():
    client = GigaChatVKClient(_fake_settings())
    client._chat = lambda _prompt: (
        '{"content_type":"image","text":"Caption","image_prompt":"Product shot in studio light"}'
    )

    result = client.generate_post(
        prompt="make image concept",
        content_type="image",
        language="ru",
    )

    assert result.content_type == "image"
    assert result.text == "Caption"
    assert result.image_prompt == "Product shot in studio light"


def test_generate_image_uses_attachment_from_chat():
    client = GigaChatVKClient(_fake_settings())
    client._chat_raw = lambda _payload: {
        "choices": [
            {
                "message": {
                    "attachments": ["file-12345678901234567890"],
                    "content": "",
                }
            }
        ]
    }
    client._download_file_content = lambda _file_id: (b"image-bytes", "image/jpeg")

    data, mime, file_id = client.generate_image(prompt="pink cat")

    assert data == b"image-bytes"
    assert mime == "image/jpeg"
    assert file_id == "file-12345678901234567890"


def test_generate_video_uses_attachment_from_chat():
    client = GigaChatVKClient(_fake_settings())
    client._chat_raw = lambda _payload: {
        "choices": [
            {
                "message": {
                    "attachments": ["video-12345678901234567890"],
                    "content": "",
                }
            }
        ]
    }
    client._download_file_content = lambda _file_id: (b"video-bytes", "video/mp4")

    data, mime, file_id = client.generate_video(prompt="short ad video")

    assert data == b"video-bytes"
    assert mime == "video/mp4"
    assert file_id == "video-12345678901234567890"
