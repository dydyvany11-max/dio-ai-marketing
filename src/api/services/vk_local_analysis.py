from __future__ import annotations

import math
import re

from src.api.services.trends_engine import get_stopwords
from src.api.services.trends_topics import build_topics_with_meta


STOPWORDS = {w.lower() for w in get_stopwords()}

GENERIC_TERMS = {
    "verified",
    "actions",
    "report",
    "reply",
    "share",
    "post",
    "posts",
    "community",
    "page",
    "group",
    "official",
    "interesting",
    "most",
    "latest",
    "raiz",
}

BAD_TERM_PARTS = {
    "\u0431\u044b\u043b",
    "\u0431\u044b\u043b\u0438",
    "\u0431\u0443\u0434\u0435\u0442",
    "\u0431\u0443\u0434\u0443\u0442",
    "\u0432\u0441\u0435",
    "\u0432\u0441\u0435\u0433\u043e",
    "\u0432\u0441\u0435\u0433\u0434\u0430",
    "\u0434\u043e\u043b\u0436\u0435\u043d",
    "\u0434\u043e\u043b\u0436\u043d\u044b",
    "\u0435\u0449\u0435",
    "\u0435\u0441\u043b\u0438",
    "\u043a\u0430\u043a",
    "\u043a\u0430\u043a\u043e\u0439",
    "\u043a\u043e\u0442\u043e\u0440\u044b\u0439",
    "\u043b\u0438\u0448\u044c",
    "\u043c\u0435\u0436\u0434\u0443",
    "\u043d\u0435",
    "\u043d\u043e",
    "\u043e\u043d",
    "\u043e\u043d\u0438",
    "\u043f\u0440\u0438",
    "\u0442\u0430\u043a",
    "\u0442\u0435\u043f\u0435\u0440\u044c",
    "\u0442\u043e\u043b\u044c\u043a\u043e",
    "\u044d\u0442\u043e",
    "\u044d\u0442\u043e\u0442",
    "\u0441\u0435\u0433\u043e\u0434\u043d\u044f",
    "\u0432\u0447\u0435\u0440\u0430",
    "\u0437\u0430\u0432\u0442\u0440\u0430",
    "\u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0438\u0439",
    "\u0441\u043b\u0430\u0439\u0434",
    "\u043b\u0438\u0441\u0442\u0430\u0439\u0442\u0435",
    "\u0441\u0432\u0430\u0439\u043f",
    "\u0442\u0430\u043a\u0436\u0435",
    "\u0443\u0436\u0435",
    "\u0431\u043e\u043b\u044c\u0448\u0435",
    "\u043c\u0435\u043d\u044c\u0448\u0435",
    "\u044d\u0442\u0430",
    "\u044d\u0442\u043e\u0439",
    "\u044d\u0442\u043e\u043c",
    "\u0433\u043e\u0434",
    "\u0433\u043e\u0434\u0443",
    "\u0433\u043e\u0434\u0430",
    "\u043b\u0435\u0442",
    "\u043f\u043e\u0441\u0442\u0443\u043f\u0438\u043b",
    "\u043f\u043e\u044f\u0432\u0438\u043b\u0441\u044f",
    "also",
    "more",
    "most",
    "just",
    "today",
    "tomorrow",
}

MONTH_STEMS = {
    "\u044f\u043d\u0432\u0430\u0440",
    "\u0444\u0435\u0432\u0440\u0430\u043b",
    "\u043c\u0430\u0440\u0442",
    "\u0430\u043f\u0440\u0435\u043b",
    "\u043c\u0430\u044f",
    "\u0438\u044e\u043d",
    "\u0438\u044e\u043b",
    "\u0430\u0432\u0433\u0443\u0441\u0442",
    "\u0441\u0435\u043d\u0442\u044f\u0431\u0440",
    "\u043e\u043a\u0442\u044f\u0431\u0440",
    "\u043d\u043e\u044f\u0431\u0440",
    "\u0434\u0435\u043a\u0430\u0431\u0440",
    "january",
    "february",
    "march",
    "april",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
}

MEDIA_SLUG_SUFFIXES = {
    "news",
    "video",
    "videos",
    "media",
    "music",
    "blog",
}

AGE_RULES = [
    ({"\u0441\u043a\u0438\u0434", "\u0430\u043a\u0446\u0438", "\u0446\u0435\u043d\u0430", "\u043f\u043e\u043a\u0443\u043f", "\u043a\u0430\u0442\u0430\u043b\u043e\u0433"}, "25-34 - \u0432\u0435\u0440\u043e\u044f\u0442\u043d\u044b\u0439 \u043e\u0441\u043d\u043e\u0432\u043d\u043e\u0439 \u0441\u0435\u0433\u043c\u0435\u043d\u0442, \u043e\u0440\u0438\u0435\u043d\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u044b\u0439 \u043d\u0430 \u043f\u0440\u0430\u043a\u0442\u0438\u0447\u0435\u0441\u043a\u0443\u044e \u043f\u043e\u043b\u044c\u0437\u0443"),
    ({"\u043d\u043e\u0432\u043e\u0441\u0442", "\u043e\u0431\u0437\u043e\u0440", "\u0440\u0435\u043b\u0438\u0437", "\u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d"}, "18-34 - \u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0439 \u0441\u0435\u0433\u043c\u0435\u043d\u0442, \u043a\u043e\u0442\u043e\u0440\u044b\u0439 \u0440\u0435\u0433\u0443\u043b\u044f\u0440\u043d\u043e \u0441\u043b\u0435\u0434\u0438\u0442 \u0437\u0430 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f\u043c\u0438"),
]

ACTIVITY_RULES = [
    ({"\u043a\u043e\u043c\u043c\u0435\u043d\u0442", "\u043e\u0431\u0441\u0443\u0436\u0434", "\u0432\u043e\u043f\u0440\u043e\u0441", "\u043e\u0442\u0432\u0435\u0442"}, "\u0420\u0435\u0433\u0443\u043b\u044f\u0440\u043d\u043e\u0435 \u0443\u0447\u0430\u0441\u0442\u0438\u0435 \u0432 \u043e\u0431\u0441\u0443\u0436\u0434\u0435\u043d\u0438\u044f\u0445"),
    ({"\u043d\u043e\u0432\u043e\u0441\u0442", "\u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d", "\u0440\u0435\u043b\u0438\u0437", "\u0430\u043d\u043e\u043d\u0441"}, "\u0421\u0442\u0430\u0431\u0438\u043b\u044c\u043d\u0430\u044f \u0440\u0435\u0430\u043a\u0446\u0438\u044f \u043d\u0430 \u043d\u043e\u0432\u043e\u0441\u0442\u043d\u044b\u0435 \u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u0438"),
]


def build_local_vk_insights(group_name: str, screen_name: str, posts: list[dict], metrics: dict) -> tuple[dict, dict]:
    cleaned_posts = []
    for post in posts:
        text = _normalize_text(str(post.get("text") or ""))
        if text:
            cleaned_posts.append({**post, "text": text})

    total_docs = len(cleaned_posts)
    unique_texts = {post["text"] for post in cleaned_posts}

    articles = [
        {
            "title": _post_title(post["text"]),
            "content": post["text"],
            "url": f"https://vk.com/{screen_name}",
            "source": group_name,
        }
        for post in cleaned_posts
    ]

    if total_docs >= 2 and len(unique_texts) >= 2:
        cluster_target = min(6, len(unique_texts), total_docs)
        try:
            topics, meta = build_topics_with_meta(
                articles,
                max_topics=max(3, min(8, cluster_target + 2)),
                method="auto",
                n_clusters=max(2, cluster_target),
                eps=0.36,
                min_samples=2,
            )
        except Exception:
            topics, meta = [], {"method_used": "single", "cluster_count": 0, "noise_ratio": 0.0}
    else:
        topics, meta = [], {"method_used": "single", "cluster_count": 0, "noise_ratio": 0.0}

    term_df, term_tf = _build_term_stats(cleaned_posts)
    topics = _sanitize_topics(
        topics,
        group_name=group_name,
        screen_name=screen_name,
        term_df=term_df,
        total_docs=total_docs,
    )

    topic_clusters = _build_topic_clusters(
        topics=topics,
        term_df=term_df,
        total_docs=total_docs,
        group_name=group_name,
        screen_name=screen_name,
    )
    topic_clusters = _deduplicate_topic_clusters(topic_clusters)

    if not topic_clusters:
        topic_clusters = _build_fallback_clusters(
            posts=cleaned_posts,
            term_df=term_df,
            term_tf=term_tf,
            banned_terms=_token_parts(group_name) | _token_parts(screen_name) | GENERIC_TERMS,
        )

    interest_clusters = _build_interest_clusters(topic_clusters)
    age_clusters = _build_age_clusters(cleaned_posts, topics)
    activity_clusters = _build_activity_clusters(cleaned_posts, metrics, topics)
    competitors = _build_competitor_hints(topic_clusters, group_name)
    summary = _build_summary(group_name, interest_clusters, activity_clusters, meta, metrics)
    limitations = _build_limitations(metrics, topic_clusters)

    return (
        {
            "audience_interests": interest_clusters,
            "audience_age": age_clusters,
            "audience_activity": activity_clusters,
            "potential_competitors": competitors,
            "summary": summary,
            "limitations": limitations,
            "topic_clusters": topic_clusters,
        },
        {
            "enabled": True,
            "available": True,
            "enhanced": False,
            "provider": "local-clustering",
            "model": f"tfidf-{meta.get('method_used', 'auto')}",
            "auth_mode": None,
            "message": "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0430 \u043b\u043e\u043a\u0430\u043b\u044c\u043d\u0430\u044f \u043a\u043b\u0430\u0441\u0442\u0435\u0440\u0438\u0437\u0430\u0446\u0438\u044f \u043f\u043e \u0442\u0435\u043a\u0441\u0442\u0430\u043c \u043f\u043e\u0441\u0442\u043e\u0432.",
        },
    )


def _normalize_text(text: str) -> str:
    lines = []
    for raw in (text or "").splitlines():
        line = " ".join(raw.strip().split())
        line = re.sub(r"https?://\S+", " ", line, flags=re.IGNORECASE)
        line = re.sub(r"(?:^|\s)[@#][a-zA-Z0-9_\-\.]+", " ", line)
        line = " ".join(line.split())
        if not line:
            continue
        lowered = line.lower()
        if len(lowered) <= 2:
            continue
        if lowered in {"pause", "unmute", "play", "actions"}:
            continue
        if "\u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0438\u0439 \u0441\u043b\u0430\u0439\u0434" in lowered or "\u043f\u0440\u0435\u0434\u044b\u0434\u0443\u0449\u0438\u0439 \u0441\u043b\u0430\u0439\u0434" in lowered:
            continue
        if re.fullmatch(r"\\d+\\s*/\\s*\\d+", lowered):
            continue
        if _looks_like_caption_noise(lowered):
            continue
        lines.append(line)
    return "\n".join(lines).strip()[:4000]


def _looks_like_caption_noise(line: str) -> bool:
    # Typical carousel/UI captions and CTA boilerplate should not form topic clusters.
    if line in {"tap to view", "watch now", "learn more", "read more"}:
        return True
    tokens = _tokenize_local(line)
    if not tokens:
        return True
    if len(tokens) <= 2 and all(token in BAD_TERM_PARTS for token in tokens):
        return True
    if len(tokens) >= 3 and all(token in BAD_TERM_PARTS or token in STOPWORDS for token in tokens):
        return True
    return False


def _sanitize_topics(
    topics: list[dict],
    *,
    group_name: str,
    screen_name: str,
    term_df: dict[str, int],
    total_docs: int,
) -> list[dict]:
    banned = _token_parts(group_name) | _token_parts(screen_name) | GENERIC_TERMS
    min_df = 2 if total_docs >= 6 else 1

    cleaned_topics: list[dict] = []
    for topic in topics:
        terms: list[str] = []
        seen: set[str] = set()
        for raw_term in topic.get("terms", []):
            term = _normalize_term(str(raw_term))
            if not term or term in seen:
                continue
            if _is_bad_term(term, banned):
                continue
            if _term_df(term, term_df) < min_df:
                continue
            if any(term in existing or existing in term for existing in terms):
                continue
            terms.append(term)
            seen.add(term)

        if not terms:
            continue

        cleaned_topics.append(
            {
                "size": int(topic.get("size", 0) or 0),
                "terms": terms[:6],
                "sample_titles": list(topic.get("sample_titles") or [])[:3],
                "sample_urls": list(topic.get("sample_urls") or [])[:3],
            }
        )

    return cleaned_topics


def _normalize_term(value: str) -> str:
    term = " ".join((value or "").strip().lower().replace("-", " " ).split())
    term = re.sub(r"[^a-z0-9\u0430-\u044f\u0451 ]+", "", term)
    return term.strip()


def _is_bad_term(term: str, banned: set[str]) -> bool:
    if not term or len(term) < 3:
        return True
    parts = [part for part in term.split() if part]
    if not parts:
        return True
    if any(part.isdigit() for part in parts):
        return True
    if any(part in banned for part in parts):
        return True
    if any(part in BAD_TERM_PARTS for part in parts):
        return True
    if any(part in STOPWORDS for part in parts):
        return True
    if any(any(month in part for month in MONTH_STEMS) for part in parts):
        return True
    if any(_looks_like_media_slug(part) for part in parts):
        return True
    if any(_looks_like_verb(part) for part in parts):
        return True
    if len(parts) > 4:
        return True
    long_parts = [part for part in parts if len(part) >= 4 and re.search(r"[a-z\u0430-\u044f\u0451]", part)]
    return not long_parts


def _token_parts(value: str) -> set[str]:
    normalized = value.lower().replace("-", " " ).replace("_", " " )
    return {part for part in normalized.split() if len(part) >= 3}


def _post_title(text: str) -> str:
    first_line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    return first_line[:120]


def _build_term_stats(posts: list[dict]) -> tuple[dict[str, int], dict[str, int]]:
    term_df: dict[str, int] = {}
    term_tf: dict[str, int] = {}

    for post in posts:
        text = str(post.get("text") or "")
        tokens = [_normalize_term(token) for token in _tokenize_local(text)]
        tokens = [token for token in tokens if token and _is_semantic_token(token)]

        terms_in_doc: set[str] = set(tokens)
        for n in (2, 3):
            for idx in range(0, max(0, len(tokens) - n + 1)):
                parts = tokens[idx : idx + n]
                if len(parts) != n:
                    continue
                phrase = " ".join(parts)
                if _is_semantic_term(phrase):
                    terms_in_doc.add(phrase)

        for term in terms_in_doc:
            term_df[term] = term_df.get(term, 0) + 1
        for term in tokens:
            term_tf[term] = term_tf.get(term, 0) + 1

    return term_df, term_tf


def _build_topic_clusters(*, topics: list[dict], term_df: dict[str, int], total_docs: int, group_name: str, screen_name: str) -> list[dict]:
    banned = _token_parts(group_name) | _token_parts(screen_name) | GENERIC_TERMS
    min_df = 2 if total_docs >= 6 else 1
    clusters: list[dict] = []

    for topic in topics[:8]:
        terms: list[str] = []
        for term in topic.get("terms", []):
            t = _normalize_term(str(term))
            if not t or _is_bad_term(t, banned):
                continue
            if _term_df(t, term_df) < min_df:
                continue
            if t not in terms:
                terms.append(t)
        if len(terms) < 2 and total_docs >= 4:
            continue
        if not terms:
            continue

        clusters.append(
            {
                "label": _topic_label(terms),
                "size": max(1, int(topic.get("size", 0) or 0)),
                "terms": terms[:5],
                "sample_titles": list(topic.get("sample_titles") or [])[:3],
                "sample_urls": list(topic.get("sample_urls") or [])[:3],
            }
        )

    clusters.sort(key=lambda item: item.get("size", 0), reverse=True)
    return clusters[:6]


def _deduplicate_topic_clusters(topic_clusters: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for cluster in topic_clusters:
        c_terms = set(cluster.get("terms") or [])
        if not c_terms:
            continue

        match_idx = -1
        for idx, existing in enumerate(merged):
            e_terms = set(existing.get("terms") or [])
            overlap = len(c_terms & e_terms)
            union = len(c_terms | e_terms) or 1
            if overlap / union >= 0.55:
                match_idx = idx
                break

        if match_idx == -1:
            merged.append(cluster)
            continue

        existing = merged[match_idx]
        existing["size"] = int(existing.get("size", 0)) + int(cluster.get("size", 0))
        terms = []
        for term in list(existing.get("terms") or []) + list(cluster.get("terms") or []):
            if term not in terms:
                terms.append(term)
        existing["terms"] = terms[:5]
        existing["label"] = _topic_label(existing["terms"])

    merged.sort(key=lambda item: item.get("size", 0), reverse=True)
    return merged[:5]


def _is_semantic_term(term: str) -> bool:
    parts = [part for part in (term or "").strip().lower().split() if part]
    if not parts:
        return False
    return all(_is_semantic_token(part) for part in parts)


def _is_semantic_token(token: str) -> bool:
    value = (token or "").strip().lower()
    if len(value) < 4:
        if len(value) < 3 or not (any(ch.isalpha() for ch in value) and any(ch.isdigit() for ch in value)):
            return False
    if value.isdigit():
        return False
    if value in STOPWORDS or value in BAD_TERM_PARTS or value in GENERIC_TERMS:
        return False
    if any(month in value for month in MONTH_STEMS):
        return False
    if _looks_like_media_slug(value):
        return False
    if _looks_like_verb(value):
        return False
    if not bool(re.search(r"[a-z\u0430-\u044f\u0451]", value)):
        return False
    if not _has_vowel(value):
        return False
    return True


def _looks_like_media_slug(token: str) -> bool:
    value = token.lower()
    if not re.fullmatch(r"[a-z0-9_]+", value):
        return False
    if len(value) < 6:
        return False
    return any(value.endswith(suffix) and value != suffix for suffix in MEDIA_SLUG_SUFFIXES)


def _has_vowel(token: str) -> bool:
    return bool(re.search(r"[aeiouy\u0430\u0435\u0438\u043e\u0443\u044b\u044d\u044e\u044f\u0451]", token.lower()))


def _looks_like_verb(token: str) -> bool:
    value = token.lower()
    suffixes = (
        "\u0430\u0435\u0442\u0441\u044f",
        "\u044f\u0435\u0442\u0441\u044f",
        "\u0435\u0442\u0441\u044f",
        "\u0443\u0435\u0442\u0441\u044f",
        "\u044f\u0442\u0441\u044f",
        "\u0438\u0442\u0441\u044f",
        "\u044e\u0442\u0441\u044f",
        "\u0443\u0442\u0441\u044f",
        "\u0442\u044c\u0441\u044f",
        "\u0438\u0442\u044c\u0441\u044f",
        "\u0430\u0442\u044c",
        "\u044f\u0442\u044c",
        "\u0435\u0442\u044c",
        "\u043e\u0432\u0430\u0442\u044c",
        "\u0438\u0440\u043e\u0432\u0430\u0442\u044c",
        "\u0435\u0448\u044c",
        "\u0435\u0442\u0435",
        "\u0435\u043c",
        "\u044e\u0442",
        "\u0443\u0442",
        "\u0438\u0442",
        "\u0430\u0442",
        "\u044f\u0442",
        "\u0438\u043b",
        "\u0438\u043b\u0430",
        "\u0438\u043b\u0438",
        "\u0430\u043b",
        "\u0430\u043b\u0430",
        "\u0430\u043b\u0438",
    )
    return any(value.endswith(suffix) for suffix in suffixes)


def _term_df(term: str, term_df: dict[str, int]) -> int:
    value = _normalize_term(term)
    if not value:
        return 0
    if value in term_df:
        return term_df[value]
    parts = [part for part in value.split() if part]
    if not parts:
        return 0
    return max(term_df.get(part, 0) for part in parts)


def _topic_label(terms: list[str]) -> str:
    cleaned = [term for term in terms if term]
    if not cleaned:
        return "\u0422\u0435\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u043a\u043b\u0430\u0441\u0442\u0435\u0440"

    phrase = next((term for term in cleaned if " " in term), None)
    if phrase:
        return _humanize_label(phrase)
    if len(cleaned) >= 2:
        return _humanize_label(f"{cleaned[0]} / {cleaned[1]}")
    return _humanize_label(cleaned[0])


def _humanize_label(text: str) -> str:
    normalized = " ".join(str(text).replace("_", " " ).split()).strip(" -,:;")
    if not normalized:
        return "\u0422\u0435\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u043a\u043b\u0430\u0441\u0442\u0435\u0440"
    return normalized[:1].upper() + normalized[1:]


def _build_fallback_clusters(*, posts: list[dict], term_df: dict[str, int], term_tf: dict[str, int], banned_terms: set[str]) -> list[dict]:
    total_docs = max(1, len(posts))
    scored_terms: list[tuple[str, float]] = []

    for term, df in term_df.items():
        if term in banned_terms or not _is_semantic_term(term):
            continue
        if total_docs >= 6 and df < 2:
            continue
        tf = term_tf.get(term, max(1, df))
        score = tf * math.log((total_docs + 1) / (df + 0.5))
        scored_terms.append((term, score))

    scored_terms.sort(key=lambda item: (item[1], len(item[0])), reverse=True)
    top_terms = [term for term, _ in scored_terms[:18]]
    if not top_terms:
        return []

    sample_titles = [
        _post_title(str(post.get("text") or ""))
        for post in posts[:3]
        if str(post.get("text") or "").strip()
    ]

    used: set[str] = set()
    clusters: list[dict] = []
    for term in top_terms:
        if term in used:
            continue
        related = [term]
        base_parts = set(term.split())
        for other in top_terms:
            if other in used or other == term:
                continue
            if base_parts & set(other.split()):
                related.append(other)
            if len(related) >= 4:
                break
        if len(related) < 2 and total_docs >= 4:
            used.update(related)
            continue
        used.update(related)

        clusters.append(
            {
                "label": _topic_label(related),
                "size": max(1, _term_df(term, term_df)),
                "terms": related[:4],
                "sample_titles": sample_titles[:3],
                "sample_urls": [],
            }
        )
        if len(clusters) >= 3:
            break

    return clusters


def _build_interest_clusters(topic_clusters: list[dict]) -> list[str]:
    items = []
    for cluster in topic_clusters[:4]:
        label = str(cluster.get("label") or "\u0422\u0435\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u043a\u043b\u0430\u0441\u0442\u0435\u0440")
        terms = [term for term in (cluster.get("terms") or []) if term][:3]
        items.append(f"{label}: {', '.join(terms)}" if terms else label)
    if not items:
        items.append("\u042f\u0432\u043d\u044b\u0435 \u0442\u0435\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0435 \u043a\u043b\u0430\u0441\u0442\u0435\u0440\u044b \u043d\u0435 \u0432\u044b\u0434\u0435\u043b\u0438\u043b\u0438\u0441\u044c - \u043d\u0443\u0436\u043d\u043e \u0431\u043e\u043b\u044c\u0448\u0435 \u043f\u043e\u0441\u0442\u043e\u0432 \u0438\u043b\u0438 \u0431\u043e\u043b\u0435\u0435 \u0447\u0438\u0441\u0442\u044b\u0435 \u0442\u0435\u043a\u0441\u0442\u044b")
    return list(dict.fromkeys(items))


def _build_age_clusters(posts: list[dict], topics: list[dict]) -> list[str]:
    blob = _text_blob(posts, topics)
    result = [label for keywords, label in AGE_RULES if any(keyword in blob for keyword in keywords)]
    if not result:
        result = [
            "18-24 - \u0432\u0435\u0440\u043e\u044f\u0442\u043d\u044b\u0439 \u0441\u0435\u0433\u043c\u0435\u043d\u0442 \u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435\u0439 \u0441\u043e\u0446\u0441\u0435\u0442\u0435\u0439",
            "25-34 - \u0432\u0435\u0440\u043e\u044f\u0442\u043d\u044b\u0439 \u043e\u0441\u043d\u043e\u0432\u043d\u043e\u0439 \u0441\u0435\u0433\u043c\u0435\u043d\u0442 \u0440\u0435\u0433\u0443\u043b\u044f\u0440\u043d\u044b\u0445 \u043f\u043e\u0442\u0440\u0435\u0431\u0438\u0442\u0435\u043b\u0435\u0439 \u043a\u043e\u043d\u0442\u0435\u043d\u0442\u0430",
        ]
    return result[:3]


def _build_activity_clusters(posts: list[dict], metrics: dict, topics: list[dict]) -> list[str]:
    posts_per_day = float(metrics.get("posts_per_day", 0) or 0)
    avg_comments = int(metrics.get("average_comments", 0) or 0)
    avg_likes = int(metrics.get("average_likes", 0) or 0)
    avg_views = int(metrics.get("average_views", 0) or 0)
    avg_len = int(sum(len(post.get("text", "")) for post in posts) / len(posts)) if posts else 0
    blob = _text_blob(posts, topics)

    items = []
    for keywords, label in ACTIVITY_RULES:
        if any(keyword in blob for keyword in keywords):
            items.append(label)
            break

    if posts_per_day >= 3 or avg_comments >= 20 or avg_likes >= 120:
        items.append("\u0412\u044b\u0441\u043e\u043a\u0430\u044f \u0432\u043e\u0432\u043b\u0435\u0447\u0435\u043d\u043d\u043e\u0441\u0442\u044c \u0432 \u043a\u043e\u043c\u043c\u0435\u043d\u0442\u0430\u0440\u0438\u0438 \u0438 \u0440\u0435\u0430\u043a\u0446\u0438\u0438")
    elif posts_per_day >= 1 or avg_comments >= 5 or avg_likes >= 20 or avg_views >= 300:
        items.append("\u0421\u0440\u0435\u0434\u043d\u044f\u044f \u0430\u043a\u0442\u0438\u0432\u043d\u043e\u0441\u0442\u044c - \u0435\u0441\u0442\u044c \u0441\u0442\u0430\u0431\u0438\u043b\u044c\u043d\u044b\u0435 \u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u0438 \u0438 \u0437\u0430\u043c\u0435\u0442\u043d\u044b\u0435 \u0440\u0435\u0430\u043a\u0446\u0438\u0438")
    else:
        items.append("\u041d\u0438\u0437\u043a\u0430\u044f \u0438\u043b\u0438 \u044d\u043f\u0438\u0437\u043e\u0434\u0438\u0447\u0435\u0441\u043a\u0430\u044f \u0430\u043a\u0442\u0438\u0432\u043d\u043e\u0441\u0442\u044c - \u0440\u0438\u0442\u043c \u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u0439 \u0441\u043b\u0430\u0431\u044b\u0439 \u0438\u043b\u0438 \u0434\u0430\u043d\u043d\u044b\u0435 \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u044b")

    if avg_len >= 900:
        items.append("\u0410\u0443\u0434\u0438\u0442\u043e\u0440\u0438\u044f \u0447\u0438\u0442\u0430\u0435\u0442 \u0434\u043b\u0438\u043d\u043d\u044b\u0435 \u043f\u043e\u0441\u0442\u044b \u0438 \u0440\u0430\u0437\u0431\u043e\u0440\u044b")
    elif avg_len >= 250:
        items.append("\u041b\u0443\u0447\u0448\u0435 \u0437\u0430\u0445\u043e\u0434\u044f\u0442 \u043a\u043e\u0440\u043e\u0442\u043a\u0438\u0435 \u043d\u043e\u0432\u043e\u0441\u0442\u0438 \u0438 \u0441\u0436\u0430\u0442\u044b\u0435 \u043e\u0431\u044a\u044f\u0441\u043d\u0435\u043d\u0438\u044f")
    else:
        items.append("\u041f\u043e\u0442\u0440\u0435\u0431\u043b\u0435\u043d\u0438\u0435 \u0441\u0432\u0435\u0440\u0445\u043a\u043e\u0440\u043e\u0442\u043a\u043e\u0435 - \u0432\u0430\u0436\u043d\u044b \u0431\u044b\u0441\u0442\u0440\u044b\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f \u0438 \u0440\u0435\u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0435 \u043f\u043e\u0441\u0442\u044b")

    return list(dict.fromkeys(items))[:3]


def _build_competitor_hints(topic_clusters: list[dict], group_name: str) -> list[str]:
    if not topic_clusters:
        return ["\u0418\u0441\u043a\u0430\u0442\u044c \u043f\u043e\u0445\u043e\u0436\u0438\u0435 VK-\u0441\u043e\u043e\u0431\u0449\u0435\u0441\u0442\u0432\u0430 \u043f\u043e \u0442\u0435\u043c\u0430\u0442\u0438\u043a\u0435 \u0438 \u0447\u0430\u0441\u0442\u043e\u0442\u0435 \u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u0439"]

    labels = [str(cluster.get("label") or "").strip() for cluster in topic_clusters[:2] if str(cluster.get("label") or "").strip()]
    terms = []
    for cluster in topic_clusters[:2]:
        terms.extend([term for term in (cluster.get("terms") or []) if term])

    hints = []
    if labels:
        hints.append(f"\u0421\u0440\u0430\u0432\u043d\u0438\u0432\u0430\u0442\u044c \u0441 \u043f\u0430\u0431\u043b\u0438\u043a\u0430\u043c\u0438 \u043f\u043e \u0442\u0435\u043c\u0430\u043c: {', '.join(labels)}")
    if terms:
        hints.append(f"\u0418\u0441\u043a\u0430\u0442\u044c \u043a\u043e\u043d\u043a\u0443\u0440\u0435\u043d\u0442\u043e\u0432 \u043f\u043e \u0437\u0430\u043f\u0440\u043e\u0441\u0430\u043c: {', '.join(terms[:4])}")
    return hints[:2] if hints else [f"\u0418\u0441\u043a\u0430\u0442\u044c \u043f\u043e\u0445\u043e\u0436\u0438\u0435 VK-\u0441\u043e\u043e\u0431\u0449\u0435\u0441\u0442\u0432\u0430 \u043f\u043e \u0442\u0435\u043c\u0430\u0442\u0438\u043a\u0435 {group_name}"]


def _build_summary(group_name: str, interest_clusters: list[str], activity_clusters: list[str], meta: dict, metrics: dict) -> str:
    lead_interest = interest_clusters[0] if interest_clusters else "\u0442\u0435\u043c\u0430\u0442\u0438\u043a\u0430 \u043d\u0435 \u0432\u044b\u0434\u0435\u043b\u0438\u043b\u0430\u0441\u044c"
    lead_activity = activity_clusters[0] if activity_clusters else "\u043f\u043e\u0432\u0435\u0434\u0435\u043d\u0447\u0435\u0441\u043a\u0438\u0439 \u0441\u0438\u0433\u043d\u0430\u043b \u043d\u0435 \u043e\u043f\u0440\u0435\u0434\u0435\u043b\u0438\u043b\u0441\u044f"
    total_posts = metrics.get("total_posts_analyzed", 0)
    method = meta.get("method_used", "auto")
    return (
        f"{group_name}: \u043f\u0440\u043e\u0430\u043d\u0430\u043b\u0438\u0437\u0438\u0440\u043e\u0432\u0430\u043d\u043e {total_posts} \u043f\u043e\u0441\u0442\u043e\u0432. "
        f"\u0413\u043b\u0430\u0432\u043d\u044b\u0439 \u0442\u0435\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u043a\u043b\u0430\u0441\u0442\u0435\u0440: {lead_interest}. "
        f"\u041f\u043e\u0432\u0435\u0434\u0435\u043d\u0447\u0435\u0441\u043a\u0438\u0439 \u0441\u0438\u0433\u043d\u0430\u043b: {lead_activity}. "
        f"\u041a\u043b\u0430\u0441\u0442\u0435\u0440\u044b \u043f\u043e\u0441\u0442\u0440\u043e\u0435\u043d\u044b \u043c\u0435\u0442\u043e\u0434\u043e\u043c {method}."
    )


def _build_limitations(metrics: dict, topic_clusters: list[dict]) -> list[str]:
    limitations = list(metrics.get("limitations", []))
    limitations.append("\u0412\u043e\u0437\u0440\u0430\u0441\u0442\u043d\u044b\u0435 \u0441\u0435\u0433\u043c\u0435\u043d\u0442\u044b \u0440\u0430\u0441\u0441\u0447\u0438\u0442\u0430\u043d\u044b \u044d\u0432\u0440\u0438\u0441\u0442\u0438\u0447\u0435\u0441\u043a\u0438 \u043f\u043e \u0442\u0435\u043c\u0430\u043c \u043f\u043e\u0441\u0442\u043e\u0432, \u0430 \u043d\u0435 \u043f\u043e \u0432\u043d\u0443\u0442\u0440\u0435\u043d\u043d\u0435\u0439 \u0430\u043d\u0430\u043b\u0438\u0442\u0438\u043a\u0435 VK.")
    limitations.append("\u041a\u043e\u043d\u043a\u0443\u0440\u0435\u043d\u0442\u044b \u043f\u043e\u0434\u0431\u0438\u0440\u0430\u044e\u0442\u0441\u044f \u043f\u043e \u0442\u0435\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u043e\u043c\u0443 \u0441\u0445\u043e\u0434\u0441\u0442\u0432\u0443 \u043a\u043e\u043d\u0442\u0435\u043d\u0442\u0430, \u0430 \u043d\u0435 \u043f\u043e \u0432\u043d\u0443\u0442\u0440\u0435\u043d\u043d\u0435\u0439 \u0430\u0443\u0434\u0438\u0442\u043e\u0440\u043d\u043e\u0439 \u043c\u0435\u0442\u0440\u0438\u043a\u0435 VK.")
    if metrics.get("average_views", 0) == 0 and metrics.get("average_likes", 0) == 0:
        limitations.append("\u041c\u0435\u0442\u0440\u0438\u043a\u0438 \u0432\u043e\u0432\u043b\u0435\u0447\u0435\u043d\u043d\u043e\u0441\u0442\u0438 \u0447\u0430\u0441\u0442\u0438\u0447\u043d\u043e \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u044b \u043f\u0443\u0431\u043b\u0438\u0447\u043d\u044b\u043c \u0440\u0435\u0436\u0438\u043c\u043e\u043c \u0434\u043e\u0441\u0442\u0443\u043f\u0430 \u043a \u0447\u0443\u0436\u043e\u0439 \u0433\u0440\u0443\u043f\u043f\u0435.")
    if not topic_clusters:
        limitations.append("\u041a\u043b\u0430\u0441\u0442\u0435\u0440\u0438\u0437\u0430\u0446\u0438\u044f \u0442\u0435\u043c \u0441\u0440\u0430\u0431\u043e\u0442\u0430\u043b\u0430 \u0441\u043b\u0430\u0431\u043e: \u043c\u0430\u043b\u043e \u0440\u0430\u0437\u043b\u0438\u0447\u0438\u043c\u044b\u0445 \u0442\u0435\u043a\u0441\u0442\u043e\u0432\u044b\u0445 \u0441\u0438\u0433\u043d\u0430\u043b\u043e\u0432.")
    return list(dict.fromkeys(limitations))


def _text_blob(posts: list[dict], topics: list[dict]) -> str:
    chunks = [str(post.get("text") or "").lower() for post in posts]
    for topic in topics:
        chunks.extend(topic.get("terms") or [])
        chunks.extend(topic.get("sample_titles") or [])
    return " ".join(chunks).lower()


def _tokenize_local(text: str) -> list[str]:
    return re.findall(
        r"(?=[a-zA-Z\u0430-\u044f\u0451])(?:[a-zA-Z\u0430-\u044f\u04510-9_]{3,})",
        str(text or "").lower(),
    )
