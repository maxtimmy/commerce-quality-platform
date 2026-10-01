from fastapi import FastAPI, HTTPException
from redis import Redis
from sqlalchemy import text

from app.catalog import router as catalog_router
from app.auth import router as auth_router
from app.config import settings
from app.database import engine

app = FastAPI(
    title="Commerce Quality Platform",
    description="Minimal commerce application designed as a reproducible QA stand.",
    version="0.1.0",
)

app.include_router(catalog_router)
app.include_router(auth_router)


@app.get("/health", tags=["system"], summary="Process health check")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "commerce-api"}


@app.get("/ready", tags=["system"], summary="Dependency readiness check")
def readiness() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        Redis.from_url(settings.redis_url, socket_connect_timeout=1).ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Service dependencies are unavailable") from exc
    return {"status": "ready", "postgres": "ok", "redis": "ok"}
