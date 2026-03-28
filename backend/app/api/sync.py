from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_auth
from app.models.database import get_db
from app.models.models import Repository, SyncEvent
from app.schemas.schemas import RepoResponse, RepoTrackUpdate, SyncEventResponse
from app.services.github_sync import run_sync

router = APIRouter(dependencies=[Depends(require_auth)])


@router.post("/sync/full", status_code=202)
async def trigger_full_sync(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_sync, "full")
    return {"status": "accepted", "sync_type": "full"}


@router.post("/sync/incremental", status_code=202)
async def trigger_incremental_sync(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_sync, "incremental")
    return {"status": "accepted", "sync_type": "incremental"}


@router.get("/sync/repos", response_model=list[RepoResponse])
async def list_repos(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Repository).order_by(Repository.full_name)
    )
    return result.scalars().all()


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
    return repo


@router.get("/sync/events", response_model=list[SyncEventResponse])
async def list_sync_events(
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SyncEvent).order_by(SyncEvent.started_at.desc()).limit(limit)
    )
    return result.scalars().all()
