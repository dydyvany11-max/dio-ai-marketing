from pydantic import BaseModel, ConfigDict, Field





class QRStatusResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)



    authorized: bool = Field(description="Авторизована ли текущая Telegram-сессия")

    pending: bool = Field(description="Ожидается ли подтверждение входа через QR")

    expires_at: str | None = Field(

        default=None,

        description="Время истечения QR-кода в ISO-формате, если QR-вход активен",

    )

    error: str | None = Field(

        default=None,

        description="Текст ошибки авторизации, если она возникла",

    )





class PasswordRequest(BaseModel):

    password: str = Field(description="Пароль двухфакторной авторизации Telegram")





class AudienceAnalyzeRequest(BaseModel):

    source: str = Field(

        description="Ссылка на канал/группу, @username или ID Telegram-источника",

        examples=["https://t.me/Cbpub", "@Cbpub", "1135818819"],

    )

    participant_limit: int = Field(

        default=200,

        ge=1,

        le=1000,

        description="Сколько участников пытаться собрать для внутренней выборки, если Telegram позволяет",

    )

    message_limit: int = Field(

        default=100,

        ge=1,

        le=500,

        description="Сколько последних сообщений анализировать для метрик",

    )





class GigaChatStatusResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)



    enabled: bool = Field(description="Включен ли AI-слой по конфигурации .env")

    available: bool = Field(description="Удалось ли приложению подготовить GigaChat-клиент")

    enhanced: bool = Field(description="Участвовал ли AI в формировании именно этого ответа")

    provider: str = Field(description="Имя AI-провайдера")

    model: str | None = Field(default=None, description="Модель GigaChat, если она настроена")

    auth_mode: str | None = Field(

        default=None,

        description="Способ авторизации: authorization_key или credentials",

    )

    message: str = Field(description="Пояснение по текущему состоянию GigaChat")





class AudienceAnalyzeInputResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)



    source: str = Field(description="Что было передано в source")

    participant_limit: int = Field(description="Какой лимит участников был запрошен")

    message_limit: int = Field(description="Какой лимит сообщений был запрошен")





class AudienceClusterResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)



    label: str = Field(description="Название кластера")

    count: int = Field(description="Оценочное количество людей в кластере")

    share: float = Field(description="Доля кластера от всей аудитории, от 0 до 1")

    confidence: str = Field(description="Уровень уверенности модели")





class ChannelThemeResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)



    key: str = Field(description="Системный ключ тематики")

    label: str = Field(description="Название тематики канала")

    share: float = Field(description="Доля тематики в контентном сигнале канала, от 0 до 1")

    evidence: list[str] = Field(description="Слова и сигналы, на которых основан вывод")





class AudiencePersonaResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)



    title: str = Field(description="Короткое название основного портрета аудитории")

    description: str = Field(description="Текстовое описание ядра аудитории")

    motivations: list[str] = Field(description="Что мотивирует аудиторию читать канал")

    content_preferences: list[str] = Field(description="Какой контент аудитория предпочитает")

    activity_pattern: str = Field(description="Когда и как аудитория обычно активна")





class EngagementMetricsResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)



    average_views: int = Field(description="Среднее число просмотров на пост")

    median_views: int = Field(description="Медианное число просмотров на пост")

    average_forwards: int = Field(description="Среднее число пересылок на пост")

    average_replies: int = Field(description="Среднее число ответов на пост")

    average_reactions: int = Field(description="Среднее число реакций на пост")

    view_rate: float = Field(description="Средняя доля просмотров относительно размера аудитории")

    deep_engagement_rate: float = Field(

        description="Глубокая вовлеченность: пересылки, ответы и реакции относительно просмотров"

    )

    posts_per_day: float = Field(description="Средняя частота публикаций в постах за день")





class ContentInsightsResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)



    channel_format: str = Field(description="Какой формат канала сейчас доминирует")

    strongest_content_hook: str = Field(description="Что сильнее всего цепляет аудиторию")

    posting_recommendations: list[str] = Field(description="Что AI советует публиковать чаще")

    best_for_growth: list[str] = Field(description="Что AI считает лучшим для роста канала")





class AudienceSourceResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)



    source: str = Field(description="Исходное значение source из запроса")

    title: str = Field(description="Название канала, группы или чата")

    entity_id: int = Field(description="Внутренний Telegram ID источника")

    entity_type: str = Field(description="Тип источника: канал, супергруппа или группа")

    username: str | None = Field(

        default=None,

        description="Публичный username источника, если он есть",

    )

    participants_estimate: int | None = Field(

        default=None,

        description="Оценка общего размера аудитории источника",

    )





class AudienceClusteringResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)



    activity_clusters: list[AudienceClusterResponse] = Field(

        description="Кластеры аудитории по активности"

    )

    age_clusters: list[AudienceClusterResponse] = Field(

        description="Кластеры аудитории по возрастным группам"

    )

    interest_clusters: list[AudienceClusterResponse] = Field(

        description="Кластеры аудитории по тематическим интересам"

    )

    audience_segments: list[AudienceClusterResponse] = Field(

        description="Итоговые сегменты аудитории"

    )

    top_active_segment: AudienceClusterResponse = Field(

        description="Самый активный сегмент аудитории"

    )

    dominant_theme: ChannelThemeResponse = Field(

        description="Главная тематика канала по контентным сигналам"

    )

    channel_themes: list[ChannelThemeResponse] = Field(

        description="Список ключевых тематик канала"

    )





class TelegramAudienceReportResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)



    input: AudienceAnalyzeInputResponse = Field(

        description="Входные параметры, с которыми был запущен анализ"

    )

    ai: GigaChatStatusResponse = Field(

        description="Состояние AI-слоя и факт его участия в этом анализе"

    )

    source: AudienceSourceResponse = Field(

        description="Информация об анализируемом Telegram-источнике"

    )

    clustering: AudienceClusteringResponse = Field(

        description="Блок кластеризации аудитории, сегментов и тематики"

    )

    audience_persona: AudiencePersonaResponse = Field(

        description="Портрет основного пользователя канала"

    )

    engagement_metrics: EngagementMetricsResponse = Field(

        description="Ключевые метрики просмотров, пересылок и ритма публикаций"

    )

    content_insights: ContentInsightsResponse = Field(

        description="Выводы и рекомендации, построенные AI"

    )

    summary: str = Field(description="Краткая итоговая сводка")

    limitations: list[str] = Field(description="Ограничения и допущения анализа")



class VKIDAuthResponse(BaseModel):

    access_token: str = Field(description="VK ID access_token")

    expires_in: int | None = Field(default=None, description="Token lifetime, seconds")

    id_token: str | None = Field(default=None, description="OpenID id_token")

    refresh_token: str | None = Field(default=None, description="Refresh token")

    state: str | None = Field(default=None, description="State echoed by VK ID")

    token_type: str | None = Field(default=None, description="Token type")

    user_id: int | None = Field(default=None, description="VK ID user_id")

    scope: str | None = Field(default=None, description="Granted scopes")

    user: dict | None = Field(default=None, description="VK ID user info payload")


class VKAudienceAnalyzeRequest(BaseModel):

    source: str = Field(

        description="Group link, screen_name or ID",

        examples=["https://vk.com/club1", "club1", "123456"],

    )

    access_token: str | None = Field(
        default=None,
        description="VK access_token with groups, wall, stats (optional, server uses saved token)",
    )

    post_limit: int = Field(default=50, ge=1, le=100, description="How many posts to analyze")



class VKGroupInfoResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)



    group_id: int = Field(description="ID группы")

    name: str = Field(description="Название группы")

    screen_name: str | None = Field(default=None, description="screen_name")

    members_count: int | None = Field(default=None, description="Количество участников (если доступно)")





class VKPostMetricsResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)



    post_id: int = Field(description="ID поста")

    date: int = Field(description="Unix timestamp публикации")

    views: int = Field(description="Просмотры")

    likes: int = Field(description="Лайки")

    comments: int = Field(description="Комментарии")

    reposts: int = Field(description="Репосты")





class VKAudienceReportResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)



    group: VKGroupInfoResponse

    average_views: int

    average_likes: int

    average_comments: int

    average_reposts: int

    posts_per_day: float

    total_posts_analyzed: int

    top_posts: list[VKPostMetricsResponse]

    limitations: list[str]





class VKPublishRequest(BaseModel):

    message: str = Field(default="", description="?????????? ??????????")


class VKPublishResponse(BaseModel):

    post_id: int = Field(description="ID созданного поста")

    owner_id: int = Field(description="Owner ID (группа = отрицательный)")



class VKKnowledgeBaseUploadRequest(BaseModel):

    name: str = Field(description="Knowledge base title")

    content: str = Field(description="Knowledge base content (rules, templates, ideas)")

    language: str = Field(default="ru", description="Knowledge base language")


class VKKnowledgeBaseItemResponse(BaseModel):

    id: str = Field(description="Knowledge base id")

    name: str = Field(description="Knowledge base title")

    language: str = Field(description="Knowledge base language")

    content_length: int = Field(description="Stored content length")

    created_at: str | None = Field(default=None, description="Created at (ISO)")

    updated_at: str | None = Field(default=None, description="Updated at (ISO)")

    is_active: bool = Field(default=False, description="Is active knowledge base")


class VKKnowledgeBaseUploadResponse(BaseModel):

    item: VKKnowledgeBaseItemResponse


class VKKnowledgeBaseListResponse(BaseModel):

    items: list[VKKnowledgeBaseItemResponse]


class VKAIPostRequest(BaseModel):

    prompt: str = Field(description="Prompt for post generation")

    theme: str | None = Field(default=None, description="Post theme/topic")

    tone: str | None = Field(default=None, description="Tone of voice")

    content_type: str = Field(
        default="text",
        description="Content type: text, story, image, video",
    )

    publish: bool = Field(default=False, description="Publish immediately if true")

    length: str = Field(
        default="medium",
        description="Desired length: short, medium, long",
    )

    language: str = Field(default="ru", description="Output language")


class VKAIPostResponse(BaseModel):

    text: str = Field(description="Generated post text")

    content_type: str = Field(description="Generated content type")

    published: bool = Field(description="Was post published")

    post_id: int | None = Field(default=None, description="VK post ID if published")

    owner_id: int | None = Field(default=None, description="VK owner ID if published")

    char_count: int = Field(description="Characters count")

    word_count: int = Field(description="Words count")

    token_estimate: int = Field(description="Rough token estimate (~4 chars per token)")

    token_estimate_method: str = Field(description="Token estimation method")

    theme: str | None = Field(default=None, description="Applied theme")

    tone: str | None = Field(default=None, description="Applied tone")

    story_frames: list[str] = Field(default_factory=list, description="Story slides/frames if content_type=story")

    image_prompt: str | None = Field(default=None, description="Image generation prompt if content_type=image")

    video_script: str | None = Field(default=None, description="Video script if content_type=video")

    knowledge_base_id: str | None = Field(default=None, description="Used knowledge base id")

    knowledge_base_name: str | None = Field(default=None, description="Used knowledge base title")


class VKGroupAnalyzeRequest(BaseModel):

    source: str = Field(description="Group link, screen_name or ID")

    post_limit: int = Field(default=50, ge=1, le=100, description="How many posts to analyze")

    language: str = Field(default="ru", description="Output language")


class VKGroupAIInsights(BaseModel):

    audience_interests: list[str] = Field(description="Interest clusters")

    audience_age: list[str] = Field(description="Age clusters")

    audience_activity: list[str] = Field(description="Activity clusters")

    potential_competitors: list[str] = Field(description="Likely competitors")

    summary: str = Field(description="Short summary")

    limitations: list[str] = Field(description="Limitations and assumptions")


class VKTopicClusterResponse(BaseModel):

    label: str = Field(description="Human-readable cluster label")

    size: int = Field(description="How many posts belong to the cluster")

    terms: list[str] = Field(description="Top cluster terms")

    sample_titles: list[str] = Field(description="Example post titles")

    sample_urls: list[str] = Field(description="Example source URLs")


class VKCompetitorFoundResponse(BaseModel):

    group_id: int = Field(description="VK group ID")

    name: str = Field(description="VK group name")

    screen_name: str | None = Field(default=None, description="VK screen name")

    members_count: int | None = Field(default=None, description="Members count if available")

    activity: str | None = Field(default=None, description="Group activity/category")

    matched_by: list[str] = Field(description="Cluster terms that matched this competitor")

    shared_topics: list[str] = Field(description="Shared topic labels with the analyzed group")

    why_similar: str = Field(description="Why this group is considered similar")

    similarity_score: float = Field(description="Heuristic similarity score from 0 to 1")


class VKAnalyticsSourceResponse(BaseModel):

    platform: str = Field(description="Platform identifier")

    group_id: int = Field(description="VK group ID")

    name: str = Field(description="VK group name")

    screen_name: str | None = Field(default=None, description="VK screen name")

    url: str = Field(description="Canonical public URL")

    members_count: int | None = Field(default=None, description="Members count if available")

    activity: str | None = Field(default=None, description="VK category/activity")

    description: str | None = Field(default=None, description="VK group description")

    site: str | None = Field(default=None, description="Linked site from VK if present")


class VKAudienceProfileResponse(BaseModel):

    interests: list[str] = Field(description="Interest profile")

    age_segments: list[str] = Field(description="Estimated age segments")

    activity_profile: list[str] = Field(description="Posting and engagement behavior")

    content_preferences: list[str] = Field(description="Preferred content formats and themes")

    engagement_style: list[str] = Field(description="How the audience tends to react to content")

    summary: str = Field(description="Audience profile summary")


class VKAnalyticsRecommendationResponse(BaseModel):

    title: str = Field(description="Short recommendation title")

    action: str = Field(description="Recommended action")

    rationale: str = Field(description="Why this recommendation follows from the analytics")


class VKGroupMetricsResponse(BaseModel):

    average_views: int

    average_likes: int

    average_comments: int

    average_reposts: int

    posts_per_day: float

    total_posts_analyzed: int

    top_posts: list[VKPostMetricsResponse]

    limitations: list[str]


class VKGroupAnalyzeResponse(BaseModel):

    source: VKAnalyticsSourceResponse

    group: VKGroupInfoResponse

    metrics: VKGroupMetricsResponse

    ai: VKGroupAIInsights

    audience_profile: VKAudienceProfileResponse

    topic_clusters: list[VKTopicClusterResponse]

    competitors_found: list[VKCompetitorFoundResponse]

    recommendations: list[VKAnalyticsRecommendationResponse]

    ai_status: GigaChatStatusResponse


class TrendItem(BaseModel):

    term: str = Field(description="Trend term")

    window_start: str = Field(description="Window start ISO")

    window_end: str = Field(description="Window end ISO")

    count_now: int = Field(description="Count in current window")

    count_prev: int = Field(description="Count in previous window")

    growth: float = Field(description="Growth ratio")

    score: float = Field(description="Trend score")

    updated_at: str = Field(description="Last update ISO")


class TrendListResponse(BaseModel):

    items: list[TrendItem]


class TrendRefreshResponse(BaseModel):

    inserted: int = Field(description="New articles inserted")

    trends: list[TrendItem]


class TrendSourceCreateRequest(BaseModel):

    name: str

    url: str

    type: str = Field(description="Source type: html")

    enabled: bool = True

    meta_json: str | None = None


class TrendSourceUpdateRequest(BaseModel):

    enabled: bool = True


class TrendSourceListResponse(BaseModel):

    items: list[dict]


class TrendArticleItem(BaseModel):

    id: int
    source: str
    url: str
    title: str | None = None
    content: str | None = None
    published_at: str | None = None
    fetched_at: str


class TrendArticleListResponse(BaseModel):

    items: list[TrendArticleItem]


class TrendTopicItem(BaseModel):

    size: int
    terms: list[str]
    sample_titles: list[str]
    sample_urls: list[str]
    top_sources: list[str]


class TrendTopicListResponse(BaseModel):

    items: list[TrendTopicItem]
