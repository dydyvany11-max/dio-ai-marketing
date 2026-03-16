import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from src.api.services.trends_db import upsert_term_counts, save_trends


EN_STOP = {
    "the","and","for","with","that","this","from","are","was","were","has","have","had","but","not","you",
    "your","about","into","over","after","before","their","they","them","his","her","she","him","its","our","out",
    "who","what","when","where","why","how","can","could","should","would","will","just","than","then","been",
}

RU_STOP = {
    "и","в","во","не","что","он","на","я","с","со","как","а","то","все","она","так","его","но","да",
    "ты","к","у","же","вы","за","бы","по","ее","мне","было","вот","от","меня","еще","нет","о","из",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _bucket_start(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    text = text.lower()
    text = re.sub(r"[^a-z0-9а-яё]+", " ", text)
    tokens = [t for t in text.split() if len(t) >= 3]
    return [t for t in tokens if t not in EN_STOP and t not in RU_STOP]


def update_term_counts(db_path: str, articles: list[dict]) -> None:
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for art in articles:
        content = (art.get("title") or "") + " " + (art.get("content") or "")
        tokens = _tokenize(content)
        if not tokens:
            continue
        published = art.get("published_at")
        try:
            dt = datetime.fromisoformat(published) if published else _utc_now()
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            dt = _utc_now()
        bucket = _bucket_start(dt).isoformat()
        for term, count in Counter(tokens).items():
            buckets[bucket][term] += count
    if buckets:
        upsert_term_counts(db_path, buckets)




def quick_trends_from_articles(articles: list[dict], max_terms: int = 50) -> list[dict]:
    all_tokens = []
    for art in articles:
        content = (art.get("title") or "") + " " + (art.get("content") or "")
        all_tokens.extend(_tokenize(content))
    counts = Counter(all_tokens)
    updated_at = _utc_now().isoformat()
    trends = []
    for term, count_now in counts.most_common(max_terms):
        score = math.log(count_now + 1)
        trends.append(
            {
                "term": term,
                "window_start": updated_at,
                "window_end": updated_at,
                "count_now": int(count_now),
                "count_prev": 0,
                "growth": 1.0,
                "score": float(score),
                "updated_at": updated_at,
            }
        )
    return trends
def compute_trends(db_path: str, window_hours: int = 6, max_terms: int = 50) -> list[dict]:
    now = _utc_now()
    end_now = _bucket_start(now)
    start_now = end_now - timedelta(hours=window_hours)
    start_prev = start_now - timedelta(hours=window_hours)

    import sqlite3
    from src.api.services.trends_db import init_db

    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT term, bucket_start, count
            FROM term_counts
            WHERE bucket_start >= ? AND bucket_start < ?
            """,
            (start_prev.isoformat(), end_now.isoformat()),
        )
        rows = cur.fetchall()

    now_counts: Counter[str] = Counter()
    prev_counts: Counter[str] = Counter()
    for term, bucket_start, count in rows:
        if start_now.isoformat() <= bucket_start < end_now.isoformat():
            now_counts[term] += int(count)
        else:
            prev_counts[term] += int(count)

    trends: list[dict] = []

    if not now_counts:
        # fallback: use recent terms if window is empty
        fallback = Counter()
        for term, count in prev_counts.items():
            fallback[term] += int(count)
        if fallback:
            trends = []
            updated_at = _utc_now().isoformat()
            for term, count_now in fallback.most_common(max_terms):
                count_prev = 0
                growth = 1.0
                score = math.log(count_now + 1)
                trends.append(
                    {
                        "term": term,
                        "window_start": start_now.isoformat(),
                        "window_end": end_now.isoformat(),
                        "count_now": int(count_now),
                        "count_prev": int(count_prev),
                        "growth": float(growth),
                        "score": float(score),
                        "updated_at": updated_at,
                    }
                )
            save_trends(db_path, trends)
            return trends
    updated_at = _utc_now().isoformat()
    for term, count_now in now_counts.items():
        count_prev = prev_counts.get(term, 0)
        growth = (count_now + 1) / (count_prev + 1)
        score = growth * math.log(count_now + 1)
        trends.append(
            {
                "term": term,
                "window_start": start_now.isoformat(),
                "window_end": end_now.isoformat(),
                "count_now": int(count_now),
                "count_prev": int(count_prev),
                "growth": float(growth),
                "score": float(score),
                "updated_at": updated_at,
            }
        )

    trends.sort(key=lambda x: x["score"], reverse=True)
    trends = trends[:max_terms]
    save_trends(db_path, trends)
    return trends
