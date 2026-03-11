from pydantic import BaseModel


class QRStatusResponse(BaseModel):
    authorized: bool
    pending: bool
    expires_at: str | None = None
    error: str | None = None


class TelegramPostResponse(BaseModel):
    url: str
    channel: str
    message_id: int
    text: str
    date_iso: str | None = None
    views: int | None = None
    forwards: int | None = None


class PasswordRequest(BaseModel):
    password: str
