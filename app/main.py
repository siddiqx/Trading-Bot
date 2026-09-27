"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import get_settings
from app.utils.logging import logger
from app.api.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    settings = get_settings()
    logger.info(
        f"Server startup: {settings.PROJECT_NAME} v{settings.VERSION} "
        f"in {settings.ENVIRONMENT} mode."
    )
    from app.database.database import init_db
    init_db()
    logger.info("Database initialized successfully.")

    # Start Telegram interactive bot polling listener
    from app.services.telegram import TelegramService
    telegram_service = TelegramService()
    stop_polling = asyncio.Event()
    polling_task = asyncio.create_task(telegram_service.run_polling(stop_polling))

    yield

    stop_polling.set()
    polling_task.cancel()
    try:
        await polling_task
    except (asyncio.CancelledError, Exception):
        pass
    logger.info("Server shutdown completed.")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        lifespan=lifespan,
    )

    # Register routers
    app.include_router(health_router)
    from app.api.webhook import router as webhook_router
    app.include_router(webhook_router)

    return app


app = create_app()
