from dataclasses import dataclass


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
    participant_sample_size: int
    message_sample_size: int


@dataclass(frozen=True)
class AudiencePersona:
    title: str
    description: str
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
    activity_clusters: list[AudienceCluster]
    age_clusters: list[AudienceCluster]
    interest_clusters: list[AudienceCluster]
    audience_segments: list[AudienceCluster]
    top_active_segment: AudienceCluster
    dominant_theme: ChannelTheme
    channel_themes: list[ChannelTheme]
    audience_persona: AudiencePersona
    engagement_metrics: EngagementMetrics
    content_insights: ContentInsights
    summary: str
    limitations: list[str]


@dataclass(frozen=True)
class GigaChatStatus:
    enabled: bool
    available: bool
    provider: str
    model: str | None
    auth_mode: str | None
    message: str


@dataclass(frozen=True)
class VKGroupInfo:
    group_id: int
    name: str
    screen_name: str | None
    members_count: int | None


@dataclass(frozen=True)
class VKPostMetrics:
    post_id: int
    date: int
    views: int
    likes: int
    comments: int
    reposts: int


@dataclass(frozen=True)
class VKAudienceReport:
    group: VKGroupInfo
    average_views: int
    average_likes: int
    average_comments: int
    average_reposts: int
    posts_per_day: float
    total_posts_analyzed: int
    top_posts: list[VKPostMetrics]
    limitations: list[str]


@dataclass(frozen=True)
class VKPublishResult:
    post_id: int
    owner_id: int
