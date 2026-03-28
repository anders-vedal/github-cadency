from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_auth
from app.models.database import get_db
from app.models.models import Developer
from app.schemas.schemas import DeveloperCreate, DeveloperResponse, DeveloperUpdate

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/developers", response_model=list[DeveloperResponse])
async def list_developers(
    team: str | None = Query(None),
    is_active: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Developer).where(Developer.is_active == is_active)
    if team:
        stmt = stmt.where(Developer.team == team)
    stmt = stmt.order_by(Developer.display_name)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post(
    "/developers",
    response_model=DeveloperResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_developer(
    data: DeveloperCreate,
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(Developer).where(Developer.github_username == data.github_username)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Developer with github_username '{data.github_username}' already exists",
        )

    now = datetime.now(timezone.utc)
    dev = Developer(**data.model_dump(), created_at=now, updated_at=now)
    db.add(dev)
    await db.commit()
    await db.refresh(dev)
    return dev


@router.get("/developers/{developer_id}", response_model=DeveloperResponse)
async def get_developer(
    developer_id: int,
    db: AsyncSession = Depends(get_db),
):
    dev = await db.get(Developer, developer_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found")
    return dev


@router.patch("/developers/{developer_id}", response_model=DeveloperResponse)
async def update_developer(
    developer_id: int,
    data: DeveloperUpdate,
    db: AsyncSession = Depends(get_db),
):
    dev = await db.get(Developer, developer_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found")

    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(dev, field, value)
    dev.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(dev)
    return dev


@router.delete(
    "/developers/{developer_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_developer(
    developer_id: int,
    db: AsyncSession = Depends(get_db),
):
    dev = await db.get(Developer, developer_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found")

    dev.is_active = False
    dev.updated_at = datetime.now(timezone.utc)
    await db.commit()
