from dataclasses import dataclass

import requests

from src.api.services.dto import VKPublishResult
from src.api.services.errors import VKOperationError
from src.api.services.vk_client import VKClient


@dataclass(frozen=True)
class VKPublishRequest:
    group_id: int
    message: str
    attachments: str | None
    publish_date: int | None


class VKPublisher:
    def __init__(self, vk_client: VKClient):
        self._vk = vk_client

    def publish(self, access_token: str, payload: VKPublishRequest) -> VKPublishResult:
        if not payload.group_id:
            raise VKOperationError("group_id is required")
        if not payload.message and not payload.attachments:
            raise VKOperationError("message or attachments required")

        owner_id = -abs(payload.group_id)
        params = {
            "owner_id": owner_id,
            "message": payload.message,
        }
        if payload.attachments:
            params["attachments"] = payload.attachments
        if payload.publish_date:
            params["publish_date"] = payload.publish_date

        response = self._vk.call_api("wall.post", access_token, **params)
        post_id = int(response.get("post_id", 0) or 0)
        if not post_id:
            raise VKOperationError("VK did not return post_id")
        return VKPublishResult(post_id=post_id, owner_id=owner_id)

    def publish_with_generated_image(
        self,
        *,
        access_token: str,
        group_id: int,
        message: str,
        image_bytes: bytes,
        image_mime_type: str = "image/jpeg",
    ) -> VKPublishResult:
        attachment = self._upload_wall_photo(
            access_token=access_token,
            group_id=group_id,
            image_bytes=image_bytes,
            image_mime_type=image_mime_type,
        )
        return self.publish(
            access_token=access_token,
            payload=VKPublishRequest(
                group_id=group_id,
                message=message,
                attachments=attachment,
                publish_date=None,
            ),
        )

    def _upload_wall_photo(
        self,
        *,
        access_token: str,
        group_id: int,
        image_bytes: bytes,
        image_mime_type: str,
    ) -> str:
        upload = self._vk.call_api(
            "photos.getWallUploadServer",
            access_token,
            group_id=group_id,
        )
        upload_url = str(upload.get("upload_url") or "").strip()
        if not upload_url:
            raise VKOperationError("VK did not provide upload_url for photo")

        files = {"photo": ("generated.jpg", image_bytes, image_mime_type)}
        try:
            upload_response = requests.post(upload_url, files=files, timeout=60)
            upload_response.raise_for_status()
            uploaded_payload = upload_response.json()
        except Exception as exc:
            raise VKOperationError(f"Failed to upload generated image to VK: {exc}") from exc

        photo = uploaded_payload.get("photo")
        server = uploaded_payload.get("server")
        hash_value = uploaded_payload.get("hash")
        if not photo or not server or not hash_value:
            raise VKOperationError("VK upload response is incomplete for photo")

        saved = self._vk.call_api(
            "photos.saveWallPhoto",
            access_token,
            group_id=group_id,
            photo=photo,
            server=server,
            hash=hash_value,
        )
        if not isinstance(saved, list) or not saved:
            raise VKOperationError("VK did not return saved photo")
        photo_item = saved[0]
        owner_id = int(photo_item.get("owner_id", 0) or 0)
        photo_id = int(photo_item.get("id", 0) or 0)
        if not owner_id or not photo_id:
            raise VKOperationError("VK saved photo payload is missing owner_id/id")
        return f"photo{owner_id}_{photo_id}"

    def publish_with_generated_video(
        self,
        *,
        access_token: str,
        group_id: int,
        message: str,
        video_bytes: bytes,
        video_mime_type: str = "video/mp4",
        video_title: str = "Generated video",
    ) -> VKPublishResult:
        attachment = self._upload_wall_video(
            access_token=access_token,
            group_id=group_id,
            video_bytes=video_bytes,
            video_mime_type=video_mime_type,
            title=video_title,
            description=message[:5000] if message else "",
        )
        return self.publish(
            access_token=access_token,
            payload=VKPublishRequest(
                group_id=group_id,
                message=message,
                attachments=attachment,
                publish_date=None,
            ),
        )

    def _upload_wall_video(
        self,
        *,
        access_token: str,
        group_id: int,
        video_bytes: bytes,
        video_mime_type: str,
        title: str,
        description: str,
    ) -> str:
        prepare = self._vk.call_api(
            "video.save",
            access_token,
            group_id=group_id,
            name=title,
            description=description,
            wallpost=0,
        )
        upload_url = str(prepare.get("upload_url") or "").strip()
        owner_id = int(prepare.get("owner_id", 0) or 0)
        video_id = int(prepare.get("video_id", 0) or 0)
        if not upload_url or not owner_id or not video_id:
            raise VKOperationError("VK did not return upload_url/owner_id/video_id for video")

        files = {"video_file": ("generated.mp4", video_bytes, video_mime_type)}
        try:
            upload_response = requests.post(upload_url, files=files, timeout=120)
            upload_response.raise_for_status()
        except Exception as exc:
            raise VKOperationError(f"Failed to upload generated video to VK: {exc}") from exc

        return f"video{owner_id}_{video_id}"
