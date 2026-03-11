import re
from typing import Protocol

from services.errors import InvalidTelegramPostUrlError


class TelegramPostUrlParser(Protocol):
    def parse(self, url: str) -> tuple[str, int]:
        ...


class RegexTelegramPostUrlParser:
    _post_patterns = (
        re.compile(r"^https?://t\.me/([A-Za-z0-9_]+)/(\d+)$", re.IGNORECASE),
        re.compile(r"^https?://telegram\.me/([A-Za-z0-9_]+)/(\d+)$", re.IGNORECASE),
    )

    def parse(self, url: str) -> tuple[str, int]:
        value = url.strip()
        for pattern in self._post_patterns:
            match = pattern.match(value)
            if match:
                return match.group(1), int(match.group(2))

        raise InvalidTelegramPostUrlError("Use URL like https://t.me/channel_name/123")
