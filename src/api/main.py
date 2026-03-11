import logging
import os

from fastapi import FastAPI

from src.api.config import is_telegram_configured
from src.api.dependencies import get_client_service
from src.api.routers.audience import router as audience_router
from src.api.routers.auth import router as auth_router
from src.api.routers.system import router as system_router
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="DIO AI Marketing API")

    app.include_router(system_router)

    if is_telegram_configured():
        @app.on_event("shutdown")
        async def shutdown() -> None:
            await get_client_service().disconnect()

        app.include_router(auth_router)
        app.include_router(audience_router)
    else:
        logger.warning(
            "Telegram routers disabled: set TG_API_ID and TG_API_HASH in .env"
        )

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("API_HOST", "127.0.0.1"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=os.getenv("API_RELOAD", "false").lower() == "true",
    )


if __name__ == "__main__":
    run()
