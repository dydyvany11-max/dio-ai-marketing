import math
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from src.api.config import _load_project_env
from src.api.services.trends_db import upsert_term_counts, save_trends

# Ensure .env is loaded for limits/flags
_load_project_env()

try:
    from stopwordsiso import stopwords
    _STOPWORDS = set(stopwords("ru")) | set(stopwords("en"))
except Exception:
    _STOPWORDS = set()

_BLOCKLIST = {
    "privacy","policy","cookie","cookies","consent","manage","preferences","preference","advertisement","advertisements",
    "subscribe","subscription","signin","sign","login","account","terms","service","services","newsletter","newsletters",
    "read","more","minute","minutes","min","updated","update","breaking","site","sites","share","sharing","amp",
    "приватность","куки","политика","подписка","подписаться",
    "реклама","рекламный","войти","вход",
    "регистрация","аккаунт","сервис","услуги","читать","далее","обновлено","сайт","поделиться",
}

try:
    from razdel import tokenize as ru_tokenize
except Exception:
    ru_tokenize = None

try:
    from deep_translator import GoogleTranslator
except Exception:
    GoogleTranslator = None

_TRANSLATE_CACHE: dict[str, str] = {}

MAX_TOKENS_PER_DOC = int(os.getenv("TRENDS_MAX_TOKENS_PER_DOC", "400"))
MAX_EN_TOKENS_PER_DOC = int(os.getenv("TRENDS_MAX_EN_TOKENS_PER_DOC", "50"))
TRANSLATE_EN_TO_RU = os.getenv("TRENDS_TRANSLATE_EN", "true").strip().lower() in {"1", "true", "yes", "on"}

_CYRILLIC_RE = re.compile(r"[а-яё]+", re.IGNORECASE)


def get_stopwords() -> set[str]:
    return _STOPWORDS | _BLOCKLIST


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _bucket_start(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def _translate_to_ru(tokens: list[str]) -> list[str]:
    if not tokens:
        return []
    if not TRANSLATE_EN_TO_RU:
        return []
    if GoogleTranslator is None:
        return []  # no translator -> drop english to keep RU-only output
    translator = GoogleTranslator(source="auto", target="ru")
    out = []
    for t in tokens:
        if t in _TRANSLATE_CACHE:
            out.append(_TRANSLATE_CACHE[t])
            continue
        try:
            translated = translator.translate(t) or ""
        except Exception:
            translated = ""
        translated = translated.strip().lower()
        if translated:
            _TRANSLATE_CACHE[t] = translated
            out.append(translated)
    return out


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    text = text.lower()
    stop = get_stopwords()

    if ru_tokenize is not None:
        ru_tokens = [t.text for t in ru_tokenize(text)]
    else:
        ru_tokens = _CYRILLIC_RE.findall(text)

    en_tokens = re.findall(r"[a-z]{3,}", text)
    if MAX_EN_TOKENS_PER_DOC > 0 and len(en_tokens) > MAX_EN_TOKENS_PER_DOC:
        en_tokens = en_tokens[:MAX_EN_TOKENS_PER_DOC]
    en_tokens = _translate_to_ru(en_tokens)

    tokens = ru_tokens + en_tokens
    if MAX_TOKENS_PER_DOC > 0 and len(tokens) > MAX_TOKENS_PER_DOC:
        tokens = tokens[:MAX_TOKENS_PER_DOC]

    cleaned: list[str] = []
    for t in tokens:
        if len(t) < 3:
            continue
        if not _CYRILLIC_RE.fullmatch(t):
            continue
        if t in stop:
            continue
        cleaned.append(t)
    return cleaned


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
