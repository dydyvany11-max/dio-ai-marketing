import logging
from dataclasses import dataclass
from typing import Any

import requests

from src.api.config import VKIDSettings
from src.api.services.errors import VKIDAuthorizationError, VKIDOperationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VKIDToken:
    access_token: str
    expires_in: int | None
    id_token: str | None
    refresh_token: str | None
    state: str | None
    token_type: str | None
    user_id: int | None
    scope: str | None


class VKIDClient:
    def __init__(self, settings: VKIDSettings):
        self._settings = settings
        self._base = f"https://{settings.domain}"

    @property
    def settings(self) -> VKIDSettings:
        return self._settings

    def build_authorize_url(
        self,
        code_challenge: str,
        state: str | None = None,
    ) -> str:
        if not code_challenge:
            raise VKIDAuthorizationError("VK ID code_challenge is required")
        params: dict[str, Any] = {
            "response_type": "code",
            "client_id": self._settings.app_id,
            "redirect_uri": self._settings.redirect_uri,
            "scope": self._settings.scope,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if state:
            params["state"] = state
        return f"{self._base}/authorize?{self._encode_params(params)}"

    def exchange_code(
        self,
        code: str,
        device_id: str,
        code_verifier: str,
        state: str | None = None,
    ) -> VKIDToken:
        if not code:
            raise VKIDAuthorizationError("VK ID code is required")
        if not device_id:
            raise VKIDAuthorizationError("VK ID device_id is required")
        if not code_verifier:
            raise VKIDAuthorizationError("VK ID code_verifier is required")

        params: dict[str, Any] = {
            "grant_type": "authorization_code",
            "redirect_uri": self._settings.redirect_uri,
            "client_id": self._settings.app_id,
            "code_verifier": code_verifier,
            "device_id": device_id,
        }
        if state:
            params["state"] = state

        url = f"{self._base}/oauth2/auth"
        try:
            response = requests.post(url, params=params, data={"code": code}, timeout=20)
            data = response.json()
        except Exception as exc:
            raise VKIDOperationError(f"VK ID auth request failed: {exc}") from exc

        if "error" in data:
            message = data.get("error_description") or data.get("error")
            raise VKIDAuthorizationError(f"VK ID auth error: {message}")

        return VKIDToken(
            access_token=data.get("access_token", ""),
            expires_in=data.get("expires_in"),
            id_token=data.get("id_token"),
            refresh_token=data.get("refresh_token"),
            state=data.get("state"),
            token_type=data.get("token_type"),
            user_id=data.get("user_id"),
            scope=data.get("scope"),
        )

    def refresh_token(self, refresh_token: str, device_id: str, state: str | None = None) -> VKIDToken:
        if not refresh_token:
            raise VKIDAuthorizationError("VK ID refresh_token is required")
        if not device_id:
            raise VKIDAuthorizationError("VK ID device_id is required")

        params: dict[str, Any] = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self._settings.app_id,
            "device_id": device_id,
        }
        if state:
            params["state"] = state

        url = f"{self._base}/oauth2/auth"
        try:
            response = requests.post(url, params=params, timeout=20)
            data = response.json()
        except Exception as exc:
            raise VKIDOperationError(f"VK ID refresh request failed: {exc}") from exc

        if "error" in data:
            message = data.get("error_description") or data.get("error")
            raise VKIDAuthorizationError(f"VK ID refresh error: {message}")

        return VKIDToken(
            access_token=data.get("access_token", ""),
            expires_in=data.get("expires_in"),
            id_token=data.get("id_token"),
            refresh_token=data.get("refresh_token"),
            state=data.get("state"),
            token_type=data.get("token_type"),
            user_id=data.get("user_id"),
            scope=data.get("scope"),
        )

    def user_info(self, access_token: str) -> dict[str, Any]:
        if not access_token:
            raise VKIDAuthorizationError("VK ID access_token is required")

        params = {"client_id": self._settings.app_id}
        url = f"{self._base}/oauth2/user_info"
        try:
            response = requests.post(url, params=params, data={"access_token": access_token}, timeout=20)
            data = response.json()
        except Exception as exc:
            raise VKIDOperationError(f"VK ID user_info request failed: {exc}") from exc

        if "error" in data:
            message = data.get("error_description") or data.get("error")
            raise VKIDAuthorizationError(f"VK ID user_info error: {message}")

        return data

    @staticmethod
    def _encode_params(params: dict[str, Any]) -> str:
        return "&".join(f"{key}={requests.utils.quote(str(value))}" for key, value in params.items())
