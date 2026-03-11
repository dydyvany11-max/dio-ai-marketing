from dataclasses import dataclass


@dataclass(frozen=True)
class AuthStatus:
    authorized: bool
    pending: bool
    expires_at: str | None
    error: str | None


@dataclass(frozen=True)
class QRCodePayload:
    image_bytes: bytes
    login_url: str
    expires_at: str | None


@dataclass(frozen=True)
class AuthorizedUser:
    user_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    phone: str | None


@dataclass(frozen=True)
class TelegramPostAnalysis:
    url: str
    channel: str
    message_id: int
    text: str
    date_iso: str | None
    views: int | None
    forwards: int | None
