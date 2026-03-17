import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from src.api.config import PROJECT_ROOT
from src.api.dependencies import get_vk_audience, get_vk_publisher
from src.api.schemas import (
    VKAudienceAnalyzeRequest,
    VKAudienceReportResponse,
    VKPublishRequest,
    VKPublishResponse,
)
from src.api.services.errors import VKAuthorizationError, VKOperationError
from src.api.services.vk_audience import VKAudienceAnalyzer
from src.api.services.vk_publisher import VKPublisher, VKPublishRequest as VKPublishPayload

router = APIRouter(prefix="/vk", tags=["VK"])

_VK_TOKEN_PATH = Path(os.getenv("VK_TOKEN_PATH", str(PROJECT_ROOT / "vk_token.json")))


def _load_vk_token() -> str | None:
    if not _VK_TOKEN_PATH.exists():
        return None
    try:
        data = json.loads(_VK_TOKEN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    token = data.get("access_token")
    return token if isinstance(token, str) and token.strip() else None


@router.post(
    "/audience/analyze",
    response_model=VKAudienceReportResponse,
    summary="Analyze VK group audience",
    description="Fetches wall metrics and computes basic averages.",
)
def vk_audience_analyze(
    payload: VKAudienceAnalyzeRequest,
    analyzer: VKAudienceAnalyzer = Depends(get_vk_audience),
):
    try:
        access_token = payload.access_token or _load_vk_token()
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
    summary="Publish a VK post",
    description="Publishes a post via wall.post.",
)
def vk_publish_post(
    payload: VKPublishRequest,
    publisher: VKPublisher = Depends(get_vk_publisher),
):
    try:
        access_token = payload.access_token or _load_vk_token()
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
