"""Phase 10 C3 — admin CRUD for classifier rules."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ClassifierRule
from app.services.ai_cohort import DEFAULT_AI_REVIEWER_USERNAMES
from app.services.classifier_rules import (
    ValidationError,
    create_rule,
    delete_rule,
    list_rules,
    load_ai_detection_rules,
    load_incident_rules,
    update_rule,
)


@pytest.mark.asyncio
async def test_create_incident_rule_roundtrip(db_session: AsyncSession):
    row = await create_rule(
        db_session,
        kind="incident",
        rule_type="pr_title_prefix",
        pattern="critical:",
        is_hotfix=False,
        is_incident=True,
        priority=15,
    )
    assert row.id is not None
    fetched = await list_rules(db_session, kind="incident")
    assert any(r.id == row.id and r.pattern == "critical:" for r in fetched)


@pytest.mark.asyncio
async def test_incident_rules_merge_into_defaults(db_session: AsyncSession):
    defaults_len = len(await load_incident_rules(db_session))
    await create_rule(
        db_session,
        kind="incident",
        rule_type="github_label",
        pattern="sev-3",
        is_incident=True,
    )
    merged = await load_incident_rules(db_session)
    assert len(merged) == defaults_len + 1
    # Still sorted by priority
    priorities = [r.priority for r in merged]
    assert priorities == sorted(priorities)


@pytest.mark.asyncio
async def test_ai_reviewer_rule_merges_into_detection(db_session: AsyncSession):
    await create_rule(
        db_session,
        kind="ai_reviewer",
        rule_type="username",
        pattern="custombot[bot]",
    )
    rules = await load_ai_detection_rules(db_session)
    assert "custombot[bot]" in rules.reviewer_usernames
    # Defaults still present
    assert next(iter(DEFAULT_AI_REVIEWER_USERNAMES)).lower() in rules.reviewer_usernames


@pytest.mark.asyncio
async def test_disabled_rule_skipped_in_merge(db_session: AsyncSession):
    row = await create_rule(
        db_session,
        kind="ai_author",
        rule_type="label",
        pattern="generated",
    )
    # Sanity: rule appears when enabled
    rules = await load_ai_detection_rules(db_session)
    assert "generated" in rules.author_labels

    # Flip off
    await update_rule(db_session, row.id, enabled=False)
    rules = await load_ai_detection_rules(db_session)
    assert "generated" not in rules.author_labels


@pytest.mark.asyncio
async def test_create_rejects_unknown_kind(db_session: AsyncSession):
    with pytest.raises(ValidationError):
        await create_rule(
            db_session, kind="nonsense", rule_type="username", pattern="x"
        )


@pytest.mark.asyncio
async def test_create_rejects_incident_without_flag(db_session: AsyncSession):
    with pytest.raises(ValidationError):
        await create_rule(
            db_session,
            kind="incident",
            rule_type="github_label",
            pattern="whatever",
            is_hotfix=False,
            is_incident=False,
        )


@pytest.mark.asyncio
async def test_delete_removes_row(db_session: AsyncSession):
    row = await create_rule(
        db_session,
        kind="ai_reviewer",
        rule_type="username",
        pattern="deletme[bot]",
    )
    assert await delete_rule(db_session, row.id) is True
    rules = await load_ai_detection_rules(db_session)
    assert "deletme[bot]" not in rules.reviewer_usernames


@pytest.mark.asyncio
async def test_update_rule_patches_fields(db_session: AsyncSession):
    row = await create_rule(
        db_session,
        kind="incident",
        rule_type="pr_title_prefix",
        pattern="wip:",
        is_hotfix=True,
        priority=50,
    )
    updated = await update_rule(db_session, row.id, pattern="todo:", priority=25)
    assert updated is not None
    assert updated.pattern == "todo:"
    assert updated.priority == 25
    # Unchanged fields preserved
    assert updated.is_hotfix is True
