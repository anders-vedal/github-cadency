import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api import ai_analysis, developers, goals, oauth, stats, sync, webhooks
from app.config import settings
from app.models.database import AsyncSessionLocal
from app.models.models import SyncEvent
from app.services.github_sync import run_sync

logger = logging.getLogger(__name__)


async def scheduled_sync(sync_type: str) -> None:
    """Wrapper for scheduled sync jobs with concurrency check."""
    async with AsyncSessionLocal() as db:
        active = await db.execute(
            select(SyncEvent).where(SyncEvent.status == "started")
        )
        if active.scalar_one_or_none():
            logger.info(
                "Skipping scheduled %s sync — another sync in progress", sync_type
            )
            return
    await run_sync(sync_type)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — schedule sync jobs
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        scheduled_sync,
        "interval",
        args=["incremental"],
        minutes=settings.sync_interval_minutes,
        id="incremental_sync",
    )
    scheduler.add_job(
        scheduled_sync,
        "cron",
        args=["full"],
        hour=settings.full_sync_cron_hour,
        id="full_sync",
    )
    scheduler.start()
    logger.info(
        "Scheduler started: incremental every %dm, full at %d:00",
        settings.sync_interval_minutes,
        settings.full_sync_cron_hour,
    )

    yield

    # Shutdown
    scheduler.shutdown(wait=True)


app = FastAPI(
    title="DevPulse",
    description="Engineering intelligence dashboard",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(oauth.router, prefix="/api", tags=["auth"])
app.include_router(developers.router, prefix="/api", tags=["developers"])
app.include_router(stats.router, prefix="/api", tags=["stats"])
app.include_router(sync.router, prefix="/api", tags=["sync"])
app.include_router(webhooks.router, prefix="/api", tags=["webhooks"])
app.include_router(goals.router, prefix="/api", tags=["goals"])
app.include_router(ai_analysis.router, prefix="/api", tags=["ai"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}
