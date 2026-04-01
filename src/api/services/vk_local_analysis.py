from __future__ import annotations

import re
from collections import Counter

from src.api.services.trends_engine import get_stopwords

STOPWORDS = {word.lower() for word in get_stopwords()}
_EXTRA_STOPWORDS = {
    # Generic UI / crawl noise
    "vk",
    "club",
    "public",
    "group",
    "community",
    "post",
    "posts",
    "wall",
    "page",
    "today",
    "yesterday",
    "this",
    "that",
    "with",
    "from",
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
    "slide",
    "next",
    "previous",
    "swipe",
    # Russian generic / weak words
    "онлайн",
    "инфо",
    "компания",
    "компании",
    "официальный",
    "партнер",
    "партнёр",
    "услуга",
    "услуги",
    "эксперт",
    "эксперты",
    "документ",
    "документы",
    "версия",
    "версии",
    "пусть",
    "необходимо",
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
    # Frequent social slugs/noise
    "ffmvideos",
    "ffmnews",
}
_ALL_STOPWORDS = STOPWORDS | _EXTRA_STOPWORDS
_MONTH_WORDS = {
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
}


def build_local_vk_insights(group_name: str, screen_name: str, posts: list[dict], metrics: dict) -> tuple[dict, dict]:
    return build_local_vk_insights_with_context(
        group_name=group_name,
        screen_name=screen_name,
        posts=posts,
        metrics=metrics,
        group_description=None,
        group_activity=None,
    )


def build_local_vk_insights_with_context(
    group_name: str,
    screen_name: str,
    posts: list[dict],
    metrics: dict,
    group_description: str | None,
    group_activity: str | None,
) -> tuple[dict, dict]:
    cleaned_posts: list[dict] = []
    for post in posts:
        text = _normalize_text(str(post.get("text") or ""))
        if text:
            cleaned_posts.append({**post, "text": text})

    banned_terms = _brand_terms(group_name) | _brand_terms(screen_name)
    post_tags = _extract_tags(cleaned_posts, banned_terms=banned_terms, limit=16)
    context_tags = _extract_context_tags(
        description=group_description or "",
        activity=group_activity or "",
        banned_terms=banned_terms,
        limit=10,
    )
    tags = _merge_tag_lists(context_tags, post_tags, limit=14)

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
    value = re.sub(r"(?:^|\s)[@#][A-Za-zА-Яа-яЁё0-9_.-]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:5000]


def _tokenize(text: str) -> list[str]:
    output: list[str] = []
    for token in re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", text or ""):
        value = token.lower()
        if len(value) >= 3:
            output.append(value)
            continue
        if len(value) >= 2 and any(ch.isdigit() for ch in value) and any(ch.isalpha() for ch in value):
            output.append(value)
    return output


def _brand_terms(value: str) -> set[str]:
    return {token for token in _tokenize(value) if len(token) >= 4}


def _extract_tags(posts: list[dict], *, banned_terms: set[str], limit: int) -> list[str]:
    token_tf: Counter[str] = Counter()
    token_df: Counter[str] = Counter()
    bigram_tf: Counter[str] = Counter()

    for post in posts:
        tokens = [token for token in _tokenize(str(post.get("text") or "")) if _is_semantic_token(token, banned_terms)]
        if not tokens:
            continue

        token_tf.update(tokens)
        token_df.update(set(tokens))

        for idx in range(len(tokens) - 1):
            bigram = f"{tokens[idx]} {tokens[idx + 1]}"
            if _is_semantic_phrase(bigram, banned_terms):
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
        score = tf * 1.3
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


def _extract_context_tags(description: str, activity: str, *, banned_terms: set[str], limit: int) -> list[str]:
    text = " ".join(part for part in [description, activity] if part).strip()
    if not text:
        return []
    tokens = [token for token in _tokenize(text) if _is_semantic_token(token, banned_terms)]
    counter: Counter[str] = Counter(tokens)
    for token in _tokenize(activity):
        if _is_semantic_token(token, banned_terms):
            counter[token] += 2
    for idx in range(len(tokens) - 1):
        phrase = f"{tokens[idx]} {tokens[idx + 1]}"
        if _is_semantic_phrase(phrase, banned_terms):
            counter[phrase] += 2
    tags: list[str] = []
    for term, _ in counter.most_common(limit * 3):
        if term in tags:
            continue
        if any(term in existing or existing in term for existing in tags):
            continue
        tags.append(term)
        if len(tags) >= limit:
            break
    return tags


def _merge_tag_lists(primary: list[str], secondary: list[str], *, limit: int) -> list[str]:
    merged: list[str] = []
    for term in list(primary) + list(secondary):
        if term in merged:
            continue
        if any(term in existing or existing in term for existing in merged):
            continue
        merged.append(term)
        if len(merged) >= limit:
            break
    return merged


def _is_semantic_token(token: str, banned_terms: set[str]) -> bool:
    if len(token) < 3:
        return False
    if token in banned_terms:
        return False
    if token in _ALL_STOPWORDS or token in _MONTH_WORDS:
        return False
    if token.isdigit():
        return False
    if token.startswith("http"):
        return False
    return True


def _is_semantic_phrase(phrase: str, banned_terms: set[str]) -> bool:
    words = phrase.split()
    if len(words) != 2:
        return False
    return all(_is_semantic_token(word, banned_terms) for word in words)


def _build_interest_bullets(tags: list[str]) -> list[str]:
    if not tags:
        return ["Явные тематические сигналы не выделились — нужно больше постов."]
    head = ", ".join(tags[:4])
    tail = ", ".join(tags[4:8])
    bullets = [f"Главные интересы аудитории: {head}"]
    if tail:
        bullets.append(f"Дополнительные сигналы интереса: {tail}")
    return bullets


def _build_age_bullets(tags: list[str], metrics: dict) -> list[str]:
    comments = int(metrics.get("average_comments") or 0)
    likes = int(metrics.get("average_likes") or 0)
    if comments >= 20 or likes >= 200:
        return ["18-24 — наиболее активная возрастная группа", "25-34 — значительная аудитория"]
    return ["18-34 — базовый активный сегмент пользователей соцсетей"]


def _build_activity_bullets(tags: list[str], metrics: dict) -> list[str]:
    comments = int(metrics.get("average_comments") or 0)
    posts_per_day = float(metrics.get("posts_per_day") or 0)
    bullets: list[str] = []
    if comments >= 10:
        bullets.append("Регулярное участие в обсуждениях")
    elif comments > 0:
        bullets.append("Комментариев немного, аудитория в основном реактивная")
    else:
        bullets.append("Низкая активность комментариев")

    if posts_per_day >= 1:
        bullets.append("Умеренный или высокий ритм публикаций")
    else:
        bullets.append("Ритм публикаций не определился из-за ограничений данных")
    return bullets[:3]


def _build_competitor_hints(tags: list[str], group_name: str) -> list[str]:
    if not tags:
        return ["Искать конкурентов по тематике контента и близким ключевым словам группы"]
    hints = [f"Искать конкурентов по тематическим тегам: {', '.join(tags[:4])}"]
    if len(tags) > 4:
        hints.append(f"Дополнительные теги для поиска: {', '.join(tags[4:8])}")
    return hints


def _build_summary(group_name: str, total_posts: int, interests: list[str], activity: list[str]) -> str:
    interest = interests[0] if interests else "Тематические сигналы не выделены"
    activity_signal = activity[0] if activity else "Активность аудитории не определена"
    return f"{group_name}: проанализировано {total_posts} постов. Ключевой интерес: {interest}. Активность аудитории: {activity_signal}."


def _dedupe(items: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = (item or "").strip()
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output
