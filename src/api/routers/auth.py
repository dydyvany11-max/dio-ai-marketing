import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from src.api.dependencies import get_auth_service
from src.api.http_errors import raise_auth_http_error
from src.api.response_builders import (
    build_auth_success_response,
    build_current_user_response,
    build_qr_status_response,
)
from src.api.schemas import PasswordRequest, QRStatusResponse
from src.api.services.errors import (
    AlreadyAuthorizedError,
    TelegramOperationError,
)
from src.api.services.interfaces import AuthServicePort

router = APIRouter(prefix="/tg", tags=["Telegram: авторизация"])


@router.get(
    "/auth/status",
    response_model=QRStatusResponse,
    summary="Статус авторизации Telegram",
    description="Показывает, авторизована ли текущая Telegram-сессия и есть ли активный QR-вход.",
)
async def tg_auth_status(auth_service: AuthServicePort = Depends(get_auth_service)):
    try:
        status = await auth_service.get_status()
    except Exception as exc:
        raise_auth_http_error(exc, status_code_for_telegram_error=503)
    return build_qr_status_response(status)


@router.get(
    "/auth/qr",
    summary="Получить QR-код для входа",
    description="Возвращает PNG QR-кода для авторизации Telegram через приложение.",
)
async def tg_auth_qr(auth_service: AuthServicePort = Depends(get_auth_service)):
    try:
        payload = await auth_service.create_qr_payload()
    except AlreadyAuthorizedError:
        return {"authorized": True, "message": "Already authorized"}
    except Exception as exc:
        raise_auth_http_error(exc, status_code_for_telegram_error=503)

    return StreamingResponse(
        io.BytesIO(payload.image_bytes),
        media_type="image/png",
        headers={
            "X-Telegram-Login-Url": payload.login_url,
            "X-QR-Expires-At": payload.expires_at or "",
        },
    )


@router.get(
    "/auth/qr/url",
    summary="Получить tg:// ссылку для QR-входа",
    description="Возвращает tg://login ссылку и срок её действия для входа в Telegram.",
)
async def tg_auth_qr_url(auth_service: AuthServicePort = Depends(get_auth_service)):
    try:
        login_url, expires_at = await auth_service.create_qr_url()
    except AlreadyAuthorizedError:
        return {"authorized": True, "message": "Already authorized"}
    except Exception as exc:
        raise_auth_http_error(exc, status_code_for_telegram_error=503)

    return {
        "authorized": False,
        "login_url": login_url,
        "expires_at": expires_at,
        "note": "Open this tg:// URL as QR in Telegram app",
    }


@router.post(
    "/auth/password",
    summary="Подтвердить вход паролем 2FA",
    description="Используется после QR-входа, если у Telegram-аккаунта включен пароль двухфакторной защиты.",
)
async def tg_auth_password(
    payload: PasswordRequest,
    auth_service: AuthServicePort = Depends(get_auth_service),
):
    if await auth_service.is_user_authorized():
        return {"message": "already authorized"}

    try:
        user = await auth_service.authorize_with_password(payload.password)
    except AlreadyAuthorizedError:
        return {"message": "already authorized"}
    except Exception as exc:
        raise_auth_http_error(exc, status_code_for_telegram_error=400)

    return build_auth_success_response(user)


@router.get(
    "/me",
    summary="Текущий Telegram-пользователь",
    description="Возвращает данные авторизованного Telegram-аккаунта.",
)
async def tg_me(auth_service: AuthServicePort = Depends(get_auth_service)):
    try:
        user = await auth_service.get_current_user()
    except Exception as exc:
        raise_auth_http_error(exc, status_code_for_telegram_error=503)

    return build_current_user_response(user)
