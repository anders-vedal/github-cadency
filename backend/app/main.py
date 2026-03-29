import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api import ai_analysis, developers, goals, oauth, relationships, slack, stats, sync, webhooks
from app.config import settings
from app.models.database import AsyncSessionLocal
from app.models.models import Repository, SyncEvent
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


async def _recover_orphaned_syncs() -> None:
    """Detect syncs stuck in 'started' from a previous crash and auto-resume them.

    On startup, any SyncEvent with status='started' is an orphan — the process
    that was running it died. We force-stop it (making it resumable), then
    kick off a resume in the background.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SyncEvent).where(SyncEvent.status == "started")
        )
        orphaned = result.scalars().all()
        if not orphaned:
            return

        for event in orphaned:
            logger.warning(
                "Found orphaned sync event #%d (started %s, repo: %s) — force-stopping",
                event.id,
                event.started_at,
                event.current_repo_name or "unknown",
            )
            now = datetime.now(timezone.utc)
            event.status = "cancelled"
            event.is_resumable = True
            event.cancel_requested = False
            event.current_repo_name = None
            event.current_step = None
            event.completed_at = now
            if event.started_at:
                event.duration_s = int((now - event.started_at).total_seconds())

        await db.commit()

        # Auto-resume the most recent orphaned sync
        most_recent = max(orphaned, key=lambda e: e.started_at or datetime.min.replace(tzinfo=timezone.utc))

        # Compute remaining repos
        completed_ids = {r["repo_id"] for r in (most_recent.repos_completed or [])}
        if most_recent.repo_ids:
            remaining = [rid for rid in most_recent.repo_ids if rid not in completed_ids]
        else:
            result = await db.execute(
                select(Repository.id).where(Repository.is_tracked.is_(True))
            )
            all_tracked = set(result.scalars().all())
            remaining = list(all_tracked - completed_ids)

        if remaining:
            logger.info(
                "Auto-resuming sync #%d with %d remaining repos",
                most_recent.id, len(remaining),
            )
            asyncio.create_task(run_sync(
                most_recent.sync_type or "incremental",
                remaining,
                most_recent.since_override,
                most_recent.id,
            ))
        else:
            logger.info("Orphaned sync #%d had no remaining repos", most_recent.id)


def _log_config_warnings() -> None:
    """Log warnings for missing GitHub App configuration at startup."""
    from app.config import validate_github_config

    checks = validate_github_config()
    errors = [c for c in checks if c["status"] == "error"]
    warns = [c for c in checks if c["status"] == "warn"]
    if errors:
        logger.warning(
            "GitHub App config has %d error(s) — sync will fail until fixed:", len(errors)
        )
        for c in errors:
            logger.warning("  [%s] %s", c["field"], c["message"])
    for c in warns:
        logger.warning("Config warning [%s]: %s", c["field"], c["message"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    _log_config_warnings()

    # Recover any syncs orphaned by a previous crash
    try:
        await _recover_orphaned_syncs()
    except Exception as e:
        logger.error("Failed to recover orphaned syncs: %s", e)

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
        misfire_grace_time=None,  # Run even after restart
    )
    # Slack notification scheduled jobs — run hourly, check configured schedule at runtime
    from app.services.slack import scheduled_stale_pr_check, scheduled_weekly_digest

    scheduler.add_job(
        scheduled_stale_pr_check,
        "cron",
        minute=5,
        id="slack_stale_pr_check",
        misfire_grace_time=None,
    )
    scheduler.add_job(
        scheduled_weekly_digest,
        "cron",
        minute=10,
        id="slack_weekly_digest",
        misfire_grace_time=None,
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
app.include_router(relationships.router, prefix="/api", tags=["relationships"])
app.include_router(slack.router, prefix="/api", tags=["slack"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}
