from app.core.config import settings
from sqlalchemy import text
from app.database import engine
from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.water import router as water_router
from app.api.hydration import router as hydration_router
from app.api.health_data import router as health_data_router
from app.api.sensor_records import router as sensor_records_router
from app.api.activity import router as activity_router
from app.api.wellness import router as wellness_router

router = APIRouter()

# Include auth and user routers
router.include_router(auth_router)
router.include_router(users_router)
router.include_router(water_router)
router.include_router(hydration_router)
router.include_router(health_data_router)
router.include_router(sensor_records_router)
router.include_router(activity_router)
router.include_router(wellness_router)


@router.get("/")
def read_root() -> dict[str, str]:
    """Return the application identity payload."""
    return {
        "app": "AURA",
        "status": "running",
        "version": settings.app_version,
    }


@router.get("/health")
def health_check() -> dict[str, str]:
    """Return a simple health response."""
    return {"status": "ok", "service": settings.app_name}


@router.get("/db-health")
def db_health_check() -> dict[str, str]:
    """Check PostgreSQL connectivity by executing a simple query."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            # SQLAlchemy 2.x returns a Result; fetch scalar
            scalar = result.scalar()
            if scalar == 1:
                return {"db_status": "ok"}
    except Exception as exc:  # pragma: no cover - runtime check
        return {"db_status": "error", "detail": str(exc)}
    return {"db_status": "unknown"}
