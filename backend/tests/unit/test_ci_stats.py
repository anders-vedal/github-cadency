"""Unit tests for CI/CD check-run stats (P3-07)."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Developer, PRCheckRun, PullRequest, Repository
from app.services.stats import get_ci_stats


NOW = datetime.now(timezone.utc)
ONE_WEEK_AGO = NOW - timedelta(days=7)
TWO_WEEKS_AGO = NOW - timedelta(days=14)


@pytest_asyncio.fixture
async def ci_repo(db_session: AsyncSession) -> Repository:
    repo = Repository(
        github_id=77777,
        name="ci-repo",
        full_name="org/ci-repo",
        is_tracked=True,
        created_at=NOW,
    )
    db_session.add(repo)
    await db_session.commit()
    await db_session.refresh(repo)
    return repo


@pytest_asyncio.fixture
async def ci_dev(db_session: AsyncSession) -> Developer:
    dev = Developer(
        github_username="ci_dev",
        display_name="CI Dev",
        app_role="developer",
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )
    db_session.add(dev)
    await db_session.commit()
    await db_session.refresh(dev)
    return dev


@pytest_asyncio.fixture
async def merged_pr_with_checks(
    db_session: AsyncSession, ci_repo: Repository, ci_dev: Developer
) -> PullRequest:
    """A merged PR with a mix of passing and failing check runs."""
    pr = PullRequest(
        github_id=5001,
        repo_id=ci_repo.id,
        author_id=ci_dev.id,
        number=1,
        title="Feature A",
        state="closed",
        is_merged=True,
        head_sha="abc123" * 6 + "abcd",
        created_at=ONE_WEEK_AGO,
        merged_at=NOW - timedelta(days=1),
    )
    db_session.add(pr)
    await db_session.flush()

    # Check run: "tests" — failed on attempt 1, passed on attempt 2
    db_session.add(PRCheckRun(
        pr_id=pr.id,
        check_name="tests",
        conclusion="failure",
        run_attempt=1,
        started_at=ONE_WEEK_AGO,
        completed_at=ONE_WEEK_AGO + timedelta(minutes=5),
        duration_s=300,
    ))
    db_session.add(PRCheckRun(
        pr_id=pr.id,
        check_name="tests",
        conclusion="success",
        run_attempt=2,
        started_at=ONE_WEEK_AGO + timedelta(hours=1),
        completed_at=ONE_WEEK_AGO + timedelta(hours=1, minutes=6),
        duration_s=360,
    ))

    # Check run: "lint" — passed first try
    db_session.add(PRCheckRun(
        pr_id=pr.id,
        check_name="lint",
        conclusion="success",
        run_attempt=1,
        started_at=ONE_WEEK_AGO,
        completed_at=ONE_WEEK_AGO + timedelta(minutes=2),
        duration_s=120,
    ))

    # Check run: "build" — failed (never green)
    db_session.add(PRCheckRun(
        pr_id=pr.id,
        check_name="build",
        conclusion="failure",
        run_attempt=1,
        started_at=ONE_WEEK_AGO,
        completed_at=ONE_WEEK_AGO + timedelta(minutes=10),
        duration_s=600,
    ))

    await db_session.commit()
    await db_session.refresh(pr)
    return pr


@pytest.mark.asyncio
async def test_prs_merged_with_failing_checks(
    db_session: AsyncSession, merged_pr_with_checks: PullRequest
):
    """PRs merged with at least one failing check should be counted."""
    result = await get_ci_stats(db_session, TWO_WEEKS_AGO, NOW)
    assert result.prs_merged_with_failing_checks == 1


@pytest.mark.asyncio
async def test_avg_checks_to_green(
    db_session: AsyncSession, merged_pr_with_checks: PullRequest
):
    """Average attempts to green: tests=2, lint=1 → avg 1.5."""
    result = await get_ci_stats(db_session, TWO_WEEKS_AGO, NOW)
    assert result.avg_checks_to_green == 1.5


@pytest.mark.asyncio
async def test_avg_build_duration(
    db_session: AsyncSession, merged_pr_with_checks: PullRequest
):
    """Avg duration across 4 check runs: (300+360+120+600)/4 = 345."""
    result = await get_ci_stats(db_session, TWO_WEEKS_AGO, NOW)
    assert result.avg_build_duration_s == 345.0


@pytest.mark.asyncio
async def test_slowest_checks(
    db_session: AsyncSession, merged_pr_with_checks: PullRequest
):
    """Slowest checks should be ordered by avg duration desc."""
    result = await get_ci_stats(db_session, TWO_WEEKS_AGO, NOW)
    assert len(result.slowest_checks) == 3
    assert result.slowest_checks[0].name == "build"
    assert result.slowest_checks[0].avg_duration_s == 600.0


@pytest.mark.asyncio
async def test_empty_data_returns_defaults(db_session: AsyncSession):
    """No check runs should return all defaults."""
    result = await get_ci_stats(db_session, TWO_WEEKS_AGO, NOW)
    assert result.prs_merged_with_failing_checks == 0
    assert result.avg_checks_to_green is None
    assert result.flaky_checks == []
    assert result.avg_build_duration_s is None
    assert result.slowest_checks == []


@pytest.mark.asyncio
async def test_repo_filter(
    db_session: AsyncSession,
    ci_repo: Repository,
    merged_pr_with_checks: PullRequest,
):
    """Filtering by repo should scope the results."""
    result = await get_ci_stats(db_session, TWO_WEEKS_AGO, NOW, repo_id=ci_repo.id)
    assert result.prs_merged_with_failing_checks == 1

    # Non-existent repo should return empty
    result_empty = await get_ci_stats(db_session, TWO_WEEKS_AGO, NOW, repo_id=99999)
    assert result_empty.prs_merged_with_failing_checks == 0


@pytest.mark.asyncio
async def test_flaky_check_detection(
    db_session: AsyncSession, ci_repo: Repository, ci_dev: Developer
):
    """Checks with >10% failure rate and >=5 runs should be flagged as flaky."""
    # Create 6 PRs each with a "flaky-test" check — 4 pass, 2 fail (33% rate)
    for i in range(6):
        pr = PullRequest(
            github_id=6000 + i,
            repo_id=ci_repo.id,
            author_id=ci_dev.id,
            number=100 + i,
            title=f"PR {i}",
            state="closed",
            is_merged=True,
            created_at=ONE_WEEK_AGO + timedelta(hours=i),
        )
        db_session.add(pr)
        await db_session.flush()

        db_session.add(PRCheckRun(
            pr_id=pr.id,
            check_name="flaky-test",
            conclusion="failure" if i < 2 else "success",
            run_attempt=1,
            duration_s=60,
        ))

    await db_session.commit()

    result = await get_ci_stats(db_session, TWO_WEEKS_AGO, NOW)
    assert len(result.flaky_checks) == 1
    assert result.flaky_checks[0].name == "flaky-test"
    assert abs(result.flaky_checks[0].failure_rate - 0.333) < 0.01
    assert result.flaky_checks[0].total_runs == 6


@pytest.mark.asyncio
async def test_non_merged_pr_not_counted_as_failing(
    db_session: AsyncSession, ci_repo: Repository, ci_dev: Developer
):
    """Open PRs with failing checks should NOT count in merged-with-failing."""
    pr = PullRequest(
        github_id=7001,
        repo_id=ci_repo.id,
        author_id=ci_dev.id,
        number=200,
        title="Open PR",
        state="open",
        is_merged=False,
        created_at=ONE_WEEK_AGO,
    )
    db_session.add(pr)
    await db_session.flush()

    db_session.add(PRCheckRun(
        pr_id=pr.id,
        check_name="tests",
        conclusion="failure",
        run_attempt=1,
    ))
    await db_session.commit()

    result = await get_ci_stats(db_session, TWO_WEEKS_AGO, NOW)
    assert result.prs_merged_with_failing_checks == 0


@pytest.mark.asyncio
async def test_date_range_filtering(
    db_session: AsyncSession, ci_repo: Repository, ci_dev: Developer
):
    """PRs outside the date range should not be included."""
    old_pr = PullRequest(
        github_id=8001,
        repo_id=ci_repo.id,
        author_id=ci_dev.id,
        number=300,
        title="Old PR",
        state="closed",
        is_merged=True,
        created_at=NOW - timedelta(days=60),
        merged_at=NOW - timedelta(days=59),
    )
    db_session.add(old_pr)
    await db_session.flush()

    db_session.add(PRCheckRun(
        pr_id=old_pr.id,
        check_name="tests",
        conclusion="failure",
        run_attempt=1,
    ))
    await db_session.commit()

    # Query last 30 days — should not include the old PR
    result = await get_ci_stats(db_session, NOW - timedelta(days=30), NOW)
    assert result.prs_merged_with_failing_checks == 0
