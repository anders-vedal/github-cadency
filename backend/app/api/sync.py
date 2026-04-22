from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_admin
from app.models.database import get_db
from app.rate_limit import limiter
from app.models.models import (
    Deployment,
    Issue,
    IssueComment,
    PRCheckRun,
    PRExternalIssueLink,
    PRFile,
    PRReview,
    PRReviewComment,
    PullRequest,
    Repository,
    RepoTreeFile,
    SyncEvent,
    SyncScheduleConfig,
)
from app.config import validate_github_config
from app.schemas.schemas import (
    PreflightCheck,
    PreflightResponse,
    RepoDataDeletedCounts,
    RepoDataDeleteResponse,
    RepoResponse,
    RepoTrackUpdate,
    SyncEventResponse,
    SyncScheduleConfigResponse,
    SyncScheduleConfigUpdate,
    SyncStatusResponse,
    SyncTriggerRequest,
)
from app.services.github_sync import (
    GitHubAuthError,
    discover_org_repos,
    run_contributor_sync,
    run_sync,
)

router = APIRouter(dependencies=[Depends(require_admin)])


# --- Sync Triggers ---


@router.post("/sync/start", status_code=202)
@limiter.limit("5/minute")
async def start_sync(
    request: Request,
    body: SyncTriggerRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Start a new sync. Returns 409 if a sync is already running."""
    active = await db.execute(
        select(SyncEvent).where(SyncEvent.status == "started").limit(1)
    )
    if active.scalar_one_or_none():
        raise HTTPException(409, "A sync is already in progress")

    # Create SyncEvent immediately so the frontend sees it on the next status poll
    sync_event = SyncEvent(
        sync_type=body.sync_type,
        status="started",
        started_at=datetime.now(timezone.utc),
        repos_synced=0,
        prs_upserted=0,
        issues_upserted=0,
        errors=[],
        repo_ids=body.repo_ids,
        since_override=body.since,
        repos_completed=[],
        repos_failed=[],
        log_summary=[],
        is_resumable=False,
        rate_limit_wait_s=0,
        triggered_by="manual",
        sync_scope=body.sync_scope,
    )
    db.add(sync_event)
    await db.commit()
    await db.refresh(sync_event)

    background_tasks.add_task(
        run_sync,
        body.sync_type,
        body.repo_ids,
        body.since,
        None,  # resumed_from_id
        "manual",  # triggered_by
        body.sync_scope,  # sync_scope
        sync_event.id,  # sync_event_id — use pre-created event
    )
    return SyncEventResponse.model_validate(sync_event)


@router.post("/sync/resume/{event_id}", status_code=202)
async def resume_sync(
    event_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Resume an interrupted sync, processing only remaining repos."""
    # Concurrency guard
    active = await db.execute(
        select(SyncEvent).where(SyncEvent.status == "started").limit(1)
    )
    if active.scalar_one_or_none():
        raise HTTPException(409, "A sync is already in progress")

    original = await db.get(SyncEvent, event_id)
    if not original:
        raise HTTPException(404, "Sync event not found")
    if not original.is_resumable:
        raise HTTPException(400, "This sync event is not resumable")

    # Compute remaining repo IDs
    completed_ids = {r["repo_id"] for r in (original.repos_completed or [])}

    if original.repo_ids:
        remaining = [rid for rid in original.repo_ids if rid not in completed_ids]
    else:
        # Original was "all tracked" — get current tracked minus completed
        result = await db.execute(
            select(Repository.id).where(Repository.is_tracked.is_(True))
        )
        all_tracked = set(result.scalars().all())
        remaining = list(all_tracked - completed_ids)

    if not remaining:
        raise HTTPException(400, "No remaining repos to sync")

    # Create SyncEvent immediately so the frontend sees it on the next status poll
    sync_event = SyncEvent(
        sync_type=original.sync_type or "incremental",
        status="started",
        started_at=datetime.now(timezone.utc),
        repos_synced=0,
        prs_upserted=0,
        issues_upserted=0,
        errors=[],
        repo_ids=remaining,
        since_override=original.since_override,
        resumed_from_id=event_id,
        repos_completed=[],
        repos_failed=[],
        log_summary=[],
        is_resumable=False,
        rate_limit_wait_s=0,
        triggered_by="auto_resume",
        sync_scope=original.sync_scope,
    )
    db.add(sync_event)
    await db.commit()
    await db.refresh(sync_event)

    background_tasks.add_task(
        run_sync,
        original.sync_type or "incremental",
        remaining,
        original.since_override,
        event_id,
        "auto_resume",  # triggered_by
        original.sync_scope,  # preserve original scope
        sync_event.id,  # sync_event_id — use pre-created event
    )
    return SyncEventResponse.model_validate(sync_event)


@router.post("/sync/cancel", status_code=200)
async def cancel_sync(db: AsyncSession = Depends(get_db)):
    """Request cancellation of the active sync."""
    active = await db.execute(
        select(SyncEvent).where(SyncEvent.status == "started").limit(1)
    )
    event = active.scalar_one_or_none()
    if not event:
        raise HTTPException(404, "No active sync to cancel")

    event.cancel_requested = True
    await db.commit()
    return {"status": "cancel_requested", "event_id": event.id}


@router.post("/sync/contributors", status_code=202)
async def sync_contributors(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Sync org members from GitHub and backfill author links on existing data.

    This does NOT run a full data sync — it only discovers contributors and
    links them to existing PRs/reviews/issues. Returns 409 if a sync is running.
    """
    active = await db.execute(
        select(SyncEvent).where(SyncEvent.status == "started").limit(1)
    )
    if active.scalar_one_or_none():
        raise HTTPException(409, "A sync is already in progress")

    background_tasks.add_task(run_contributor_sync)
    return {"status": "accepted"}


@router.post("/sync/force-stop", status_code=200)
async def force_stop_sync(db: AsyncSession = Depends(get_db)):
    """Force-stop a stale sync by marking it as failed + resumable."""
    active = await db.execute(
        select(SyncEvent).where(SyncEvent.status == "started").limit(1)
    )
    event = active.scalar_one_or_none()
    if not event:
        raise HTTPException(404, "No active sync to stop")

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
    return {"status": "force_stopped", "event_id": event.id}


# --- Sync Status ---


async def _build_sync_status(db: AsyncSession) -> SyncStatusResponse:
    """Assemble sync status from DB queries."""
    active_result = await db.execute(
        select(SyncEvent)
        .where(SyncEvent.status == "started")
        .order_by(SyncEvent.started_at.desc())
        .limit(1)
    )
    active_event = active_result.scalar_one_or_none()

    last_result = await db.execute(
        select(SyncEvent)
        .where(SyncEvent.status.in_(["completed", "completed_with_errors", "failed", "cancelled"]))
        .order_by(SyncEvent.completed_at.desc())
        .limit(1)
    )
    last_event = last_result.scalar_one_or_none()

    tracked_count = await db.scalar(
        select(func.count()).select_from(Repository).where(
            Repository.is_tracked.is_(True)
        )
    ) or 0
    total_count = await db.scalar(
        select(func.count()).select_from(Repository)
    ) or 0

    last_success_result = await db.execute(
        select(SyncEvent)
        .where(SyncEvent.status == "completed")
        .order_by(SyncEvent.completed_at.desc())
        .limit(1)
    )
    last_success = last_success_result.scalar_one_or_none()

    schedule_row = await db.get(SyncScheduleConfig, 1)
    schedule = SyncScheduleConfigResponse.model_validate(schedule_row) if schedule_row else SyncScheduleConfigResponse()

    return SyncStatusResponse(
        active_sync=active_event,
        last_completed=last_event,
        tracked_repos_count=tracked_count,
        total_repos_count=total_count,
        last_successful_sync=last_success.completed_at if last_success else None,
        last_sync_duration_s=last_success.duration_s if last_success else None,
        schedule=schedule,
    )


@router.get("/sync/status", response_model=SyncStatusResponse)
async def sync_status(db: AsyncSession = Depends(get_db)):
    """Get current sync status: active sync + summary stats."""
    return await _build_sync_status(db)


# --- Schedule Config ---


@router.get("/sync/schedule", response_model=SyncScheduleConfigResponse)
async def get_schedule(db: AsyncSession = Depends(get_db)):
    """Get the sync schedule configuration."""
    row = await db.get(SyncScheduleConfig, 1)
    if not row:
        return SyncScheduleConfigResponse()
    return row


@router.patch("/sync/schedule", response_model=SyncScheduleConfigResponse)
async def update_schedule(
    data: SyncScheduleConfigUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Update sync schedule config and reschedule APScheduler jobs."""
    row = await db.get(SyncScheduleConfig, 1)
    if not row:
        row = SyncScheduleConfig(id=1)
        db.add(row)

    if data.auto_sync_enabled is not None:
        row.auto_sync_enabled = data.auto_sync_enabled
    if data.incremental_interval_minutes is not None:
        if data.incremental_interval_minutes < 5:
            raise HTTPException(400, "Minimum interval is 5 minutes")
        row.incremental_interval_minutes = data.incremental_interval_minutes
    if data.full_sync_cron_hour is not None:
        if not (0 <= data.full_sync_cron_hour <= 23):
            raise HTTPException(400, "Hour must be 0-23")
        row.full_sync_cron_hour = data.full_sync_cron_hour

    await db.commit()
    await db.refresh(row)

    # Reschedule APScheduler jobs via app.state
    from app.main import reschedule_sync_jobs
    reschedule_sync_jobs(row, getattr(request.app.state, 'scheduler', None))

    return row


# --- Repo Management ---


@router.get("/sync/preflight", response_model=PreflightResponse)
async def preflight():
    """Check GitHub App configuration before attempting a sync."""
    checks = validate_github_config()
    ready = all(c["status"] != "error" for c in checks)
    return PreflightResponse(
        checks=[PreflightCheck(**c) for c in checks],
        ready=ready,
    )


@router.post("/sync/discover-repos", response_model=list[RepoResponse])
async def discover_repos(db: AsyncSession = Depends(get_db)):
    """Fetch repos from the GitHub org and upsert them into the database.

    This does NOT run a full sync — it only discovers repos so users can
    select which ones to track/sync.
    """
    try:
        await discover_org_repos(db)
    except GitHubAuthError as e:
        raise HTTPException(status_code=422, detail=f"{e} — Hint: {e.hint}")
    except httpx.HTTPStatusError as e:
        github_msg = ""
        try:
            github_msg = e.response.json().get("message", "")
        except Exception:
            pass
        detail = f"GitHub API error (HTTP {e.response.status_code})"
        if github_msg:
            detail += f": {github_msg}"
        raise HTTPException(status_code=502, detail=detail)

    # Return the full repo list (same as GET /sync/repos)
    return await _list_repos_query(db)


async def _list_repos_query(db: AsyncSession) -> list[dict]:
    """Shared repo listing query used by both list and discover endpoints."""
    pr_count_sq = (
        select(
            PullRequest.repo_id,
            func.count().label("pr_count"),
        )
        .group_by(PullRequest.repo_id)
        .subquery()
    )
    issue_count_sq = (
        select(
            Issue.repo_id,
            func.count().label("issue_count"),
        )
        .group_by(Issue.repo_id)
        .subquery()
    )

    result = await db.execute(
        select(
            Repository,
            func.coalesce(pr_count_sq.c.pr_count, 0).label("pr_count"),
            func.coalesce(issue_count_sq.c.issue_count, 0).label("issue_count"),
        )
        .outerjoin(pr_count_sq, Repository.id == pr_count_sq.c.repo_id)
        .outerjoin(issue_count_sq, Repository.id == issue_count_sq.c.repo_id)
        .order_by(Repository.full_name)
    )

    repos = []
    for row in result.all():
        repo = row[0]
        repos.append({
            "id": repo.id,
            "github_id": repo.github_id,
            "name": repo.name,
            "full_name": repo.full_name,
            "description": repo.description,
            "language": repo.language,
            "is_tracked": repo.is_tracked,
            "last_synced_at": repo.last_synced_at,
            "created_at": repo.created_at,
            "pr_count": row[1],
            "issue_count": row[2],
        })
    return repos


@router.get("/sync/repos", response_model=list[RepoResponse])
async def list_repos(db: AsyncSession = Depends(get_db)):
    """List all repos with PR and issue counts."""
    return await _list_repos_query(db)


@router.patch("/sync/repos/{repo_id}/track", response_model=RepoResponse)
async def toggle_tracking(
    repo_id: int,
    data: RepoTrackUpdate,
    db: AsyncSession = Depends(get_db),
):
    repo = await db.get(Repository, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    repo.is_tracked = data.is_tracked
    await db.commit()
    await db.refresh(repo)

    # Get counts for this repo
    pr_count = await db.scalar(
        select(func.count()).select_from(PullRequest).where(
            PullRequest.repo_id == repo_id
        )
    ) or 0
    issue_count = await db.scalar(
        select(func.count()).select_from(Issue).where(Issue.repo_id == repo_id)
    ) or 0

    return RepoResponse(
        id=repo.id,
        github_id=repo.github_id,
        name=repo.name,
        full_name=repo.full_name,
        description=repo.description,
        language=repo.language,
        is_tracked=repo.is_tracked,
        last_synced_at=repo.last_synced_at,
        created_at=repo.created_at,
        pr_count=pr_count,
        issue_count=issue_count,
    )


@router.delete("/sync/repos/{repo_id}/data", response_model=RepoDataDeleteResponse)
async def delete_repo_data(
    repo_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Purge all synced data for a repo (PRs, issues, reviews, deployments, tree files).

    Keeps the repository row but marks it untracked and clears last_synced_at, so a
    future sync won't pull data for this repo unless the admin re-enables tracking.
    """
    repo = await db.get(Repository, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    pr_ids = (await db.scalars(
        select(PullRequest.id).where(PullRequest.repo_id == repo_id)
    )).all()
    issue_ids = (await db.scalars(
        select(Issue.id).where(Issue.repo_id == repo_id)
    )).all()

    counts = {
        "pr_reviews": 0,
        "pr_review_comments": 0,
        "pr_files": 0,
        "pr_check_runs": 0,
        "pr_external_issue_links": 0,
        "pull_requests": 0,
        "issue_comments": 0,
        "issues": 0,
        "deployments": 0,
        "repo_tree_files": 0,
    }

    if pr_ids:
        for model, key in (
            (PRReviewComment, "pr_review_comments"),
            (PRReview, "pr_reviews"),
            (PRFile, "pr_files"),
            (PRCheckRun, "pr_check_runs"),
        ):
            res = await db.execute(delete(model).where(model.pr_id.in_(pr_ids)))
            counts[key] = res.rowcount or 0
        res = await db.execute(
            delete(PRExternalIssueLink).where(PRExternalIssueLink.pull_request_id.in_(pr_ids))
        )
        counts["pr_external_issue_links"] = res.rowcount or 0
        res = await db.execute(delete(PullRequest).where(PullRequest.repo_id == repo_id))
        counts["pull_requests"] = res.rowcount or 0

    if issue_ids:
        res = await db.execute(
            delete(IssueComment).where(IssueComment.issue_id.in_(issue_ids))
        )
        counts["issue_comments"] = res.rowcount or 0
        res = await db.execute(delete(Issue).where(Issue.repo_id == repo_id))
        counts["issues"] = res.rowcount or 0

    # Null out recovery_deployment_id self-refs before deleting deployments
    await db.execute(
        update(Deployment)
        .where(Deployment.repo_id == repo_id)
        .values(recovery_deployment_id=None)
    )
    res = await db.execute(delete(Deployment).where(Deployment.repo_id == repo_id))
    counts["deployments"] = res.rowcount or 0

    res = await db.execute(delete(RepoTreeFile).where(RepoTreeFile.repo_id == repo_id))
    counts["repo_tree_files"] = res.rowcount or 0

    repo.is_tracked = False
    repo.last_synced_at = None
    await db.commit()

    return RepoDataDeleteResponse(
        repo_id=repo.id,
        full_name=repo.full_name,
        deleted=RepoDataDeletedCounts(**counts),
    )


# --- Sync History ---


@router.get("/sync/events/{event_id}", response_model=SyncEventResponse)
async def get_sync_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a single sync event by ID."""
    event = await db.get(SyncEvent, event_id)
    if not event:
        raise HTTPException(404, "Sync event not found")
    return event


@router.get("/sync/events", response_model=list[SyncEventResponse])
async def list_sync_events(
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SyncEvent).order_by(SyncEvent.started_at.desc()).limit(limit)
    )
    return result.scalars().all()
