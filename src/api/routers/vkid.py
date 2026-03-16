import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
import base64
import hashlib
import secrets
import time
from typing import Dict, Tuple

from src.api.dependencies import get_vkid_client, get_vk_client
from src.api.config import PROJECT_ROOT
from src.api.schemas import VKIDAuthResponse
from src.api.services.errors import VKIDAuthorizationError, VKIDOperationError
from src.api.services.vkid_client import VKIDClient
from src.api.services.vk_client import VKClient



_VK_TOKEN_PATH = Path(os.getenv("VK_TOKEN_PATH", str(PROJECT_ROOT / "vk_token.json")))


def _save_vk_token(access_token: str, expires_in: int | None, user_id: int | None) -> None:
    data = {
        "access_token": access_token,
        "expires_in": expires_in,
        "user_id": user_id,
    }
    _VK_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _VK_TOKEN_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

router = APIRouter(prefix="/vkid", tags=["VK ID"])

# state -> (code_verifier, created_ts)
_VKID_STATE_STORE: Dict[str, Tuple[str, float]] = {}
_VKID_STATE_TTL = 600


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _create_pkce() -> tuple[str, str]:
    code_verifier = _b64url(secrets.token_bytes(32))
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = _b64url(digest)
    return code_verifier, code_challenge


def _put_state(state: str, code_verifier: str) -> None:
    _VKID_STATE_STORE[state] = (code_verifier, time.time())


def _pop_state(state: str) -> str | None:
    item = _VKID_STATE_STORE.pop(state, None)
    if not item:
        return None
    code_verifier, created = item
    if time.time() - created > _VKID_STATE_TTL:
        return None
    return code_verifier


def _gc_states() -> None:
    now = time.time()
    expired = [k for k, (_, ts) in _VKID_STATE_STORE.items() if now - ts > _VKID_STATE_TTL]
    for k in expired:
        _VKID_STATE_STORE.pop(k, None)


@router.get(
    "/start",
    summary="Start VK ID auth (redirects to VK ID)",
)
def vkid_start(client: VKIDClient = Depends(get_vkid_client)):
    _gc_states()
    code_verifier, code_challenge = _create_pkce()
    state = _b64url(secrets.token_bytes(16))
    _put_state(state, code_verifier)
    url = client.build_authorize_url(code_challenge=code_challenge, state=state)
    return RedirectResponse(url=url, status_code=302)




def _load_vk_token() -> str | None:
    if not _VK_TOKEN_PATH.exists():
        return None
    try:
        data = json.loads(_VK_TOKEN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    token = data.get("access_token")
    return token if isinstance(token, str) and token.strip() else None


@router.get(
    "/groups/admin",
    summary="VK ID admin groups",
)
def vkid_admin_groups(vk_client: VKClient = Depends(get_vk_client)):
    token = _load_vk_token()
    if not token:
        raise HTTPException(status_code=401, detail="VK ID access token is not saved")
    data = vk_client.call_api("groups.get", token, filter="admin")
    return data

@router.get(
    "/callback",
    response_model=VKIDAuthResponse,
    summary="VK ID callback (auto exchange + user info)",
)
def vkid_callback(
    code: str | None = None,
    device_id: str | None = None,
    state: str | None = None,
    client: VKIDClient = Depends(get_vkid_client),
):
    if not code:
        raise HTTPException(status_code=400, detail="code is required")
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id is required")
    if not state:
        raise HTTPException(status_code=400, detail="state is required")

    code_verifier = _pop_state(state)
    if not code_verifier:
        raise HTTPException(status_code=400, detail="state is missing or expired")

    try:
        token = client.exchange_code(
            code=code,
            device_id=device_id,
            code_verifier=code_verifier,
            state=state,
        )
        info = client.user_info(access_token=token.access_token)
    except VKIDAuthorizationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except VKIDOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _save_vk_token(token.access_token, token.expires_in, token.user_id)

    return VKIDAuthResponse(
        access_token=token.access_token,
        expires_in=token.expires_in,
        id_token=token.id_token,
        refresh_token=token.refresh_token,
        state=token.state,
        token_type=token.token_type,
        user_id=token.user_id,
        scope=token.scope,
        user=info.get("user"),
    )
