from __future__ import annotations

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
    QRStatusResponse,
    TelegramAudienceReportResponse,
)
from src.api.services.dto import (
    AuthStatus,
    AuthorizedUser,
    CompetitorDiscoveryReport,
    GigaChatStatus,
    TelegramAudienceReport,
)


def build_qr_status_response(status: AuthStatus) -> QRStatusResponse:
    return QRStatusResponse(
        authorized=status.authorized,
        pending=status.pending,
        expires_at=status.expires_at,
        error=status.error,
    )


def build_auth_success_response(user: AuthorizedUser) -> dict[str, object]:
    return {
        "status": "authorized",
        "user": {
            "id": user.user_id,
            "username": user.username,
            "name": user.first_name,
        },
    }


def build_current_user_response(user: AuthorizedUser) -> dict[str, object]:
    return {
        "id": user.user_id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone,
    }


def build_gigachat_status_response(
    status: GigaChatStatus,
    *,
    enhanced: bool,
    message_override: str | None = None,
) -> GigaChatStatusResponse:
    return GigaChatStatusResponse(
        enabled=status.enabled,
        available=status.available,
        enhanced=enhanced,
        provider=status.provider,
        model=status.model,
        auth_mode=status.auth_mode,
        message=message_override or status.message,
    )


def build_audience_report_response(
    payload: AudienceAnalyzeRequest,
    report: TelegramAudienceReport,
    status: GigaChatStatus,
) -> TelegramAudienceReportResponse:
    return TelegramAudienceReportResponse(
        input=AudienceAnalyzeInputResponse(
            source=payload.source,
            message_limit=payload.message_limit,
        ),
        ai=build_gigachat_status_response(
            status,
            enhanced=report.ai_enhanced,
            message_override=report.ai_message,
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


def build_competitor_discovery_response(
    payload: AudienceCompetitorsRequest,
    result: CompetitorDiscoveryReport,
) -> CompetitorDiscoveryResponse:
    return CompetitorDiscoveryResponse(
        input=AudienceCompetitorsInputResponse(source=payload.source),
        source=result.source,
        discovered_candidates=result.discovered_candidates,
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
