import io
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from src.api.dependencies import get_audience_analyzer, get_gigachat_status
from src.api.http_errors import raise_audience_http_error
from src.api.response_builders import (
    build_audience_report_response,
    build_competitor_discovery_response,
    build_gigachat_status_response,
)
from src.api.schemas import AudienceAnalyzeRequest, AudienceCompetitorsRequest, CompetitorDiscoveryResponse, GigaChatStatusResponse, TelegramAudienceReportResponse
from src.api.services.audiance.dashboards import (
    build_audience_dashboard,
    build_competitors_dashboard,
    dashboards_available,
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
        return build_audience_report_response(payload, report, status)
    except Exception as exc:
        raise_audience_http_error(
            exc,
            logger=logger,
            unexpected_log_message="Audience analysis failed",
        )


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
    except Exception as exc:
        raise_audience_http_error(
            exc,
            logger=logger,
            unexpected_log_message="Audience dashboard build failed",
        )


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
        )
        return build_competitor_discovery_response(payload, result)
    except Exception as exc:
        raise_audience_http_error(
            exc,
            logger=logger,
            unexpected_log_message="Competitor discovery failed",
        )


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
        )
        image_bytes = build_competitors_dashboard(result)
        return StreamingResponse(
            io.BytesIO(image_bytes),
            media_type="image/png",
            headers={"Content-Disposition": 'inline; filename="competitors-dashboard.png"'},
        )
    except Exception as exc:
        raise_audience_http_error(
            exc,
            logger=logger,
            unexpected_log_message="Competitor dashboard build failed",
        )


@router.get(
    "/ai/status",
    response_model=GigaChatStatusResponse,
    summary="Статус GigaChat",
    description="Показывает, настроен ли GigaChat и будет ли AI участвовать в анализе.",
)
async def tg_ai_status():
    status = get_gigachat_status()
    return build_gigachat_status_response(status, enhanced=False)
