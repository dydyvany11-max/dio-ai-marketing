from pydantic import BaseModel, ConfigDict, Field


class QRStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    authorized: bool = Field(description="Авторизована ли текущая Telegram-сессия")
    pending: bool = Field(description="Ожидается ли подтверждение входа через QR")
    expires_at: str | None = Field(default=None, description="Время истечения QR-кода в ISO-формате")
    error: str | None = Field(default=None, description="Текст ошибки авторизации, если она возникла")


class PasswordRequest(BaseModel):
    password: str = Field(description="Пароль двухфакторной авторизации Telegram")


class AudienceAnalyzeRequest(BaseModel):
    source: str = Field(
        description="Ссылка на канал/группу, @username или ID Telegram-источника",
        examples=["https://t.me/Cbpub", "@Cbpub", "1135818819"],
    )
    message_limit: int = Field(
        default=100,
        ge=1,
        le=500,
        description="Сколько последних сообщений анализировать для метрик и AI-портрета",
    )


class AudienceCompetitorsRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "source": "https://t.me/Cbpub",
                "candidate_sources": [
                    "https://t.me/mediyca",
                    "https://t.me/raiznews",
                    "https://t.me/paritet_development",
                ],
                "message_limit": 100,
                "top_k": 5,
            }
        }
    )

    source: str = Field(
        description="Ссылка на канал/группу, @username или ID Telegram-источника",
        examples=["https://t.me/Cbpub", "@Cbpub", "1135818819"],
    )
    candidate_sources: list[str] = Field(
        min_length=1,
        max_length=30,
        description="Список каналов-кандидатов для сравнения с основным источником",
    )
    message_limit: int = Field(
        default=100,
        ge=1,
        le=500,
        description="Сколько последних сообщений анализировать у каждого канала",
    )
    top_k: int = Field(default=5, ge=1, le=20, description="Сколько лучших совпадений вернуть")


class GigaChatStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    enabled: bool
    available: bool
    enhanced: bool
    provider: str
    model: str | None = None
    auth_mode: str | None = None
    message: str


class AudienceAnalyzeInputResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    message_limit: int


class AudienceCompetitorsInputResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    candidate_sources: list[str]
    message_limit: int
    top_k: int


class AudienceClusterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    label: str
    count: int
    share: float
    confidence: str


class ChannelThemeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    share: float
    evidence: list[str]


class AudiencePersonaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    description: str
    motivations: list[str]
    content_preferences: list[str]
    activity_pattern: str


class EngagementMetricsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    average_views: int
    average_forwards: int
    average_reactions: int
    posts_per_day: float


class ContentInsightsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    channel_format: str
    strongest_content_hook: str
    posting_recommendations: list[str]
    best_for_growth: list[str]


class AudienceSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    title: str
    entity_id: int
    entity_type: str
    username: str | None = None
    participants_estimate: int | None = None
    message_sample_size: int


class AudienceClusteringResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    interest_clusters: list[AudienceClusterResponse]
    dominant_theme: ChannelThemeResponse


class TelegramAudienceReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    input: AudienceAnalyzeInputResponse
    ai: GigaChatStatusResponse
    source: AudienceSourceResponse
    clustering: AudienceClusteringResponse
    audience_persona: AudiencePersonaResponse
    engagement_metrics: EngagementMetricsResponse
    content_insights: ContentInsightsResponse
    summary: str
    limitations: list[str]


class CompetitorMatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: AudienceSourceResponse
    match_percent: float
    competitor_type: str
    common_topics: list[str]
    common_content_signals: list[str]
    why_it_matched: str
    limitations: list[str]


class CompetitorFailureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    error: str


class CompetitorDiscoveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    input: AudienceCompetitorsInputResponse
    source: AudienceSourceResponse
    competitors: list[CompetitorMatchResponse]
    failed_candidates: list[CompetitorFailureResponse]
