from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_auth
from app.models.database import get_db
from app.models.models import Developer
from app.schemas.schemas import (
    GoalCreate,
    GoalProgressResponse,
    GoalResponse,
    GoalUpdate,
)
from app.services.goals import create_goal, get_goal_progress, list_goals, update_goal

router = APIRouter(dependencies=[Depends(require_auth)])


@router.post("/goals", response_model=GoalResponse)
async def create(
    goal_data: GoalCreate,
    db: AsyncSession = Depends(get_db),
):
    dev = await db.get(Developer, goal_data.developer_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found")
    goal = await create_goal(db, goal_data)
    return goal


@router.get("/goals", response_model=list[GoalResponse])
async def list_developer_goals(
    developer_id: int,
    db: AsyncSession = Depends(get_db),
):
    dev = await db.get(Developer, developer_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found")
    return await list_goals(db, developer_id)


@router.patch("/goals/{goal_id}", response_model=GoalResponse)
async def update(
    goal_id: int,
    update_data: GoalUpdate,
    db: AsyncSession = Depends(get_db),
):
    goal = await update_goal(db, goal_id, update_data)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


@router.get("/goals/{goal_id}/progress", response_model=GoalProgressResponse)
async def progress(
    goal_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await get_goal_progress(db, goal_id)
    if not result:
        raise HTTPException(status_code=404, detail="Goal not found")
    return result
