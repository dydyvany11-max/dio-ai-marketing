from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import get_vk_audience, get_vk_client, get_vk_publisher
from src.api.schemas import (
    VKAuthCallbackRequest,
    VKAuthCallbackResponse,
    VKAuthUrlResponse,
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


@router.get(
    "/auth/url",
    response_model=VKAuthUrlResponse,
    summary="OAuth ссылка VK",
    description="Возвращает URL для авторизации VK и получения code.",
)
def vk_auth_url(vk_client: VKClient = Depends(get_vk_client)):
    url = vk_client.build_auth_url()
    return VKAuthUrlResponse(url=url)


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

    return VKAuthCallbackResponse(
        access_token=token.access_token,
        expires_in=token.expires_in,
        user_id=token.user_id,
    )


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
        report = analyzer.analyze(
            source=payload.source,
            access_token=payload.access_token,
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
        result = publisher.publish(
            access_token=payload.access_token,
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
