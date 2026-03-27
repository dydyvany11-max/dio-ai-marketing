from __future__ import annotations

import re
from collections import Counter
from typing import Any


def build_query_terms(company: str, aliases: list[str] | None = None) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for raw in [company, *(aliases or [])]:
        value = " ".join(str(raw or "").split()).strip()
        if len(value) < 2:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        terms.append(value)
    return terms


def analyze_mentions(
    *,
    articles: list[dict[str, Any]],
    company: str,
    aliases: list[str] | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    terms = build_query_terms(company, aliases)
    if not terms:
        return {
            "company": company,
            "query_terms": [],
            "scanned_articles": len(articles),
            "matched_articles": 0,
            "total_mentions": 0,
            "top_sources": [],
            "items": [],
        }

    compiled = []
    for term in terms:
        # Phrase-aware regex with light boundaries to avoid random substring matches.
        pattern = re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE | re.UNICODE)
        compiled.append((term, pattern))

    items: list[dict[str, Any]] = []
    source_counter: Counter[str] = Counter()
    total_mentions = 0

    for article in articles:
        title = str(article.get("title") or "").strip()
        content = str(article.get("content") or "").strip()
        text = f"{title}\n{content}".strip()
        if not text:
            continue

        matched_terms: list[str] = []
        mention_hits = 0
        first_match_start: int | None = None
        for term, pattern in compiled:
            matches = list(pattern.finditer(text))
            if not matches:
                continue
            matched_terms.append(term)
            mention_hits += len(matches)
            if first_match_start is None:
                first_match_start = matches[0].start()

        if mention_hits <= 0:
            continue

        total_mentions += mention_hits
        source = str(article.get("source") or "").strip() or "unknown"
        source_counter[source] += 1

        snippet = _build_snippet(text=text, anchor=first_match_start or 0, max_chars=260)
        items.append(
            {
                "source": source,
                "url": str(article.get("url") or "").strip(),
                "title": title or None,
                "published_at": article.get("published_at"),
                "matched_terms": matched_terms,
                "mentions_in_article": mention_hits,
                "snippet": snippet,
            }
        )

    matched_articles = len(items)
    items.sort(key=lambda x: (int(x.get("mentions_in_article") or 0), len(x.get("matched_terms") or [])), reverse=True)
    items = items[: max(1, int(limit))]

    top_sources = [
        {"source": source, "count": count}
        for source, count in source_counter.most_common(10)
    ]

    return {
        "company": company,
        "query_terms": terms,
        "scanned_articles": len(articles),
        "matched_articles": matched_articles,
        "total_mentions": total_mentions,
        "top_sources": top_sources,
        "items": items,
    }


def _build_snippet(*, text: str, anchor: int, max_chars: int) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if not clean:
        return ""
    max_chars = max(120, max_chars)
    if len(clean) <= max_chars:
        return clean

    anchor = max(0, min(anchor, len(clean) - 1))
    half = max_chars // 2
    start = max(0, anchor - half)
    end = min(len(clean), start + max_chars)
    start = max(0, end - max_chars)
    snippet = clean[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(clean):
        snippet = snippet + "..."
    return snippet
