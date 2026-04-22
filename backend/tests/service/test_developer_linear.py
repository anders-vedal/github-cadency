"""Phase 01 regression — developer_linear Worker date filter.

Pre-fix, the Worker profile filtered issues by ``created_at`` in range, which
dropped long-lived issues created BEFORE the window but started or completed
inside it. That made cycle-time, triage-to-start, and self-picked% all
undercount on exactly the work where those signals matter most.

Post-fix, Worker issues are the union of "started in range" and "completed in
range" — regardless of when they were created.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Developer, ExternalIssue, IntegrationConfig
from app.services.developer_linear import get_developer_worker_profile

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


@pytest_asyncio.fixture
async def worker(db_session: AsyncSession) -> Developer:
    dev = Developer(
        github_username="worker",
        display_name="Worker Dev",
        is_active=True,
        app_role="developer",
        created_at=WINDOW_START,
        updated_at=WINDOW_START,
    )
    db_session.add(dev)
    await db_session.commit()
    await db_session.refresh(dev)
    return dev


async def _seed_issue(
    db: AsyncSession,
    integration: IntegrationConfig,
    assignee: Developer,
    *,
    identifier: str,
    created_at: datetime,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> ExternalIssue:
    issue = ExternalIssue(
        integration_id=integration.id,
        external_id=f"w-{identifier}",
        identifier=identifier,
        title=identifier,
        created_at=created_at,
        updated_at=created_at,
        started_at=started_at,
        completed_at=completed_at,
        assignee_developer_id=assignee.id,
        creator_developer_id=assignee.id,
        status_category="done" if completed_at else "in_progress",
    )
    db.add(issue)
    await db.commit()
    await db.refresh(issue)
    return issue


@pytest.mark.asyncio
async def test_long_lived_issue_created_before_window_completed_inside_is_included(
    db_session: AsyncSession,
    linear_integration: IntegrationConfig,
    worker: Developer,
):
    """The Phase 01 fix: an issue created 2 months before the window but
    completed inside it MUST be included in the Worker profile. Pre-fix, the
    ``created_at`` filter excluded it and cycle-time averaged only short
    issues.
    """
    issue = await _seed_issue(
        db_session,
        linear_integration,
        worker,
        identifier="LONG-1",
        created_at=WINDOW_START - timedelta(days=60),
        started_at=WINDOW_START - timedelta(days=40),
        completed_at=WINDOW_START + timedelta(days=5),
    )

    profile = await get_developer_worker_profile(
        db_session,
        worker.id,
        date_from=WINDOW_START,
        date_to=WINDOW_END,
    )

    assert profile["issues_worked"] == 1, (
        "Long-lived issue completed in range was dropped — the Worker date "
        "filter regressed back to created_at."
    )
    # Cycle time = completed_at - started_at = 45 days, regardless of when
    # the issue was originally filed.
    expected_cycle_s = int(timedelta(days=45).total_seconds())
    assert profile["median_cycle_time_s"] == expected_cycle_s
    # silence unused warning
    _ = issue


@pytest.mark.asyncio
async def test_issue_started_in_window_but_not_completed_is_included(
    db_session: AsyncSession,
    linear_integration: IntegrationConfig,
    worker: Developer,
):
    await _seed_issue(
        db_session,
        linear_integration,
        worker,
        identifier="STARTED",
        created_at=WINDOW_START - timedelta(days=30),
        started_at=WINDOW_START + timedelta(days=2),
        completed_at=None,
    )

    profile = await get_developer_worker_profile(
        db_session,
        worker.id,
        date_from=WINDOW_START,
        date_to=WINDOW_END,
    )
    assert profile["issues_worked"] == 1


@pytest.mark.asyncio
async def test_issue_fully_outside_window_excluded(
    db_session: AsyncSession,
    linear_integration: IntegrationConfig,
    worker: Developer,
):
    # Completed and started months before window
    await _seed_issue(
        db_session,
        linear_integration,
        worker,
        identifier="OLD",
        created_at=WINDOW_START - timedelta(days=120),
        started_at=WINDOW_START - timedelta(days=90),
        completed_at=WINDOW_START - timedelta(days=60),
    )

    profile = await get_developer_worker_profile(
        db_session,
        worker.id,
        date_from=WINDOW_START,
        date_to=WINDOW_END,
    )
    assert profile["issues_worked"] == 0
