from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, require_admin
from app.models.database import get_db
from app.models.models import Developer, DeveloperGoal
from app.schemas.schemas import (
    AppRole,
    AuthUser,
    GoalCreate,
    GoalProgressResponse,
    GoalResponse,
    GoalSelfCreate,
    GoalSelfUpdate,
    GoalUpdate,
)
from app.services.goals import (
    create_goal,
    get_goal_progress,
    list_goals,
    update_goal,
    update_goal_self,
)

router = APIRouter()


@router.post("/goals", response_model=GoalResponse)
async def create(
    goal_data: GoalCreate,
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    dev = await db.get(Developer, goal_data.developer_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found")
    goal = await create_goal(db, goal_data, created_by="admin")
    return goal


@router.get("/goals", response_model=list[GoalResponse])
async def list_developer_goals(
    developer_id: int,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.app_role != AppRole.admin and user.developer_id != developer_id:
        raise HTTPException(status_code=403, detail="Access denied")
    dev = await db.get(Developer, developer_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found")
    return await list_goals(db, developer_id)


@router.patch("/goals/{goal_id}", response_model=GoalResponse)
async def update(
    goal_id: int,
    update_data: GoalUpdate,
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    goal = await update_goal(db, goal_id, update_data)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


@router.get("/goals/{goal_id}/progress", response_model=GoalProgressResponse)
async def progress(
    goal_id: int,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Ownership check before executing service call
    if user.app_role != AppRole.admin:
        goal_obj = await db.get(DeveloperGoal, goal_id)
        if not goal_obj or goal_obj.developer_id != user.developer_id:
            raise HTTPException(status_code=404, detail="Goal not found")
    result = await get_goal_progress(db, goal_id)
    if not result:
        raise HTTPException(status_code=404, detail="Goal not found")
    return result


@router.post("/goals/self", response_model=GoalResponse)
async def create_self(
    goal_data: GoalSelfCreate,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dev = await db.get(Developer, user.developer_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found")
    full_goal = GoalCreate(
        developer_id=user.developer_id,
        title=goal_data.title,
        description=goal_data.description,
        metric_key=goal_data.metric_key,
        target_value=goal_data.target_value,
        target_direction=goal_data.target_direction,
        target_date=goal_data.target_date,
    )
    goal = await create_goal(db, full_goal, created_by="self")
    return goal


@router.patch("/goals/self/{goal_id}", response_model=GoalResponse)
async def update_self(
    goal_id: int,
    update_data: GoalSelfUpdate,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    goal_obj = await db.get(DeveloperGoal, goal_id)
    if not goal_obj:
        raise HTTPException(status_code=404, detail="Goal not found")
    if goal_obj.developer_id != user.developer_id:
        raise HTTPException(status_code=403, detail="Access denied")
    if goal_obj.created_by != "self":
        raise HTTPException(
            status_code=403, detail="Cannot modify admin-created goals"
        )
    goal = await update_goal_self(db, goal_id, update_data)
    return goal
