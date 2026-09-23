"""
FastAPI application entry point, lifecycle management, and CORS configuration.
Endpoints are defined in api/endpoints.py.
"""

from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from settings import settings
from api import endpoints
from api.endpoints import router as api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    endpoints.init_services()
    yield
    endpoints.shutdown_services()


app = FastAPI(
    title="InboxIQ API",
    description="Local privacy-first agentic Gmail assistant API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all API endpoints
app.include_router(api_router)

# Mount Frontend static files if present
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


# Expose singletons for backward compatibility and tests
def __getattr__(name: str):
    if hasattr(endpoints, name):
        return getattr(endpoints, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __setattr__(name: str, value):
    if name in ("llm", "db", "gmail_sync", "sync_job_state"):
        setattr(endpoints, name, value)
    else:
        super().__setattr__(name, value)
