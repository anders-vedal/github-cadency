"""Integration test for the Phase D2-optimized compute_rework_rate self-join.

Previously the function issued one query per merged PR (N+1); this asserts the
single self-join produces the same answers on a seeded dataset.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Developer, PRFile, PullRequest, Repository
from app.services.dora_v2 import compute_rework_rate

NOW = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def repo(db_session: AsyncSession) -> Repository:
    r = Repository(
        github_id=1,
        name="widgets",
        full_name="acme/widgets",
        is_tracked=True,
        created_at=NOW,
    )
    db_session.add(r)
    await db_session.commit()
    await db_session.refresh(r)
    return r


@pytest_asyncio.fixture
async def author(db_session: AsyncSession) -> Developer:
    dev = Developer(
        github_username="author",
        display_name="Author",
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
) -> PullRequest:
    pr = PullRequest(
        github_id=1000 + number,
        repo_id=repo.id,
        author_id=author.id,
        number=number,
        title=f"PR {number}",
        state="closed",
        is_merged=True,
        merged_at=merged_at,
        created_at=merged_at - timedelta(hours=2),
        updated_at=merged_at,
    )
    db.add(pr)
    await db.flush()
    for fn in files:
        db.add(PRFile(pr_id=pr.id, filename=fn))
    await db.commit()
    await db.refresh(pr)
    return pr


@pytest.mark.asyncio
async def test_rework_rate_counts_shared_file_followups_within_seven_days(
    db_session: AsyncSession, repo: Repository, author: Developer
):
    base = NOW - timedelta(days=3)
    # PR #1: merged at base, touches a.py. Has a follow-up (#2) two days later.
    # PR #2: the follow-up itself also touches a.py — it should NOT count as reworked
    #        unless someone else touches a.py after its merge within 7 days.
    # PR #3: merged two days before base, touches b.py. No follow-up.
    await _make_pr(
        db_session, repo, author, number=1, merged_at=base, files=["a.py"]
    )
    await _make_pr(
        db_session, repo, author, number=2, merged_at=base + timedelta(days=2), files=["a.py"]
    )
    await _make_pr(
        db_session, repo, author, number=3, merged_at=base - timedelta(days=2), files=["b.py"]
    )

    result = await compute_rework_rate(
        db_session,
        date_from=base - timedelta(days=5),
        date_to=base + timedelta(days=5),
    )

    # PR #1 has a follow-up (#2) on the same file within 7 days → reworked
    # PR #2 has no follow-up in the window → not reworked
    # PR #3 has no follow-up on its file → not reworked
    assert result["merges"] == 3
    assert result["reworks"] == 1
    assert result["rework_rate"] == pytest.approx(1 / 3)


@pytest.mark.asyncio
async def test_rework_rate_ignores_followups_outside_window(
    db_session: AsyncSession, repo: Repository, author: Developer
):
    base = NOW - timedelta(days=30)
    await _make_pr(
        db_session, repo, author, number=10, merged_at=base, files=["c.py"]
    )
    # Follow-up 10 days later — outside the 7-day window
    await _make_pr(
        db_session, repo, author, number=11, merged_at=base + timedelta(days=10), files=["c.py"]
    )

    result = await compute_rework_rate(
        db_session, date_from=base - timedelta(days=1), date_to=base + timedelta(days=1)
    )
    assert result["merges"] == 1
    assert result["reworks"] == 0


@pytest.mark.asyncio
async def test_rework_rate_respects_pr_ids_filter(
    db_session: AsyncSession, repo: Repository, author: Developer
):
    base = NOW - timedelta(days=3)
    pr1 = await _make_pr(
        db_session, repo, author, number=20, merged_at=base, files=["d.py"]
    )
    await _make_pr(
        db_session, repo, author, number=21, merged_at=base + timedelta(days=1), files=["d.py"]
    )
    # Restrict to pr1 only
    result = await compute_rework_rate(
        db_session,
        date_from=base - timedelta(days=5),
        date_to=base + timedelta(days=5),
        pr_ids={pr1.id},
    )
    assert result["merges"] == 1
    assert result["reworks"] == 1
