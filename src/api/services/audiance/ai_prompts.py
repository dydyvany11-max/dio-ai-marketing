from __future__ import annotations

import json

from src.api.services.audiance.ai_utils import truncate_text
from src.api.services.dto import CompetitorMatch, TelegramAudienceReport

MAX_THEME_EVIDENCE = 1
MAX_CLUSTER_NOTES = 1


def build_audience_prompt(report: TelegramAudienceReport, *, compact: bool) -> str:
    payload = report_to_payload(report, compact=compact)
    return (
        "Сформируй результат анализа Telegram-канала.\n"
        "Верни строго один JSON-объект.\n"
        "Все текстовые значения должны быть на русском языке.\n"
        "Нельзя писать markdown, пояснения и текст до или после JSON.\n"
        "Целевую аудиторию выводи только из постов, тем и метрик постов.\n"
        "Не придумывай характеристики подписчиков, которых нет в данных.\n\n"
        "Структура JSON:\n"
        "{\n"
        '  "dominant_theme": {"key": "string", "label": "string", "share": 0.0, "evidence": ["string"]},\n'
        '  "channel_themes": [{"key": "string", "label": "string", "share": 0.0, "evidence": ["string"]}],\n'
        '  "audience_persona": {\n'
        '    "title": "string",\n'
        '    "description": "string",\n'
        '    "age_range": "string",\n'
        '    "persona_summary": "string",\n'
        '    "motivations": ["string"],\n'
        '    "content_preferences": ["string"],\n'
        '    "activity_pattern": "string"\n'
        "  },\n"
        '  "summary": "string"\n'
        "}\n\n"
        f"Данные анализа:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def build_repair_prompt(bad_content: str, report: TelegramAudienceReport) -> str:
    payload = report_to_payload(report, compact=True)
    return (
        "Верни только валидный JSON-объект по данным анализа.\n"
        "Игнорируй невалидный прошлый ответ и пересобери JSON с нуля.\n"
        "Все текстовые поля должны быть на русском.\n\n"
        "Структура JSON:\n"
        "{\n"
        '  "dominant_theme": {"key": "string", "label": "string", "share": 0.0, "evidence": ["string"]},\n'
        '  "channel_themes": [{"key": "string", "label": "string", "share": 0.0, "evidence": ["string"]}],\n'
        '  "audience_persona": {"title": "string", "description": "string", "age_range": "string", "persona_summary": "string", "motivations": ["string"], "content_preferences": ["string"], "activity_pattern": "string"},\n'
        '  "summary": "string"\n'
        "}\n\n"
        f"Данные анализа:\n{json.dumps(payload, ensure_ascii=False)}\n\n"
        f"Плохой прошлый ответ:\n{truncate_text(bad_content, 800)}"
    )


def build_competitor_explanation_prompt(
    base_report: TelegramAudienceReport,
    candidate_report: TelegramAudienceReport,
    match: CompetitorMatch,
) -> str:
    payload = {
        "base_channel": {
            "title": base_report.source.title,
            "dominant_theme": base_report.dominant_theme.label,
            "top_topics": [theme.label for theme in base_report.channel_themes[:4]],
        },
        "candidate_channel": {
            "title": candidate_report.source.title,
            "dominant_theme": candidate_report.dominant_theme.label,
            "top_topics": [theme.label for theme in candidate_report.channel_themes[:4]],
        },
        "comparison": {
            "competitor_type": match.relation_type,
            "match_percent": round(match.similarity_score * 100, 1),
            "common_topics": match.matched_themes[:4],
            "common_content_signals": match.matched_keywords[:4],
            "limitations": match.disqualifiers[:3],
        },
    }
    return (
        "Объясни, почему один Telegram-канал похож на другой.\n"
        "Напиши короткое объяснение на русском языке в 1-2 предложениях.\n"
        "Без markdown, списков и дисклеймеров.\n\n"
        f"Данные:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def build_keyword_batch_prompt(batch: list[dict[str, object]]) -> str:
    return (
        "Для каждого Telegram-поста выдели 2-5 коротких ключевых фраз.\n"
        "Ключевые фразы должны быть на русском, если исходный пост на русском.\n"
        "Верни строго JSON с полем items.\n\n"
        f"Посты:\n{json.dumps(batch, ensure_ascii=False)}"
    )


def report_to_payload(report: TelegramAudienceReport, *, compact: bool) -> dict[str, object]:
    theme_limit = 2 if compact else 3
    cluster_limit = 2 if compact else 3
    return {
        "source": {
            "title": report.source.title,
            "entity_type": report.source.entity_type,
            "username": report.source.username,
            "participants_estimate": report.source.participants_estimate,
            "message_sample_size": report.source.message_sample_size,
        },
        "interest_clusters": [
            {
                "key": cluster.key,
                "label": cluster.label,
                "share": cluster.share,
                "notes": [
                    truncate_text(note, 120)
                    for note in cluster.notes[:MAX_CLUSTER_NOTES]
                ],
            }
            for cluster in report.interest_clusters[:cluster_limit]
        ],
        "dominant_theme": {
            "key": report.dominant_theme.key,
            "label": report.dominant_theme.label,
            "share": report.dominant_theme.share,
            "evidence": [
                truncate_text(item, 120)
                for item in report.dominant_theme.evidence[:MAX_THEME_EVIDENCE]
            ],
        },
        "channel_themes": [
            {
                "key": theme.key,
                "label": theme.label,
                "share": theme.share,
                "evidence": [
                    truncate_text(item, 120)
                    for item in theme.evidence[:MAX_THEME_EVIDENCE]
                ],
            }
            for theme in report.channel_themes[:theme_limit]
        ],
        "engagement_metrics": {
            "average_views": report.engagement_metrics.average_views,
            "average_forwards": report.engagement_metrics.average_forwards,
            "average_reactions": report.engagement_metrics.average_reactions,
            "posts_per_day": report.engagement_metrics.posts_per_day,
        },
        "audience_persona_seed": {
            "title": report.audience_persona.title,
            "description": report.audience_persona.description,
            "age_range": report.audience_persona.age_range,
            "persona_summary": report.audience_persona.persona_summary,
            "activity_pattern": report.audience_persona.activity_pattern,
        },
        "summary_seed": truncate_text(report.summary, 180),
        "limitations": report.limitations[:1],
    }
