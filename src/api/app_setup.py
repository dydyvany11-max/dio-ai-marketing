from __future__ import annotations

import logging

from fastapi import FastAPI

from src.api.config import is_telegram_configured
from src.api.routers.audience import router as audience_router
from src.api.routers.auth import router as auth_router
from src.api.routers.system import router as system_router
from src.api.service_container import get_service_container

logger = logging.getLogger(__name__)


def configure_routes(app: FastAPI) -> None:
    app.include_router(system_router)

    if not is_telegram_configured():
        logger.warning("Telegram routers disabled: set TG_API_ID and TG_API_HASH in .env")
        return

    app.include_router(auth_router)
    app.include_router(audience_router)


def configure_lifecycle(app: FastAPI) -> None:
    if not is_telegram_configured():
        return

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await get_service_container().client_service.disconnect()
