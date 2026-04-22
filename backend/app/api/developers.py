from datetime import datetime, timezone
from enum import Enum as PyEnum

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, require_admin
from app.models.database import get_db
from app.models.models import Developer
from app.models.models import Issue, PullRequest
from app.schemas.schemas import (
    ActivitySummaryResponse,
    AppRole,
    AuthUser,
    DeactivationImpactResponse,
    DeveloperCreate,
    DeveloperResponse,
    DeveloperUpdateAdmin,
    LinearCreatorProfile,
    LinearShepherdProfile,
    LinearWorkerProfile,
    UnassignedRoleCountResponse,
)
from app.services.developer_linear import (
    get_developer_creator_profile,
    get_developer_shepherd_profile,
    get_developer_worker_profile,
)
from app.services.linear_health import is_linear_primary
from app.services.roles import validate_role_key
from app.services.stats import get_activity_summary
from app.services.teams import resolve_team

router = APIRouter()


@router.get("/developers", response_model=list[DeveloperResponse])
async def list_developers(
    team: str | None = Query(None),
    is_active: bool = Query(True),
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Developer).where(Developer.is_active == is_active)
    if team:
        stmt = stmt.where(Developer.team == team)
    stmt = stmt.order_by(Developer.display_name)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/developers/unassigned-role-count", response_model=UnassignedRoleCountResponse)
async def unassigned_role_count(
    _: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count = await db.scalar(
        select(func.count()).select_from(Developer).where(
            Developer.is_active.is_(True),
            Developer.role.is_(None),
        )
    ) or 0
    return UnassignedRoleCountResponse(count=count)


@router.post(
    "/developers",
    response_model=DeveloperResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_developer(
    data: DeveloperCreate,
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(Developer).where(Developer.github_username == data.github_username)
    )
    existing_dev = existing.scalar_one_or_none()
    if existing_dev:
        if not existing_dev.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "inactive_exists",
                    "developer_id": existing_dev.id,
                    "display_name": existing_dev.display_name,
                },
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Developer with github_username '{data.github_username}' already exists",
        )

    if data.role and not await validate_role_key(db, data.role):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: '{data.role}'",
        )

    # Resolve team name (find or auto-create in teams table)
    dev_data = data.model_dump()
    dev_data["team"] = await resolve_team(db, dev_data.get("team"))

    now = datetime.now(timezone.utc)
    dev = Developer(**dev_data, created_at=now, updated_at=now)
    db.add(dev)
    await db.commit()
    await db.refresh(dev)
    return dev


@router.get("/developers/{developer_id}", response_model=DeveloperResponse)
async def get_developer(
    developer_id: int,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.app_role != AppRole.admin and user.developer_id != developer_id:
        raise HTTPException(status_code=403, detail="Access denied")
    dev = await db.get(Developer, developer_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found")
    return dev


@router.get(
    "/developers/{developer_id}/activity-summary",
    response_model=ActivitySummaryResponse,
)
async def developer_activity_summary(
    developer_id: int,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.app_role != AppRole.admin and user.developer_id != developer_id:
        raise HTTPException(status_code=403, detail="Access denied")
    dev = await db.get(Developer, developer_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found")
    return await get_activity_summary(db, developer_id)


@router.patch("/developers/{developer_id}", response_model=DeveloperResponse)
async def update_developer(
    developer_id: int,
    data: DeveloperUpdateAdmin,
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    dev = await db.get(Developer, developer_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found")

    updates = data.model_dump(exclude_unset=True)
    if "role" in updates and updates["role"] is not None:
        if not await validate_role_key(db, updates["role"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role: '{updates['role']}'",
            )
    # Resolve team name if provided
    if "team" in updates and updates["team"] is not None:
        updates["team"] = await resolve_team(db, updates["team"])

    # Increment token_version when app_role or is_active changes (invalidates existing JWTs)
    role_changing = "app_role" in updates and updates["app_role"] != dev.app_role
    deactivating = "is_active" in updates and updates["is_active"] != dev.is_active

    for field, value in updates.items():
        setattr(dev, field, value.value if isinstance(value, PyEnum) else value)

    if role_changing or deactivating:
        dev.token_version = (dev.token_version or 1) + 1

    dev.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(dev)
    return dev


@router.get(
    "/developers/{developer_id}/deactivation-impact",
    response_model=DeactivationImpactResponse,
)
async def get_deactivation_impact(
    developer_id: int,
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    dev = await db.get(Developer, developer_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found")

    from sqlalchemy import func, distinct

    open_prs_result = await db.execute(
        select(func.count()).where(
            PullRequest.author_id == developer_id,
            PullRequest.state == "open",
            PullRequest.is_draft.isnot(True),
        )
    )
    open_prs = open_prs_result.scalar() or 0

    branches_result = await db.execute(
        select(distinct(PullRequest.head_branch)).where(
            PullRequest.author_id == developer_id,
            PullRequest.state == "open",
            PullRequest.is_draft.isnot(True),
            PullRequest.head_branch.isnot(None),
        )
    )
    open_branches = [row[0] for row in branches_result.all()]

    open_issues_result = await db.execute(
        select(func.count()).where(
            Issue.assignee_id == developer_id,
            Issue.state == "open",
        )
    )
    open_issues = open_issues_result.scalar() or 0

    return DeactivationImpactResponse(
        open_prs=open_prs,
        open_issues=open_issues,
        open_branches=open_branches,
    )


def _assert_self_or_admin(dev: Developer, user: AuthUser) -> None:
    """Phase 05 visibility gate: creator/shepherd signals are self+admin only."""
    is_admin = user.app_role == AppRole.admin
    is_self = user.developer_id == dev.id
    if not (is_admin or is_self):
        raise HTTPException(
            status_code=403,
            detail="Linear creator/worker/shepherd profiles are visible to admins and self only.",
        )


@router.get(
    "/developers/{developer_id}/linear-creator-profile",
    response_model=LinearCreatorProfile,
)
async def linear_creator_profile(
    developer_id: int,
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dev = await db.get(Developer, developer_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found")
    _assert_self_or_admin(dev, user)
    data = await get_developer_creator_profile(
        db, developer_id, date_from=date_from, date_to=date_to
    )
    return LinearCreatorProfile(**data)


@router.get(
    "/developers/{developer_id}/linear-worker-profile",
    response_model=LinearWorkerProfile,
)
async def linear_worker_profile(
    developer_id: int,
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dev = await db.get(Developer, developer_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found")
    # Worker profile is peer-visible per spec — anyone authenticated can see
    # any developer's work pattern when Linear is the primary issue source.
    # Creator + Shepherd remain self-or-admin; those carry more sensitive signal.
    if not await is_linear_primary(db):
        raise HTTPException(
            status_code=409,
            detail="Linear must be configured as the primary issue source",
        )
    data = await get_developer_worker_profile(
        db, developer_id, date_from=date_from, date_to=date_to
    )
    return LinearWorkerProfile(**data)


@router.get(
    "/developers/{developer_id}/linear-shepherd-profile",
    response_model=LinearShepherdProfile,
)
async def linear_shepherd_profile(
    developer_id: int,
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dev = await db.get(Developer, developer_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found")
    _assert_self_or_admin(dev, user)
    data = await get_developer_shepherd_profile(
        db, developer_id, date_from=date_from, date_to=date_to
    )
    return LinearShepherdProfile(**data)


@router.delete(
    "/developers/{developer_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_developer(
    developer_id: int,
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    dev = await db.get(Developer, developer_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found")

    dev.is_active = False
    dev.token_version = (dev.token_version or 1) + 1
    dev.updated_at = datetime.now(timezone.utc)
    await db.commit()
