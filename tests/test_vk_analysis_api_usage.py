from __future__ import annotations

from types import SimpleNamespace

from src.api.config import GigaChatSettings
from src.api.routers import vk as vk_router
from src.api.schemas import VKGroupAnalyzeRequest
from src.api.services.vk_ai import GigaChatVKClient


def _fake_gigachat_settings() -> GigaChatSettings:
    return GigaChatSettings(
        credentials=None,
        authorization_key="test",
        client_id=None,
        model="GigaChat",
        verify_ssl_certs=False,
        scope="GIGACHAT_API_PERS",
        auth_url="https://example.com/oauth",
        base_url="https://example.com/chat",
    )


def test_usage_capture_supports_openai_style_usage_fields():
    client = GigaChatVKClient(_fake_gigachat_settings())

    client._capture_usage(
        {
            "usage": {
                "prompt_tokens": 15,
                "completion_tokens": 5,
                "total_tokens": 20,
            }
        }
    )

    client._capture_usage(
        {
            "result": {
                "usage": {
                    "promptTokens": 6,
                    "completionTokens": 4,
                }
            }
        }
    )

    usage = client.get_usage_totals()
    assert usage["input_tokens"] == 21
    assert usage["output_tokens"] == 9
    assert usage["total_tokens"] == 30


def test_compact_group_payload_contains_only_parsed_subset():
    posts = []
    for idx in range(12):
        posts.append(
            {
                "text": f"Русский пост #{idx} про VK-маркетинг и контент " + ("детали " * 120),
                "likes": 10 + idx,
                "comments": 2 + idx,
                "views": 100 + idx,
                "raw_html": "<div>no</div>",
            }
        )

    payload = {
        "group": {
            "id": 45172096,
            "name": "ДИО Консалт",
            "screen_name": "diocon",
            "members_count": 12345,
            "activity": "Маркетинг",
            "description": "Лишнее поле не должно уходить как есть",
        },
        "metrics": {
            "average_views": 500,
            "average_likes": 30,
            "average_comments": 7,
            "average_reposts": 2,
            "posts_per_day": 1.2,
            "total_posts_analyzed": 40,
            "limitations": ["only public posts", "demo"],
            "raw_payload": {"very": "large"},
        },
        "local_clusters": {
            "audience_interests": ["автоматизация", "CRM", "VK"],
            "audience_age": ["25-34"],
            "audience_activity": ["реагируют на кейсы"],
            "potential_competitors": ["конкурент 1"],
            "search_tags": ["vk маркетинг", "контент стратегия"],
            "summary": "локальная сводка",
            "debug_tokens": ["must", "not", "leak"],
        },
        "posts": posts,
    }

    compact = GigaChatVKClient._compact_group_payload(payload)

    assert set(compact.keys()) == {"group", "metrics", "local_clusters", "posts"}
    assert set(compact["group"].keys()) == {"id", "name", "screen_name", "members_count", "activity"}
    assert set(compact["metrics"].keys()) == {
        "average_views",
        "average_likes",
        "average_comments",
        "average_reposts",
        "posts_per_day",
        "total_posts_analyzed",
        "limitations",
    }
    assert len(compact["posts"]) == 8
    assert all(set(item.keys()) == {"text", "likes", "comments", "views"} for item in compact["posts"])
    assert all(len(item["text"]) <= 320 for item in compact["posts"])


def test_vk_group_analyze_returns_vk_platform_and_usage(monkeypatch):
    class _FakeVKClient:
        def call_api(self, method, access_token, **kwargs):  # noqa: ANN001
            if method == "groups.getById":
                return [
                    {
                        "id": 45172096,
                        "name": "ДИО Консалт",
                        "screen_name": "diocon",
                        "members_count": 12000,
                        "description": "Автоматизация, CRM и маркетинг в VK",
                        "activity": "Маркетинг",
                        "site": "https://example.ru",
                    }
                ]
            if method == "wall.get":
                return {
                    "items": [
                        {
                            "id": 111,
                            "text": "Разбор контент-стратегии для VK и лидогенерации",
                            "views": {"count": 250},
                            "likes": {"count": 34},
                            "comments": {"count": 6},
                            "reposts": {"count": 2},
                            "date": 1_710_000_000,
                        }
                    ]
                }
            if method == "groups.search":
                return {"items": []}
            return {}

    class _FakeAIClient:
        def analyze_group(self, payload, language="ru"):  # noqa: ANN001
            return SimpleNamespace(
                audience_interests=["контент-маркетинг", "продажи в соцсетях"],
                audience_age=["25-34"],
                audience_activity=["активно комментируют кейсы"],
                potential_competitors=["Конкурент A"],
                search_tags=["vk маркетинг", "контент стратегия"],
                summary="Русский анализ готов.",
                limitations=[],
                recommendations=[
                    SimpleNamespace(
                        title="Усилить регулярность",
                        action="Публиковать 3 экспертных поста в неделю",
                        rationale="Это стабилизирует охват и вовлеченность",
                    )
                ],
            )

        def generate_search_tags_from_group(self, group, language="ru", limit=16):  # noqa: ANN001
            return ["vk маркетинг", "контент стратегия"]

        def get_usage_totals(self):
            return {"input_tokens": 321, "output_tokens": 79, "total_tokens": 400}

        def provider_name(self):
            return "yandex"

        def model_name(self):
            return "yandexgpt-lite"

    monkeypatch.setattr(vk_router, "_resolve_access_token", lambda payload_token=None: "token")
    monkeypatch.setattr(
        vk_router,
        "_build_text_ai_client",
        lambda requested_provider=None: (_FakeAIClient(), "yandex", "yandexgpt-lite", "api_key"),
    )
    monkeypatch.setattr(vk_router, "_search_vk_competitors", lambda *args, **kwargs: [])
    monkeypatch.setattr(vk_router, "_safe_save_analysis_history", lambda **kwargs: None)

    response = vk_router.vk_group_analyze(
        VKGroupAnalyzeRequest(
            source="45172096",
            post_limit=10,
            language="ru",
            ai_provider="yandex",
        ),
        _FakeVKClient(),
    )

    assert response.source.platform == "vk"
    assert response.source.group_id == 45172096
    assert response.ai.summary == "Русский анализ готов."
    assert response.ai_usage is not None
    assert response.ai_usage.input_tokens == 321
    assert response.ai_usage.output_tokens == 79
    assert response.ai_usage.total_tokens == 400
