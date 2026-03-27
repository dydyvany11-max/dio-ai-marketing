import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
import feedparser

try:
    import trafilatura
    import trafilatura.extract
except Exception:
    trafilatura = None

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

from src.api.services.trends_db import Article


@dataclass
class Source:
    id: int
    name: str
    url: str
    type: str
    meta_json: str | None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_newsapi(api_key: str, sources: list[str], page_size: int = 50) -> list[Article]:
    if not api_key or not sources:
        return []
    url = "https://newsapi.org/v2/top-headlines"
    params = {
        "sources": ",".join(sources),
        "pageSize": page_size,
        "apiKey": api_key,
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    articles: list[Article] = []
    for item in data.get("articles", []):
        articles.append(
            Article(
                source_id=None,
                source=item.get("source", {}).get("name") or "newsapi",
                url=item.get("url") or "",
                title=item.get("title") or "",
                content=(item.get("description") or "") + " " + (item.get("content") or ""),
                published_at=item.get("publishedAt"),
                fetched_at=_utc_now(),
            )
        )
    return [a for a in articles if a.url]


def _fetch_gdelt(query: str, maxrecords: int = 50) -> list[Article]:
    if not query:
        return []
    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": maxrecords,
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    articles: list[Article] = []
    for item in data.get("articles", []):
        articles.append(
            Article(
                source_id=None,
                source=item.get("sourcecountry") or "gdelt",
                url=item.get("url") or "",
                title=item.get("title") or "",
                content=item.get("seendate") or "",
                published_at=item.get("seendate"),
                fetched_at=_utc_now(),
            )
        )
    return [a for a in articles if a.url]


def _fetch_page_html(url: str, timeout_sec: int = 12) -> str:
    try:
        response = requests.get(
            url,
            timeout=timeout_sec,
            headers={"User-Agent": "dio-ai-marketing/1.0 (+trend-collector)"},
        )
        response.raise_for_status()
        return response.text or ""
    except Exception:
        return ""


def _extract_readable(url: str, html: str) -> tuple[str, str]:
    if not html:
        return "", ""
    if trafilatura is None:
        return "", ""
    text = trafilatura.extract(html, url=url, include_links=False, include_formatting=False) or ""
    title = ""
    try:
        meta = trafilatura.extract_metadata(html, url=url)
        if meta and meta.title:
            title = meta.title
    except Exception:
        title = ""
    return title.strip(), text.strip()


def _extract_plain_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html or "", flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    title = re.sub(r"\s+", " ", unescape(match.group(1))).strip()
    return title


def _extract_plain_text(html: str, max_chars: int = 6000) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html or "")
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "..."
    return text


def _fetch_rss(source: Source, max_items: int = 50, timeout_sec: int = 12) -> list[Article]:
    try:
        response = requests.get(
            source.url,
            timeout=timeout_sec,
            headers={"User-Agent": "dio-ai-marketing/1.0 (+rss-collector)"},
        )
        response.raise_for_status()
        payload = response.content
    except Exception:
        return []

    feed = feedparser.parse(payload)
    articles: list[Article] = []
    for entry in feed.entries[:max_items]:
        title = entry.get("title") or ""
        link = entry.get("link") or ""
        published = entry.get("published") or entry.get("updated")
        summary = entry.get("summary") or ""
        articles.append(
            Article(
                source_id=source.id,
                source=source.name,
                url=link,
                title=title,
                content=summary,
                published_at=published,
                fetched_at=_utc_now(),
            )
        )
    return [a for a in articles if a.url]


def _extract_links_from_page(source: Source, html: str, max_links: int = 8) -> list[str]:
    if not html:
        return []
    links = []
    try:
        if trafilatura is not None:
            links = trafilatura.extract_links(html, url=source.url) or []
    except Exception:
        links = []
    if not links:
        links = re.findall(r'href=["\']([^"\']+)["\']', html or "", flags=re.IGNORECASE)

    base = urlparse(source.url).netloc
    cleaned = []
    for link in links:
        if not link or not isinstance(link, str):
            continue
        full = urljoin(source.url, link)
        if urlparse(full).netloc != base:
            continue
        if any(x in full for x in ["/privacy", "/cookie", "/consent", "/login", "/signin"]):
            continue
        cleaned.append(full.split("#")[0])

    # de-dup
    uniq = list(dict.fromkeys(cleaned))
    return uniq[:max_links]


def _fetch_html_articles(
    source: Source,
    *,
    max_links_default: int = 6,
    crawl_links: bool = True,
    timeout_sec: int = 12,
) -> list[Article]:
    html = _fetch_page_html(source.url, timeout_sec=timeout_sec)
    if not html:
        return []
    title, content = _extract_readable(source.url, html)
    if not content:
        content = _extract_plain_text(html, max_chars=7000)
    if not title:
        title = _extract_plain_title(html)

    # If this looks like a list page, try multiple links
    meta = {}
    if source.meta_json:
        try:
            meta = json.loads(source.meta_json)
        except Exception:
            meta = {}
    max_links = int(meta.get("max_links", max_links_default)) if isinstance(meta, dict) else max_links_default
    max_links = max(1, min(max_links, 20))

    links = _extract_links_from_page(source, html, max_links=max_links) if crawl_links else []
    articles: list[Article] = []

    if links:
        for link in links:
            try:
                resp = requests.get(
                    link,
                    timeout=timeout_sec,
                    headers={"User-Agent": "dio-ai-marketing/1.0 (+trend-collector)"},
                )
                resp.raise_for_status()
                page_html = resp.text
                atitle, acontent = _extract_readable(link, page_html)
                if not acontent:
                    acontent = _extract_plain_text(page_html, max_chars=5000)
                if not atitle:
                    atitle = _extract_plain_title(page_html)
                if not acontent:
                    continue
                if not atitle:
                    atitle = link
                articles.append(
                    Article(
                        source_id=source.id,
                        source=source.name,
                        url=link,
                        title=atitle,
                        content=acontent,
                        published_at=None,
                        fetched_at=_utc_now(),
                    )
                )
            except Exception:
                continue

    if not articles and content:
        if not title:
            lines = [l.strip() for l in content.split("\n") if l.strip()]
            title = lines[0][:200] if lines else source.name
        articles.append(
            Article(
                source_id=source.id,
                source=source.name,
                url=source.url,
                title=title,
                content=content,
                published_at=None,
                fetched_at=_utc_now(),
            )
        )

    return articles


def _fetch_html_articles_playwright(
    source: Source,
    *,
    max_items: int = 30,
    timeout_sec: int = 12,
) -> list[Article]:
    if sync_playwright is None:
        return []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(source.url, wait_until="domcontentloaded", timeout=timeout_sec * 1000)
            page.wait_for_timeout(1800)
            rows = page.evaluate(
                """
                (maxItems) => {
                  const badHref = (href) => /\\/privacy|\\/cookie|\\/consent|\\/login|\\/signin/i.test(href || "");
                  const clean = (v) => (v || "").replace(/\\s+/g, " ").trim();
                  const out = [];
                  const seen = new Set();
                  const anchors = Array.from(document.querySelectorAll('article a[href], h1 a[href], h2 a[href], h3 a[href], a[href]'));
                  for (const a of anchors) {
                    const title = clean(a.textContent || "");
                    if (!title || title.length < 20) continue;
                    const hrefRaw = a.getAttribute('href') || "";
                    let href = "";
                    try { href = new URL(hrefRaw, location.href).toString(); } catch (e) { continue; }
                    if (!href || badHref(href)) continue;
                    if (seen.has(href)) continue;
                    seen.add(href);
                    const parent = a.closest('article, li, div');
                    const context = clean(parent ? parent.textContent || "" : "");
                    out.push({ title: title.slice(0, 260), url: href, content: context.slice(0, 700) });
                    if (out.length >= maxItems) break;
                  }
                  if (!out.length) {
                    const titleTag = clean((document.querySelector('title') || {}).textContent || "");
                    const body = clean((document.querySelector('main') || document.body || {}).textContent || "");
                    if (titleTag || body) {
                      out.push({ title: titleTag || location.hostname, url: location.href, content: body.slice(0, 1200) });
                    }
                  }
                  return out;
                }
                """,
                max(5, min(max_items, 60)),
            )
            browser.close()
    except Exception:
        return []

    articles: list[Article] = []
    for row in rows or []:
        url = str((row or {}).get("url") or "").strip()
        title = str((row or {}).get("title") or "").strip()
        content = str((row or {}).get("content") or "").strip()
        if not url or not title:
            continue
        articles.append(
            Article(
                source_id=source.id,
                source=source.name,
                url=url,
                title=title,
                content=content or title,
                published_at=None,
                fetched_at=_utc_now(),
            )
        )
    return articles


def collect_from_sources(
    sources: list[Source],
    newsapi_key: str | None = None,
    newsapi_sources: list[str] | None = None,
    gdelt_query: str | None = None,
    rss_max_items: int = 40,
    html_max_links: int = 6,
    crawl_html_links: bool = True,
    timeout_sec: int = 12,
    use_playwright_html: bool = True,
    playwright_max_items: int = 30,
) -> list[Article]:
    articles: list[Article] = []

    if newsapi_key and newsapi_sources:
        try:
            articles.extend(_fetch_newsapi(newsapi_key, newsapi_sources))
        except Exception:
            pass

    if gdelt_query:
        try:
            articles.extend(_fetch_gdelt(gdelt_query))
        except Exception:
            pass

    for src in sources:
        if src.type == "html":
            try:
                html_articles: list[Article] = []
                if use_playwright_html:
                    html_articles = _fetch_html_articles_playwright(
                        src,
                        max_items=playwright_max_items,
                        timeout_sec=timeout_sec,
                    )
                if not html_articles:
                    html_articles = _fetch_html_articles(
                        src,
                        max_links_default=html_max_links,
                        crawl_links=crawl_html_links,
                        timeout_sec=timeout_sec,
                    )
                articles.extend(html_articles)
            except Exception:
                continue
        elif src.type == "rss":
            try:
                articles.extend(_fetch_rss(src, max_items=rss_max_items, timeout_sec=timeout_sec))
            except Exception:
                continue

    return articles


def parse_sources(rows: list[dict]) -> list[Source]:
    sources: list[Source] = []
    for row in rows:
        raw_type = str(row.get("type") or "").strip().lower()
        url = str(row.get("url") or "").strip()
        if raw_type in {"rss", "xml", "atom"}:
            source_type = "rss"
        elif raw_type in {"html", "news", "site", "website"}:
            source_type = "html"
        else:
            source_type = "rss" if ("rss" in url.lower() or url.lower().endswith(".xml")) else "html"
        sources.append(
            Source(
                id=int(row["id"]),
                name=row["name"],
                url=url,
                type=source_type,
                meta_json=row.get("meta_json"),
            )
        )
    return sources
