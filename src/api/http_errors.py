from __future__ import annotations

import logging

from fastapi import HTTPException

from src.api.services.errors import (
    AIEnhancementError,
    AuthorizationRequiredError,
    TelegramOperationError,
)


def raise_audience_http_error(
    exc: Exception,
    *,
    logger: logging.Logger,
    unexpected_log_message: str,
) -> None:
    if isinstance(exc, AuthorizationRequiredError):
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if isinstance(exc, AIEnhancementError):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if isinstance(exc, TelegramOperationError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.exception(unexpected_log_message)
    raise HTTPException(status_code=500, detail=str(exc)) from exc


def raise_auth_http_error(
    exc: Exception,
    *,
    status_code_for_telegram_error: int = 503,
) -> None:
    if isinstance(exc, AuthorizationRequiredError):
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if isinstance(exc, TelegramOperationError):
        raise HTTPException(status_code=status_code_for_telegram_error, detail=str(exc)) from exc

    raise HTTPException(status_code=500, detail=str(exc)) from exc
