from __future__ import annotations

from collections import Counter
from io import BytesIO

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception:
    plt = None

from src.api.schemas import VKGroupAIInsights, VKGroupAnalyzeResponse, VKGroupMetricsResponse
from src.api.services.trends_engine import get_stopwords
from src.api.services.vk_client import VKClient
from src.api.services.vk_public import fetch_public_group_data, search_public_groups

STOPWORDS = {word.lower() for word in get_stopwords()}
_MONTH_QUERY_STEMS = {
    "\u044f\u043d\u0432",
    "\u0444\u0435\u0432",
    "\u043c\u0430\u0440\u0442",
    "\u0430\u043f\u0440",
    "\u043c\u0430\u0439",
    "\u0438\u044e\u043d",
    "\u0438\u044e\u043b",
    "\u0430\u0432\u0433",
    "\u0441\u0435\u043d",
    "\u043e\u043a\u0442",
    "\u043d\u043e\u044f",
    "\u0434\u0435\u043a",
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
_WEAK_QUERY_WORDS = {
    "vk",
    "club",
    "public",
    "group",
    "community",
    "post",
    "posts",
    "news",
    "latest",
    "today",
    "yesterday",
    "video",
    "internet",
    "media",
    "movement",
    "internetmedia",
    "\u0438\u043d\u0442\u0435\u0440\u043d\u0435\u0442",
    "\u043c\u0435\u0434\u0438\u0430",
    "\u0438\u0437\u0434\u0430\u043d\u0438\u0435",
    "\u0438\u043d\u0442\u0435\u0440\u043d\u0435\u0442\u0438\u0437\u0434\u0430\u043d\u0438\u0435",
    "\u0438\u043d\u0442\u0435\u0440\u043d\u0435\u0442-\u0438\u0437\u0434\u0430\u043d\u0438\u0435",
    "\u0434\u043d\u044f",
    "\u043d\u043e\u0432\u043e\u0441\u0442\u0438",
    "\u043a\u043e\u0442\u043e\u0440\u044b\u0439",
    "\u043a\u043e\u0442\u043e\u0440\u0430\u044f",
    "\u043a\u043e\u0442\u043e\u0440\u044b\u0435",
    "\u0432\u0438\u0434\u0435\u043e",
    "\u043f\u043e\u0441\u0442",
    "\u0433\u0440\u0443\u043f\u043f\u0430",
    "\u0441\u043e\u043e\u0431\u0449\u0435\u0441\u0442\u0432\u043e",
    "\u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0438\u0439",
    "\u0441\u043b\u0430\u0439\u0434",
    "\u0442\u0430\u043a\u0436\u0435",
    "\u0443\u0436\u0435",
    "\u0431\u043e\u043b\u044c\u0448\u0435",
    "\u043c\u0435\u043d\u044c\u0448\u0435",
    "\u043e\u0442\u0432\u0435\u0442",
    "\u0432\u0441\u0435\u0433\u0434\u0430",
    "\u044d\u0442\u043e\u043c",
    "\u0433\u043e\u0434\u0443",
    "\u0433\u043e\u0434",
    "\u043a\u043e\u0442\u043e\u0440\u044b\u0439",
    "\u043a\u043e\u0442\u043e\u0440\u0430\u044f",
    "\u043a\u043e\u0442\u043e\u0440\u044b\u0435",
    "this",
    "that",
    "these",
    "those",
    "has",
    "been",
    "because",
    "unavailable",
    "oldest",
    "leave",
    "comment",
    "comments",
    "reply",
    "replies",
    "april",
    "march",
    "may",
    "apr",
    "year",
    "which",
    "new",
}

def _search_vk_competitors(
    vk_client: VKClient,
    access_token: str,
    *,
    current_group_id: int,
    current_screen_name: str | None,
    current_name: str,
    current_activity: str | None,
    current_description: str | None,
    topic_clusters: list[dict],
    source_posts: list[dict] | None = None,
    ai_tags: list[str] | None = None,
    topic_labels: list[str] | None = None,
    use_ai_tags_only: bool = False,
    limit: int = 5,
) -> list[dict]:
    source_posts = source_posts or []
    normalized_ai_tags = _normalize_terms(ai_tags or [], limit=16)
    topic_labels = [label.strip() for label in (topic_labels or []) if str(label).strip()]

    banned_name_terms = _brand_terms(current_screen_name or "")
    context_terms = {
        token
        for token in _tokenize_loose(" ".join([current_name or "", current_activity or "", current_description or ""]))
        if _is_query_word(token) and token not in banned_name_terms
    }
    if normalized_ai_tags:
        normalized_ai_tags = [
            tag
            for tag in normalized_ai_tags
            if _term_supported_by_context(tag, context_terms)
        ]

    source_terms = set()
    source_tags: list[str] = []
    meta_tags: list[str] = []
    name_tags: list[str] = []
    if use_ai_tags_only and normalized_ai_tags:
        source_terms.update(normalized_ai_tags)
        source_tags = list(normalized_ai_tags)
    else:
        source_terms = _extract_cluster_terms(topic_clusters)
        source_tags = _normalize_terms(
            _extract_source_tags(source_posts, limit=24, banned_terms=banned_name_terms),
            banned_terms=banned_name_terms,
            limit=24,
        )
        meta_tags = _normalize_terms(
            _extract_meta_tags(current_activity or "", current_description or "", current_screen_name or "", limit=10),
            banned_terms=banned_name_terms,
            limit=10,
        )
        name_tags = [token for token in _tokenize_loose(current_name or "") if _is_query_word(token)]

    for term in source_tags + meta_tags + name_tags + normalized_ai_tags:
        if _is_query_term(term) and term not in banned_name_terms:
            source_terms.add(term)

    source_terms = {
        term
        for term in source_terms
        if _is_query_term(term) and _is_specific_term(term, banned_terms=banned_name_terms)
    }
    if not source_terms:
        return []

    ranked_anchors = sorted(
        source_terms,
        key=lambda value: (_term_specificity(value), len(value)),
        reverse=True,
    )
    anchor_terms_set = set(ranked_anchors[:12])
    domain_terms = set(ranked_anchors[:18])

    queries = _build_competitor_queries(
        source_terms=source_terms,
        source_tags=source_tags,
        meta_tags=meta_tags,
        ai_tags=normalized_ai_tags,
        current_name=current_name,
        allow_name_fallback=not use_ai_tags_only,
    )
    if not queries:
        return []

    candidates: dict[str, dict] = {}
    current_screen_name_l = (current_screen_name or "").lower()
    current_name_l = (current_name or "").lower()

    for query in queries:
        query_tokens = {token for token in _tokenize_loose(query) if _is_query_word(token)}
        matched_terms = _match_terms(source_terms, query_tokens)

        try:
            result = vk_client.call_api(
                "groups.search",
                access_token,
                q=query,
                count=25,
                sort=0,
                fields="members_count,activity,description,screen_name",
            )
            items = result.get("items", []) if isinstance(result, dict) else []
        except Exception:
            items = []

        for item in items:
            if not isinstance(item, dict):
                continue
            gid = int(item.get("id", 0) or 0)
            if not gid or gid == current_group_id:
                continue

            name = str(item.get("name") or "").strip()
            screen_name = str(item.get("screen_name") or "").strip()
            if current_screen_name_l and screen_name.lower() == current_screen_name_l:
                continue
            if current_name_l and name.lower() == current_name_l:
                continue

            key = screen_name.lower() or str(gid)
            haystack = " ".join(
                part
                for part in [
                    name,
                    screen_name,
                    str(item.get("activity") or ""),
                    str(item.get("description") or ""),
                ]
                if part
            ).lower()

            entry = candidates.get(key)
            if entry is None:
                entry = {
                    "group_id": gid,
                    "name": name,
                    "screen_name": screen_name or None,
                    "members_count": item.get("members_count"),
                    "activity": item.get("activity"),
                    "_search_text": haystack,
                    "matched_by": [],
                    "_query_quality": 0.0,
                    "_matched_terms": set(),
                }
                candidates[key] = entry

            if query not in entry["matched_by"]:
                entry["matched_by"].append(query)
            entry["_query_quality"] = max(entry["_query_quality"], _query_quality(query, source_terms))
            entry["_matched_terms"].update(matched_terms)

        for item in search_public_groups(query, limit=8):
            if current_screen_name_l and item.screen_name.lower() == current_screen_name_l:
                continue
            key = item.screen_name.lower()
            if key not in candidates:
                candidates[key] = {
                    "group_id": abs(hash(item.screen_name)) % 1_000_000_000 + 1_000_000_000,
                    "name": item.name,
                    "screen_name": item.screen_name,
                    "members_count": None,
                    "activity": None,
                    "_search_text": f"{item.name} {item.screen_name}".lower(),
                    "matched_by": [],
                    "_query_quality": 0.0,
                    "_matched_terms": set(),
                }
            if query not in candidates[key]["matched_by"]:
                candidates[key]["matched_by"].append(query)
            candidates[key]["_query_quality"] = max(
                float(candidates[key].get("_query_quality") or 0.0),
                _query_quality(query, source_terms),
            )
            candidates[key]["_matched_terms"].update(matched_terms)

    if not candidates:
        return []

    source_activity_tokens = {
        token for token in _tokenize_loose(current_activity or "") if _is_query_word(token)
    }

    preliminary: list[dict] = []
    for candidate in candidates.values():
        candidate_tokens = {
            token
            for token in _tokenize_loose(candidate.get("_search_text") or "")
            if _is_query_word(token)
        }
        metadata_overlap = _match_terms(source_terms, candidate_tokens)
        query_overlap = set(candidate.get("_matched_terms") or set())
        overlap = metadata_overlap | query_overlap
        domain_overlap = _match_terms(domain_terms, candidate_tokens) if domain_terms else set()

        if not overlap:
            continue

        if anchor_terms_set:
            strong_overlap = (anchor_terms_set & metadata_overlap) | (anchor_terms_set & query_overlap)
            if not strong_overlap and len(overlap) < 2:
                continue

        query_signal = float(candidate.get("_query_quality") or 0.0)
        overlap_ratio = len(metadata_overlap) / max(1, len(source_terms))
        domain_ratio = len(domain_overlap) / max(1, len(domain_terms)) if domain_terms else 0.0
        member_signal = (
            min(1.0, (int(candidate.get("members_count") or 0) / 2_000_000))
            if candidate.get("members_count")
            else 0.1
        )
        candidate_activity_tokens = {
            token
            for token in _tokenize_loose(str(candidate.get("activity") or ""))
            if _is_query_word(token)
        }
        activity_overlap = len(source_activity_tokens & candidate_activity_tokens)

        score = 0.14 + overlap_ratio * 0.48 + domain_ratio * 0.2 + query_signal * 0.2 + member_signal * 0.08
        if source_activity_tokens and candidate_activity_tokens:
            if activity_overlap == 0:
                score *= 0.84
            else:
                score += min(0.08, activity_overlap * 0.03)
        if domain_terms and not domain_overlap:
            score *= 0.72
        score = max(0.05, min(0.9, round(score, 3)))

        candidate["_metadata_overlap"] = sorted(metadata_overlap)
        candidate["_overlap_terms"] = sorted(overlap)
        candidate["_domain_overlap"] = sorted(domain_overlap)
        candidate["_score"] = score
        preliminary.append(candidate)

    preliminary.sort(
        key=lambda item: (
            float(item.get("_score") or 0.0),
            len(item.get("matched_by") or []),
            int(item.get("members_count") or 0),
        ),
        reverse=True,
    )

    cluster_labels = topic_labels or [
        str(cluster.get("label") or "").strip()
        for cluster in topic_clusters[:5]
        if str(cluster.get("label") or "").strip()
    ]

    validated: list[dict] = []
    for index, item in enumerate(preliminary[:12]):
        final_score = float(item.get("_score") or 0.0)
        metadata_overlap = set(item.get("_metadata_overlap") or [])
        overlap_terms = set(item.get("_overlap_terms") or [])

        content_overlap: set[str] = set()
        screen_name = str(item.get("screen_name") or "").strip()
        if screen_name and index < 8:
            try:
                public_data = fetch_public_group_data(screen_name, limit=8)
                candidate_posts = [{"text": post.text} for post in public_data.posts if (post.text or "").strip()]
                if candidate_posts:
                    candidate_terms = set(_extract_source_tags(candidate_posts, limit=28))
                    content_overlap = _match_terms(source_terms, candidate_terms)
                    if content_overlap:
                        overlap_terms |= content_overlap
                        content_ratio = len(content_overlap) / max(1, len(source_terms))
                        final_score = min(0.94, round(final_score * 0.7 + content_ratio * 0.3 + 0.05, 3))
                    elif metadata_overlap:
                        final_score = round(final_score * 0.9, 3)
                    else:
                        final_score = round(final_score * 0.6, 3)
            except Exception:
                if not metadata_overlap:
                    # Without metadata/content overlap it is too risky to keep candidate.
                    continue

        if not metadata_overlap and not content_overlap:
            continue
        if final_score < 0.24:
            continue

        shared_topics: list[str] = []
        for cluster in topic_clusters:
            cluster_terms = {
                str(term).strip().lower()
                for term in cluster.get("terms", [])
                if _is_query_term(str(term))
            }
            if cluster_terms and (cluster_terms & overlap_terms):
                label = str(cluster.get("label") or "").strip()
                if label and label not in shared_topics:
                    shared_topics.append(label)
        if not shared_topics:
            shared_topics = cluster_labels[:2]

        matched_by = [query for query in (item.get("matched_by") or []) if _is_query_term(query)][:10]
        if not matched_by:
            continue

        why_similar = (
            f"\u041d\u0430\u0439\u0434\u0435\u043d \u043f\u043e \u043f\u0435\u0440\u0435\u0441\u0435\u0447\u0435\u043d\u0438\u044e \u0437\u0430\u043f\u0440\u043e\u0441\u043e\u0432: {', ' .join(matched_by[:4])}. "
            f"\u0421\u043e\u0432\u043f\u0430\u0432\u0448\u0438\u0435 \u0442\u0435\u0433\u0438: {', ' .join(sorted(overlap_terms)[:6])}."
        )

        validated.append(
            {
                "group_id": int(item.get("group_id") or 0),
                "name": str(item.get("name") or ""),
                "screen_name": item.get("screen_name"),
                "members_count": item.get("members_count"),
                "activity": item.get("activity"),
                "matched_by": matched_by,
                "shared_topics": shared_topics[:3],
                "why_similar": why_similar,
                "similarity_score": round(final_score, 3),
            }
        )

    if not validated:
        fallback_queries = queries[:6]
        for fallback_query in fallback_queries:
            for item in search_public_groups(fallback_query, limit=max(4, limit)):
                screen_name = (item.screen_name or "").strip().lower()
                if not screen_name:
                    continue
                if current_screen_name_l and screen_name == current_screen_name_l:
                    continue
                name_tokens = {token for token in _tokenize_loose(item.name) if _is_query_word(token)}
                if domain_terms and not _match_terms(domain_terms, name_tokens):
                    continue
                validated.append(
                    {
                        "group_id": abs(hash(item.screen_name)) % 1_000_000_000 + 1_000_000_000,
                        "name": item.name,
                        "screen_name": item.screen_name,
                        "members_count": None,
                        "activity": None,
                        "matched_by": [fallback_query],
                        "shared_topics": cluster_labels[:2],
                        "why_similar": f"Найден через публичный VK search по тегу: {fallback_query}.",
                        "similarity_score": 0.22,
                    }
                )
                if len(validated) >= limit * 2:
                    break
            if len(validated) >= limit * 2:
                break

    if not validated and not use_ai_tags_only:
        source_name_query = " ".join((current_name or "").split())
        for item in search_public_groups(source_name_query, limit=max(3, limit * 2)):
            screen_name = (item.screen_name or "").strip().lower()
            if not screen_name:
                continue
            if current_screen_name_l and screen_name == current_screen_name_l:
                continue
            name_tokens = {token for token in _tokenize_loose(item.name) if _is_query_word(token)}
            if anchor_terms_set and not (anchor_terms_set & name_tokens):
                continue
            validated.append(
                {
                    "group_id": abs(hash(item.screen_name)) % 1_000_000_000 + 1_000_000_000,
                    "name": item.name,
                    "screen_name": item.screen_name,
                    "members_count": None,
                    "activity": None,
                    "matched_by": [source_name_query],
                    "shared_topics": cluster_labels[:2],
                    "why_similar": f"Найден через публичный VK search по названию: {source_name_query}.",
                    "similarity_score": 0.24,
                }
            )

    validated.sort(
        key=lambda item: (
            float(item.get("similarity_score") or 0.0),
            len(item.get("matched_by") or []),
            int(item.get("members_count") or 0),
        ),
        reverse=True,
    )

    result: list[dict] = []
    seen_names: set[tuple[str, str]] = set()
    for item in validated:
        name_key = (
            str(item.get("name") or "").strip().lower(),
            str(item.get("screen_name") or "").strip().lower(),
        )
        if name_key in seen_names:
            continue
        seen_names.add(name_key)
        result.append(item)
        if len(result) >= limit:
            break
    return result


def _build_competitor_queries(
    *,
    source_terms: set[str],
    source_tags: list[str],
    meta_tags: list[str],
    ai_tags: list[str],
    current_name: str,
    allow_name_fallback: bool = True,
) -> list[str]:
    queries: list[str] = []

    for term in ai_tags[:10]:
        normalized = _normalize_query_for_search(term)
        if normalized:
            queries.append(normalized)

    for term in source_tags[:10]:
        normalized = _normalize_query_for_search(term)
        if normalized:
            queries.append(normalized)

    for term in meta_tags[:8]:
        normalized = _normalize_query_for_search(term)
        if normalized:
            queries.append(normalized)

    ranked = sorted(
        [term for term in source_terms if " " not in term],
        key=lambda value: (_term_specificity(value), len(value)),
        reverse=True,
    )
    pair_added = 0
    for idx in range(min(8, max(0, len(ranked) - 1))):
        left = ranked[idx]
        right = ranked[idx + 1]
        if left == right:
            continue
        query = f"{left} {right}"
        if _is_query_term(query):
            queries.append(query)
            pair_added += 1
        if pair_added >= 5:
            break

    name_tokens = [token for token in _tokenize_loose(current_name) if _is_query_word(token)]
    if allow_name_fallback and len(name_tokens) >= 1:
        queries.append(" ".join(name_tokens[:2]))

    deduped: list[str] = []
    seen: set[str] = set()
    for query in queries:
        normalized = " ".join(query.split()).strip().lower()
        if not normalized or normalized in seen:
            continue
        if not _is_query_term(normalized) or not _is_specific_term(normalized):
            continue
        seen.add(normalized)
        deduped.append(normalized)
        if len(deduped) >= 22:
            break
    if not deduped and allow_name_fallback and name_tokens:
        fallback = name_tokens[0]
        if _is_query_term(fallback):
            deduped.append(fallback)
    return deduped


def _normalize_query_for_search(value: str) -> str:
    normalized_value = str(value or "").replace("_", " ").replace("-", " ")
    tokens = [token for token in _tokenize_loose(normalized_value) if _is_query_word(token)]
    if not tokens:
        return ""
    return " ".join(tokens[:3]).strip()


def _normalize_terms(
    values: list[str] | tuple[str, ...],
    *,
    banned_terms: set[str] | None = None,
    limit: int = 16,
) -> list[str]:
    banned_terms = banned_terms or set()
    terms: list[str] = []
    seen: set[str] = set()
    for raw in values:
        normalized = _normalize_query_for_search(str(raw or "").strip().lower())
        if not normalized:
            continue
        if normalized in seen:
            continue
        if not _is_query_term(normalized):
            continue
        if not _is_specific_term(normalized, banned_terms=banned_terms):
            continue
        seen.add(normalized)
        terms.append(normalized)
        if len(terms) >= limit:
            break
    return terms


def _filter_tags_by_group_context(
    tags: list[str] | tuple[str, ...],
    *,
    group_name: str,
    group_description: str | None,
    group_activity: str | None,
    limit: int = 16,
) -> list[str]:
    banned_name_terms = _brand_terms(group_name or "")
    context_terms = {
        token
        for token in _tokenize_loose(" ".join([group_name or "", group_activity or "", group_description or ""]))
        if _is_query_word(token) and token not in banned_name_terms
    }
    normalized = _normalize_terms(list(tags or []), banned_terms=banned_name_terms, limit=limit * 2)
    filtered = [tag for tag in normalized if _term_supported_by_context(tag, context_terms)]
    return filtered[:limit]


def _term_supported_by_context(term: str, context_terms: set[str]) -> bool:
    words = [token for token in _tokenize_loose(term) if _is_query_word(token)]
    if not words:
        return False
    if not context_terms:
        return True
    if any(word in context_terms for word in words):
        return True
    return any(any(ch.isdigit() for ch in word) for word in words)


def _match_terms(source_terms: set[str], candidate_tokens: set[str]) -> set[str]:
    if not source_terms or not candidate_tokens:
        return set()
    candidate_words = {token for token in candidate_tokens if _is_query_word(token)}
    if not candidate_words:
        return set()
    matched: set[str] = set()
    for source in source_terms:
        source_words = [token for token in _tokenize_loose(source) if _is_query_word(token)]
        if not source_words:
            continue
        if all(any(_tokens_similar(word, candidate) for candidate in candidate_words) for word in source_words):
            matched.add(source)
            continue
        if any(any(_tokens_similar(word, candidate) for candidate in candidate_words) for word in source_words):
            matched.add(source)
    return matched


def _tokens_similar(left: str, right: str) -> bool:
    if left == right:
        return True
    if min(len(left), len(right)) < 4:
        return False
    return left.startswith(right) or right.startswith(left)
def _extract_cluster_terms(topic_clusters: list[dict]) -> set[str]:
    terms: set[str] = set()
    for cluster in topic_clusters:
        for term in cluster.get("terms", []) or []:
            normalized = str(term).strip().lower()
            if not normalized or not _is_query_term(normalized):
                continue
            terms.add(normalized)
            parts = [part for part in normalized.split() if _is_query_word(part)]
            terms.update(parts)
    return terms


def _extract_source_tags(posts: list[dict], limit: int = 10, banned_terms: set[str] | None = None) -> list[str]:
    banned_terms = banned_terms or set()
    token_tf: Counter[str] = Counter()
    token_df: Counter[str] = Counter()
    phrase_tf: Counter[str] = Counter()
    phrase_df: Counter[str] = Counter()

    for post in posts:
        text = str(post.get("text") or "")
        tokens = [token for token in _tokenize_loose(text) if len(token) >= 4]
        tokens = [token.lower() for token in tokens if _is_query_word(token) and token.lower() not in banned_terms]
        if not tokens:
            continue

        uniq_tokens = set(tokens)
        for token in tokens:
            token_tf[token] += 1
        for token in uniq_tokens:
            token_df[token] += 1

        uniq_phrases: set[str] = set()
        for idx in range(len(tokens) - 1):
            phrase = f"{tokens[idx]} {tokens[idx + 1]}"
            if _is_query_term(phrase):
                phrase_tf[phrase] += 1
                uniq_phrases.add(phrase)
        for phrase in uniq_phrases:
            phrase_df[phrase] += 1

    total_docs = max(1, len(posts))

    scored: list[tuple[str, float]] = []
    for token, tf in token_tf.items():
        df = token_df.get(token, 1)
        if total_docs >= 6 and df < 2:
            continue
        score = tf * (1.0 + (1.0 / max(1, df)))
        scored.append((token, score))

    for phrase, tf in phrase_tf.items():
        df = phrase_df.get(phrase, 1)
        if total_docs >= 6 and df < 2:
            continue
        score = tf * 1.25
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


def _brand_terms(*values: str) -> set[str]:
    terms: set[str] = set()
    for value in values:
        for token in _tokenize_loose(value):
            if len(token) >= 4:
                terms.add(token)
    return terms


def _extract_meta_tags(activity: str, description: str, name: str, limit: int = 8) -> list[str]:
    brand = _brand_terms(name)
    text = description or ""
    tokens = [token for token in _tokenize_loose(text) if _is_query_word(token) and token not in brand]

    counter: Counter[str] = Counter(tokens)
    description_tokens = {
        token
        for token in _tokenize_loose(description or "")
        if _is_query_word(token) and token not in brand
    }
    for token in _tokenize_loose(activity):
        if _is_query_word(token) and token not in brand and token in description_tokens:
            counter[token] += 2

    # Useful phrases from description (e.g. "новый альбом", "авто новости").
    seq = [token for token in _tokenize_loose(description or "") if _is_query_word(token) and token not in brand]
    for idx in range(len(seq) - 1):
        phrase = f"{seq[idx]} {seq[idx + 1]}"
        if _is_query_term(phrase):
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


def _extract_ai_search_tags(ai: VKGroupAIInsights, limit: int = 14) -> list[str]:
    explicit_tags = [str(tag).strip().lower() for tag in (ai.search_tags or []) if _is_query_term(str(tag))]
    if explicit_tags:
        deduped: list[str] = []
        seen: set[str] = set()
        for tag in explicit_tags:
            if tag in seen:
                continue
            seen.add(tag)
            deduped.append(tag)
            if len(deduped) >= limit:
                break
        return deduped

    counters: Counter[str] = Counter()
    texts = list(ai.audience_interests or []) + list(ai.potential_competitors or []) + [ai.summary or ""]
    for text in texts:
        tokens = [token for token in _tokenize_loose(str(text or "").lower()) if _is_query_word(token)]
        for token in tokens:
            counters[token] += 1
        for idx in range(len(tokens) - 1):
            phrase = f"{tokens[idx]} {tokens[idx + 1]}"
            if _is_query_term(phrase):
                counters[phrase] += 2

    tags: list[str] = []
    for term, _ in counters.most_common(limit * 3):
        if term in tags:
            continue
        if any(term in existing or existing in term for existing in tags):
            continue
        tags.append(term)
        if len(tags) >= limit:
            break
    return tags


def _extract_ai_topic_labels(ai: VKGroupAIInsights, limit: int = 4) -> list[str]:
    if ai.search_tags:
        labels = []
        for tag in ai.search_tags:
            label = " ".join(str(tag or "").split()).strip()
            if not label:
                continue
            if label not in labels:
                labels.append(label)
            if len(labels) >= limit:
                break
        if labels:
            return labels

    labels: list[str] = []
    for raw in list(ai.audience_interests or [])[:limit]:
        label = str(raw or "").strip()
        if not label:
            continue
        if ":" in label:
            label = label.split(":", 1)[0].strip()
        label = " ".join(label.split())
        if len(label) > 56:
            label = label[:56].rstrip(" ,.;:")
        if label and label not in labels:
            labels.append(label)
    return labels


def _query_quality(query: str, source_terms: set[str]) -> float:
    words = [word for word in _tokenize_loose(query) if _is_query_word(word)]
    if not words:
        return 0.0
    overlap = len(set(words) & source_terms)
    return min(1.0, overlap / max(1, len(set(words))))


def _is_query_term(text: str) -> bool:
    words = [word.strip().lower() for word in _tokenize_loose(str(text or "")) if word.strip()]
    if not words:
        return False
    meaningful = [word for word in words if _is_query_word(word)]
    if not meaningful:
        return False
    if len(words) >= 2 and len(meaningful) < 2:
        if len(meaningful) == 1:
            token = meaningful[0]
            if any(ch.isdigit() for ch in token):
                return True
            return len(token) >= 5
        return False
    return True


def _is_query_word(word: str) -> bool:
    value = str(word or "").strip().lower()
    if len(value) < 4:
        if len(value) < 2:
            return False
        # Allow short technical acronyms (e.g., erp/crm/seo) and mixed alpha-numeric terms.
        if not (
            value.isalpha()
            or (any(ch.isalpha() for ch in value) and any(ch.isdigit() for ch in value))
        ):
            return False
    if value in _WEAK_QUERY_WORDS:
        return False
    if value in STOPWORDS:
        return False
    if any(stem in value for stem in _MONTH_QUERY_STEMS):
        return False
    if _looks_like_verb(value):
        return False
    if _looks_like_noise_slug(value):
        return False
    return any(ch.isalpha() for ch in value)


def _is_specific_term(term: str, banned_terms: set[str] | None = None) -> bool:
    banned_terms = banned_terms or set()
    tokens = [token for token in _tokenize_loose(term) if _is_query_word(token)]
    if not tokens:
        return False
    if all(token in banned_terms for token in tokens):
        return False
    strong_tokens = [token for token in tokens if (len(token) >= 5 or any(ch.isdigit() for ch in token))]
    return bool(strong_tokens)


def _term_specificity(term: str) -> float:
    tokens = [token for token in _tokenize_loose(term) if _is_query_word(token)]
    if not tokens:
        return 0.0
    score = 0.0
    for token in tokens:
        if any(ch.isdigit() for ch in token):
            score += 1.2
        elif len(token) >= 8:
            score += 1.15
        elif len(token) >= 6:
            score += 1.0
        else:
            score += 0.8
    if len(tokens) >= 2:
        score += 0.2
    return round(score, 3)


def _looks_like_noise_slug(word: str) -> bool:
    value = word.lower()
    if not value.isascii() or len(value) < 6:
        return False
    suffixes = ("news", "video", "videos", "media", "music", "blog")
    return any(value.endswith(suffix) and value != suffix for suffix in suffixes)


def _tokenize_loose(text: str) -> list[str]:
    text = str(text or "").lower()
    tokens: list[str] = []
    buf: list[str] = []
    for ch in text:
        if ch.isalnum():
            buf.append(ch)
        else:
            if buf:
                token = "".join(buf)
                if len(token) >= 2:
                    tokens.append(token)
                buf = []
    if buf:
        token = "".join(buf)
        if len(token) >= 2:
            tokens.append(token)
    return tokens


def _looks_like_verb(token: str) -> bool:
    value = token.lower()
    verb_suffixes = (
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
        "\u0430\u0439\u0442\u0435",
        "\u044f\u0439\u0442\u0435",
        "\u0438\u0442\u0435",
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
    return any(value.endswith(suffix) for suffix in verb_suffixes)


def _is_group_auth_restriction(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "method is unavailable with group auth" in message
        or "group authorization failed" in message
    )


def _build_audience_profile(ai: VKGroupAIInsights, metrics: VKGroupMetricsResponse) -> dict:
    content_preferences = []
    if ai.search_tags:
        content_preferences.append(f"Лучше всего заходят темы: {', '.join(ai.search_tags[:4])}")
    if metrics.average_views >= 300:
        content_preferences.append("Контент продолжает получать заметный охват даже в публичном режиме")
    if metrics.average_comments >= 10:
        content_preferences.append("Посты с прямыми вопросами дают более сильную активность в комментариях")
    if not content_preferences:
        content_preferences.append("Нужно больше данных, чтобы уверенно определить предпочитаемые форматы контента")

    engagement_style = []
    if metrics.average_comments >= 10:
        engagement_style.append("Аудитория активно обсуждает и спорит в комментариях")
    if metrics.average_likes >= 50:
        engagement_style.append("Реакции стабильны, особенно на новостном и событийном контенте")
    if metrics.posts_per_day >= 2:
        engagement_style.append("Лента потребляется быстро; аудитория привыкла к плотному ритму публикаций")
    if not engagement_style:
        engagement_style.append("Вовлеченность видна частично, потому что публичный доступ ограничивает часть метрик")

    return {
        "interests": ai.audience_interests,
        "age_segments": ai.audience_age,
        "activity_profile": ai.audience_activity,
        "content_preferences": content_preferences[:3],
        "engagement_style": engagement_style[:3],
        "summary": ai.summary,
    }

def _render_group_report_png(report: VKGroupAnalyzeResponse) -> bytes:
    if plt is None:
        raise RuntimeError("matplotlib is not installed")

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.patch.set_facecolor("white")
    fig.suptitle(f"VK Analytics Report: {report.source.name}", fontsize=16, fontweight="bold")

    metric_names = ["Views", "Likes", "Comments", "Reposts"]
    metric_values = [
        report.metrics.average_views,
        report.metrics.average_likes,
        report.metrics.average_comments,
        report.metrics.average_reposts,
    ]
    ax = axes[0][0]
    bars = ax.bar(metric_names, metric_values, color=["#3b82f6", "#22c55e", "#f59e0b", "#ef4444"])
    ax.set_title("Average Post Metrics")
    ax.set_ylabel("Count")
    ax.grid(axis="y", alpha=0.25)
    for bar, value in zip(bars, metric_values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + max(metric_values + [1]) * 0.02, str(value), ha="center", va="bottom", fontsize=9)

    ax = axes[0][1]
    tag_labels = [tag[:26] for tag in report.ai.search_tags[:5]]
    tag_sizes = list(range(len(tag_labels), 0, -1))
    if tag_labels:
        ax.barh(tag_labels, tag_sizes, color="#8b5cf6")
        ax.invert_yaxis()
    ax.set_title("Top Search Tags")
    ax.set_xlabel("Relative priority")
    ax.grid(axis="x", alpha=0.25)

    ax = axes[1][0]
    competitor_labels = [item.name[:24] for item in report.competitors_found[:5]]
    competitor_scores = [item.similarity_score for item in report.competitors_found[:5]]
    if competitor_labels:
        ax.bar(competitor_labels, competitor_scores, color="#14b8a6")
        ax.set_ylim(0, 1)
        ax.tick_params(axis="x", rotation=20)
    ax.set_title("Competitor Similarity")
    ax.set_ylabel("Score")
    ax.grid(axis="y", alpha=0.25)

    ax = axes[1][1]
    ax.axis("off")
    summary_lines = [
        f"Source: {report.source.screen_name or report.source.name}",
        f"Posts analyzed: {report.metrics.total_posts_analyzed}",
        f"Posts/day: {report.metrics.posts_per_day}",
        f"Top interest: {report.audience_profile.interests[0] if report.audience_profile.interests else 'n/a'}",
        f"Audience age: {', '.join(report.audience_profile.age_segments[:2]) or 'n/a'}",
        f"AI status: {report.ai_status.message[:120]}",
    ]
    ax.text(
        0.0,
        1.0,
        "\n".join(summary_lines),
        va="top",
        ha="left",
        fontsize=10,
        wrap=True,
        family="DejaVu Sans",
    )
    ax.set_title("Summary")

    plt.tight_layout(rect=(0, 0, 1, 0.96))
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buffer.seek(0)
    return buffer.getvalue()


