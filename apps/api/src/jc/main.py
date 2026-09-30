import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy import text
from starlette.exceptions import HTTPException

from jc.config import get_settings
from jc.db import engine
from jc.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from jc.jobs import Coordinator, start_scheduler

    coordinator = Coordinator(get_settings())
    app.state.coordinator = coordinator
    scheduler = None
    if get_settings().app_env != "test":
        coordinator.initialize_states()
        if get_settings().scheduler_enabled:
            scheduler = start_scheduler(coordinator)
    yield
    if scheduler:
        scheduler.shutdown(wait=False)
    await coordinator.close()


app = FastAPI(title="竞彩智研 / JC Football Intelligence", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)


def envelope(request: Request, data):
    return {"success": True, "data": data, "request_id": request.state.request_id}


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = str(uuid4())
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(
            "Request failed",
            extra={
                "request_id": request.state.request_id,
                "operation": request.url.path,
                "status": "FAILED",
                "error_code": type(exc).__name__,
            },
        )
        response = JSONResponse(
            status_code=500,
            content={
                "success": False,
                "data": None,
                "error": {"code": "INTERNAL_ERROR", "message": "服务处理失败，请根据 request_id 查看日志"},
                "request_id": request.state.request_id,
            },
        )
    response.headers["X-Request-ID"] = request.state.request_id
    logger.info(
        "request",
        extra={
            "operation": request.url.path,
            "request_id": request.state.request_id,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "status": response.status_code,
        },
    )
    return response


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={
            "success": False,
            "data": None,
            "error": {"code": str(exc.status_code), "message": exc.detail},
            "request_id": request.state.request_id,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Never echo passwords/tokens or arbitrary request bodies in validation errors.
    errors = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder(
            {
                "success": False,
                "data": None,
                "error": {"code": "VALIDATION", "message": errors},
                "request_id": request.state.request_id,
            }
        ),
    )


@app.get("/health")
def health(request: Request):
    return envelope(request, {"status": "ok"})


@app.get("/ready")
def ready(request: Request):
    checks = {"postgres": False, "redis": False}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            checks["postgres"] = engine.dialect.name == "postgresql"
    except Exception:
        pass
    try:
        with Redis.from_url(settings.redis_url, socket_timeout=2, socket_connect_timeout=2) as client:
            checks["redis"] = bool(client.ping())
    except Exception:
        pass
    ok = all(checks.values())
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"success": ok, "data": checks, "request_id": request.state.request_id},
    )


@app.get("/api/v1/system/info")
def system_info(request: Request):
    return envelope(
        request,
        {
            "name": "竞彩智研",
            "version": "0.1.0",
            "phase": "4 (P4-0–P4-2)",
            "demo_mode": settings.demo_mode,
            "timezone": "UTC",
            "display_timezone": "Asia/Shanghai",
        },
    )


from jc.api import router  # noqa: E402

app.include_router(router)
from jc.admin import router as admin_router  # noqa: E402
from jc.auth import router as auth_router  # noqa: E402

app.include_router(auth_router)
app.include_router(admin_router)
from jc.odds_api import router as odds_router  # noqa: E402

app.include_router(odds_router)
from jc.quality import router as quality_router  # noqa: E402

app.include_router(quality_router)
