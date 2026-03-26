from src.api.services.vk_local_analysis import build_local_vk_insights
from src.api.services.vk_public import (
    _extract_post_metrics_from_html,
    _fetch_from_browser,
    _fetch_from_context,
    _extract_search_results,
    _is_post_owner_match,
    _search_public_groups_http,
    PublicVKGroupData,
    PublicVKPost,
    PublicVKSearchResult,
)
from src.api.routers.vk import _is_query_term, _is_query_word, _search_vk_competitors


def test_local_vk_insights_filters_ui_noise_and_builds_topics():
    posts = [
        {"text": "next slide\\nDiscount for coffee and chocolate only today"},
        {"text": "New weekly promo: tea, coffee, chocolate at a special price"},
        {"text": "Drinks and sweets catalog with better price"},
        {"text": "Discount on tea and coffee until Sunday"},
        {"text": "Buy groceries near home: promo on sweets"},
    ]
    metrics = {
        "average_views": 120,
        "average_likes": 34,
        "average_comments": 3,
        "average_reposts": 1,
        "posts_per_day": 1.1,
        "total_posts_analyzed": len(posts),
        "limitations": [],
    }

    payload, status = build_local_vk_insights(
        group_name="retail group",
        screen_name="krasnoebeloe",
        posts=posts,
        metrics=metrics,
    )

    assert status["provider"] == "local-heuristics"
    assert payload["topic_clusters"] == []
    assert payload["search_tags"]
    assert all("slide" not in term for term in payload["search_tags"])
    assert payload["audience_interests"]


def test_public_search_results_do_not_include_unrelated_gaming_groups():
    raw_links = [
        {"href": "/xatab_repack_net", "text": "byXatab - Games"},
        {"href": "/fcsm_official", "text": "Spartak Moscow"},
        {"href": "/krasnoebeloe", "text": "Krasnoe i Beloe"},
    ]

    results = _extract_search_results(raw_links, query="krasnoe beloe", limit=10)
    names = {item.screen_name for item in results}

    assert "krasnoebeloe" in names
    assert "xatab_repack_net" not in names
    assert "fcsm_official" not in names


def test_extract_post_metrics_from_html_fallback_counts():
    html = '<div data-count="1732"></div><div data-count="20"></div><div data-count="3"></div>'
    metrics = _extract_post_metrics_from_html(html)

    assert metrics["likes"] == 1732
    assert metrics["comments"] in {20, 3}


def test_query_term_filters_weak_words_and_month_noise():
    assert _is_query_word("cs2")
    assert _is_query_term("cs2 новости")
    assert not _is_query_word("также")
    assert not _is_query_term("также")
    assert not _is_query_term("марта vk")


def test_local_vk_insights_drop_media_slug_noise_terms():
    posts = [
        {"text": "#ffmvideos #fastfoodmusic Новый трек и клип этой недели"},
        {"text": "Вышел клип артиста, разбор трека и премьеры"},
        {"text": "Музыкальные релизы недели: новый трек и клип"},
        {"text": "Премьера клипа: обсуждаем трек и артистов"},
    ]
    metrics = {
        "average_views": 200,
        "average_likes": 45,
        "average_comments": 8,
        "average_reposts": 2,
        "posts_per_day": 1.4,
        "total_posts_analyzed": len(posts),
        "limitations": [],
    }

    payload, _ = build_local_vk_insights(
        group_name="music updates",
        screen_name="fastfoodmusic",
        posts=posts,
        metrics=metrics,
    )

    terms = set(payload["search_tags"])
    assert "ffmvideos" not in terms
    assert "fastfoodmusic" not in terms


def test_post_owner_match_accepts_both_vk_owner_id_signs():
    assert _is_post_owner_match("-24410762_100", 24410762)
    assert _is_post_owner_match("24410762_100", 24410762)
    assert not _is_post_owner_match("-123_100", 24410762)


def test_competitor_search_uses_public_fallback_content_overlap(monkeypatch):
    class _FakeVKClient:
        def call_api(self, method, access_token, **kwargs):  # noqa: ANN001
            if method == "groups.search":
                return {"items": []}
            return {}

    def _fake_search_public_groups(query: str, limit: int = 5):  # noqa: ARG001
        return [
            PublicVKSearchResult(name="HipHop Daily", screen_name="hiphopdaily"),
            PublicVKSearchResult(name="Rap Updates", screen_name="rapupdates"),
        ]

    def _fake_fetch_public_group_data(screen_name: str, group_id=None, limit: int = 20):  # noqa: ANN001,ARG001
        if screen_name == "hiphopdaily":
            posts = [
                PublicVKPost(
                    post_id="-1_1",
                    text="Новый альбом и релиз трека артиста недели",
                    likes=10,
                    comments=2,
                    reposts=1,
                    views=120,
                    date_label="today",
                    timestamp=1,
                ),
                PublicVKPost(
                    post_id="-1_2",
                    text="Премьера клипа и музыкальные новости",
                    likes=8,
                    comments=1,
                    reposts=0,
                    views=90,
                    date_label="today",
                    timestamp=2,
                ),
            ]
        else:
            posts = [
                PublicVKPost(
                    post_id="-2_1",
                    text="Новости спорта и футбола",
                    likes=4,
                    comments=0,
                    reposts=0,
                    views=50,
                    date_label="today",
                    timestamp=1,
                ),
            ]
        return PublicVKGroupData(name=screen_name, screen_name=screen_name, posts=posts)

    monkeypatch.setattr("src.api.routers.vk.search_public_groups", _fake_search_public_groups)
    monkeypatch.setattr("src.api.routers.vk.fetch_public_group_data", _fake_fetch_public_group_data)

    result = _search_vk_competitors(
        _FakeVKClient(),
        "token",
        current_group_id=45172096,
        current_screen_name="fastfoodmusic",
        current_name="Fast Food Music",
        current_activity="Internet media",
        current_description="Издание о музыке и современной культуре",
        topic_clusters=[
            {"label": "Музыка / релизы", "terms": ["альбом", "артист", "релиз"]},
            {"label": "Клипы", "terms": ["клип", "премьера"]},
        ],
        source_posts=[
            {"text": "Альбом артиста и музыкальные релизы недели"},
            {"text": "Премьера клипа и новости музыки"},
        ],
        limit=5,
    )

    assert result, "expected at least one competitor from public fallback"
    names = {item["screen_name"] for item in result}
    assert "hiphopdaily" in names


def test_fetch_from_browser_skips_empty_first_url(monkeypatch):
    calls = {"n": 0}

    def _fake_fetch_from_page(page, url, clean_name, limit, group_id):  # noqa: ANN001, ARG001
        calls["n"] += 1
        if calls["n"] == 1:
            return PublicVKGroupData(name=clean_name, screen_name=clean_name, posts=[])
        return PublicVKGroupData(
            name=clean_name,
            screen_name=clean_name,
            posts=[
                PublicVKPost(
                    post_id="-1_1",
                    text="test",
                    likes=1,
                    comments=1,
                    reposts=0,
                    views=10,
                    date_label="today",
                    timestamp=1,
                )
            ],
        )

    class _FakePage:
        def close(self):
            return None

    class _FakeBrowser:
        def new_page(self, **kwargs):  # noqa: ANN003, ARG002
            return _FakePage()

    monkeypatch.setattr("src.api.services.vk_public._fetch_from_page", _fake_fetch_from_page)
    result = _fetch_from_browser(
        _FakeBrowser(),
        urls=["https://vk.com/a", "https://vk.com/b"],
        clean_name="name",
        limit=10,
        group_id=None,
    )
    assert result.posts
    assert calls["n"] == 2


def test_fetch_from_context_skips_empty_first_url(monkeypatch):
    calls = {"n": 0}

    def _fake_fetch_from_page(page, url, clean_name, limit, group_id):  # noqa: ANN001, ARG001
        calls["n"] += 1
        if calls["n"] == 1:
            return PublicVKGroupData(name=clean_name, screen_name=clean_name, posts=[])
        return PublicVKGroupData(
            name=clean_name,
            screen_name=clean_name,
            posts=[
                PublicVKPost(
                    post_id="-1_2",
                    text="test",
                    likes=1,
                    comments=0,
                    reposts=0,
                    views=5,
                    date_label="today",
                    timestamp=2,
                )
            ],
        )

    class _FakePage:
        def close(self):
            return None

    class _FakeContext:
        def new_page(self):
            return _FakePage()

    monkeypatch.setattr("src.api.services.vk_public._fetch_from_page", _fake_fetch_from_page)
    result = _fetch_from_context(
        _FakeContext(),
        urls=["https://vk.com/a", "https://vk.com/b"],
        clean_name="name",
        limit=10,
        group_id=None,
    )
    assert result.posts
    assert calls["n"] == 2


def test_competitor_search_drops_query_only_matches_without_overlap(monkeypatch):
    class _FakeVKClient:
        def call_api(self, method, access_token, **kwargs):  # noqa: ANN001
            if method == "groups.search":
                return {
                    "items": [
                        {
                            "id": 101,
                            "name": "Spartak Football",
                            "screen_name": "spartak_football",
                            "members_count": 120000,
                            "activity": "",
                            "description": "",
                        }
                    ]
                }
            return {}

    monkeypatch.setattr(
        "src.api.routers.vk.fetch_public_group_data",
        lambda *args, **kwargs: PublicVKGroupData(name="stub", screen_name="stub", posts=[]),
    )

    result = _search_vk_competitors(
        _FakeVKClient(),
        "token",
        current_group_id=45172096,
        current_screen_name="fastfoodmusic",
        current_name="Fast Food Music",
        current_activity="",
        current_description="",
        topic_clusters=[],
        source_posts=[],
        limit=5,
    )

    assert result == []


def test_search_public_groups_http_parses_vk_links(monkeypatch):
    class _Resp:
        status_code = 200
        text = """
        <html><body>
            <a href="/xatab_repack_net">byXatab - Games</a>
            <a href="/fastfoodmusic">Fast Food Music</a>
            <a href="/music_media_ru">Music Media RU</a>
        </body></html>
        """

    monkeypatch.setattr("src.api.services.vk_public.requests.get", lambda *args, **kwargs: _Resp())
    results = _search_public_groups_http("fast food music", limit=5)
    names = {item.screen_name for item in results}
    assert "fastfoodmusic" in names


def test_query_word_rejects_internet_generic():
    assert not _is_query_word("internet")


def test_competitor_search_fallback_by_source_name(monkeypatch):
    class _FakeVKClient:
        def call_api(self, method, access_token, **kwargs):  # noqa: ANN001
            if method == "groups.search":
                return {"items": []}
            return {}

    monkeypatch.setattr(
        "src.api.routers.vk.search_public_groups",
        lambda query, limit=5: [PublicVKSearchResult(name="Music Hub", screen_name="music_hub_vk")],  # noqa: ARG005
    )
    monkeypatch.setattr(
        "src.api.routers.vk.fetch_public_group_data",
        lambda *args, **kwargs: PublicVKGroupData(name="stub", screen_name="stub", posts=[]),
    )

    result = _search_vk_competitors(
        _FakeVKClient(),
        "token",
        current_group_id=1,
        current_screen_name="fastfoodmusic",
        current_name="Fast Food Music",
        current_activity="Internet media",
        current_description="",
        topic_clusters=[],
        source_posts=[],
        limit=5,
    )

    assert result
    assert result[0]["screen_name"] == "music_hub_vk"


def test_competitor_search_works_with_ai_tags_without_clusters(monkeypatch):
    class _FakeVKClient:
        def call_api(self, method, access_token, **kwargs):  # noqa: ANN001
            if method == "groups.search":
                return {
                    "items": [
                        {
                            "id": 303,
                            "name": "Music Radar",
                            "screen_name": "music_radar",
                            "members_count": 50000,
                            "activity": "Internet media",
                            "description": "Музыкальные релизы и альбомы",
                        }
                    ]
                }
            return {}

    monkeypatch.setattr(
        "src.api.routers.vk.fetch_public_group_data",
        lambda *args, **kwargs: PublicVKGroupData(name="stub", screen_name="stub", posts=[]),
    )

    result = _search_vk_competitors(
        _FakeVKClient(),
        "token",
        current_group_id=45172096,
        current_screen_name="fastfoodmusic",
        current_name="Fast Food Music",
        current_activity="Internet media",
        current_description="Издание о музыке",
        topic_clusters=[],
        source_posts=[],
        ai_tags=["музыка", "альбом", "релизы"],
        topic_labels=["Музыкальные релизы"],
        limit=5,
    )

    assert result
    assert result[0]["screen_name"] == "music_radar"
