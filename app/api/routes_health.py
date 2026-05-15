"""健康检查路由。"""

from fastapi import APIRouter

from app.config import get_settings
from app.storage.database import check_database

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    settings = get_settings()
    db_ok, db_message = await check_database()
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else f"error:{db_message}",
        "environment": settings.env,
    }
