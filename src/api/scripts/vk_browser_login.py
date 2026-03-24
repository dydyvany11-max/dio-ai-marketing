from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> int:
    profile_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else (Path.cwd() / "db" / "vk_browser_profile")
    profile_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile_dir),
            headless=False,
            viewport={"width": 1440, "height": 960},
        )
        page = context.new_page()
        page.goto("https://vk.com/", wait_until="domcontentloaded", timeout=60000)
        print("Login to vk.com in this browser window. Close the browser when done.")
        page.wait_for_timeout(10 * 60 * 1000)
        context.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
