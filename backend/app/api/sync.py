from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_admin
from app.models.database import get_db
from app.models.models import Issue, PullRequest, Repository, SyncEvent
from app.schemas.schemas import (
    RepoResponse,
    RepoTrackUpdate,
    SyncEventResponse,
    SyncStatusResponse,
    SyncTriggerRequest,
)
from app.services.github_sync import run_sync

router = APIRouter(dependencies=[Depends(require_admin)])


# --- Sync Triggers ---


@router.post("/sync/start", status_code=202)
async def start_sync(
    request: SyncTriggerRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Start a new sync. Returns 409 if a sync is already running."""
    active = await db.execute(
        select(SyncEvent).where(SyncEvent.status == "started")
    )
    if active.scalar_one_or_none():
        raise HTTPException(409, "A sync is already in progress")

    background_tasks.add_task(
        run_sync,
        request.sync_type,
        request.repo_ids,
        request.since,
    )
    return {"status": "accepted", "sync_type": request.sync_type}


@router.post("/sync/resume/{event_id}", status_code=202)
async def resume_sync(
    event_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Resume an interrupted sync, processing only remaining repos."""
    # Concurrency guard
    active = await db.execute(
        select(SyncEvent).where(SyncEvent.status == "started")
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

    background_tasks.add_task(
        run_sync,
        original.sync_type or "incremental",
        remaining,
        original.since_override,
        event_id,
    )
    return {"status": "accepted", "remaining_repos": len(remaining)}


# --- Sync Status ---


@router.get("/sync/status", response_model=SyncStatusResponse)
async def sync_status(db: AsyncSession = Depends(get_db)):
    """Get current sync status: active sync + summary stats."""
    # Active sync
    active_result = await db.execute(
        select(SyncEvent).where(SyncEvent.status == "started")
    )
    active_event = active_result.scalar_one_or_none()

    # Last completed sync
    last_result = await db.execute(
        select(SyncEvent)
        .where(SyncEvent.status.in_(["completed", "completed_with_errors", "failed"]))
        .order_by(SyncEvent.completed_at.desc())
        .limit(1)
    )
    last_event = last_result.scalar_one_or_none()

    # Repo counts
    tracked_count = await db.scalar(
        select(func.count()).select_from(Repository).where(
            Repository.is_tracked.is_(True)
        )
    ) or 0
    total_count = await db.scalar(
        select(func.count()).select_from(Repository)
    ) or 0

    # Last successful sync
    last_success_result = await db.execute(
        select(SyncEvent)
        .where(SyncEvent.status == "completed")
        .order_by(SyncEvent.completed_at.desc())
        .limit(1)
    )
    last_success = last_success_result.scalar_one_or_none()

    return SyncStatusResponse(
        active_sync=active_event,
        last_completed=last_event,
        tracked_repos_count=tracked_count,
        total_repos_count=total_count,
        last_successful_sync=last_success.completed_at if last_success else None,
        last_sync_duration_s=last_success.duration_s if last_success else None,
    )


# --- Repo Management ---


@router.get("/sync/repos", response_model=list[RepoResponse])
async def list_repos(db: AsyncSession = Depends(get_db)):
    """List all repos with PR and issue counts."""
    # Subquery for PR count per repo
    pr_count_sq = (
        select(
            PullRequest.repo_id,
            func.count().label("pr_count"),
        )
        .group_by(PullRequest.repo_id)
        .subquery()
    )
    # Subquery for issue count per repo
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
        repo_dict = {
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
        }
        repos.append(repo_dict)
    return repos


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


# --- Sync History ---


@router.get("/sync/events", response_model=list[SyncEventResponse])
async def list_sync_events(
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SyncEvent).order_by(SyncEvent.started_at.desc()).limit(limit)
    )
    return result.scalars().all()
