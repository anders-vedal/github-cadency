"""Phase 06 — ClassifierRule pattern hardening.

Locks the length cap + ReDoS guard that the admin surface depends on. The
service-level ``_validate`` runs on create AND update so belt-and-braces holds
even when the API-level Pydantic validator is skipped by a direct service call.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.classifier_rules import (
    MAX_PATTERN_LENGTH,
    ValidationError,
    create_rule,
    update_rule,
)


@pytest.mark.asyncio
async def test_create_rejects_overlong_pattern(db_session: AsyncSession):
    too_long = "a" * (MAX_PATTERN_LENGTH + 1)
    with pytest.raises(ValidationError) as exc:
        await create_rule(
            db_session,
            kind="incident",
            rule_type="github_label",
            pattern=too_long,
            is_incident=True,
        )
    assert "exceeds" in str(exc.value)


@pytest.mark.asyncio
async def test_create_rejects_redos_regex_on_regex_rule_type(
    db_session: AsyncSession,
):
    # Nested quantifier — classic catastrophic backtracking shape.
    with pytest.raises(ValidationError):
        await create_rule(
            db_session,
            kind="ai_author",
            rule_type="email_pattern",
            pattern=r"(a+)+b",
        )


@pytest.mark.asyncio
async def test_create_accepts_safe_regex_on_regex_rule_type(
    db_session: AsyncSession,
):
    row = await create_rule(
        db_session,
        kind="ai_author",
        rule_type="email_pattern",
        pattern=r"^[a-z]+@bots\.example\.com$",
    )
    assert row.id is not None
    assert row.rule_type == "email_pattern"


@pytest.mark.asyncio
async def test_create_accepts_safe_non_regex_pattern(db_session: AsyncSession):
    row = await create_rule(
        db_session,
        kind="incident",
        rule_type="linear_label",
        pattern="sev-1",
        is_incident=True,
    )
    assert row.id is not None


@pytest.mark.asyncio
async def test_update_rejects_overlong_pattern(db_session: AsyncSession):
    row = await create_rule(
        db_session,
        kind="incident",
        rule_type="pr_title_prefix",
        pattern="hotfix:",
        is_hotfix=True,
    )
    with pytest.raises(ValidationError):
        await update_rule(db_session, row.id, pattern="x" * (MAX_PATTERN_LENGTH + 1))


@pytest.mark.asyncio
async def test_update_regex_rule_type_rejects_redos(db_session: AsyncSession):
    row = await create_rule(
        db_session,
        kind="ai_author",
        rule_type="email_pattern",
        pattern=r"^safe@example\.com$",
    )
    # Classic catastrophic-backtracking shape — nested quantifier inside a
    # grouping, then another quantifier on the group.
    with pytest.raises(ValidationError):
        await update_rule(db_session, row.id, pattern=r"(a+)+b")
