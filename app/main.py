from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import settings
from app.core.exceptions import NotFoundError

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AURA backend foundation for hydration intelligence and future wellness integrations.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.exception_handler(NotFoundError)
async def not_found_handler(_: object, exc: NotFoundError) -> dict[str, str]:
    return {"detail": exc.detail}
