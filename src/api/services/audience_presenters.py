from src.api.services.audience_constants import (
    CONFIDENCE_LABELS,
    ENTITY_TYPE_LABELS,
    KEY_TRANSLATIONS,
)
from src.api.services.dto import AudienceCluster, AudienceSource, ChannelTheme


def translate_key(key: str) -> str:
    return KEY_TRANSLATIONS.get(key, key)


def translate_cluster(cluster: AudienceCluster) -> AudienceCluster:
    label_overrides = {
        "core_active": "Основная часть аудитории",
        "warm_audience": "Регулярные читатели",
        "silent_audience": "Редкие читатели",
        "bots": "Сервисные аккаунты",
    }
    return AudienceCluster(
        key=translate_key(cluster.key),
        label=label_overrides.get(cluster.key, cluster.label),
        count=cluster.count,
        share=cluster.share,
        confidence=CONFIDENCE_LABELS.get(cluster.confidence, cluster.confidence),
        notes=cluster.notes,
    )


def translate_source(source: AudienceSource) -> AudienceSource:
    return AudienceSource(
        source=source.source,
        title=source.title,
        entity_id=source.entity_id,
        entity_type=ENTITY_TYPE_LABELS.get(source.entity_type, source.entity_type),
        username=source.username,
        participants_estimate=source.participants_estimate,
        participant_sample_size=source.participant_sample_size,
        message_sample_size=source.message_sample_size,
    )


def translate_theme(theme: ChannelTheme) -> ChannelTheme:
    return ChannelTheme(
        key=theme.key,
        label=theme.label,
        share=theme.share,
        evidence=theme.evidence,
    )


def build_summary(
    source_info: AudienceSource,
    activity_clusters: list[AudienceCluster],
    age_clusters: list[AudienceCluster],
    interest_clusters: list[AudienceCluster],
) -> str:
    top_activity_cluster = max(activity_clusters, key=lambda cluster: cluster.share) if activity_clusters else None
    top_age_cluster = max(age_clusters, key=lambda cluster: cluster.share) if age_clusters else None
    top_interest_cluster = max(interest_clusters, key=lambda cluster: cluster.share) if interest_clusters else None

    top_activity = top_activity_cluster.label if top_activity_cluster else "нет данных"
    top_age = top_age_cluster.label if top_age_cluster else "нет данных"
    top_interest = top_interest_cluster.label if top_interest_cluster else "нет данных"
    if top_activity_cluster and top_activity_cluster.count == 0:
        top_activity = "нет данных"
    if top_age_cluster and top_age_cluster.count == 0:
        top_age = "нет данных"
    if top_interest_cluster and top_interest_cluster.count == 0:
        top_interest = top_interest_cluster.label
    return (
        f"{source_info.title}: основной сигнал по активности '{top_activity}', "
        f"по возрасту '{top_age}', по интересам '{top_interest}'."
    )
