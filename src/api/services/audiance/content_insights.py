from __future__ import annotations

from src.api.services.dto import ChannelTheme, ContentInsights, EngagementMetrics


def derive_content_insights(
    dominant_theme: ChannelTheme,
    engagement_metrics: EngagementMetrics,
) -> ContentInsights:
    if dominant_theme.label == "новости и актуальная повестка":
        channel_format = "Новостной канал"
    elif dominant_theme.label == "мемы и развлекательный контент":
        channel_format = "Развлекательный канал"
    else:
        channel_format = f"Контентный канал с фокусом на тему '{dominant_theme.label}'"

    if engagement_metrics.deep_engagement_rate >= 0.045:
        strongest_content_hook = "Лучше всего заходят посты, которые хочется переслать дальше и обсудить."
    elif engagement_metrics.view_rate >= 0.25:
        strongest_content_hook = "Лучше всего работает быстрый, легко считываемый контент с сильным заголовком."
    else:
        strongest_content_hook = "Лучше всего срабатывают точечные публикации с понятной пользой для аудитории."

    return ContentInsights(
        channel_format=channel_format,
        strongest_content_hook=strongest_content_hook,
        posting_recommendations=[
            "Держать короткие смысловые абзацы и быстро подводить к сути.",
            "Начинать пост с самого сильного факта, тезиса или повода.",
            "Сохранять понятную пользу для аудитории без перегруза общими словами.",
        ],
        best_for_growth=[
            strongest_content_hook,
            f"Формат канала: {channel_format.lower()}",
        ],
    )
