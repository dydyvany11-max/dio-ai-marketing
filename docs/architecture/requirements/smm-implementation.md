# Реализация SMM модуля (Django + FastAPI + React)

Ниже — практическая схема реализации требований из `smm.md` в рамках стека Django + FastAPI + React. Документ ориентирован на MVP и расширение без ломки контрактов.

## Роли сервисов

- **Django (core API + DB + auth)**: пользователи, проекты, подключение аккаунтов соцсетей, настройки, отчёты, планировщик, права доступа.
- **FastAPI (аналитика/AI/интеграции)**: сбор метрик, анализ аудитории, тренды, генерация контента, обработка медиа, публикация постов.
- **React (UI)**: кабинет пользователя, формы подключения, отчёты, генерация контента, календарь публикаций.

## Модель данных (Django)

Минимальный набор таблиц:

- `User` (стандартная)
- `Workspace` (организация/команда)
- `Project` (привязка бренда)
- `SocialAccount`
  - `platform` = `vk | telegram`
  - `external_id`
  - `display_name`
  - `access_token` (зашифрованно)
  - `token_expires_at`
  - `status`
- `AudienceReport`
  - `project_id`, `platform`, `source_id`
  - `summary_json`, `clusters_json`, `competitors_json`
  - `created_at`
- `ContentBrief`
  - `topic`, `tone`, `prompt`, `knowledge_base_refs`
- `GeneratedContent`
  - `type` = `text | image | video_script`
  - `payload_json`, `platform_variant`, `quality_score`
- `PostDraft`
  - `platform`, `source_id`, `content_id`, `scheduled_at`, `status`
- `AccountReport`
  - `period_from`, `period_to`, `metrics_json`, `best_posts_json`
  - `export_status`, `export_url`
- `TrendSnapshot`
  - `platform`, `keywords_json`, `mentions_json`, `created_at`

## Контракты API

### Django REST (core)

- `POST /api/social-accounts/connect`  
  Вход: `platform`, `external_id`, `access_token`  
  Выход: `social_account_id`
- `GET /api/social-accounts`  
  Список подключённых аккаунтов
- `POST /api/projects/:id/audience-reports`  
  Запуск анализа аудитории (делегирование в FastAPI)
- `GET /api/projects/:id/audience-reports/:report_id`
- `POST /api/projects/:id/content/generate`  
  Делегирование в FastAPI
- `POST /api/projects/:id/posts/schedule`
- `GET /api/projects/:id/reports/account`
- `POST /api/projects/:id/reports/account/export`

### FastAPI (analytics/AI)

- `POST /smm/audience/analyze`  
  Вход: `platform`, `source_id`, `date_range`  
  Выход: `summary`, `clusters`, `competitors`, `user_personas`
- `POST /smm/content/generate`  
  Вход: `topic`, `prompt`, `tone`, `platform`, `knowledge_base_refs`, `audience_report_id`
  Выход: `variants`
- `POST /smm/posts/publish`  
  Вход: `platform`, `source_id`, `content_payload`, `media_refs`
  Выход: `external_post_id`
- `GET /smm/trends`  
  Вход: `platform`, `keywords`  
  Выход: `trend_items`, `mentions`
- `GET /smm/account/metrics`  
  Вход: `platform`, `source_id`, `period`
  Выход: `reach`, `engagement`, `followers_delta`, `top_posts`

## Фоновые задачи

Использовать Celery/Redis (Django) или RQ. Планировщик:

- ночной сбор метрик `account/metrics`
- ежедневный тренд-снапшот
- автогенерация/отправка отчётов на email
- публикации по расписанию

## Интеграции соцсетей

- **VK**: OAuth + API для групп, статистики, публикаций
- **Telegram**: Bot API для публикаций, парсинг сообщений/статистики из канала (ограничения учитывать)

Токены хранить зашифрованно. Не давать FastAPI прямой доступ к токенам; FastAPI запрашивает через Django по внутреннему сервисному ключу.

## UI (React)

Основные экраны:

- Подключение аккаунтов
- Анализ аудитории (запуск, результат, кластеры, конкуренты)
- Генерация контента (варианты, предпросмотр, адаптация под ВК/Telegram)
- Календарь публикаций
- Сводный отчёт (PDF/DOCX экспорт)
- Тренды и упоминания

## Этапы MVP

1. Подключение аккаунтов VK/Telegram
2. Анализ аудитории (кластеризация + портрет)
3. Генерация текстового контента под VK/Telegram
4. Публикации и расписание
5. Сводный отчёт и экспорт

## Замечания

- Сначала реализовать текстовый контент и базовые метрики, затем расширять на медиа.
- Контракты FastAPI сделать стабильными, чтобы React работал через Django gateway.
