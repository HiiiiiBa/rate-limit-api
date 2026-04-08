from contextlib import asynccontextmanager

import asyncio
import logging
import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import metrics
from dashboard_routes import broadcast_loop, router as dashboard_router
from rate_limiter import check_rate_limit, get_client_key, get_window_usage


def _is_dashboard_path(path: str) -> bool:
    return path.startswith("/api/dashboard") or path.startswith("/dashboard")


def _configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


_configure_logging()
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(broadcast_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Rate limit API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # Pour la soutenance, c'est OK. En prod stricte, mets l'URL du dashboard/front.
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(",") if os.getenv("CORS_ORIGINS") else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def limit_and_metrics_middleware(request: Request, call_next):
    path = request.url.path

    if not _is_dashboard_path(path):
        try:
            key, usage_after, lim = check_rate_limit(request)
        except HTTPException as e:
            if e.status_code == 429:
                key = get_client_key(request)
                usage, lim = get_window_usage(key)
                metrics.record_request(
                    key,
                    path,
                    429,
                    lim,
                    usage,
                )
            logger.warning("request_blocked path=%s status=%s detail=%s", path, e.status_code, e.detail)
            return JSONResponse(status_code=e.status_code, content={"detail": e.detail})

        response = await call_next(request)
        metrics.record_request(key, path, response.status_code, lim, usage_after)
        return response

    return await call_next(request)


app.include_router(dashboard_router)

app.mount(
    "/dashboard",
    StaticFiles(directory="static/dashboard", html=True),
    name="dashboard",
)


@app.get("/")
def home():
    return {
        "message": "API fonctionne",
        "dashboard": "/dashboard/",
    }


@app.get("/users")
def users():
    return {"users": ["Ahmed", "Sara", "Ali"]}


@app.get("/products")
def products():
    return {"products": ["Laptop", "Phone", "Tablet"]}
