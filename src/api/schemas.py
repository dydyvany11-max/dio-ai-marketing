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

    message: str = Field(default="", description="Текст публикации")


class VKPublishResponse(BaseModel):

    post_id: int = Field(description="ID созданного поста")

    owner_id: int = Field(description="Owner ID (группа = отрицательный)")



class VKKnowledgeBaseUploadRequest(BaseModel):

    name: str = Field(description="Knowledge base title")

    content: str = Field(description="Knowledge base content (rules, templates, ideas)")

    language: str = Field(default="ru", description="Knowledge base language")


class VKKnowledgeUrlUploadRequest(BaseModel):

    url: str = Field(description="Public URL to ingest into knowledge base")

    name: str | None = Field(default=None, description="Knowledge base title (optional)")

    title: str | None = Field(default=None, description="Document title override (optional)")

    language: str = Field(default="ru", description="Knowledge base language")


class VKKnowledgeBaseItemResponse(BaseModel):

    id: str = Field(description="Knowledge base id")

    name: str = Field(description="Knowledge base title")

    language: str = Field(description="Knowledge base language")

    content_length: int = Field(description="Stored content length")

    created_at: str | None = Field(default=None, description="Created at (ISO)")

    updated_at: str | None = Field(default=None, description="Updated at (ISO)")

    is_active: bool = Field(default=False, description="Is active knowledge base")

    files: list["VKKnowledgeFileItemResponse"] = Field(
        default_factory=list,
        description="Uploaded files stored in this knowledge base",
    )


class VKKnowledgeFileItemResponse(BaseModel):

    id: str = Field(description="Knowledge document id")

    filename: str = Field(description="Uploaded filename")

    title: str | None = Field(default=None, description="Document title")

    source_type: str = Field(description="Document source type")

    mime_type: str | None = Field(default=None, description="MIME type")

    content_length: int = Field(description="Document content length")

    created_at: str | None = Field(default=None, description="Created at (ISO)")

    updated_at: str | None = Field(default=None, description="Updated at (ISO)")


class VKKnowledgeBaseUploadResponse(BaseModel):

    item: VKKnowledgeBaseItemResponse


class VKKnowledgeBaseListResponse(BaseModel):

    items: list[VKKnowledgeBaseItemResponse]


class VKKnowledgeDeleteFileResponse(BaseModel):

    deleted: bool = Field(default=True, description="Was file deleted")

    document_id: str = Field(description="Deleted document id")

    knowledge_base_id: str = Field(description="Knowledge base id where file was deleted")

    remaining_documents: int = Field(description="How many documents left in the KB")


class VKAIUsageResponse(BaseModel):
    provider: str = Field(description="AI provider that produced usage stats")
    model: str | None = Field(default=None, description="Model name/uri")
    input_tokens: int = Field(default=0, description="Prompt/input tokens")
    output_tokens: int = Field(default=0, description="Completion/output tokens")
    total_tokens: int = Field(default=0, description="Total tokens")
    estimated_cost: float | None = Field(
        default=None,
        description="Estimated generation cost based on configured per-1k token prices",
    )
    currency: str | None = Field(default=None, description="Currency for estimated_cost")


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
    ai_provider: str | None = Field(
        default="auto",
        description="AI provider: auto, gigachat, yandex",
    )

    use_kb_image_references: bool = Field(
        default=True,
        description="If true and content_type=image, enrich image prompt with relevant image notes from KB",
    )


class VKAIPostResponse(BaseModel):

    text: str = Field(description="Generated post text")

    content_type: str = Field(description="Generated content type")

    published: bool = Field(description="Was post published")

    post_id: int | None = Field(default=None, description="VK post ID if published")

    owner_id: int | None = Field(default=None, description="VK owner ID if published")

    media_attached: bool | None = Field(
        default=None,
        description="Was generated media actually attached to published post (for image/video)",
    )

    publish_note: str | None = Field(
        default=None,
        description="Additional publish details/warnings",
    )

    char_count: int = Field(description="Characters count")

    word_count: int = Field(description="Words count")

    token_estimate: int = Field(description="Rough token estimate (~4 chars per token)")

    token_estimate_method: str = Field(description="Token estimation method")

    theme: str | None = Field(default=None, description="Applied theme")

    tone: str | None = Field(default=None, description="Applied tone")

    story_frames: list[str] = Field(default_factory=list, description="Story slides/frames if content_type=story")

    image_prompt: str | None = Field(default=None, description="Image generation prompt if content_type=image")

    video_script: str | None = Field(default=None, description="Video script if content_type=video")

    generated_image_base64: str | None = Field(
        default=None,
        description="Generated image as base64 string (for preview/download in UI)",
    )

    generated_image_mime_type: str | None = Field(
        default=None,
        description="MIME type of generated image",
    )

    image_reference_files_attached: int = Field(
        default=0,
        description="How many KB image reference files were attached for image generation",
    )

    ai_usage: VKAIUsageResponse | None = Field(
        default=None,
        description="Token usage and estimated cost for the generation request",
    )

    knowledge_base_id: str | None = Field(default=None, description="Used knowledge base id")

    knowledge_base_name: str | None = Field(default=None, description="Used knowledge base title")

    knowledge_chunks_used: int | None = Field(
        default=None,
        description="How many KB chunks were retrieved by RAG",
    )

    knowledge_chunks: list["VKRAGChunkUsedResponse"] = Field(
        default_factory=list,
        description="Which KB chunks were used for generation and why",
    )

    history_id: int | None = Field(default=None, description="Saved content generation history item id")


class VKRegenerateImageRequest(BaseModel):
    post_text: str = Field(description="Generated/edited post text used as visual source")
    image_prompt: str | None = Field(default=None, description="Optional manual image prompt override")
    theme: str | None = Field(default=None, description="Theme hint")
    tone: str | None = Field(default=None, description="Tone hint")
    language: str = Field(default="ru", description="Output language")
    ai_provider: str | None = Field(
        default="auto",
        description="AI provider for image prompt generation: auto, gigachat, yandex",
    )
    use_kb_image_references: bool = Field(
        default=True,
        description="If true, use relevant image notes from active KB as visual references",
    )


class VKRegenerateImageResponse(BaseModel):
    image_prompt: str = Field(description="Final prompt used for image generation")
    generated_image_base64: str = Field(description="Generated image as base64 string")
    generated_image_mime_type: str = Field(description="MIME type of generated image")
    knowledge_chunks_used: int = Field(default=0, description="How many KB chunks were used during image regeneration")
    knowledge_chunks: list["VKRAGChunkUsedResponse"] = Field(
        default_factory=list,
        description="KB chunks used during image regeneration",
    )
    image_reference_files_attached: int = Field(
        default=0,
        description="How many image reference files were attached to the model request",
    )
    ai_usage: VKAIUsageResponse | None = Field(
        default=None,
        description="Token usage and estimated cost for image regeneration",
    )


class VKPostGenerateHistoryItemSummary(BaseModel):
    id: int
    created_at: str
    prompt: str | None = None
    theme: str | None = None
    tone: str | None = None
    content_type: str | None = None
    publish_requested: bool = False
    language: str | None = None
    length: str | None = None
    published: bool = False
    post_id: int | None = None
    owner_id: int | None = None
    char_count: int | None = None
    word_count: int | None = None
    text_preview: str | None = None


class VKPostGenerateHistoryListResponse(BaseModel):
    items: list[VKPostGenerateHistoryItemSummary]


class VKPostGenerateHistoryClearResponse(BaseModel):
    cleared: int = Field(description="How many history rows were removed")


class VKPostGenerateHistoryDeleteItemResponse(BaseModel):
    deleted: bool = Field(default=True, description="Was history item deleted")
    history_id: int = Field(description="Deleted history item id")


class VKPostGenerateHistoryItemResponse(BaseModel):
    id: int
    created_at: str
    prompt: str | None = None
    theme: str | None = None
    tone: str | None = None
    content_type: str | None = None
    publish_requested: bool = False
    language: str | None = None
    length: str | None = None
    published: bool = False
    post_id: int | None = None
    owner_id: int | None = None
    char_count: int | None = None
    word_count: int | None = None
    text_preview: str | None = None
    report: VKAIPostResponse


class VKRAGChunkUsedResponse(BaseModel):
    title: str | None = Field(default=None, description="Document/chunk title")
    filename: str | None = Field(default=None, description="Source filename if available")
    source_type: str | None = Field(default=None, description="Source type: text/file")
    score: float = Field(description="Final retrieval relevance score")
    reason: str | None = Field(default=None, description="Short explanation why this chunk was selected")
    matched_terms: list[str] = Field(default_factory=list, description="Query terms matched in this chunk")
    snippet_preview: str | None = Field(default=None, description="Short chunk preview")


class VKGroupAnalyzeRequest(BaseModel):

    source: str = Field(description="Group link, screen_name or ID")

    post_limit: int = Field(default=50, ge=1, le=100, description="How many posts to analyze")

    language: str = Field(default="ru", description="Output language")
    ai_provider: str | None = Field(
        default="auto",
        description="AI provider: auto, gigachat, yandex",
    )


class VKGroupAIInsights(BaseModel):

    audience_interests: list[str] = Field(description="Interest clusters")

    audience_age: list[str] = Field(description="Age clusters")

    audience_activity: list[str] = Field(description="Activity clusters")

    potential_competitors: list[str] = Field(description="Likely competitors")

    search_tags: list[str] = Field(default_factory=list, description="AI-generated tags for competitor search")

    summary: str = Field(description="Short summary")

    limitations: list[str] = Field(description="Limitations and assumptions")


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

    competitors_found: list[VKCompetitorFoundResponse]

    recommendations: list[VKAnalyticsRecommendationResponse]

    ai_status: GigaChatStatusResponse
    ai_usage: VKAIUsageResponse | None = Field(
        default=None,
        description="Token usage and estimated cost for analysis generation",
    )

    history_id: int | None = Field(default=None, description="Saved analysis history item id")


class VKGroupAnalyzeHistoryItemSummary(BaseModel):
    id: int
    created_at: str
    source_input: str | None = None
    post_limit: int | None = None
    language: str | None = None
    group_id: int | None = None
    group_name: str | None = None
    screen_name: str | None = None
    members_count: int | None = None
    total_posts_analyzed: int | None = None
    average_likes: int | None = None
    average_comments: int | None = None
    ai_summary: str | None = None


class VKGroupAnalyzeHistoryListResponse(BaseModel):
    items: list[VKGroupAnalyzeHistoryItemSummary]


class VKGroupAnalyzeHistoryClearResponse(BaseModel):
    cleared: int = Field(description="How many history rows were removed")


class VKGroupAnalyzeHistoryDeleteItemResponse(BaseModel):
    deleted: bool = Field(default=True, description="Was history item deleted")
    history_id: int = Field(description="Deleted history item id")


class VKRecommendationsChatMessage(BaseModel):
    role: str = Field(description="Message role: user or assistant")
    text: str = Field(description="Message text")
    created_at: str | None = Field(default=None, description="UTC ISO datetime")


class VKGroupAnalyzeHistoryItemResponse(BaseModel):
    id: int
    created_at: str
    source_input: str | None = None
    post_limit: int | None = None
    language: str | None = None
    group_id: int | None = None
    group_name: str | None = None
    screen_name: str | None = None
    members_count: int | None = None
    total_posts_analyzed: int | None = None
    average_likes: int | None = None
    average_comments: int | None = None
    ai_summary: str | None = None
    chat_messages: list[VKRecommendationsChatMessage] = Field(default_factory=list)
    report: VKGroupAnalyzeResponse


class VKRecommendationsChatRequest(BaseModel):
    report: dict = Field(description="VK group analysis report payload")
    message: str = Field(description="User message/question for recommendation assistant")
    language: str = Field(default="ru", description="Response language")
    history_id: int | None = Field(default=None, description="Analysis history id to persist chat")


class VKRecommendationsChatResponse(BaseModel):
    answer: str = Field(description="Detailed recommendation assistant answer")
    chat_messages: list[VKRecommendationsChatMessage] = Field(default_factory=list)


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


class TrendMentionAnalyzeRequest(BaseModel):

    company: str = Field(description="Company/brand name to search mentions for")

    aliases: list[str] = Field(
        default_factory=list,
        description="Optional aliases/variants to include in mention search",
    )

    limit: int = Field(default=50, ge=1, le=500, description="Max mention items in response")

    article_limit: int = Field(
        default=1000,
        ge=50,
        le=5000,
        description="How many recent articles to scan",
    )


class TrendMentionItem(BaseModel):

    source: str = Field(description="Source name")

    url: str = Field(description="Article URL")

    title: str | None = Field(default=None, description="Article title")

    published_at: str | None = Field(default=None, description="Article published datetime")

    matched_terms: list[str] = Field(default_factory=list, description="Matched company terms")

    mentions_in_article: int = Field(description="Total matched mentions in this article")

    snippet: str = Field(description="Context snippet around mention")


class TrendSourceMentionStat(BaseModel):

    source: str = Field(description="Source name")

    count: int = Field(description="Matched articles count from this source")


class TrendMentionAnalyzeResponse(BaseModel):

    company: str = Field(description="Input company name")

    query_terms: list[str] = Field(description="Effective terms used for mention search")

    scanned_articles: int = Field(description="How many articles were scanned")

    matched_articles: int = Field(description="How many articles matched at least one term")

    total_mentions: int = Field(description="Total mention hits across matched articles")

    top_sources: list[TrendSourceMentionStat] = Field(
        default_factory=list,
        description="Top sources by matched articles",
    )

    items: list[TrendMentionItem] = Field(default_factory=list, description="Mention hits")


class TrendAIAnalyzeRequest(BaseModel):

    company: str | None = Field(default=None, description="Optional company name for focused mention analysis")

    article_limit: int = Field(default=400, ge=50, le=5000, description="How many recent articles to use")

    language: str = Field(default="ru", description="Output language")
    ai_provider: str | None = Field(
        default="auto",
        description="AI provider: auto, gigachat, yandex",
    )


class TrendAIAnalyzeResponse(BaseModel):

    summary: str = Field(default="", description="Overall trend summary")

    key_trends: list[str] = Field(default_factory=list, description="Main trend lines")

    infopovody: list[str] = Field(default_factory=list, description="Current news hooks")

    potential_risks: list[str] = Field(default_factory=list, description="Potential reputational/content risks")

    company_mentions: list[str] = Field(default_factory=list, description="Company mention insights")

    limitations: list[str] = Field(default_factory=list, description="Analysis limitations")
