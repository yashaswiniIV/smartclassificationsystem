import time
import uuid

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging

log = structlog.get_logger()

# Conservative security headers for every response (tightened further by Caddy in prod).
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-XSS-Protection": "0",
}


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    # Fail loud if a real deployment is still using the dev JWT secret.
    if settings.env != "dev" and settings.jwt_secret == "dev-secret-change-me-32-bytes-min!!":
        raise RuntimeError("Set a real JWT_SECRET before running outside dev")

    app = FastAPI(
        title="CivicPulse AI",
        version="0.1.0",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def observability(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:12])
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.monotonic()
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        elapsed = round((time.monotonic() - start) * 1000, 1)
        # Health checks are noisy; log everything else.
        if request.url.path != "/api/v1/health":
            log.info(
                "request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                ms=elapsed,
            )
        response.headers.update(SECURITY_HEADERS)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Never leak a stack trace to the client; log it, return a clean error shape.
        log.exception("unhandled_error", path=request.url.path)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "Something went wrong"}},
        )

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
