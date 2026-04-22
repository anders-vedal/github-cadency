"""Phase 10 — DORA v2 API."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.models.database import get_db
from app.schemas.schemas import AuthUser, DoraV2Response
from app.services.dora_v2 import get_dora_v2

router = APIRouter()


@router.get("/dora/v2", response_model=DoraV2Response)
async def dora_v2(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    cohort: str = Query("all"),
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    """DORA v2 with AI-cohort split + rework rate."""
    data = await get_dora_v2(db, date_from=date_from, date_to=date_to, cohort=cohort)
    return DoraV2Response(**data)
