"""Admin CRUD for classifier rules (Phase 10 C3).

Backs the incident/hotfix detection + AI-cohort detection rule table surfaced
at ``/admin/classifier-rules``. Defaults always apply underneath these rows —
DB rows ADD, never REPLACE. Disabling a default requires setting a same-
priority override row in the future (deliberately not supported in v1).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_admin
from app.models.database import get_db
from app.services.classifier_rules import (
    ValidationError,
    create_rule,
    delete_rule,
    list_rules,
    rule_to_dict,
    rules_to_dicts,
    update_rule,
)

router = APIRouter()


class ClassifierRuleCreate(BaseModel):
    kind: str
    rule_type: str
    pattern: str = Field(default="")
    is_hotfix: bool = False
    is_incident: bool = False
    priority: int = 100
    enabled: bool = True


class ClassifierRulePatch(BaseModel):
    pattern: str | None = None
    is_hotfix: bool | None = None
    is_incident: bool | None = None
    priority: int | None = None
    enabled: bool | None = None


@router.get("/admin/classifier-rules", dependencies=[Depends(require_admin)])
async def list_classifier_rules(
    kind: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Return all admin-editable classifier rules, optionally filtered by kind."""
    rows = await list_rules(db, kind=kind)
    return {"rules": rules_to_dicts(rows)}


@router.post("/admin/classifier-rules", dependencies=[Depends(require_admin)])
async def create_classifier_rule(
    body: ClassifierRuleCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await create_rule(
            db,
            kind=body.kind,
            rule_type=body.rule_type,
            pattern=body.pattern,
            is_hotfix=body.is_hotfix,
            is_incident=body.is_incident,
            priority=body.priority,
            enabled=body.enabled,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return rule_to_dict(row)


@router.patch(
    "/admin/classifier-rules/{rule_id}", dependencies=[Depends(require_admin)]
)
async def patch_classifier_rule(
    rule_id: int,
    body: ClassifierRulePatch,
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await update_rule(
            db,
            rule_id,
            pattern=body.pattern,
            is_hotfix=body.is_hotfix,
            is_incident=body.is_incident,
            priority=body.priority,
            enabled=body.enabled,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if row is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule_to_dict(row)


@router.delete(
    "/admin/classifier-rules/{rule_id}", dependencies=[Depends(require_admin)]
)
async def delete_classifier_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
):
    if not await delete_rule(db, rule_id):
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"status": "deleted"}
