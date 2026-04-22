"""Phase 02 regression — DORA v2 cohort filtering.

Locks two fixes:

* ``get_dora_v2(cohort=X)`` must scope the top-level ``stability.rework_rate``
  to the cohort, not silently report the all-cohort number.
* ``compute_rework_rate(pr_ids=cohort_ids)`` must scope the follow-up PRs to
  the same set — otherwise a follow-up from a different cohort contaminates
  the current cohort's rework count.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Developer, PRFile, PullRequest, Repository
from app.services.dora_v2 import compute_rework_rate, get_dora_v2

NOW = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def repo(db_session: AsyncSession) -> Repository:
    r = Repository(
        github_id=2001,
        name="core",
        full_name="acme/core",
        is_tracked=True,
        created_at=NOW,
    )
    db_session.add(r)
    await db_session.commit()
    await db_session.refresh(r)
    return r


@pytest_asyncio.fixture
async def human_author(db_session: AsyncSession) -> Developer:
    dev = Developer(
        github_username="human_dev",
        display_name="Human Dev",
        is_active=True,
        app_role="developer",
        created_at=NOW,
        updated_at=NOW,
    )
    db_session.add(dev)
    await db_session.commit()
    await db_session.refresh(dev)
    return dev


async def _make_pr(
    db: AsyncSession,
    repo: Repository,
    author: Developer,
    *,
    number: int,
    merged_at: datetime,
    files: list[str],
    labels: list[str] | None = None,
) -> PullRequest:
    pr = PullRequest(
        github_id=5000 + number,
        repo_id=repo.id,
        author_id=author.id,
        number=number,
        title=f"PR {number}",
        state="closed",
        is_merged=True,
        merged_at=merged_at,
        created_at=merged_at - timedelta(hours=2),
        updated_at=merged_at,
        labels=labels or [],
    )
    db.add(pr)
    await db.flush()
    for fn in files:
        db.add(PRFile(pr_id=pr.id, filename=fn))
    await db.commit()
    await db.refresh(pr)
    return pr


@pytest.mark.asyncio
async def test_rework_rate_both_sides_scoped_by_pr_ids(
    db_session: AsyncSession, repo: Repository, human_author: Developer
):
    """Follow-up-side cohort filter: without it, a follow-up from a DIFFERENT
    cohort counts as rework against the current cohort's base PRs. With the
    fix, the filter is symmetric."""
    base = NOW - timedelta(days=3)
    base_pr = await _make_pr(
        db_session, repo, human_author, number=1, merged_at=base, files=["shared.py"]
    )
    # Follow-up PR touching the same file within 7 days — represents "other
    # cohort" by simply being outside the pr_ids set we pass in.
    other_cohort_followup = await _make_pr(
        db_session,
        repo,
        human_author,
        number=2,
        merged_at=base + timedelta(days=1),
        files=["shared.py"],
    )

    # Unfiltered: the follow-up counts → 1 rework.
    all_cohort = await compute_rework_rate(
        db_session,
        date_from=base - timedelta(days=5),
        date_to=base + timedelta(days=5),
    )
    assert all_cohort["merges"] == 2
    assert all_cohort["reworks"] == 1

    # Cohort-scoped: only base_pr is in the cohort. The follow-up is outside
    # the cohort, so base_pr's rework count MUST drop to 0.
    cohort_scoped = await compute_rework_rate(
        db_session,
        date_from=base - timedelta(days=5),
        date_to=base + timedelta(days=5),
        pr_ids={base_pr.id},
    )
    assert cohort_scoped["merges"] == 1
    assert cohort_scoped["reworks"] == 0, (
        "Cross-cohort follow-up leaked into cohort rework count — "
        "the fix scoping follow-up side to pr_ids regressed."
    )

    # Sanity: with both PRs in the cohort, the rework comes back.
    both_in = await compute_rework_rate(
        db_session,
        date_from=base - timedelta(days=5),
        date_to=base + timedelta(days=5),
        pr_ids={base_pr.id, other_cohort_followup.id},
    )
    assert both_in["reworks"] == 1


@pytest.mark.asyncio
async def test_get_dora_v2_flags_cohort_filter_applied(
    db_session: AsyncSession, repo: Repository, human_author: Developer
):
    """v2 must signal which top-level metrics honored the cohort filter, so
    the UI can stop silently displaying all-cohort numbers on cohort-scoped
    cards."""
    base = NOW - timedelta(days=3)
    await _make_pr(
        db_session, repo, human_author, number=10, merged_at=base, files=["a.py"]
    )

    result_all = await get_dora_v2(
        db_session,
        date_from=base - timedelta(days=5),
        date_to=base + timedelta(days=5),
        cohort="all",
    )
    # rework_rate is the only top-level field we can cohort-filter; the
    # deployment-based ones share Deployment rows across cohorts.
    assert result_all["cohort_filter_applied"]["rework_rate"] is False
    assert result_all["cohort_filter_applied"]["deployment_frequency"] is False

    result_cohort = await get_dora_v2(
        db_session,
        date_from=base - timedelta(days=5),
        date_to=base + timedelta(days=5),
        cohort="human",
    )
    assert result_cohort["cohort_filter_applied"]["rework_rate"] is True
    # Deployment-based metrics still False because we can't cohort-filter them.
    assert result_cohort["cohort_filter_applied"]["deployment_frequency"] is False
