import logging

from fastapi import FastAPI

from src.api.app_setup import configure_lifecycle, configure_routes
from src.api.config import get_app_settings

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="DIO AI Marketing API")
    configure_routes(app)
    configure_lifecycle(app)
    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_app_settings()

    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )


if __name__ == "__main__":
    run()
