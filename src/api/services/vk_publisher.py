from dataclasses import dataclass

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
