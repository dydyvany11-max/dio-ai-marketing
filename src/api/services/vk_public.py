from __future__ import annotations

import os
import re
import subprocess
import sys
import random
from html import unescape
import json
import requests
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None


_SKIP_LINE_RE = re.compile(
    r"^(share|comment|comments|like|likes|repost|reposts|reply|replies|"
    r"j[' ]aime|partager|afficher|il y a|today at|yesterday at|"
    r"send reaction like|select reaction|leave like|leave a comment|"
    r"show more|show next comments|most interesting|verified|actions|report|"
    r"attach|photo|post|add emoji or sticker|следующий слайд|предыдущий слайд|листайте|свайп)$",
    re.IGNORECASE,
)

_CHALLENGE_TITLES = {
    "\u041f\u0440\u043e\u0432\u0435\u0440\u044f\u0435\u043c, \u0447\u0442\u043e \u0432\u044b \u043d\u0435 \u0440\u043e\u0431\u043e\u0442",
    "VK | VK",
}

_BAD_PAGE_TITLES = {
    "error",
    "ошибка",
    "vk",
    "доступ ограничен",
    "access denied",
}

_MONTHS = {
    "jan": 1, "january": 1, "\u044f\u043d\u0432": 1, "\u044f\u043d\u0432\u0430\u0440\u044f": 1,
    "feb": 2, "february": 2, "\u0444\u0435\u0432": 2, "\u0444\u0435\u0432\u0440\u0430\u043b\u044f": 2,
    "mar": 3, "march": 3, "\u043c\u0430\u0440": 3, "\u043c\u0430\u0440\u0442\u0430": 3,
    "apr": 4, "april": 4, "\u0430\u043f\u0440": 4, "\u0430\u043f\u0440\u0435\u043b\u044f": 4,
    "may": 5, "\u043c\u0430\u044f": 5,
    "jun": 6, "june": 6, "\u0438\u044e\u043d": 6, "\u0438\u044e\u043d\u044f": 6,
    "jul": 7, "july": 7, "\u0438\u044e\u043b": 7, "\u0438\u044e\u043b\u044f": 7,
    "aug": 8, "august": 8, "\u0430\u0432\u0433": 8, "\u0430\u0432\u0433\u0443\u0441\u0442\u0430": 8,
    "sep": 9, "september": 9, "\u0441\u0435\u043d": 9, "\u0441\u0435\u043d\u0442\u044f\u0431\u0440\u044f": 9,
    "oct": 10, "october": 10, "\u043e\u043a\u0442": 10, "\u043e\u043a\u0442\u044f\u0431\u0440\u044f": 10,
    "nov": 11, "november": 11, "\u043d\u043e\u044f": 11, "\u043d\u043e\u044f\u0431\u0440\u044f": 11,
    "dec": 12, "december": 12, "\u0434\u0435\u043a": 12, "\u0434\u0435\u043a\u0430\u0431\u0440\u044f": 12,
}

@dataclass(frozen=True)
class PublicVKPost:
    post_id: str
    text: str
    likes: int
    comments: int
    reposts: int
    views: int
    date_label: str
    timestamp: int


@dataclass(frozen=True)
class PublicVKGroupData:
    name: str
    screen_name: str
    posts: list[PublicVKPost]


@dataclass(frozen=True)
class PublicVKSearchResult:
    name: str
    screen_name: str

CHROME_VERSIONS: tuple[str, ...] = (
    "120.0.0.0",
    "119.0.0.0",
    "118.0.0.0",
    "117.0.0.0",
    "116.0.0.0",
    "115.0.0.0",
    "114.0.0.0",
)

PLATFORMS: tuple[str, ...] = (
    "Windows NT 10.0; Win64; x64",
    "Windows NT 6.1; Win64; x64",
    "Macintosh; Intel Mac OS X 10_15_7",
    "X11; Linux x86_64",
)

SCREEN_RESOLUTIONS: tuple[dict[str, int], ...] = (
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 720},
)

LANGUAGES: tuple[str, ...] = (
    "en-US,en;q=0.9",
    "ru-RU,ru;q=0.9,en;q=0.8",
    "de-DE,de;q=0.9,en;q=0.8",
    "fr-FR,fr;q=0.9,en;q=0.8",
)

FINGERPRINT_SPOOFING_SCRIPT = """
() => {
    delete navigator.__proto__.webdriver;

    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
        configurable: true
    });

    Object.defineProperty(navigator, 'languages', {
        get: () => ['%s', '%s'],
        configurable: true
    });

    Object.defineProperty(navigator, 'platform', {
        get: () => '%s',
        configurable: true
    });

    Object.defineProperty(navigator, 'hardwareConcurrency', {
        get: () => %d,
        configurable: true
    });

    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true
    });

    const originalQuery = navigator.permissions.query;
    navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters)
    );

    window.chrome = {
        runtime: {},
        loadTimes: function() { return {}; },
        csi: function() { return {}; },
        src: { isInstalled: false }
    };
}
"""

WEBGL_SPOOFING_SCRIPT = """
() => {
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) return 'Intel Inc.';
        if (parameter === 37446) return 'Intel Iris OpenGL Engine';
        return getParameter.call(this, parameter);
    };
}
"""

CANVAS_SPOOFING_SCRIPT = """
() => {
    const toDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(type) {
        const context = this.getContext('2d');
        if (context) {
            context.fillText('Modified Canvas Fingerprint', 10, 10);
        }
        return toDataURL.call(this, type);
    };
}
"""


def _generate_user_agent() -> str:
    return (
        f"Mozilla/5.0 ({random.choice(PLATFORMS)}) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{random.choice(CHROME_VERSIONS)} Safari/537.36"
    )


def _generate_screen_resolution() -> dict[str, int]:
    return random.choice(SCREEN_RESOLUTIONS)


def _generate_accept_language() -> str:
    return random.choice(LANGUAGES)


def _generate_extra_http_headers() -> dict[str, str]:
    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": _generate_accept_language(),
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "DNT": str(random.randint(0, 1)),
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }


def _build_stealth_scripts() -> tuple[str, ...]:
    platform = random.choice(PLATFORMS)
    return (
        CANVAS_SPOOFING_SCRIPT,
        FINGERPRINT_SPOOFING_SCRIPT % (
            "ru-RU",
            "ru",
            platform,
            random.choice([4, 8, 12, 16]),
        ),
        WEBGL_SPOOFING_SCRIPT,
    )


def _create_stealth_context(playwright, *, persistent_profile_dir: str | None = None):
    screen_resolution = _generate_screen_resolution()
    context_kwargs = {
        "viewport": screen_resolution,
        "screen": screen_resolution,
        "user_agent": _generate_user_agent(),
        "accept_downloads": False,
        "ignore_https_errors": True,
        "java_script_enabled": True,
        "has_touch": random.choice([True, False]),
        "is_mobile": False,
        "extra_http_headers": _generate_extra_http_headers(),
        "locale": "ru-RU",
        "timezone_id": "Europe/Moscow",
    }

    if persistent_profile_dir:
        context = playwright.chromium.launch_persistent_context(
            persistent_profile_dir,
            headless=True,
            **context_kwargs,
        )
    else:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(**context_kwargs)
        context._linked_browser = browser  # noqa: SLF001

    for script in _build_stealth_scripts():
        context.add_init_script(script)

    return context


def _close_context_with_browser(context) -> None:
    try:
        linked_browser = getattr(context, "_linked_browser", None)
        context.close()
        if linked_browser is not None:
            linked_browser.close()
    except Exception:
        pass


def vk_browser_profile_dir() -> Path:
    raw = os.getenv("VK_BROWSER_PROFILE_DIR", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path(__file__).resolve().parents[2] / "db" / "vk_browser_profile").resolve()


def has_vk_browser_profile() -> bool:
    profile_dir = vk_browser_profile_dir()
    return profile_dir.exists() and any(profile_dir.iterdir())


def launch_vk_browser_login() -> dict[str, str]:
    profile_dir = vk_browser_profile_dir()
    profile_dir.mkdir(parents=True, exist_ok=True)
    script = Path(__file__).resolve().parents[1] / "scripts" / "vk_browser_login.py"
    process = subprocess.Popen(
        [sys.executable, str(script), str(profile_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    return {
        "message": "VK login browser started. Sign in to vk.com in the opened window and then close it.",
        "profile_dir": str(profile_dir),
        "pid": str(process.pid),
    }


def search_public_groups(query: str, limit: int = 5) -> list[PublicVKSearchResult]:
    clean_query = (query or "").strip()
    if len(clean_query) < 2:
        return []

    url = f"https://vk.com/search/communities?q={quote(clean_query)}"
    if sync_playwright is not None:
        with sync_playwright() as playwright:
            context = None
            try:
                if has_vk_browser_profile():
                    context = _create_stealth_context(
                        playwright,
                        persistent_profile_dir=str(vk_browser_profile_dir()),
                    )
                else:
                    context = _create_stealth_context(playwright)

                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(3500)

                try:
                    search_input = page.locator(
                        "input[placeholder='Enter a search'], input[placeholder='Search']"
                    ).first
                    if search_input.count() > 0:
                        search_input.click(timeout=1200)
                        search_input.fill(clean_query, timeout=2000)
                        search_input.press("Enter", timeout=1200)
                        page.wait_for_timeout(2200)
                except Exception:
                    pass

                raw_links = page.evaluate(
                    """() => Array.from(document.querySelectorAll('a[href]'))
                    .map(a => ({href: a.getAttribute('href') || '', text: (a.textContent || '').trim()}))
                    """
                )
                results = _extract_search_results(raw_links, query=clean_query, limit=limit)
                if results:
                    return results
            except Exception:
                pass
            finally:
                if context is not None:
                    _close_context_with_browser(context)

    return _search_public_groups_http(clean_query, limit)

def _search_public_groups_http(query: str, limit: int) -> list[PublicVKSearchResult]:
    urls = [
        f"https://vk.com/search/communities?q={quote(query)}",
        f"https://vk.com/search?c%5Bsection%5D=communities&c%5Bq%5D={quote(query)}",
        f"https://m.vk.com/search?c%5Bsection%5D=communities&c%5Bq%5D={quote(query)}",
        f"https://vk.com/search?section=communities&q={quote(query)}",
    ]
    headers = {"User-Agent": "Mozilla/5.0"}
    for url in urls:
        try:
            response = requests.get(url, headers=headers, timeout=18)
            if response.status_code >= 400:
                continue
            html = response.text
            raw_links: list[dict] = []
            for href, text_html in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.IGNORECASE | re.DOTALL):
                text = re.sub(r"<[^>]+>", " ", text_html)
                text = unescape(" ".join(text.split()))
                raw_links.append({"href": href, "text": text})
            results = _extract_search_results(raw_links, query=query, limit=limit)
            if results:
                return results
        except Exception:
            continue
    return []


def fetch_public_group_data(screen_name: str, group_id: int | None = None, limit: int = 20) -> PublicVKGroupData:
    if sync_playwright is None:
        raise RuntimeError("Playwright is not installed")

    clean_name = screen_name.lstrip("@")
    urls = [
        f"https://vk.com/wall-{group_id}" if group_id else None,
        f"https://vk.com/public{group_id}" if group_id else None,
        f"https://vk.com/club{group_id}" if group_id else None,
        f"https://m.vk.com/wall-{group_id}" if group_id else None,
        f"https://vk.com/{clean_name}",
        f"https://m.vk.com/{clean_name}",
    ]
    urls = [url for url in urls if url]

    with sync_playwright() as playwright:
        last_error: Exception | None = None

        if has_vk_browser_profile():
            context = None
            try:
                context = _create_stealth_context(
                    playwright,
                    persistent_profile_dir=str(vk_browser_profile_dir()),
                )
                result = _fetch_from_context(context, urls, clean_name, limit, group_id)
                if result.posts:
                    return result
                last_error = RuntimeError("Authenticated browser profile loaded but no posts were found")
            except Exception as exc:
                last_error = exc
            finally:
                if context is not None:
                    _close_context_with_browser(context)

        context = None
        try:
            context = _create_stealth_context(playwright)
            result = _fetch_from_context(context, urls, clean_name, limit, group_id)
            return result
        except Exception as exc:
            if last_error:
                raise RuntimeError(f"Failed to load VK public page: {last_error}") from exc
            raise RuntimeError(f"Failed to load VK public page: {exc}") from exc
        finally:
            if context is not None:
                _close_context_with_browser(context)

def _fetch_from_browser(browser, urls: list[str], clean_name: str, limit: int, group_id: int | None) -> PublicVKGroupData:
    last_error: Exception | None = None
    best_result: PublicVKGroupData | None = None
    for idx, url in enumerate(urls):
        page = browser.new_page(
            viewport={"width": 1440, "height": 2400} if idx == 0 else {"width": 430, "height": 2400}
        )
        try:
            result = _fetch_from_page(page, url, clean_name, limit, group_id)
            if result.posts and len(result.posts) >= max(3, int(limit * 0.6)):
                return result
            if best_result is None or len(result.posts) > len(best_result.posts):
                best_result = result
        except Exception as exc:
            last_error = exc
        finally:
            page.close()
    if best_result is not None and best_result.posts:
        return best_result
    if last_error:
        raise last_error
    if best_result is not None:
        return best_result
    return PublicVKGroupData(name=clean_name, screen_name=clean_name, posts=[])


def _fetch_from_context(context, urls: list[str], clean_name: str, limit: int, group_id: int | None) -> PublicVKGroupData:
    last_error: Exception | None = None
    best_result: PublicVKGroupData | None = None
    for url in urls:
        page = context.new_page()
        try:
            result = _fetch_from_page(page, url, clean_name, limit, group_id)
            if result.posts and len(result.posts) >= max(3, int(limit * 0.6)):
                return result
            if best_result is None or len(result.posts) > len(best_result.posts):
                best_result = result
        except Exception as exc:
            last_error = exc
        finally:
            page.close()
    if best_result is not None and best_result.posts:
        return best_result
    if last_error:
        raise last_error
    if best_result is not None:
        return best_result
    return PublicVKGroupData(name=clean_name, screen_name=clean_name, posts=[])

   
def _fetch_from_page(page, url: str, clean_name: str, limit: int, group_id: int | None) -> PublicVKGroupData:
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(4500)
    print("URL AFTER GOTO:", page.url)
    print("PAGE TITLE:", page.title())
    print("HTML LEN:", len(page.content()))
    print("DATA-POST-ID COUNT:", page.locator("[data-post-id]").count())
    print("WALL LINKS COUNT:", page.locator("a[href*='wall-']").count())
    html = page.content()
    print(html[:3000])
    try:
        _scroll_feed_until_loaded(page, limit)
    except Exception:
        pass

    seen: set[str] = set()
    posts: list[PublicVKPost] = []
    no_new_rounds = 0
    rounds = max(8, min(26, limit + 8))

    for _ in range(rounds):
        before = len(posts)
        _collect_visible_posts(page, posts, seen, limit=limit, group_id=group_id)
        after = len(posts)
        if after >= limit:
            break

        if after == before:
            no_new_rounds += 1
        else:
            no_new_rounds = 0
        if no_new_rounds >= 4:
            break

        try:
            page.evaluate("() => window.scrollBy(0, Math.max(window.innerHeight * 0.9, 1200))")
        except Exception:
            pass
        try:
            page.mouse.wheel(0, 3200)
        except Exception:
            pass
        try:
            show_more = page.locator(
                "button:has-text('Показать ещё'), a:has-text('Показать ещё'), "
                "button:has-text('Show more'), a:has-text('Show more')"
            )
            if show_more.count() > 0:
                show_more.first.click(timeout=1200)
        except Exception:
            pass
        page.wait_for_timeout(850)

    raw_title = (page.title() or "").strip()
    title = raw_title.replace("| VK", "").strip()
    title = re.sub(r"\s*:\s*posts?$", "", title, flags=re.IGNORECASE).strip()
    title_lc = title.lower()
    if (
        raw_title in _CHALLENGE_TITLES
        or title in _CHALLENGE_TITLES
        or title_lc in _BAD_PAGE_TITLES
        or title_lc.startswith("error")
        or title_lc.startswith("ошибка")
    ):
        title = clean_name
    return PublicVKGroupData(name=title or clean_name, screen_name=clean_name, posts=posts)


def _scroll_feed_until_loaded(page, target_posts: int) -> None:
    target = max(8, min(int(target_posts or 0), 180))
    max_rounds = 22
    stable_rounds = 0
    prev_count = -1
    prev_height = -1

    for _ in range(max_rounds):
        count = page.locator("[data-post-id]").count()
        if count == 0:
            count = page.locator("a[href*='wall-']").count()

        try:
            height = int(page.evaluate("() => document.body ? document.body.scrollHeight : 0") or 0)
        except Exception:
            height = 0

        enough_posts = count >= target
        if count == prev_count and height == prev_height:
            stable_rounds += 1
        else:
            stable_rounds = 0

        if enough_posts and stable_rounds >= 2:
            break
        if stable_rounds >= 4:
            break

        try:
            page.evaluate("() => window.scrollBy(0, Math.max(window.innerHeight * 0.9, 1200))")
        except Exception:
            pass
        try:
            page.mouse.wheel(0, 3200)
        except Exception:
            pass
        try:
            show_more = page.locator(
                "button:has-text('Показать ещё'), a:has-text('Показать ещё'), "
                "button:has-text('Show more'), a:has-text('Show more')"
            )
            if show_more.count() > 0:
                show_more.first.click(timeout=1200)
        except Exception:
            pass

        page.wait_for_timeout(900)
        prev_count = count
        prev_height = height


def _collect_visible_posts(
    page,
    posts: list[PublicVKPost],
    seen: set[str],
    *,
    limit: int,
    group_id: int | None,
) -> None:
    post_nodes = page.locator("[data-post-id]")
    if post_nodes.count() == 0:
        post_nodes = page.locator("a[href*='wall-']")

    max_scan = min(post_nodes.count(), max(20, limit * 6))
    for item_idx in range(max_scan):
        node = post_nodes.nth(item_idx)
        post_id = node.get_attribute("data-post-id") or node.get_attribute("href") or ""
        post_id = _normalize_post_id(post_id)
        if not post_id or post_id in seen:
            continue
        if not _is_post_owner_match(post_id, group_id):
            continue
        seen.add(post_id)

        raw_text = node.inner_text(timeout=5000)
        raw_html = node.inner_html(timeout=5000)
        parsed = _parse_post_block(raw_text)
        html_metrics = _extract_post_metrics_from_html(raw_html)
        text = _extract_post_text(node, fallback=str(parsed["text"]))
        if _looks_like_ui_text(text):
            text = ""
        if (
            len(text) < 8
            and int(parsed["likes"]) == 0
            and int(parsed["comments"]) == 0
            and int(parsed["views"]) == 0
            and int(parsed["timestamp"]) == 0
        ):
            continue

        likes = int(html_metrics.get("likes") or parsed["likes"])
        comments = int(html_metrics.get("comments") or parsed["comments"])
        reposts = int(html_metrics.get("reposts") or parsed["reposts"])
        views = int(html_metrics.get("views") or parsed["views"])
        if views > 100_000_000:
            views = 0

        posts.append(
            PublicVKPost(
                post_id=post_id,
                text=text,
                likes=likes,
                comments=comments,
                reposts=reposts,
                views=views,
                date_label=str(parsed["date_label"]),
                timestamp=int(parsed["timestamp"]),
            )
        )
        if len(posts) >= limit:
            break


def _is_post_owner_match(post_id: str, group_id: int | None) -> bool:
    if not post_id or not re.fullmatch(r"-?\d+_\d+", post_id):
        return False
    if group_id is None:
        return True
    owner = post_id.split("_", 1)[0]
    gid = str(abs(group_id))
    return owner in {gid, f"-{gid}"}


def _clean_post_text(raw_text: str) -> str:
    lines: list[str] = []
    for line in (raw_text or "").splitlines():
        item = " ".join(line.strip().split())
        if not item or len(item) <= 2:
            continue
        lowered = item.lower()
        if _SKIP_LINE_RE.match(lowered):
            continue
        if re.fullmatch(r"\d+\s*/\s*\d+", lowered):
            continue
        if re.fullmatch(r"[a-zа-яё]+(\s+[a-zа-яё]+){1,2}", lowered) and len(item) <= 32:
            # Often author/comment short labels in feed cards.
            continue
        if re.fullmatch(r"[\d\s:.,]+", item):
            continue
        if re.fullmatch(r"\d+[a-z\u0430-\u044f\u0451 ]*ago", lowered):
            continue
        lines.append(item)

    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:4000]


def _normalize_post_id(value: str) -> str:
    text = (value or "").strip()
    if "wall" in text:
        match = re.search(r"wall(-?\d+_\d+)", text)
        if match:
            return match.group(1)
    return text


def _extract_search_results(raw_links: list[dict], query: str, limit: int) -> list[PublicVKSearchResult]:
    results: list[PublicVKSearchResult] = []
    seen: set[str] = set()
    ignored = {
        "feed",
        "im",
        "friends",
        "groups",
        "photos466026575",
        "audios466026575",
        "docs",
        "about",
        "blog",
        "verify",
        "games",
        "market",
        "settings",
        "vk_authors",
    }
    query_tokens = {
        token.lower()
        for token in re.findall(r"[a-zA-Z\u0430-\u044f\u0410-\u042f\u0451\u04010-9]+", query)
        if len(token) >= 2
    }
    query_tokens_canon = {_canon_search_token(token) for token in query_tokens}
    for item in raw_links:
        href = str(item.get("href") or "").strip()
        text = " ".join(str(item.get("text") or "").split())
        if not href.startswith("/") or href.startswith("/search") or not text:
            continue
        path = href.split("?", 1)[0].strip("/")
        if not path or "/" in path or path in ignored:
            continue
        if not _is_likely_group_screen_name(path):
            continue
        if path.startswith("audio") or path.startswith("away.php") or path.endswith(".php"):
            continue
        if path in seen:
            continue
        if text in {"Profile", "News", "Messenger", "Friends", "Communities", "About VK"}:
            continue
        if len(text) < 2:
            continue
        haystack = f"{text} {path}".lower()
        haystack_tokens = {
            token.lower()
            for token in re.findall(r"[a-zA-Z\u0430-\u044f\u0410-\u042f\u0451\u04010-9]+", haystack)
            if len(token) >= 2
        }
        haystack_tokens_canon = {_canon_search_token(token) for token in haystack_tokens}
        if query_tokens:
            overlap = 0
            for token in query_tokens:
                token_canon = _canon_search_token(token)
                if token in haystack_tokens or token_canon in haystack_tokens_canon:
                    overlap += 1
                    continue
                if any(item.startswith(token) or token.startswith(item) for item in haystack_tokens):
                    overlap += 1
                    continue
                if any(
                    item.startswith(token_canon) or token_canon.startswith(item)
                    for item in haystack_tokens_canon
                ):
                    overlap += 1
            if overlap == 0:
                continue
        seen.add(path)
        results.append(PublicVKSearchResult(name=text, screen_name=path))
        if len(results) >= limit:
            break
    return results


def _is_likely_group_screen_name(path: str) -> bool:
    value = (path or "").strip()
    if not value:
        return False
    lowered = value.lower()
    if lowered.startswith("@@"):
        return False
    if any(part in lowered for part in {"rss-", "-rss-", "article", "podcast", "clip"}):
        return False
    if lowered.startswith(("id", "wall", "photo", "video", "feed", "topic")):
        return False
    # Typical public/community aliases and numeric IDs.
    if re.fullmatch(r"(club|public|event)\d+", lowered):
        return True
    # Human-readable aliases.
    if not re.fullmatch(r"[a-zA-Zа-яА-ЯёЁ0-9_.-]{3,64}", value):
        return False
    # Must contain at least one letter to avoid random numeric fragments.
    return bool(re.search(r"[a-zA-Zа-яА-ЯёЁ]", value))


def _canon_search_token(value: str) -> str:
    token = (value or "").strip().lower()
    if not token:
        return ""
    # Unify visually similar Cyrillic/Latin letters to improve matches like "1с" vs "1c".
    table = str.maketrans(
        {
            "а": "a",
            "е": "e",
            "о": "o",
            "р": "p",
            "с": "c",
            "у": "y",
            "к": "k",
            "м": "m",
            "т": "t",
            "х": "x",
            "в": "b",
            "н": "h",
            "ё": "e",
        }
    )
    return token.translate(table)


def _parse_post_block(raw_text: str) -> dict[str, object]:
    lines = [" ".join(line.strip().split()) for line in (raw_text or "").splitlines()]
    lines = [line for line in lines if line]

    date_idx = -1
    for idx, line in enumerate(lines):
        if _looks_like_date_label(line.lower()):
            date_idx = idx
            break

    date_label = lines[date_idx] if date_idx >= 0 else ""
    timestamp = _parse_timestamp(date_label)

    likes = comments = reposts = views = 0
    if date_idx >= 1:
        numeric_lines: list[int] = []
        scan_start = max(0, date_idx - 5)
        for line in lines[scan_start:date_idx]:
            if not _is_probably_metric_line(line):
                continue
            value = _parse_metric_value(line)
            if value > 0:
                numeric_lines.append(value)
        if numeric_lines:
            likes = numeric_lines[0]
        if len(numeric_lines) >= 2:
            comments = numeric_lines[1]
        if len(numeric_lines) >= 3:
            views = numeric_lines[2]
        if len(numeric_lines) >= 4:
            reposts = numeric_lines[3]

    if likes == 0 or comments == 0 or views == 0:
        for line in lines[max(0, date_idx - 10) : date_idx if date_idx > 0 else len(lines)]:
            lowered = line.lower()
            value = _parse_metric_value(line)
            if value <= 0:
                continue
            if likes == 0 and any(token in lowered for token in {"лайк", "like", "нрав"}):
                likes = value
            elif comments == 0 and any(token in lowered for token in {"коммент", "comment", "reply"}):
                comments = value
            elif reposts == 0 and any(token in lowered for token in {"репост", "share", "подел"}):
                reposts = value
            elif views == 0 and any(token in lowered for token in {"просмотр", "view"}):
                views = value

    if views and views < max(likes, comments, 10):
        views = 0

    text = _clean_post_text("\n".join(lines[: date_idx if date_idx > 0 else len(lines)]))
    return {
        "text": text,
        "likes": likes,
        "comments": comments,
        "reposts": reposts,
        "views": views,
        "date_label": date_label,
        "timestamp": timestamp,
    }


def _parse_metric_value(value: str) -> int:
    text = " ".join((value or "").strip().lower().replace("\xa0", " ").split())
    if not text:
        return 0

    compact = re.search(r"\b(\d{1,3}(?:\s\d{3})+)\b", text)
    if compact:
        try:
            parsed = int(compact.group(1).replace(" ", ""))
            return parsed if parsed <= 100_000_000 else 0
        except ValueError:
            pass

    match = re.search(r"(\d+(?:[.,]\d+)?)\s*(k|к|тыс|m|м|млн)?\b", text)
    if not match:
        return 0
    raw = match.group(1).replace(",", ".")
    unit = (match.group(2) or "").strip()
    try:
        number = float(raw)
    except ValueError:
        return 0

    multiplier = 1
    if unit in {"k", "к", "тыс"}:
        multiplier = 1_000
    elif unit in {"m", "м", "млн"}:
        multiplier = 1_000_000

    parsed = int(number * multiplier)
    if parsed > 100_000_000:
        return 0
    return parsed


def _looks_like_ui_text(text: str) -> bool:
    value = " ".join((text or "").strip().lower().split())
    if not value:
        return True
    bad_phrases = {
        "следующий слайд",
        "предыдущий слайд",
        "листайте",
        "свайп",
        "играть",
        "play",
        "leave comment",
        "leave a comment",
        "this video has been unavailable because",
        "oldest",
        "most interesting",
        "view replies",
    }
    if any(phrase in value for phrase in bad_phrases):
        return True
    words = [word for word in re.findall(r"[a-zа-яё]+", value) if len(word) >= 3]
    if not words:
        return True
    unique = set(words)
    return len(unique) <= 2 and len(words) >= 4


def _is_probably_metric_line(line: str) -> bool:
    value = " ".join((line or "").strip().lower().replace("\xa0", " ").split())
    if not value:
        return False
    if re.fullmatch(r"[\d\s.,kкmмтысмилн]+", value):
        return True
    if any(keyword in value for keyword in {"лайк", "like", "коммент", "comment", "репост", "share", "просмотр", "view"}):
        return True
    return False


def _extract_post_text(node, fallback: str) -> str:
    selectors = [
        ".wall_text",
        ".PostContentContainer__contentContainer--rLkRl",
    ]
    for selector in selectors:
        try:
            loc = node.locator(selector)
            if loc.count() > 0:
                text = _clean_post_text(loc.first.inner_text(timeout=3000))
                if text and not _looks_like_ui_text(text):
                    return text
        except Exception:
            continue
    return _clean_post_text(fallback)


def _extract_post_metrics_from_html(raw_html: str) -> dict[str, int]:
    html = raw_html or ""
    likes = comments = reposts = views = 0

    reactions = re.search(r'data-reaction-counts="([^"]+)"', html)
    if reactions:
        encoded = unescape(reactions.group(1))
        try:
            payload = json.loads(encoded)
            likes = int(sum(int(v) for v in payload.values()))
        except Exception:
            likes = 0

    share = re.search(r'data-like-button-type="share"[^>]*data-count="(\d+)"', html)
    if share:
        reposts = int(share.group(1))

    comments_match = re.search(r'(?:comment|коммент)[^>]*data-count="(\d+)"', html, flags=re.IGNORECASE)
    if comments_match:
        comments = int(comments_match.group(1))

    views_match = re.search(r'(?:view|просмотр)[^>]*data-count="(\d+)"', html, flags=re.IGNORECASE)
    if views_match:
        views = int(views_match.group(1))

    raw_counts = [int(value) for value in re.findall(r'data-count="(\d+)"', html)]
    labeled_hits = sum(1 for v in [likes, comments, reposts, views] if v > 0)
    if raw_counts:
        unique_counts = sorted(set(raw_counts), reverse=True)
        # If no labeled counters exist, we still provide a deterministic fallback:
        # largest count -> likes, next -> comments/reposts.
        if labeled_hits == 0:
            likes = unique_counts[0]
            if len(unique_counts) >= 2:
                comments = unique_counts[1]
            if len(unique_counts) >= 3:
                reposts = unique_counts[2]
        # Conservative merge when some labeled counters were already found.
        elif labeled_hits >= 2:
            if likes == 0:
                if views > 0 and unique_counts[0] == views and len(unique_counts) >= 2:
                    likes = unique_counts[1]
                else:
                    likes = unique_counts[0]
            if comments == 0 and len(unique_counts) >= 2:
                comments = unique_counts[1]
            if reposts == 0 and len(unique_counts) >= 3:
                reposts = unique_counts[2]
            if views == 0 and likes > 0 and unique_counts[0] >= likes * 5:
                views = unique_counts[0]

    # Basic sanity filters against obviously wrong metric combinations.
    if likes > 0 and comments > likes * 3:
        comments = 0
    if likes > 0 and reposts > likes * 2:
        reposts = 0

    return {
        "likes": likes,
        "comments": comments,
        "reposts": reposts,
        "views": views,
    }


def _looks_like_date_label(value: str) -> bool:
    value = (value or "").strip().lower()
    if not value:
        return False
    if re.search(r"\b\d+\s*(min|mins|minutes|h|hr|hrs|hour|hours)\s+ago\b", value):
        return True
    if re.search(r"\b\d+\s*(\u043c\u0438\u043d|\u043c\u0438\u043d\u0443\u0442\u0430|\u043c\u0438\u043d\u0443\u0442|\u0447\u0430\u0441|\u0447\u0430\u0441\u0430|\u0447\u0430\u0441\u043e\u0432)\s+\u043d\u0430\u0437\u0430\u0434\b", value):
        return True
    if (
        "today at" in value
        or "yesterday at" in value
        or "\u0441\u0435\u0433\u043e\u0434\u043d\u044f \u0432" in value
        or "\u0432\u0447\u0435\u0440\u0430 \u0432" in value
    ):
        return True
    return bool(re.search(r"\b\d{1,2}\s+[a-z\u0430-\u044f\u0451]{3,}\s+(at|\u0432)\s+\d{1,2}:\d{2}", value))


def _parse_timestamp(date_label: str) -> int:
    value = (date_label or "").strip().lower()
    if not value:
        return 0

    now = datetime.now()

    relative_match = re.search(r"(\d+)\s*(min|mins|minutes|h|hr|hrs|hour|hours)\s+ago", value)
    if relative_match:
        amount = int(relative_match.group(1))
        unit = relative_match.group(2)
        delta = timedelta(minutes=amount) if unit.startswith("m") else timedelta(hours=amount)
        return int((now - delta).timestamp())

    relative_ru = re.search(
        r"(\d+)\s*(\u043c\u0438\u043d|\u043c\u0438\u043d\u0443\u0442\u0430|\u043c\u0438\u043d\u0443\u0442|\u0447\u0430\u0441|\u0447\u0430\u0441\u0430|\u0447\u0430\u0441\u043e\u0432)\s+\u043d\u0430\u0437\u0430\u0434",
        value,
    )
    if relative_ru:
        amount = int(relative_ru.group(1))
        unit = relative_ru.group(2)
        delta = timedelta(minutes=amount) if unit.startswith("\u043c\u0438\u043d") else timedelta(hours=amount)
        return int((now - delta).timestamp())

    today_yesterday = re.search(
        r"(today|yesterday|\u0441\u0435\u0433\u043e\u0434\u043d\u044f|\u0432\u0447\u0435\u0440\u0430)\s+(?:at|\u0432)\s+(\d{1,2}):(\d{2})(?:\s*(am|pm))?",
        value,
    )
    if today_yesterday:
        marker, hour, minute, ampm = today_yesterday.groups()
        hour_i = int(hour)
        if ampm == "pm" and hour_i < 12:
            hour_i += 12
        if ampm == "am" and hour_i == 12:
            hour_i = 0
        base = now.date()
        if marker in {"yesterday", "\u0432\u0447\u0435\u0440\u0430"}:
            base = (now - timedelta(days=1)).date()
        dt = datetime.combine(base, datetime.min.time()).replace(hour=hour_i, minute=int(minute))
        return int(dt.timestamp())

    absolute = re.search(
        r"(\d{1,2})\s+([a-z\u0430-\u044f\u0451]{3,})\s+(?:at|\u0432)\s+(\d{1,2}):(\d{2})(?:\s*(am|pm))?",
        value,
    )
    if absolute:
        day, month_name, hour, minute, ampm = absolute.groups()
        month = _MONTHS.get(month_name)
        if month:
            hour_i = int(hour)
            if ampm == "pm" and hour_i < 12:
                hour_i += 12
            if ampm == "am" and hour_i == 12:
                hour_i = 0
            year = now.year
            try:
                dt = datetime(year, month, int(day), hour_i, int(minute))
            except ValueError:
                return 0
            if dt.timestamp() > now.timestamp() + 86400:
                dt = dt.replace(year=year - 1)
            return int(dt.timestamp())

    return 0
