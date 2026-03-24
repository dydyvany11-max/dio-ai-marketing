import logging
from dataclasses import dataclass
from typing import Any

import requests
import vk_api
from vk_api.exceptions import VkApiError

from src.api.config import VKSettings
from src.api.services.errors import VKAuthorizationError, VKOperationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VKToken:
    access_token: str
    expires_in: int | None
    user_id: int | None


class VKClient:
    def __init__(self, settings: VKSettings):
        self._settings = settings
        self._api_base = "https://api.vk.com/method"
        self._oauth_base = "https://oauth.vk.com"

    @property
    def settings(self) -> VKSettings:
        return self._settings

    def build_auth_url(self, scope: str = "wall,groups") -> str:

        params = {
            "client_id": self._settings.app_id,
            "display": "page",
            "redirect_uri": self._settings.redirect_uri,
            "scope": scope,
            "response_type": "code",
            "v": self._settings.api_version,
        }
        return f"{self._oauth_base}/authorize?{self._encode_params(params)}"

    def build_group_auth_url(
        self,
        group_ids: list[int],
        scope: str = "manage,messages,photos,docs",
        display: str = "page",
    ) -> str:
        if not group_ids:
            raise VKAuthorizationError("group_ids is required")
        params = {
            "client_id": self._settings.app_id,
            "display": display,
            "redirect_uri": self._settings.redirect_uri,
            "group_ids": ",".join(str(gid) for gid in group_ids),
            "scope": scope,
            "response_type": "code",
            "v": self._settings.api_version,
        }
        return f"{self._oauth_base}/authorize?{self._encode_params(params)}"

    def exchange_code(self, code: str) -> VKToken:
        if not code:
            raise VKAuthorizationError("VK OAuth code is required")

        params = {
            "client_id": self._settings.app_id,
            "client_secret": self._settings.app_secret,
            "redirect_uri": self._settings.redirect_uri,
            "code": code,
        }
        url = f"{self._oauth_base}/access_token"
        try:
            response = requests.get(url, params=params, timeout=20)
            data = response.json()
        except Exception as exc:
            raise VKOperationError(f"Failed to exchange VK code: {exc}") from exc

        if "error" in data:
            message = data.get("error_description") or data.get("error")
            raise VKAuthorizationError(f"VK OAuth error: {message}")

        return VKToken(
            access_token=data.get("access_token", ""),
            expires_in=data.get("expires_in"),
            user_id=data.get("user_id"),
        )

    def exchange_code_for_groups(self, code: str) -> dict[str, Any]:
        if not code:
            raise VKAuthorizationError("VK OAuth code is required")
        if not self._settings.app_secret or not self._settings.redirect_uri:
            raise VKAuthorizationError("VK app_secret and redirect_uri are required")

        params = {
            "client_id": self._settings.app_id,
            "client_secret": self._settings.app_secret,
            "redirect_uri": self._settings.redirect_uri,
            "code": code,
        }
        url = f"{self._oauth_base}/access_token"
        try:
            response = requests.get(url, params=params, timeout=20)
            data = response.json()
        except Exception as exc:
            raise VKOperationError(f"Failed to exchange VK code: {exc}") from exc

        if "error" in data:
            message = data.get("error_description") or data.get("error")
            raise VKAuthorizationError(f"VK OAuth error: {message}")

        return data

    def call_api(self, method: str, access_token: str, **params: Any) -> dict[str, Any]:
        if not access_token:
            raise VKAuthorizationError("VK access_token is required")

        try:
            session = vk_api.VkApi(token=access_token, api_version=self._settings.api_version)
            return session.method(method, params)
        except VkApiError as exc:
            raise VKOperationError(str(exc)) from exc
        except Exception as exc:
            raise VKOperationError(f"VK API request failed: {exc}") from exc

    def resolve_screen_name(self, access_token: str, screen_name: str) -> dict[str, Any]:
        value = (screen_name or "").strip().lstrip("@")
        if not value:
            raise VKOperationError("VK source is empty")
        response = self.call_api("utils.resolveScreenName", access_token, screen_name=value)
        if not isinstance(response, dict):
            raise VKOperationError("VK returned unexpected resolveScreenName response")
        return response

    @staticmethod
    def _encode_params(params: dict[str, Any]) -> str:
        return "&".join(f"{key}={requests.utils.quote(str(value))}" for key, value in params.items())
