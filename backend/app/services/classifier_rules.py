"""Admin CRUD + load helpers for ``ClassifierRule`` (Phase 10 C3).

Keeps the public surface minimal on purpose: services in
``incident_classification`` and ``ai_cohort`` call ``load_rules()`` to merge
admin-edited rules on top of their hard-coded defaults. The API router uses
the CRUD helpers directly.
"""

from __future__ import annotations

from typing import Iterable, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ClassifierRule
from app.services.ai_cohort import AIDetectionRules, default_rules as default_ai_rules
from app.services.incident_classification import (
    IncidentRule,
    default_rules as default_incident_rules,
)

RuleKind = Literal["incident", "ai_reviewer", "ai_author"]
VALID_KINDS: tuple[RuleKind, ...] = ("incident", "ai_reviewer", "ai_author")

# Accepted rule_type values per kind. Anything else is rejected at create time.
VALID_INCIDENT_RULE_TYPES = {
    "pr_title_prefix",
    "revert_detection",
    "github_label",
    "linear_label",
    "linear_issue_type",
}
VALID_AI_RULE_TYPES = {"username", "label", "email_pattern"}


class ValidationError(ValueError):
    """Raised when a caller provides an invalid rule shape."""


def _validate(kind: str, rule_type: str) -> None:
    if kind not in VALID_KINDS:
        raise ValidationError(f"Unknown kind {kind!r}; expected one of {VALID_KINDS}")
    if kind == "incident":
        if rule_type not in VALID_INCIDENT_RULE_TYPES:
            raise ValidationError(
                f"Incident rule_type must be one of {sorted(VALID_INCIDENT_RULE_TYPES)}"
            )
    else:  # ai_reviewer / ai_author
        if rule_type not in VALID_AI_RULE_TYPES:
            raise ValidationError(
                f"AI rule_type must be one of {sorted(VALID_AI_RULE_TYPES)}"
            )


async def list_rules(
    db: AsyncSession, kind: str | None = None, include_disabled: bool = True
) -> list[ClassifierRule]:
    """Return all rules, optionally filtered by kind."""
    query = select(ClassifierRule).order_by(
        ClassifierRule.kind, ClassifierRule.priority, ClassifierRule.id
    )
    if kind:
        query = query.where(ClassifierRule.kind == kind)
    if not include_disabled:
        query = query.where(ClassifierRule.enabled.is_(True))
    result = await db.execute(query)
    return list(result.scalars().all())


async def create_rule(
    db: AsyncSession,
    *,
    kind: str,
    rule_type: str,
    pattern: str,
    is_hotfix: bool = False,
    is_incident: bool = False,
    priority: int = 100,
    enabled: bool = True,
) -> ClassifierRule:
    _validate(kind, rule_type)
    if kind == "incident" and not (is_hotfix or is_incident):
        raise ValidationError(
            "Incident rules must set is_hotfix=True or is_incident=True (or both)"
        )
    row = ClassifierRule(
        kind=kind,
        rule_type=rule_type,
        pattern=pattern,
        is_hotfix=is_hotfix,
        is_incident=is_incident,
        priority=priority,
        enabled=enabled,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_rule(db: AsyncSession, rule_id: int) -> bool:
    row = await db.get(ClassifierRule, rule_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def update_rule(
    db: AsyncSession,
    rule_id: int,
    *,
    pattern: str | None = None,
    is_hotfix: bool | None = None,
    is_incident: bool | None = None,
    priority: int | None = None,
    enabled: bool | None = None,
) -> ClassifierRule | None:
    row = await db.get(ClassifierRule, rule_id)
    if not row:
        return None
    if pattern is not None:
        row.pattern = pattern
    if is_hotfix is not None:
        row.is_hotfix = is_hotfix
    if is_incident is not None:
        row.is_incident = is_incident
    if priority is not None:
        row.priority = priority
    if enabled is not None:
        row.enabled = enabled
    await db.commit()
    await db.refresh(row)
    return row


# ── Rule loaders consumed by the classifier services ────────────────────────


async def load_incident_rules(db: AsyncSession) -> list[IncidentRule]:
    """Defaults + enabled DB rows, sorted by priority."""
    rows = await list_rules(db, kind="incident", include_disabled=False)
    combined: list[IncidentRule] = list(default_incident_rules())
    for row in rows:
        combined.append(
            IncidentRule(
                rule_type=row.rule_type,  # type: ignore[arg-type]
                pattern=row.pattern,
                is_hotfix=row.is_hotfix,
                is_incident=row.is_incident,
                priority=row.priority,
            )
        )
    combined.sort(key=lambda r: r.priority)
    return combined


async def load_ai_detection_rules(db: AsyncSession) -> AIDetectionRules:
    """Defaults + enabled DB rows merged into an AIDetectionRules set."""
    base = default_ai_rules()
    reviewer_usernames = set(base.reviewer_usernames)
    author_labels = set(base.author_labels)
    author_email_patterns = set(base.author_email_patterns)

    rows = await list_rules(db, include_disabled=False)
    for row in rows:
        if row.kind == "ai_reviewer" and row.rule_type == "username":
            reviewer_usernames.add(row.pattern.lower())
        elif row.kind == "ai_author":
            if row.rule_type == "label":
                author_labels.add(row.pattern.lower())
            elif row.rule_type == "email_pattern":
                author_email_patterns.add(row.pattern.lower())

    return AIDetectionRules(
        reviewer_usernames=reviewer_usernames,
        author_labels=author_labels,
        author_email_patterns=author_email_patterns,
    )


def rule_to_dict(row: ClassifierRule) -> dict:
    return {
        "id": row.id,
        "kind": row.kind,
        "rule_type": row.rule_type,
        "pattern": row.pattern,
        "is_hotfix": row.is_hotfix,
        "is_incident": row.is_incident,
        "priority": row.priority,
        "enabled": row.enabled,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def rules_to_dicts(rows: Iterable[ClassifierRule]) -> list[dict]:
    return [rule_to_dict(r) for r in rows]
