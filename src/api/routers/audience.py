from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import get_audience_analyzer, get_gigachat_status
from src.api.schemas import (
    AudienceAnalyzeInputResponse,
    AudienceAnalyzeRequest,
    AudienceClusteringResponse,
    GigaChatStatusResponse,
    TelegramAudienceReportResponse,
)
from src.api.services.errors import (
    AIEnhancementError,
    AuthorizationRequiredError,
    TelegramOperationError,
)
from src.api.services.interfaces import AudienceAnalyzerPort

router = APIRouter(prefix="/tg", tags=["Telegram: анализ аудитории"])


@router.post(
    "/audience/analyze",
    response_model=TelegramAudienceReportResponse,
    summary="Анализ аудитории Telegram-источника",
    description=(
        "Принимает ссылку, username или ID канала/группы Telegram и возвращает "
        "кластеры аудитории по активности, возрасту, интересам и итоговым сегментам."
    ),
)
async def analyze_audience(
    payload: AudienceAnalyzeRequest,
    audience_analyzer: AudienceAnalyzerPort = Depends(get_audience_analyzer),
):
    try:
        report = await audience_analyzer.analyze(
            source=payload.source,
            participant_limit=payload.participant_limit,
            message_limit=payload.message_limit,
        )
    except AuthorizationRequiredError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AIEnhancementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except TelegramOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    status = get_gigachat_status()
    return TelegramAudienceReportResponse(
        input=AudienceAnalyzeInputResponse(
            source=payload.source,
            participant_limit=payload.participant_limit,
            message_limit=payload.message_limit,
        ),
        ai=GigaChatStatusResponse(
            enabled=status.enabled,
            available=status.available,
            enhanced=report.ai_enhanced,
            provider=status.provider,
            model=status.model,
            auth_mode=status.auth_mode,
            message=report.ai_message or status.message,
        ),
        source=report.source,
        clustering=AudienceClusteringResponse(
            activity_clusters=report.activity_clusters,
            age_clusters=report.age_clusters,
            interest_clusters=report.interest_clusters,
            audience_segments=report.audience_segments,
            top_active_segment=report.top_active_segment,
            dominant_theme=report.dominant_theme,
            channel_themes=report.channel_themes,
        ),
        audience_persona=report.audience_persona,
        engagement_metrics=report.engagement_metrics,
        content_insights=report.content_insights,
        summary=report.summary,
        limitations=report.limitations,
    )


@router.get(
    "/ai/status",
    response_model=GigaChatStatusResponse,
    summary="Статус GigaChat",
    description="Показывает, настроен ли GigaChat, удалось ли приложению создать AI-клиент и будет ли AI участвовать в анализе.",
)
async def tg_ai_status():
    status = get_gigachat_status()
    return GigaChatStatusResponse(
        enabled=status.enabled,
        available=status.available,
        enhanced=False,
        provider=status.provider,
        model=status.model,
        auth_mode=status.auth_mode,
        message=status.message,
    )
