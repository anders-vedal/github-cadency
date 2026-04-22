"""Phase 11 — Metrics catalog API for frontend consumption."""

from fastapi import APIRouter, Depends

from app.api.auth import get_current_user
from app.schemas.schemas import AuthUser
from app.services.metric_spec import get_catalog

router = APIRouter()


@router.get("/metrics/catalog")
async def metrics_catalog(user: AuthUser = Depends(get_current_user)):
    """Return the registry of exposed metrics (plus the banned list).

    Used by the frontend to render tooltips, paired-outcome companions,
    and AI-cohort badges consistently.
    """
    return get_catalog()
