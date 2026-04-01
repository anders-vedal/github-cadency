"""API routes for configurable work categories and classification rules."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, require_admin
from app.models.database import get_db
from app.rate_limit import limiter
from app.schemas.schemas import (
    AuthUser,
    BulkCreateRulesRequest,
    BulkCreateRulesResponse,
    ReclassifyResponse,
    WorkCategoryCreate,
    WorkCategoryResponse,
    WorkCategoryRuleCreate,
    WorkCategoryRuleResponse,
    WorkCategoryRuleUpdate,
    WorkCategorySuggestion,
    WorkCategoryUpdate,
)
from app.services.work_categories import (
    bulk_create_rules,
    create_category,
    create_rule,
    delete_category,
    delete_rule,
    get_all_categories,
    get_all_rules,
    reclassify_all,
    scan_suggestions,
    update_category,
    update_rule,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


@router.get("/work-categories", response_model=list[WorkCategoryResponse])
async def list_categories(
    _: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_all_categories(db)


@router.post(
    "/work-categories",
    response_model=WorkCategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_category_endpoint(
    data: WorkCategoryCreate,
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await create_category(db, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.patch("/work-categories/{category_key}", response_model=WorkCategoryResponse)
async def update_category_endpoint(
    category_key: str,
    data: WorkCategoryUpdate,
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await update_category(db, category_key, data)
    except ValueError as e:
        detail = str(e)
        code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=detail)


@router.delete("/work-categories/{category_key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category_endpoint(
    category_key: str,
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        await delete_category(db, category_key)
    except ValueError as e:
        detail = str(e)
        code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=detail)


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


@router.get("/work-categories/rules", response_model=list[WorkCategoryRuleResponse])
async def list_rules(
    _: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_all_rules(db)


@router.post(
    "/work-categories/rules",
    response_model=WorkCategoryRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_rule_endpoint(
    data: WorkCategoryRuleCreate,
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await create_rule(db, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.patch("/work-categories/rules/{rule_id}", response_model=WorkCategoryRuleResponse)
async def update_rule_endpoint(
    rule_id: int,
    data: WorkCategoryRuleUpdate,
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await update_rule(db, rule_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/work-categories/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule_endpoint(
    rule_id: int,
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        await delete_rule(db, rule_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


# ---------------------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------------------


@router.post(
    "/work-categories/suggestions",
    response_model=list[WorkCategorySuggestion],
)
async def scan_suggestions_endpoint(
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await scan_suggestions(db)


# ---------------------------------------------------------------------------
# Bulk rule creation
# ---------------------------------------------------------------------------


@router.post(
    "/work-categories/rules/bulk",
    response_model=BulkCreateRulesResponse,
    status_code=status.HTTP_201_CREATED,
)
async def bulk_create_rules_endpoint(
    data: BulkCreateRulesRequest,
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        created = await bulk_create_rules(db, data.rules)
        return BulkCreateRulesResponse(created=created)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


# ---------------------------------------------------------------------------
# Reclassify
# ---------------------------------------------------------------------------


@router.post("/work-categories/reclassify", response_model=ReclassifyResponse)
@limiter.limit("2/minute")
async def reclassify_endpoint(
    request: Request,
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await reclassify_all(db)
    return ReclassifyResponse(**result)
