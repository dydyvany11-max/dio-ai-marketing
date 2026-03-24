import logging
import os

from fastapi import FastAPI

from src.api.routers.system import router as system_router
from src.api.routers.trends import router as trends_router
from src.api.routers.vk import router as vk_router
from src.api.routers.vkid import router as vkid_router
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="DIO AI Marketing API")

    app.include_router(system_router)

    app.include_router(vk_router)
    app.include_router(vkid_router)

    app.include_router(trends_router)

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
