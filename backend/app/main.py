import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import select

# Configure structured logging before any logger is created
from app.config import settings
from app.logging import LoggingContextMiddleware, configure_logging, get_logger

configure_logging(
    level=settings.log_level,
    json_output=settings.log_format == "json",
)

from app.api import ai_analysis, developers, goals, logs, notifications, oauth, relationships, roles, slack, stats, sync, teams, webhooks, work_categories  # noqa: E402
from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.models import NotificationConfig, Repository, SyncEvent, SyncScheduleConfig  # noqa: E402
from app.services.github_sync import run_sync  # noqa: E402

logger = get_logger(__name__)


def reschedule_sync_jobs(config: SyncScheduleConfig, scheduler: AsyncIOScheduler | None = None) -> None:
    """Reschedule APScheduler sync jobs based on updated config.

    Called from the PATCH /sync/schedule endpoint.
    """
    if scheduler is None:
        logger.warning("Cannot reschedule — scheduler not available", event_type="system.scheduler")
        return

    # Incremental sync job
    try:
        scheduler.remove_job("incremental_sync")
    except Exception:
        pass
    if config.auto_sync_enabled:
        scheduler.add_job(
            scheduled_sync,
            "interval",
            args=["incremental"],
            minutes=config.incremental_interval_minutes,
            id="incremental_sync",
        )

    # Full sync cron job
    try:
        scheduler.remove_job("full_sync")
    except Exception:
        pass
    if config.auto_sync_enabled:
        scheduler.add_job(
            scheduled_sync,
            "cron",
            args=["full"],
            hour=config.full_sync_cron_hour,
            id="full_sync",
            misfire_grace_time=None,
        )

    logger.info(
        "Rescheduled sync jobs",
        enabled=config.auto_sync_enabled,
        interval_minutes=config.incremental_interval_minutes,
        full_hour=config.full_sync_cron_hour,
        event_type="system.scheduler",
    )


async def scheduled_sync(sync_type: str) -> None:
    """Wrapper for scheduled sync jobs with concurrency and auto_sync_enabled check."""
    async with AsyncSessionLocal() as db:
        # Check if auto-sync is enabled
        schedule_config = await db.get(SyncScheduleConfig, 1)
        if schedule_config and not schedule_config.auto_sync_enabled:
            logger.info("Skipping scheduled sync — auto-sync is disabled", sync_type=sync_type, event_type="system.scheduler")
            return

        active = await db.execute(
            select(SyncEvent).where(SyncEvent.status == "started")
        )
        if active.scalar_one_or_none():
            logger.info(
                "Skipping scheduled sync — another sync in progress",
                sync_type=sync_type, event_type="system.scheduler",
            )
            return

    scope = f"All tracked repos · {'nightly full resync' if sync_type == 'full' else 'incremental'}"
    await run_sync(sync_type, triggered_by="scheduled", sync_scope=scope)


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
                "Found orphaned sync event — force-stopping",
                sync_event_id=event.id,
                started_at=str(event.started_at),
                repo=event.current_repo_name or "unknown",
                event_type="system.sync",
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
                "Auto-resuming sync",
                sync_event_id=most_recent.id, remaining_repos=len(remaining),
                event_type="system.sync",
            )
            asyncio.create_task(run_sync(
                most_recent.sync_type or "incremental",
                remaining,
                most_recent.since_override,
                most_recent.id,
                "auto_resume",  # triggered_by
                most_recent.sync_scope,  # preserve original scope
            ))
        else:
            logger.info("Orphaned sync had no remaining repos", sync_event_id=most_recent.id, event_type="system.sync")


def _log_config_warnings() -> None:
    """Log warnings for missing GitHub App configuration at startup."""
    from app.config import validate_github_config

    checks = validate_github_config()
    errors = [c for c in checks if c["status"] == "error"]
    warns = [c for c in checks if c["status"] == "warn"]
    if errors:
        logger.warning(
            "GitHub App config has errors — sync will fail until fixed",
            error_count=len(errors), event_type="system.config",
        )
        for c in errors:
            logger.warning("Config error", field=c["field"], message=c["message"], event_type="system.config")
    for c in warns:
        logger.warning("Config warning", field=c["field"], message=c["message"], event_type="system.config")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _log_config_warnings()

    # Recover any syncs orphaned by a previous crash
    try:
        await _recover_orphaned_syncs()
    except Exception as e:
        logger.error("Failed to recover orphaned syncs", error=str(e), event_type="system.sync")

    # Load sync schedule config from DB (fall back to env var defaults)
    interval_minutes = settings.sync_interval_minutes
    full_hour = settings.full_sync_cron_hour
    auto_enabled = True
    try:
        async with AsyncSessionLocal() as db:
            config_row = await db.get(SyncScheduleConfig, 1)
            if config_row:
                interval_minutes = config_row.incremental_interval_minutes
                full_hour = config_row.full_sync_cron_hour
                auto_enabled = config_row.auto_sync_enabled
    except Exception as e:
        logger.warning("Could not load sync schedule config — using env defaults", error=str(e), event_type="system.config")

    # Startup — schedule sync jobs
    scheduler = AsyncIOScheduler()
    if auto_enabled:
        scheduler.add_job(
            scheduled_sync,
            "interval",
            args=["incremental"],
            minutes=interval_minutes,
            id="incremental_sync",
        )
        scheduler.add_job(
            scheduled_sync,
            "cron",
            args=["full"],
            hour=full_hour,
            id="full_sync",
            misfire_grace_time=None,  # Run even after restart
        )
    # Notification evaluation scheduled job
    from app.services.notifications import evaluate_all_alerts as _eval_alerts

    async def scheduled_notification_evaluation() -> None:
        async with AsyncSessionLocal() as db:
            try:
                await _eval_alerts(db)
            except Exception as e:
                logger.warning("Scheduled notification evaluation failed", error=str(e), event_type="system.notifications")

    eval_interval = 15
    try:
        async with AsyncSessionLocal() as db:
            nc = await db.get(NotificationConfig, 1)
            if nc:
                eval_interval = nc.evaluation_interval_minutes
    except Exception:
        pass

    scheduler.add_job(
        scheduled_notification_evaluation,
        "interval",
        minutes=eval_interval,
        id="notification_evaluation",
        misfire_grace_time=None,
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
    app.state.scheduler = scheduler
    if auto_enabled:
        logger.info(
            "Scheduler started",
            interval_minutes=interval_minutes, full_hour=full_hour,
            event_type="system.startup",
        )
    else:
        logger.info("Scheduler started: auto-sync is disabled", event_type="system.startup")

    yield

    # Shutdown
    scheduler.shutdown(wait=True)


app = FastAPI(
    title="DevPulse",
    description="Engineering intelligence dashboard",
    version="0.1.0",
    lifespan=lifespan,
)


from app.rate_limit import limiter  # noqa: E402 — must be after settings import

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Middleware is LIFO — last added = outermost.
# LoggingContext added first so it's innermost (closest to route handlers).
app.add_middleware(LoggingContextMiddleware)
app.add_middleware(SlowAPIMiddleware)
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
app.include_router(roles.router, prefix="/api", tags=["roles"])
app.include_router(teams.router, prefix="/api", tags=["teams"])
app.include_router(logs.router, prefix="/api", tags=["logs"])
app.include_router(work_categories.router, prefix="/api", tags=["work-categories"])
app.include_router(notifications.router, prefix="/api", tags=["notifications"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}
