from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AuthStatus:
    authorized: bool
    pending: bool
    expires_at: str | None
    error: str | None


@dataclass(frozen=True)
class QRCodePayload:
    image_bytes: bytes
    login_url: str
    expires_at: str | None


@dataclass(frozen=True)
class AuthorizedUser:
    user_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    phone: str | None


@dataclass(frozen=True)
class AudienceCluster:
    key: str
    label: str
    count: int
    share: float
    confidence: str
    notes: list[str]


@dataclass(frozen=True)
class AudienceSource:
    source: str
    title: str
    entity_id: int
    entity_type: str
    username: str | None
    participants_estimate: int | None
    message_sample_size: int


@dataclass(frozen=True)
class AudiencePersona:
    title: str
    description: str
    age_range: str
    persona_summary: str
    motivations: list[str]
    content_preferences: list[str]
    activity_pattern: str


@dataclass(frozen=True)
class ChannelTheme:
    key: str
    label: str
    share: float
    evidence: list[str]


@dataclass(frozen=True)
class EngagementMetrics:
    average_views: int
    median_views: int
    average_forwards: int
    average_replies: int
    average_reactions: int
    view_rate: float
    deep_engagement_rate: float
    posts_per_day: float


@dataclass(frozen=True)
class ContentInsights:
    channel_format: str
    strongest_content_hook: str
    posting_recommendations: list[str]
    best_for_growth: list[str]


@dataclass(frozen=True)
class TelegramAudienceReport:
    ai_enhanced: bool
    ai_message: str | None
    source: AudienceSource
    message_samples: list[str]
    interest_clusters: list[AudienceCluster]
    dominant_theme: ChannelTheme
    channel_themes: list[ChannelTheme]
    audience_persona: AudiencePersona
    engagement_metrics: EngagementMetrics
    content_insights: ContentInsights
    summary: str
    limitations: list[str]


@dataclass(frozen=True)
class CompetitorMatch:
    source: AudienceSource
    similarity_score: float
    relation_type: str
    audience_similarity: float
    engagement_similarity: float
    format_similarity: float
    shared_theme_count: int
    shared_specific_theme_count: int
    dominant_specific_theme: str | None
    candidate_dominant_specific_theme: str | None
    matched_themes: list[str]
    matched_keywords: list[str]
    disqualifiers: list[str]
    reason: str


@dataclass(frozen=True)
class CompetitorFailure:
    source: str
    error: str


@dataclass(frozen=True)
class CompetitorDiscoveryReport:
    source: AudienceSource
    discovered_candidates: list[str]
    competitors: list[CompetitorMatch]
    failed_candidates: list[CompetitorFailure]


@dataclass(frozen=True)
class GigaChatStatus:
    enabled: bool
    available: bool
    provider: str
    model: str | None
    auth_mode: str | None
    message: str


@dataclass(frozen=True)
class AudienceAnalysisSnapshot:
    source_key: str
    source_title: str
    source_username: str | None
    entity_id: int
    entity_type: str
    analyzed_at: str
    dominant_theme_key: str
    dominant_theme_label: str
    summary: str
    report_payload: dict[str, Any]
