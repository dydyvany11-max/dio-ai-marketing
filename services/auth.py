import asyncio
import io
from dataclasses import dataclass
from typing import Optional

import qrcode
from telethon.errors import SessionPasswordNeededError

from services.dto import AuthStatus, AuthorizedUser, QRCodePayload
from services.errors import (
    AlreadyAuthorizedError,
    AuthorizationRequiredError,
    TelegramOperationError,
)
from services.telegram_client import TelegramClientService


@dataclass
class _QRStatusState:
    pending: bool = False
    expires_at: str | None = None
    error: str | None = None


class TelegramAuthService:
    def __init__(self, client_service: TelegramClientService):
        self._client_service = client_service
        self._qr_login_obj = None
        self._qr_wait_task: Optional[asyncio.Task] = None
        self._qr_state = _QRStatusState()

    async def get_status(self) -> AuthStatus:
        await self._client_service.ensure_connected()
        authorized = await self._client_service.client.is_user_authorized()
        if authorized:
            self._qr_state.pending = False
        return AuthStatus(
            authorized=authorized,
            pending=self._qr_state.pending,
            expires_at=self._qr_state.expires_at,
            error=self._qr_state.error,
        )

    async def is_user_authorized(self) -> bool:
        await self._client_service.ensure_connected()
        return await self._client_service.client.is_user_authorized()

    async def create_qr_payload(self) -> QRCodePayload:
        login_url, expires_at = await self._start_qr_login()
        image_bytes = self._build_qr_png(login_url)
        return QRCodePayload(
            image_bytes=image_bytes,
            login_url=login_url,
            expires_at=expires_at,
        )

    async def create_qr_url(self) -> tuple[str, str | None]:
        return await self._start_qr_login()

    async def authorize_with_password(self, password: str) -> AuthorizedUser:
        await self._client_service.ensure_connected()
        if await self._client_service.client.is_user_authorized():
            raise AlreadyAuthorizedError("already authorized")

        try:
            await self._client_service.client.sign_in(password=password)
        except Exception as exc:
            raise TelegramOperationError(str(exc)) from exc

        me = await self._client_service.client.get_me()
        self._qr_state.pending = False
        self._qr_state.error = None
        return self._to_authorized_user(me)

    async def get_current_user(self) -> AuthorizedUser:
        await self._client_service.ensure_connected()
        if not await self._client_service.client.is_user_authorized():
            raise AuthorizationRequiredError("Not authorized yet")

        me = await self._client_service.client.get_me()
        return self._to_authorized_user(me)

    async def _start_qr_login(self) -> tuple[str, str | None]:
        await self._client_service.ensure_connected()
        if await self._client_service.client.is_user_authorized():
            raise AlreadyAuthorizedError("Already authorized")

        self._qr_login_obj = await self._client_service.client.qr_login()
        self._qr_state.pending = True
        self._qr_state.expires_at = (
            self._qr_login_obj.expires.isoformat() if self._qr_login_obj.expires else None
        )
        self._qr_state.error = None

        self._cancel_previous_wait_task()
        self._qr_wait_task = asyncio.create_task(self._wait_for_qr_login(self._qr_login_obj))

        return self._qr_login_obj.url, self._qr_state.expires_at

    def _cancel_previous_wait_task(self) -> None:
        if self._qr_wait_task and not self._qr_wait_task.done():
            self._qr_wait_task.cancel()

    async def _wait_for_qr_login(self, qr_login_obj) -> None:
        try:
            await qr_login_obj.wait()
            self._qr_state.pending = False
            self._qr_state.error = None
        except SessionPasswordNeededError:
            self._qr_state.pending = False
            self._qr_state.error = "Two-factor password required"
        except asyncio.CancelledError:
            return
        except Exception as exc:
            self._qr_state.pending = False
            self._qr_state.error = str(exc)

    @staticmethod
    def _build_qr_png(content: str) -> bytes:
        qr = qrcode.QRCode(box_size=10, border=2)
        qr.add_data(content)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer.read()

    @staticmethod
    def _to_authorized_user(me) -> AuthorizedUser:
        return AuthorizedUser(
            user_id=me.id,
            username=me.username,
            first_name=me.first_name,
            last_name=me.last_name,
            phone=me.phone,
        )
