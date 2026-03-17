import pytest

from src.api.services.trends_topics import build_topics


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
