from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from src.api.services.dto import AudienceAnalysisSnapshot, TelegramAudienceReport


def build_audience_analysis_snapshot(report: TelegramAudienceReport) -> AudienceAnalysisSnapshot:
    source_key = report.source.username or report.source.source
    analyzed_at = datetime.now(timezone.utc).isoformat()

    generation_payload = {
        "source": {
            "title": report.source.title,
            "source": report.source.source,
            "entity_type": report.source.entity_type,
            "username": report.source.username,
        },
        "dominant_theme": asdict(report.dominant_theme),
        "channel_themes": [asdict(theme) for theme in report.channel_themes[:5]],
        "interest_clusters": [asdict(cluster) for cluster in report.interest_clusters[:5]],
        "audience_persona": asdict(report.audience_persona),
        "engagement_metrics": asdict(report.engagement_metrics),
        "summary": report.summary,
        "limitations": report.limitations,
    }

    report_payload = {
        "ai_enhanced": report.ai_enhanced,
        "ai_message": report.ai_message,
        "source": asdict(report.source),
        "message_samples": report.message_samples,
        "interest_clusters": [asdict(cluster) for cluster in report.interest_clusters],
        "dominant_theme": asdict(report.dominant_theme),
        "channel_themes": [asdict(theme) for theme in report.channel_themes],
        "audience_persona": asdict(report.audience_persona),
        "engagement_metrics": asdict(report.engagement_metrics),
        "content_insights": asdict(report.content_insights),
        "summary": report.summary,
        "limitations": report.limitations,
    }

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
        generation_payload=generation_payload,
    )
