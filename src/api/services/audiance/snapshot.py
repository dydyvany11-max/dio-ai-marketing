from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from src.api.services.audiance.content_insights import derive_content_insights
from src.api.services.dto import (
    AudienceAnalysisSnapshot,
    AudienceCluster,
    AudiencePersona,
    AudienceSource,
    ChannelTheme,
    EngagementMetrics,
    TelegramAudienceReport,
)


def build_audience_analysis_snapshot(report: TelegramAudienceReport) -> AudienceAnalysisSnapshot:
    source_key = normalize_source_key(report.source.username or report.source.source)
    analyzed_at = datetime.now(timezone.utc).isoformat()

    report_payload = _prune_none_values({
        "ai_enhanced": report.ai_enhanced,
        "ai_message": report.ai_message,
        "source": asdict(report.source),
        "message_samples": report.message_samples,
        "interest_clusters": [asdict(cluster) for cluster in report.interest_clusters],
        "dominant_theme": asdict(report.dominant_theme),
        "channel_themes": [asdict(theme) for theme in report.channel_themes],
        "audience_persona": asdict(report.audience_persona),
        "engagement_metrics": asdict(report.engagement_metrics),
        "summary": report.summary,
        "limitations": report.limitations,
    })

    return AudienceAnalysisSnapshot(
        source_key=source_key,
        source_title=report.source.title,
        source_username=report.source.username,
        entity_id=report.source.entity_id,
        entity_type=report.source.entity_type,
        analyzed_at=analyzed_at,
        dominant_theme_key=report.dominant_theme.key,
        dominant_theme_label=report.dominant_theme.label,
        summary=report.summary,
        report_payload=report_payload,
    )


def restore_audience_report(snapshot: AudienceAnalysisSnapshot) -> TelegramAudienceReport:
    payload = snapshot.report_payload
    source_payload = payload.get("source", {})
    dominant_theme_payload = payload.get("dominant_theme", {})
    engagement_payload = payload.get("engagement_metrics", {})
    dominant_theme = ChannelTheme(
        key=dominant_theme_payload.get("key", ""),
        label=dominant_theme_payload.get("label", ""),
        share=dominant_theme_payload.get("share", 0.0),
        evidence=dominant_theme_payload.get("evidence", []),
    )
    engagement_metrics = EngagementMetrics(
        average_views=engagement_payload.get("average_views", 0),
        median_views=engagement_payload.get("median_views", 0),
        average_forwards=engagement_payload.get("average_forwards", 0),
        average_replies=engagement_payload.get("average_replies", 0),
        average_reactions=engagement_payload.get("average_reactions", 0),
        view_rate=engagement_payload.get("view_rate", 0.0),
        deep_engagement_rate=engagement_payload.get("deep_engagement_rate", 0.0),
        posts_per_day=engagement_payload.get("posts_per_day", 0.0),
    )

    return TelegramAudienceReport(
        ai_enhanced=payload.get("ai_enhanced", False),
        ai_message=payload.get("ai_message"),
        source=AudienceSource(
            source=source_payload.get("source", snapshot.source_key),
            title=source_payload.get("title", snapshot.source_title),
            entity_id=source_payload.get("entity_id", snapshot.entity_id),
            entity_type=source_payload.get("entity_type", snapshot.entity_type),
            username=source_payload.get("username", snapshot.source_username),
            participants_estimate=source_payload.get("participants_estimate"),
            message_sample_size=source_payload.get("message_sample_size", 0),
        ),
        message_samples=payload.get("message_samples", []),
        interest_clusters=[
            AudienceCluster(
                key=item.get("key", ""),
                label=item.get("label", ""),
                count=item.get("count", 0),
                share=item.get("share", 0.0),
                confidence=item.get("confidence", ""),
                notes=item.get("notes", []),
            )
            for item in payload.get("interest_clusters", [])
        ],
        dominant_theme=dominant_theme,
        channel_themes=[
            ChannelTheme(
                key=item.get("key", ""),
                label=item.get("label", ""),
                share=item.get("share", 0.0),
                evidence=item.get("evidence", []),
            )
            for item in payload.get("channel_themes", [])
        ],
        audience_persona=AudiencePersona(
            title=payload.get("audience_persona", {}).get("title", ""),
            description=payload.get("audience_persona", {}).get("description", ""),
            age_range=payload.get("audience_persona", {}).get("age_range", ""),
            persona_summary=payload.get("audience_persona", {}).get("persona_summary", ""),
            motivations=payload.get("audience_persona", {}).get("motivations", []),
            content_preferences=payload.get("audience_persona", {}).get("content_preferences", []),
            activity_pattern=payload.get("audience_persona", {}).get("activity_pattern", ""),
        ),
        engagement_metrics=engagement_metrics,
        content_insights=derive_content_insights(dominant_theme, engagement_metrics),
        summary=payload.get("summary", snapshot.summary),
        limitations=payload.get("limitations", []),
    )


def normalize_source_key(source: str) -> str:
    value = (source or "").strip()
    if value.startswith("@"):
        return value[1:]
    if value.startswith("https://t.me/") or value.startswith("http://t.me/"):
        tail = value.split("t.me/", 1)[1].strip("/")
        if tail.startswith("s/"):
            tail = tail[2:]
        return tail.split("/", 1)[0]
    return value


def _prune_none_values(value):
    if isinstance(value, dict):
        cleaned = {
            key: _prune_none_values(item)
            for key, item in value.items()
            if item is not None
        }
        return cleaned
    if isinstance(value, list):
        return [_prune_none_values(item) for item in value if item is not None]
    return value
