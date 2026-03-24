from src.api.services.vk_publisher import VKPublisher


class _FakeVKClient:
    def call_api(self, method, access_token, **params):
        if method == "photos.getWallUploadServer":
            return {"upload_url": "https://upload.example.com"}
        if method == "photos.saveWallPhoto":
            return [{"owner_id": -123, "id": 456}]
        if method == "video.save":
            return {"upload_url": "https://upload-video.example.com", "owner_id": -123, "video_id": 999}
        if method == "wall.post":
            return {"post_id": 789}
        raise AssertionError(f"Unexpected method: {method}")


def test_publish_with_generated_image(monkeypatch):
    publisher = VKPublisher(_FakeVKClient())

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"photo": "photo_json", "server": 1, "hash": "hash_value"}

    monkeypatch.setattr(
        "src.api.services.vk_publisher.requests.post",
        lambda *args, **kwargs: _FakeResponse(),
    )

    result = publisher.publish_with_generated_image(
        access_token="token",
        group_id=123,
        message="caption",
        image_bytes=b"img",
        image_mime_type="image/jpeg",
    )

    assert result.post_id == 789
    assert result.owner_id == -123


def test_publish_with_generated_video(monkeypatch):
    publisher = VKPublisher(_FakeVKClient())

    class _FakeResponse:
        def raise_for_status(self):
            return None

    monkeypatch.setattr(
        "src.api.services.vk_publisher.requests.post",
        lambda *args, **kwargs: _FakeResponse(),
    )

    result = publisher.publish_with_generated_video(
        access_token="token",
        group_id=123,
        message="video caption",
        video_bytes=b"video",
        video_mime_type="video/mp4",
        video_title="AI video",
    )

    assert result.post_id == 789
    assert result.owner_id == -123
