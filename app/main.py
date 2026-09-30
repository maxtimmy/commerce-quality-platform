from fastapi import FastAPI

app = FastAPI(
    title="Commerce Quality Platform",
    description="Minimal commerce application designed as a reproducible QA stand.",
    version="0.1.0",
)


@app.get("/health", tags=["system"], summary="Process health check")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "commerce-api"}
