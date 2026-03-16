import json
import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from src.api.dependencies import get_vk_audience, get_vk_client, get_vk_publisher
from src.api.config import PROJECT_ROOT
from src.api.schemas import (
    VKAuthCallbackRequest,
    VKAuthCallbackResponse,
    VKAuthUrlResponse,
    VKCommunityAuthStartRequest,
    VKCommunityAuthUrlResponse,
    VKCommunityTokenResponse,
    VKAudienceAnalyzeRequest,
    VKAudienceReportResponse,
    VKPublishRequest,
    VKPublishResponse,
)
from src.api.services.errors import VKAuthorizationError, VKOperationError
from src.api.services.vk_audience import VKAudienceAnalyzer
from src.api.services.vk_client import VKClient
from src.api.services.vk_publisher import VKPublisher, VKPublishRequest as VKPublishPayload

router = APIRouter(prefix="/vk", tags=["VK"])


_VK_COMMUNITY_TOKEN_PATH = Path(os.getenv("VK_COMMUNITY_TOKEN_PATH", str(PROJECT_ROOT / "vk_community_tokens.json")))


def _save_vk_community_tokens(data: dict) -> None:
    _VK_COMMUNITY_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _VK_COMMUNITY_TOKEN_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_vk_community_tokens() -> dict | None:
    if not _VK_COMMUNITY_TOKEN_PATH.exists():
        return None
    try:
        return json.loads(_VK_COMMUNITY_TOKEN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _get_group_token(group_id: int) -> str | None:
    data = _load_vk_community_tokens()
    if not data:
        return None
    groups = data.get("groups") or []
    for item in groups:
        if item.get("group_id") == group_id and item.get("access_token"):
            return item.get("access_token")
    return None


def _extract_group_id(source: str) -> int | None:
    if not source:
        return None
    value = source.strip()
    # digits only
    if re.fullmatch(r"\d+", value):
        return int(value)
    # vk.com/club123 or club123
    m = re.search(r"(?:club|public)(\d+)", value)
    if m:
        return int(m.group(1))
    return None

_VK_TOKEN_PATH = Path(os.getenv("VK_TOKEN_PATH", str(PROJECT_ROOT / "vk_token.json")))


def _save_vk_token(payload: VKAuthCallbackResponse) -> None:
    data = {
        "access_token": payload.access_token,
        "expires_in": payload.expires_in,
        "user_id": payload.user_id,
    }
    _VK_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _VK_TOKEN_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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
    "/auth/url",
    response_model=VKAuthUrlResponse,
    summary="OAuth ссылка VK",
    description="Возвращает URL для авторизации VK и получения code.",
)
def vk_auth_url(vk_client: VKClient = Depends(get_vk_client)):
    url = vk_client.build_auth_url()
    return VKAuthUrlResponse(url=url)

@router.get(
    "/login",
    summary="VK OAuth login (redirect)",
    description="Redirects to VK OAuth authorization page.",
)
def vk_login(vk_client: VKClient = Depends(get_vk_client)):
    url = vk_client.build_auth_url()
    return RedirectResponse(url=url, status_code=302)

@router.get(
    "/callback",
    response_model=VKAuthCallbackResponse,
    summary="OAuth callback VK (auto обмен code на токен)",
    description="Принимает code из query, обменивает на токен и сохраняет его на сервере.",
)
def vk_auth_callback_get(
    code: str,
    vk_client: VKClient = Depends(get_vk_client),
):
    try:
        token = vk_client.exchange_code(code)
    except VKAuthorizationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except VKOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = VKAuthCallbackResponse(
        access_token=token.access_token,
        expires_in=token.expires_in,
        user_id=token.user_id,
    )
    _save_vk_token(payload)
    return payload

@router.get(
    "/callback/html",
    response_class=HTMLResponse,
    summary="OAuth callback VK (HTML)",
    description="То же, что /vk/callback, но возвращает простую HTML-страницу.",
)
def vk_auth_callback_html(
    code: str,
    vk_client: VKClient = Depends(get_vk_client),
):
    payload = vk_auth_callback_get(code=code, vk_client=vk_client)
    html = f"""
    <html><body style='font-family:Arial;padding:24px;'>
      <h2>VK authorization complete</h2>
      <p>Token saved on server.</p>
      <p>User ID: {payload.user_id}</p>
    </body></html>
    """
    return HTMLResponse(content=html)

@router.get(
    "/auth/status",
    summary="Статус сохраненного VK токена",
)
def vk_auth_status():
    token = _load_vk_token()
    return {"authorized": bool(token), "token_path": str(_VK_TOKEN_PATH)}


@router.post(
    "/auth/callback",
    response_model=VKAuthCallbackResponse,
    summary="Обмен code на access_token",
    description="Принимает code и возвращает access_token, expires_in, user_id.",
)
def vk_auth_callback(
    payload: VKAuthCallbackRequest,
    vk_client: VKClient = Depends(get_vk_client),
):
    try:
        token = vk_client.exchange_code(payload.code)
    except VKAuthorizationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except VKOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response = VKAuthCallbackResponse(
        access_token=token.access_token,
        expires_in=token.expires_in,
        user_id=token.user_id,
    )
    _save_vk_token(response)
    return response



@router.post(
    "/community/auth/start",
    response_model=VKCommunityAuthUrlResponse,
    summary="Community OAuth start",
    description="Build OAuth URL for community token authorization.",
)
def vk_community_auth_start(
    payload: VKCommunityAuthStartRequest,
    vk_client: VKClient = Depends(get_vk_client),
):
    scope = payload.scope or "manage,messages,photos,docs"
    url = vk_client.build_group_auth_url(group_ids=payload.group_ids, scope=scope)
    return VKCommunityAuthUrlResponse(url=url)


@router.get(
    "/community/callback",
    response_model=VKCommunityTokenResponse,
    summary="Community OAuth callback",
    description="Exchange code for community access tokens and save them on server.",
)
def vk_community_callback(
    code: str,
    vk_client: VKClient = Depends(get_vk_client),
):
    data = vk_client.exchange_code_for_groups(code)
    _save_vk_community_tokens(data)
    return VKCommunityTokenResponse(groups=data.get("groups", []), expires_in=data.get("expires_in"))


@router.get(
    "/community/tokens",
    summary="Community token status",
)
def vk_community_tokens():
    return _load_vk_community_tokens() or {"groups": []}

@router.post(
    "/audience/analyze",
    response_model=VKAudienceReportResponse,
    summary="Анализ аудитории VK группы",
    description="Собирает базовые метрики стены и считает средние показатели.",
)
def vk_audience_analyze(
    payload: VKAudienceAnalyzeRequest,
    analyzer: VKAudienceAnalyzer = Depends(get_vk_audience),
):
    try:
        access_token = payload.access_token
        if not access_token:
            access_token = _get_group_token(payload.group_id)
        if not access_token:
            access_token = _load_vk_token()
        if not access_token:
            raise VKAuthorizationError("VK access_token is required")
        report = analyzer.analyze(
            source=payload.source,
            access_token=access_token,
            post_limit=payload.post_limit,
        )
    except VKAuthorizationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except VKOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return VKAudienceReportResponse(
        group=report.group,
        average_views=report.average_views,
        average_likes=report.average_likes,
        average_comments=report.average_comments,
        average_reposts=report.average_reposts,
        posts_per_day=report.posts_per_day,
        total_posts_analyzed=report.total_posts_analyzed,
        top_posts=report.top_posts,
        limitations=report.limitations,
    )


@router.post(
    "/posts/publish",
    response_model=VKPublishResponse,
    summary="Публикация поста в VK",
    description="Публикует пост в группу через wall.post.",
)
def vk_publish_post(
    payload: VKPublishRequest,
    publisher: VKPublisher = Depends(get_vk_publisher),
):
    try:
        access_token = payload.access_token
        if not access_token:
            group_id = _extract_group_id(payload.source)
            if group_id:
                access_token = _get_group_token(group_id)
        if not access_token:
            access_token = _load_vk_token()
        if not access_token:
            raise VKAuthorizationError("VK access_token is required")
        result = publisher.publish(
            access_token=access_token,
            payload=VKPublishPayload(
                group_id=payload.group_id,
                message=payload.message,
                attachments=payload.attachments,
                publish_date=payload.publish_date,
            ),
        )
    except VKAuthorizationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except VKOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return VKPublishResponse(
        post_id=result.post_id,
        owner_id=result.owner_id,
    )
