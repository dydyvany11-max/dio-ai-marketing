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
                "participant_limit": 200,
                "message_limit": 100,
                "top_k": 5,
            }
        }
    )

    source: str = Field(
        default="https://t.me/Cbpub",
        description="Ссылка на канал/группу, @username или ID Telegram-источника",
        examples=["https://t.me/Cbpub", "@Cbpub", "1135818819"],
    )
    candidate_sources: list[str] = Field(
        default=[
            "https://t.me/mediyca",
            "https://t.me/raiznews",
            "https://t.me/paritet_development",
        ],
        min_length=1,
        max_length=30,
        description="Список каналов-кандидатов, с которыми нужно сравнить основной источник",
        examples=[["@meduzalive", "@bbbreaking", "@rian_ru"]],
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
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Сколько самых похожих кандидатов вернуть в ответе",
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


class AudienceCompetitorsInputResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str = Field(description="Что было передано в source")
    candidate_sources: list[str] = Field(description="Список кандидатов на сравнение")
    participant_limit: int = Field(description="Какой лимит участников был запрошен")
    message_limit: int = Field(description="Какой лимит сообщений был запрошен")
    top_k: int = Field(description="Сколько лучших совпадений нужно вернуть")


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
    age_hypothesis_clusters: list[AudienceClusterResponse] = Field(
        description="Гипотеза по возрастным группам аудитории на основе косвенных сигналов"
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


class CompetitorMatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: AudienceSourceResponse = Field(description="Информация о похожем канале-кандидате")
    similarity_score: float = Field(description="Итоговый скор похожести от 0 до 1")
    relation_type: str = Field(description="Тип совпадения каналов")
    theme_similarity: float = Field(description="Похожесть по тематике контента")
    audience_similarity: float = Field(description="Похожесть по структуре аудитории")
    engagement_similarity: float = Field(description="Похожесть по метрикам вовлечения")
    format_similarity: float = Field(description="Похожесть по формату и подаче")
    shared_theme_count: int = Field(description="Общее число пересекающихся тем")
    shared_specific_theme_count: int = Field(description="Число пересекающихся нишевых тем")
    generic_overlap_count: int = Field(description="Сколько пересечений пришлось на широкие общие темы")
    niche_overlap_score: float = Field(description="Сила пересечения именно по нишевым темам")
    dominant_specific_theme: str | None = Field(default=None, description="Главная нишевая тема исходного канала")
    candidate_dominant_specific_theme: str | None = Field(default=None, description="Главная нишевая тема канала-кандидата")
    matched_themes: list[str] = Field(description="Какие темы совпали сильнее всего")
    matched_keywords: list[str] = Field(description="Какие ключевые сигналы контента пересеклись")
    disqualifiers: list[str] = Field(description="Почему канал не прошел в более близкую категорию конкурента")
    reason: str = Field(description="Краткое объяснение, почему канал похож")


class CompetitorFailureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str = Field(description="Кандидат, который не удалось обработать")
    error: str = Field(description="Причина, по которой кандидат был пропущен")


class CompetitorDiscoveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    input: AudienceCompetitorsInputResponse = Field(
        description="Входные параметры, с которыми был запущен поиск конкурентов"
    )
    source: AudienceSourceResponse = Field(
        description="Информация об основном анализируемом Telegram-источнике"
    )
    competitors: list[CompetitorMatchResponse] = Field(
        description="Список наиболее похожих каналов из переданных кандидатов"
    )
    failed_candidates: list[CompetitorFailureResponse] = Field(
        description="Кандидаты, которых не удалось проанализировать"
    )
