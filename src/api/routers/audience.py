import io
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from src.api.dependencies import get_audience_analyzer, get_gigachat_status
from src.api.schemas import (
    AudienceAnalyzeInputResponse,
    AudienceAnalyzeRequest,
    AudienceClusteringResponse,
    AudienceCompetitorsInputResponse,
    AudienceCompetitorsRequest,
    CompetitorDiscoveryResponse,
    CompetitorFailureResponse,
    CompetitorMatchResponse,
    GigaChatStatusResponse,
    TelegramAudienceReportResponse,
)
from src.api.services.audience_dashboards import (
    build_audience_dashboard,
    build_competitors_dashboard,
    dashboards_available,
)
from src.api.services.errors import (
    AIEnhancementError,
    AuthorizationRequiredError,
    TelegramOperationError,
)
from src.api.services.interfaces import AudienceAnalyzerPort

router = APIRouter(prefix="/tg", tags=["Telegram: анализ аудитории"])
logger = logging.getLogger(__name__)


@router.post(
    "/audience/analyze",
    response_model=TelegramAudienceReportResponse,
    summary="Анализ аудитории Telegram-источника",
    description="Анализирует последние посты канала или группы и строит портрет целевой аудитории по контенту и метрикам постов.",
)
async def analyze_audience(
    payload: AudienceAnalyzeRequest,
    audience_analyzer: AudienceAnalyzerPort = Depends(get_audience_analyzer),
):
    try:
        report = await audience_analyzer.analyze(
            source=payload.source,
            message_limit=payload.message_limit,
        )
        status = get_gigachat_status()
        return TelegramAudienceReportResponse(
            input=AudienceAnalyzeInputResponse(
                source=payload.source,
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
                interest_clusters=report.interest_clusters,
                dominant_theme=report.dominant_theme,
            ),
            audience_persona=report.audience_persona,
            engagement_metrics={
                "average_views": report.engagement_metrics.average_views,
                "average_forwards": report.engagement_metrics.average_forwards,
                "average_reactions": report.engagement_metrics.average_reactions,
                "posts_per_day": report.engagement_metrics.posts_per_day,
            },
            summary=report.summary,
            limitations=report.limitations,
        )
    except AuthorizationRequiredError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AIEnhancementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except TelegramOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Audience analysis failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/audience/analyze/dashboard",
    summary="PNG-дашборд по анализу аудитории",
    description="Строит PNG-дашборд по темам, интересам и метрикам постов Telegram-источника.",
)
async def analyze_audience_dashboard(
    payload: AudienceAnalyzeRequest,
    audience_analyzer: AudienceAnalyzerPort = Depends(get_audience_analyzer),
):
    if not dashboards_available():
        raise HTTPException(status_code=503, detail="matplotlib is not installed")

    try:
        report = await audience_analyzer.analyze(
            source=payload.source,
            message_limit=payload.message_limit,
        )
        image_bytes = build_audience_dashboard(report)
        return StreamingResponse(
            io.BytesIO(image_bytes),
            media_type="image/png",
            headers={"Content-Disposition": 'inline; filename="audience-dashboard.png"'},
        )
    except AuthorizationRequiredError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AIEnhancementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except TelegramOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Audience dashboard build failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/audience/competitors",
    response_model=CompetitorDiscoveryResponse,
    summary="Поиск похожих каналов-конкурентов",
    description="Сравнивает каналы по контенту, темам, формату и вовлечению постов.",
)
async def find_audience_competitors(
    payload: AudienceCompetitorsRequest,
    audience_analyzer: AudienceAnalyzerPort = Depends(get_audience_analyzer),
):
    try:
        result = await audience_analyzer.compare_competitors(
            source=payload.source,
            candidate_sources=payload.candidate_sources,
            message_limit=payload.message_limit,
            top_k=payload.top_k,
        )
        return CompetitorDiscoveryResponse(
            input=AudienceCompetitorsInputResponse(
                source=payload.source,
                candidate_sources=payload.candidate_sources,
                message_limit=payload.message_limit,
                top_k=payload.top_k,
            ),
            source=result.source,
            competitors=[
                CompetitorMatchResponse(
                    source=item.source,
                    match_percent=round(item.similarity_score * 100, 1),
                    competitor_type=item.relation_type,
                    common_topics=item.matched_themes,
                    common_content_signals=item.matched_keywords,
                    why_it_matched=item.reason,
                    limitations=item.disqualifiers,
                )
                for item in result.competitors
            ],
            failed_candidates=[
                CompetitorFailureResponse(source=item.source, error=item.error)
                for item in result.failed_candidates
            ],
        )
    except AuthorizationRequiredError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AIEnhancementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except TelegramOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Competitor discovery failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/audience/competitors/dashboard",
    summary="PNG-дашборд по конкурентам",
    description="Строит PNG-дашборд по результату сравнения Telegram-канала с конкурентами.",
)
async def find_audience_competitors_dashboard(
    payload: AudienceCompetitorsRequest,
    audience_analyzer: AudienceAnalyzerPort = Depends(get_audience_analyzer),
):
    if not dashboards_available():
        raise HTTPException(status_code=503, detail="matplotlib is not installed")

    try:
        result = await audience_analyzer.compare_competitors(
            source=payload.source,
            candidate_sources=payload.candidate_sources,
            message_limit=payload.message_limit,
            top_k=payload.top_k,
        )
        image_bytes = build_competitors_dashboard(result)
        return StreamingResponse(
            io.BytesIO(image_bytes),
            media_type="image/png",
            headers={"Content-Disposition": 'inline; filename="competitors-dashboard.png"'},
        )
    except AuthorizationRequiredError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AIEnhancementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except TelegramOperationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Competitor dashboard build failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/ai/status",
    response_model=GigaChatStatusResponse,
    summary="Статус GigaChat",
    description="Показывает, настроен ли GigaChat и будет ли AI участвовать в анализе.",
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
