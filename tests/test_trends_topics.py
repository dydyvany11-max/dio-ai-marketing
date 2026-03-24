import json

from src.api.services.trends_topics import build_topics
from src.api.services.vk_ai import GigaChatVKClient
from src.api.services.vk_public import _parse_post_block


def _articles():
    sport = [
        {"title": "Зенит выиграл матч", "content": "Зенит обыграл соперника в чемпионате"},
        {"title": "Спартак подписал форварда", "content": "Трансфер нападающего в Спартак"},
        {"title": "Матч закончился вничью", "content": "Команды сыграли вничью в дерби"},
    ]
    economy = [
        {"title": "Курс рубля вырос", "content": "Рубль укрепился к доллару"},
        {"title": "Инфляция замедлилась", "content": "Цены растут медленнее"},
        {"title": "Нефть подорожала", "content": "Цена нефти выросла на фоне спроса"},
    ]
    return sport + economy


def test_kmeans_topics():
    topics = build_topics(_articles(), max_topics=5, method="kmeans", n_clusters=2)
    assert len(topics) == 2


def test_dbscan_topics():
    topics = build_topics(_articles(), max_topics=5, method="dbscan", eps=0.7, min_samples=2)
    assert isinstance(topics, list)


def test_auto_topics():
    topics = build_topics(_articles(), max_topics=5, method="auto", eps=0.5, min_samples=2, n_clusters=2)
    assert len(topics) >= 1


def test_vk_public_post_block_metrics_are_parsed():
    raw = """РАЙЗ
Verified
Actions
Как изменилось количество патронов некоторых оружий с новым обновлением:
AWP ? 15 патронов (было 35)
113
40
929
6 h ago
Most interesting"""
    parsed = _parse_post_block(raw)
    assert parsed["likes"] == 113
    assert parsed["comments"] == 40
    assert parsed["views"] == 929
    assert parsed["timestamp"] > 0
    assert "патронов" in parsed["text"]


def test_vk_group_insights_validation_accepts_wrapped_payload():
    wrapped = {
        "VKGroupInsights": {
            "audience_interests": ["Игровые обновления"],
            "audience_age": ["18-24 - ядро"],
            "audience_activity": ["Средняя активность"],
            "potential_competitors": ["Паблики про CS"],
            "summary": "Короткий вывод.",
            "limitations": ["Часть выводов эвристические."],
        }
    }
    result = GigaChatVKClient._validate_group_insights_json(json.dumps(wrapped, ensure_ascii=False))
    assert result.summary == "Короткий вывод."
    assert result.audience_interests == ["Игровые обновления"]
