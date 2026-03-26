from functools import lru_cache
from typing import NamedTuple

from src.api.config import (
    is_vkid_configured,
    is_vk_configured,
    load_vk_api_settings,
    load_vk_settings,
)
from src.api.services.vk_client import VKClient
from src.api.services.vk_publisher import VKPublisher


class _Services(NamedTuple):
    vk_client: VKClient | None
    vk_publisher: VKPublisher | None


@lru_cache(maxsize=1)
def _build_services() -> _Services:
    vk_client = None
    vk_publisher = None

    if is_vk_configured():
        vk_client = VKClient(load_vk_settings())
        vk_publisher = VKPublisher(vk_client)
    elif is_vkid_configured():
        # VK ID stores access_token via /vkid/store, no VK_APP_SECRET needed
        vk_client = VKClient(load_vk_api_settings())
        vk_publisher = VKPublisher(vk_client)

    return _Services(
        vk_client=vk_client,
        vk_publisher=vk_publisher,
    )


def get_vk_client() -> VKClient:
    client = _build_services().vk_client
    if client is None:
        raise RuntimeError("VK is not configured")
    return client


def get_vk_publisher() -> VKPublisher:
    service = _build_services().vk_publisher
    if service is None:
        raise RuntimeError("VK is not configured")
    return service
