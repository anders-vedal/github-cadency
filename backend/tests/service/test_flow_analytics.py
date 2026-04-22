"""Phase 01 regression — flow_analytics status-time distribution.

The previous implementation lost two buckets of time per issue:
1. The initial state (from ``since`` → first transition) was never
   accumulated because ``prev_time`` started at ``None``.
2. The trailing open interval (last transition → ``until``) was not added,
   so issues still in their current state contributed zero to that state.

These tests seed a hand-built transition sequence with known durations and
assert every bucket matches to the second.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    ExternalIssue,
    ExternalIssueHistoryEvent,
    IntegrationConfig,
)
from app.services.flow_analytics import get_status_time_distribution

WINDOW_START = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def linear_integration(db_session: AsyncSession) -> IntegrationConfig:
    config = IntegrationConfig(
        type="linear",
        display_name="Linear",
        status="active",
        is_primary_issue_source=True,
    )
    db_session.add(config)
    await db_session.commit()
    await db_session.refresh(config)
    return config


async def _seed_issue_with_history(
    db: AsyncSession,
    integration: IntegrationConfig,
    *,
    identifier: str,
    created_at: datetime,
    transitions: list[tuple[datetime, str, str]],
) -> ExternalIssue:
    """Seed an issue + its history events.

    ``transitions`` is a list of ``(changed_at, from_category, to_category)``.
    Categories should be drawn from STATUS_ORDER (triage / backlog / todo /
    in_progress / in_review / done) — that's what the distribution function
    iterates over.
    """
    issue = ExternalIssue(
        integration_id=integration.id,
        external_id=f"ext-{identifier}",
        identifier=identifier,
        title=f"Issue {identifier}",
        status_category=transitions[-1][2] if transitions else "triage",
        created_at=created_at,
        updated_at=transitions[-1][0] if transitions else created_at,
    )
    db.add(issue)
    await db.flush()
    for idx, (changed_at, from_cat, to_cat) in enumerate(transitions):
        db.add(
            ExternalIssueHistoryEvent(
                issue_id=issue.id,
                external_id=f"hist-{identifier}-{idx}",
                changed_at=changed_at,
                from_state_category=from_cat,
                to_state_category=to_cat,
            )
        )
    await db.commit()
    await db.refresh(issue)
    return issue


@pytest.mark.asyncio
async def test_initial_state_duration_is_accumulated(
    db_session: AsyncSession, linear_integration: IntegrationConfig
):
    """Issue sits in triage from window-start through a single transition.
    Triage duration must equal the elapsed time from window-start to the
    transition timestamp.
    """
    transition_at = WINDOW_START + timedelta(days=2)  # 2 days in triage
    await _seed_issue_with_history(
        db_session,
        linear_integration,
        identifier="T-1",
        created_at=WINDOW_START,
        transitions=[(transition_at, "triage", "in_progress")],
    )

    rows = await get_status_time_distribution(
        db_session, date_from=WINDOW_START, date_to=WINDOW_END
    )
    by_state = {r["status_category"]: r for r in rows}

    assert "triage" in by_state, (
        "Initial-state bucket missing — the prev_time/current_state seed "
        "regressed (first state's duration is not being accumulated)."
    )
    expected_triage_s = int(timedelta(days=2).total_seconds())
    assert by_state["triage"]["p50_s"] == expected_triage_s


@pytest.mark.asyncio
async def test_trailing_open_interval_is_accumulated(
    db_session: AsyncSession, linear_integration: IntegrationConfig
):
    """Issue transitions into in_progress on day 2, never leaves. in_progress
    duration should equal ``until - last_transition``.
    """
    last_transition = WINDOW_START + timedelta(days=2)
    await _seed_issue_with_history(
        db_session,
        linear_integration,
        identifier="T-2",
        created_at=WINDOW_START,
        transitions=[(last_transition, "triage", "in_progress")],
    )

    rows = await get_status_time_distribution(
        db_session, date_from=WINDOW_START, date_to=WINDOW_END
    )
    by_state = {r["status_category"]: r for r in rows}

    assert "in_progress" in by_state, (
        "Trailing open-interval missing — issues still in their current state "
        "at `until` aren't contributing to the bucket."
    )
    expected_in_progress_s = int((WINDOW_END - last_transition).total_seconds())
    assert by_state["in_progress"]["p50_s"] == expected_in_progress_s


@pytest.mark.asyncio
async def test_full_sequence_hits_every_bucket(
    db_session: AsyncSession, linear_integration: IntegrationConfig
):
    """A full triage → in_progress → in_review sequence should accumulate
    all three buckets — not just the middle one."""
    t1 = WINDOW_START + timedelta(days=1)
    t2 = WINDOW_START + timedelta(days=3)
    await _seed_issue_with_history(
        db_session,
        linear_integration,
        identifier="T-3",
        created_at=WINDOW_START,
        transitions=[
            (t1, "triage", "in_progress"),
            (t2, "in_progress", "in_review"),
        ],
    )

    rows = await get_status_time_distribution(
        db_session, date_from=WINDOW_START, date_to=WINDOW_END
    )
    by_state = {r["status_category"]: r for r in rows}

    assert by_state["triage"]["p50_s"] == int(timedelta(days=1).total_seconds())
    assert by_state["in_progress"]["p50_s"] == int(
        timedelta(days=2).total_seconds()
    )
    assert by_state["in_review"]["p50_s"] == int(
        (WINDOW_END - t2).total_seconds()
    )
