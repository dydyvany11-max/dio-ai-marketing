import logging
from dataclasses import dataclass
from typing import Any

import requests

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

    def build_auth_url(self, scope: str = "wall,groups,stats,offline") -> str:
        params = {
            "client_id": self._settings.app_id,
            "display": "page",
            "redirect_uri": self._settings.redirect_uri,
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
            raise VKOperationError(f"Failed to обменять код VK: {exc}") from exc

        if "error" in data:
            message = data.get("error_description") or data.get("error")
            raise VKAuthorizationError(f"VK OAuth error: {message}")

        return VKToken(
            access_token=data.get("access_token", ""),
            expires_in=data.get("expires_in"),
            user_id=data.get("user_id"),
        )

    def call_api(self, method: str, access_token: str, **params: Any) -> dict[str, Any]:
        if not access_token:
            raise VKAuthorizationError("VK access_token is required")

        payload = {
            "access_token": access_token,
            "v": self._settings.api_version,
            **params,
        }
        url = f"{self._api_base}/{method}"

        try:
            response = requests.get(url, params=payload, timeout=20)
            data = response.json()
        except Exception as exc:
            raise VKOperationError(f"VK API request failed: {exc}") from exc

        if "error" in data:
            error = data.get("error", {})
            message = error.get("error_msg") or "VK API error"
            raise VKOperationError(message)

        return data.get("response", {})

    @staticmethod
    def _encode_params(params: dict[str, Any]) -> str:
        return "&".join(f"{key}={requests.utils.quote(str(value))}" for key, value in params.items())
