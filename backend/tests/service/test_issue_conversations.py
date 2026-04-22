"""Phase 01 regression — issue_conversations label filter.

Pre-fix, the label filter ran in Python AFTER ``.limit(limit)`` had already
truncated the result set to the top-N commented issues. If the label's
matching issues didn't happen to land in that top-N slice, the user saw
zero rows even when matching issues existed further down the list.

Post-fix, the label filter runs in SQL as a WHERE clause, so the LIMIT
applies to the label-matched set.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    ExternalIssue,
    ExternalIssueComment,
    IntegrationConfig,
)
from app.services.issue_conversations import get_chattiest_issues

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


async def _seed_issue(
    db: AsyncSession,
    integration: IntegrationConfig,
    *,
    identifier: str,
    labels: list[str],
    comments: int,
) -> ExternalIssue:
    issue = ExternalIssue(
        integration_id=integration.id,
        external_id=f"c-{identifier}",
        identifier=identifier,
        title=identifier,
        labels=labels,
        created_at=WINDOW_START + timedelta(days=1),
        updated_at=WINDOW_START + timedelta(days=1),
    )
    db.add(issue)
    await db.flush()
    for i in range(comments):
        db.add(
            ExternalIssueComment(
                issue_id=issue.id,
                external_id=f"c-{identifier}-{i}",
                body_preview="discussion",
                body_length=10,
                created_at=WINDOW_START + timedelta(days=1, hours=i),
                is_system_generated=False,
            )
        )
    await db.commit()
    await db.refresh(issue)
    return issue


@pytest.mark.asyncio
async def test_label_filter_sees_past_top_n_window(
    db_session: AsyncSession, linear_integration: IntegrationConfig
):
    """Seed 25 chatty issues with no label, and one moderately-commented issue
    carrying the ``frontend`` label. With ``limit=20`` the labelled issue
    would never appear in the pre-filter top-N. Post-fix, the label filter
    runs in SQL so the label-matched issue surfaces."""
    # 25 chatty issues (more than limit=20), none carry the target label.
    for i in range(25):
        await _seed_issue(
            db_session,
            linear_integration,
            identifier=f"CH-{i:02d}",
            labels=["backend"],
            comments=50,
        )
    # One modestly-commented issue with the target label — it would never
    # reach the top-20 pre-filter slice because its comment count is much
    # smaller than the 25 chatty ones above.
    await _seed_issue(
        db_session,
        linear_integration,
        identifier="FE-1",
        labels=["frontend"],
        comments=3,
    )

    results = await get_chattiest_issues(
        db_session,
        date_from=WINDOW_START,
        date_to=WINDOW_END,
        limit=20,
        label="frontend",
    )
    identifiers = [row["identifier"] for row in results]
    assert "FE-1" in identifiers, (
        "Label-matched issue was silently excluded — label filter regressed "
        "to running AFTER the LIMIT slice."
    )
    # And no backend-labelled issue should sneak through.
    assert all(not ident.startswith("CH-") for ident in identifiers)


@pytest.mark.asyncio
async def test_no_label_filter_returns_top_commented(
    db_session: AsyncSession, linear_integration: IntegrationConfig
):
    # Seed 3 issues with distinct comment counts, no label filter.
    await _seed_issue(
        db_session, linear_integration, identifier="A", labels=[], comments=2
    )
    await _seed_issue(
        db_session, linear_integration, identifier="B", labels=[], comments=10
    )
    await _seed_issue(
        db_session, linear_integration, identifier="C", labels=[], comments=5
    )
    results = await get_chattiest_issues(
        db_session,
        date_from=WINDOW_START,
        date_to=WINDOW_END,
        limit=20,
    )
    # Highest comment count first.
    ordered = [r["identifier"] for r in results]
    assert ordered.index("B") < ordered.index("C")
    assert ordered.index("C") < ordered.index("A")
