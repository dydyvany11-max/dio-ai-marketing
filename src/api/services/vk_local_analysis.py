from __future__ import annotations

import re
from collections import Counter

from src.api.services.trends_engine import get_stopwords

STOPWORDS = {word.lower() for word in get_stopwords()}
_EXTRA_STOPWORDS = {
    "vk",
    "club",
    "public",
    "group",
    "community",
    "post",
    "posts",
    "wall",
    "official",
    "page",
    "today",
    "yesterday",
    "this",
    "that",
    "with",
    "from",
    "для",
    "это",
    "также",
    "уже",
    "еще",
    "ещё",
    "просто",
    "очень",
    "следующий",
    "слайд",
    "предыдущий",
    "листайте",
    "свайп",
    "comment",
    "comments",
    "leave",
    "reply",
    "replies",
    "view",
    "views",
    "oldest",
    "unavailable",
    "because",
}


def build_local_vk_insights(group_name: str, screen_name: str, posts: list[dict], metrics: dict) -> tuple[dict, dict]:
    cleaned_posts: list[dict] = []
    for post in posts:
        text = _normalize_text(str(post.get("text") or ""))
        if text:
            cleaned_posts.append({**post, "text": text})

    tags = _extract_tags(
        cleaned_posts,
        banned_terms=_brand_terms(group_name) | _brand_terms(screen_name),
        limit=14,
    )

    interests = _build_interest_bullets(tags)
    age = _build_age_bullets(tags, metrics)
    activity = _build_activity_bullets(tags, metrics)
    competitors = _build_competitor_hints(tags, group_name)

    total_posts = int(metrics.get("total_posts_analyzed") or len(cleaned_posts) or 0)
    summary = _build_summary(group_name, total_posts, interests, activity)

    limitations = list(metrics.get("limitations") or [])
    limitations.append("Использован локальный fallback-анализ, потому что AI недоступен.")
    if not cleaned_posts:
        limitations.append("Текстов постов недостаточно для точного тематического анализа.")

    payload = {
        "audience_interests": interests,
        "audience_age": age,
        "audience_activity": activity,
        "potential_competitors": competitors,
        "search_tags": tags,
        "summary": summary,
        "limitations": _dedupe(limitations)[:8],
        "topic_clusters": [],
    }
    status = {
        "enabled": True,
        "available": True,
        "enhanced": False,
        "provider": "local-heuristics",
        "model": "keyword-fallback",
        "auth_mode": None,
        "message": "Применен локальный fallback-анализ.",
    }
    return payload, status


def _normalize_text(text: str) -> str:
    value = " ".join((text or "").split())
    if not value:
        return ""
    value = re.sub(r"https?://\S+", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"(?:^|\s)[@#][A-Za-zА-Яа-яЁё0-9_\-.]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:5000]


def _tokenize(text: str) -> list[str]:
    return [
        token.lower()
        for token in re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", text or "")
        if len(token) >= 3
    ]


def _brand_terms(value: str) -> set[str]:
    return {token for token in _tokenize(value) if len(token) >= 4}


def _extract_tags(posts: list[dict], *, banned_terms: set[str], limit: int) -> list[str]:
    token_tf: Counter[str] = Counter()
    token_df: Counter[str] = Counter()
    bigram_tf: Counter[str] = Counter()

    for post in posts:
        tokens = [
            token
            for token in _tokenize(str(post.get("text") or ""))
            if _is_semantic_token(token, banned_terms)
        ]
        if not tokens:
            continue

        token_tf.update(tokens)
        token_df.update(set(tokens))

        for idx in range(len(tokens) - 1):
            bigram = f"{tokens[idx]} {tokens[idx + 1]}"
            if _is_semantic_phrase(bigram):
                bigram_tf[bigram] += 1

    total_docs = max(1, len(posts))
    min_df = 2 if total_docs >= 8 else 1

    scored: list[tuple[str, float]] = []
    for token, tf in token_tf.items():
        df = token_df.get(token, 1)
        if df < min_df:
            continue
        score = tf * (1.0 + 1.0 / df)
        scored.append((token, score))

    for phrase, tf in bigram_tf.items():
        if tf < min_df:
            continue
        score = tf * 1.35
        scored.append((phrase, score))

    scored.sort(key=lambda item: (item[1], len(item[0])), reverse=True)

    tags: list[str] = []
    for term, _ in scored:
        if term in tags:
            continue
        if any(term in existing or existing in term for existing in tags):
            continue
        tags.append(term)
        if len(tags) >= limit:
            break
    return tags


def _is_semantic_token(token: str, banned_terms: set[str]) -> bool:
    if len(token) < 3:
        return False
    if token in banned_terms:
        return False
    if token in STOPWORDS or token in _EXTRA_STOPWORDS:
        return False
    if token.isdigit():
        return False
    if any(ch.isdigit() for ch in token) and len(token) < 4:
        return False
    if not any(ch.isalpha() for ch in token):
        return False
    if token.endswith(("ing", "ed", "tion", "ions", "ться", "овать", "ение")):
        return False
    return True


def _is_semantic_phrase(phrase: str) -> bool:
    parts = phrase.split()
    if len(parts) != 2:
        return False
    return all(len(part) >= 3 and part not in STOPWORDS and part not in _EXTRA_STOPWORDS for part in parts)


def _build_interest_bullets(tags: list[str]) -> list[str]:
    if not tags:
        return ["Явные тематические кластеры не выделились: нужно больше чистых текстов постов."]

    bullets: list[str] = []
    first = ", ".join(tags[:4])
    bullets.append(f"Главные интересы аудитории: {first}")
    if len(tags) > 4:
        second = ", ".join(tags[4:8])
        bullets.append(f"Дополнительные сигналы интереса: {second}")
    return bullets[:4]


def _build_age_bullets(tags: list[str], metrics: dict) -> list[str]:
    text = " ".join(tags)
    if any(word in text for word in ["бизнес", "финансы", "карьера", "b2b", "сделка", "инвестиции"]):
        return [
            "25-44 - вероятный основной сегмент, ориентированный на прикладной контент",
            "18-24 - дополнительный сегмент для быстрых форматов и трендов",
        ]
    if any(word in text for word in ["игра", "кибер", "музыка", "мем", "стрим", "кино"]):
        return ["18-34 - активный сегмент, регулярно потребляющий развлекательный контент"]
    if (metrics.get("average_comments") or 0) >= 10:
        return [
            "18-24 - заметная доля активных комментаторов",
            "25-34 - стабильный вовлеченный сегмент",
        ]
    return ["18-34 - базовый активный сегмент пользователей соцсетей"]


def _build_activity_bullets(tags: list[str], metrics: dict) -> list[str]:
    comments = int(metrics.get("average_comments") or 0)
    likes = int(metrics.get("average_likes") or 0)
    posts_per_day = float(metrics.get("posts_per_day") or 0)

    bullets: list[str] = []
    if comments >= 8:
        bullets.append("Регулярное участие в обсуждениях")
    elif comments > 0:
        bullets.append("Есть вовлеченность, но комментариев немного")
    else:
        bullets.append("Комментариев мало, аудитория в основном реактивная")

    if likes >= 50:
        bullets.append("Высокая вовлеченность в реакции")
    elif likes >= 15:
        bullets.append("Средняя вовлеченность в реакции")
    else:
        bullets.append("Низкая реактивность, нужны более сильные контент-хуки")

    if posts_per_day >= 2:
        bullets.append("Высокий ритм публикаций, аудитория привыкла к частым обновлениям")
    elif posts_per_day > 0:
        bullets.append("Умеренный ритм публикаций")
    else:
        bullets.append("Ритм публикаций не определился из-за ограничений данных")

    return bullets[:3]


def _build_competitor_hints(tags: list[str], group_name: str) -> list[str]:
    if not tags:
        return [f"Искать похожие VK-сообщества по теме '{group_name}' и близким ключевым словам."]

    shortlist = tags[:6]
    hints = ["Искать конкурентов по тематическим тегам: " + ", ".join(shortlist[:3])]
    if len(shortlist) >= 4:
        hints.append("Дополнительные теги для поиска: " + ", ".join(shortlist[3:6]))
    return hints[:3]


def _build_summary(group_name: str, total_posts: int, interests: list[str], activity: list[str]) -> str:
    top_interest = interests[0] if interests else "тематические сигналы не определились"
    top_activity = activity[0] if activity else "активность не определилась"
    return (
        f"{group_name}: проанализировано {total_posts} постов. "
        f"Ключевой интерес: {top_interest}. "
        f"Активность аудитории: {top_activity}."
    )


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(str(value or "").split()).strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(normalized)
    return output
