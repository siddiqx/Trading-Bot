"""Health check endpoint router."""

from fastapi import APIRouter
from app.config import get_settings

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    """Health check endpoint for uptime and container orchestration monitoring."""
    settings = get_settings()
    return {
        "status": "ok",
        "service": "forex-signal-bot",
        "version": settings.VERSION,
    }
