from src.api.services.audience_constants import (
    CONFIDENCE_LABELS,
    ENTITY_TYPE_LABELS,
    KEY_TRANSLATIONS,
)
from src.api.services.dto import AudienceCluster, AudienceSource, ChannelTheme


def translate_key(key: str) -> str:
    return KEY_TRANSLATIONS.get(key, key)


def translate_cluster(cluster: AudienceCluster) -> AudienceCluster:
    return AudienceCluster(
        key=translate_key(cluster.key),
        label=cluster.label,
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
        message_sample_size=source.message_sample_size,
    )


def translate_theme(theme: ChannelTheme) -> ChannelTheme:
    return ChannelTheme(
        key=theme.key,
        label=theme.label,
        share=theme.share,
        evidence=theme.evidence,
    )


def build_summary(source_info: AudienceSource, interest_clusters: list[AudienceCluster]) -> str:
    top_interest_cluster = max(interest_clusters, key=lambda cluster: cluster.share) if interest_clusters else None
    top_interest = top_interest_cluster.label if top_interest_cluster else "нет данных"
    return f"{source_info.title}: основной контентный сигнал канала связан с интересом '{top_interest}'."
