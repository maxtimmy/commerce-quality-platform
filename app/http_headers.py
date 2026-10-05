from fastapi import FastAPI, Request, Response


def add_api_security_headers(application: FastAPI) -> None:
    """Add defensive headers shared by every JSON API in the QA stand."""

    @application.middleware("http")
    async def security_headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
