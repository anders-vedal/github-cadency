"""Unit tests for CI/CD check-run stats (P3-07)."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Developer, PRCheckRun, PullRequest, Repository
from app.services.stats import get_check_failure_details, get_ci_stats


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
            started_at=ONE_WEEK_AGO + timedelta(hours=i),
            duration_s=60,
        ))

    await db_session.commit()

    result = await get_ci_stats(db_session, TWO_WEEKS_AGO, NOW)
    assert len(result.flaky_checks) == 1
    assert result.flaky_checks[0].name == "flaky-test"
    assert abs(result.flaky_checks[0].failure_rate - 0.333) < 0.01
    assert result.flaky_checks[0].total_runs == 6
    assert result.flaky_checks[0].category == "flaky"
    # last_run_at should be the most recent started_at (i=5 → ONE_WEEK_AGO + 5h).
    # aiosqlite may return naive datetimes, so compare via .replace(tzinfo=None).
    assert result.flaky_checks[0].last_run_at is not None
    expected_last = (ONE_WEEK_AGO + timedelta(hours=5)).replace(tzinfo=None)
    actual_last = result.flaky_checks[0].last_run_at.replace(tzinfo=None)
    assert abs((actual_last - expected_last).total_seconds()) < 1


@pytest.mark.asyncio
async def test_last_run_at_reflects_stale_check(
    db_session: AsyncSession, ci_repo: Repository, ci_dev: Developer
):
    """A check whose latest run is 30 days old should surface that last_run_at."""
    stale_start = NOW - timedelta(days=30)
    for i in range(6):
        pr = PullRequest(
            github_id=11000 + i,
            repo_id=ci_repo.id,
            author_id=ci_dev.id,
            number=600 + i,
            title=f"Stale PR {i}",
            state="closed",
            is_merged=True,
            created_at=stale_start + timedelta(minutes=i),
        )
        db_session.add(pr)
        await db_session.flush()

        db_session.add(PRCheckRun(
            pr_id=pr.id,
            check_name="stale-check",
            conclusion="failure" if i < 3 else "success",
            run_attempt=1,
            started_at=stale_start + timedelta(minutes=i),
            duration_s=30,
        ))

    await db_session.commit()

    result = await get_ci_stats(db_session, NOW - timedelta(days=60), NOW)
    stale = [c for c in result.flaky_checks if c.name == "stale-check"]
    assert len(stale) == 1
    assert stale[0].last_run_at is not None
    # aiosqlite may return naive datetimes — normalize both sides before subtracting.
    now_naive = NOW.replace(tzinfo=None)
    last_naive = stale[0].last_run_at.replace(tzinfo=None)
    age_days = (now_naive - last_naive).total_seconds() / 86400
    assert 29 < age_days < 31


@pytest.mark.asyncio
async def test_broken_check_category(
    db_session: AsyncSession, ci_repo: Repository, ci_dev: Developer
):
    """A check that fails 100% of the time (10 runs) should be categorized as broken."""
    for i in range(10):
        pr = PullRequest(
            github_id=9000 + i,
            repo_id=ci_repo.id,
            author_id=ci_dev.id,
            number=400 + i,
            title=f"Broken PR {i}",
            state="closed",
            is_merged=True,
            created_at=ONE_WEEK_AGO + timedelta(hours=i),
        )
        db_session.add(pr)
        await db_session.flush()

        db_session.add(PRCheckRun(
            pr_id=pr.id,
            check_name="always-fails",
            conclusion="failure",
            run_attempt=1,
            duration_s=30,
        ))

    await db_session.commit()

    result = await get_ci_stats(db_session, TWO_WEEKS_AGO, NOW)
    broken = [c for c in result.flaky_checks if c.name == "always-fails"]
    assert len(broken) == 1
    assert broken[0].category == "broken"
    assert broken[0].failure_rate == 1.0
    assert broken[0].total_runs == 10


@pytest.mark.asyncio
async def test_flaky_check_category_midrange(
    db_session: AsyncSession, ci_repo: Repository, ci_dev: Developer
):
    """A check at 30% failure rate over 20 runs should be categorized as flaky, not broken."""
    # 6 failures, 14 successes over 20 runs = 30%
    for i in range(20):
        pr = PullRequest(
            github_id=10000 + i,
            repo_id=ci_repo.id,
            author_id=ci_dev.id,
            number=500 + i,
            title=f"Flaky PR {i}",
            state="closed",
            is_merged=True,
            created_at=ONE_WEEK_AGO + timedelta(hours=i),
        )
        db_session.add(pr)
        await db_session.flush()

        db_session.add(PRCheckRun(
            pr_id=pr.id,
            check_name="sometimes-fails",
            conclusion="failure" if i < 6 else "success",
            run_attempt=1,
            duration_s=30,
        ))

    await db_session.commit()

    result = await get_ci_stats(db_session, TWO_WEEKS_AGO, NOW)
    flaky = [c for c in result.flaky_checks if c.name == "sometimes-fails"]
    assert len(flaky) == 1
    assert flaky[0].category == "flaky"
    assert abs(flaky[0].failure_rate - 0.3) < 0.01
    assert flaky[0].total_runs == 20


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


@pytest.mark.asyncio
async def test_trend_falling(
    db_session: AsyncSession, ci_repo: Repository, ci_dev: Developer
):
    """A check at 80% first half, 20% second half should report trend='falling'."""
    # 14-day window: midpoint = NOW - 7d.
    # First-half: 10 PRs at NOW - 12d, 8 failures (80%).
    # Second-half: 10 PRs at NOW - 2d, 2 failures (20%).
    for i in range(10):
        pr = PullRequest(
            github_id=12000 + i,
            repo_id=ci_repo.id,
            author_id=ci_dev.id,
            number=700 + i,
            title=f"First-half PR {i}",
            state="closed",
            is_merged=True,
            created_at=NOW - timedelta(days=12, minutes=i),
        )
        db_session.add(pr)
        await db_session.flush()
        db_session.add(PRCheckRun(
            pr_id=pr.id,
            check_name="trend-check",
            conclusion="failure" if i < 8 else "success",
            run_attempt=1,
            started_at=NOW - timedelta(days=12, minutes=i),
            duration_s=60,
        ))

    for i in range(10):
        pr = PullRequest(
            github_id=13000 + i,
            repo_id=ci_repo.id,
            author_id=ci_dev.id,
            number=800 + i,
            title=f"Second-half PR {i}",
            state="closed",
            is_merged=True,
            created_at=NOW - timedelta(days=2, minutes=i),
        )
        db_session.add(pr)
        await db_session.flush()
        db_session.add(PRCheckRun(
            pr_id=pr.id,
            check_name="trend-check",
            conclusion="failure" if i < 2 else "success",
            run_attempt=1,
            started_at=NOW - timedelta(days=2, minutes=i),
            duration_s=60,
        ))

    await db_session.commit()

    result = await get_ci_stats(db_session, NOW - timedelta(days=14), NOW)
    trend_rows = [c for c in result.flaky_checks if c.name == "trend-check"]
    assert len(trend_rows) == 1
    row = trend_rows[0]
    assert row.trend == "falling"
    assert row.failure_rate_first_half == 0.8
    assert row.failure_rate_second_half == 0.2


@pytest.mark.asyncio
async def test_trend_insufficient_sample_returns_none(
    db_session: AsyncSession, ci_repo: Repository, ci_dev: Developer
):
    """If one half has <3 runs the trend should be None (not invented)."""
    # First half: 5 PRs (3 failures → 60%). Second half: 2 PRs (1 failure → 50%).
    # Total = 7 runs so ≥5 runs having clause passes; overall failure rate 4/7 ≈ 57%.
    for i in range(5):
        pr = PullRequest(
            github_id=14000 + i,
            repo_id=ci_repo.id,
            author_id=ci_dev.id,
            number=900 + i,
            title=f"Early PR {i}",
            state="closed",
            is_merged=True,
            created_at=NOW - timedelta(days=12, minutes=i),
        )
        db_session.add(pr)
        await db_session.flush()
        db_session.add(PRCheckRun(
            pr_id=pr.id,
            check_name="skinny-trend",
            conclusion="failure" if i < 3 else "success",
            run_attempt=1,
            started_at=NOW - timedelta(days=12, minutes=i),
            duration_s=60,
        ))

    for i in range(2):
        pr = PullRequest(
            github_id=15000 + i,
            repo_id=ci_repo.id,
            author_id=ci_dev.id,
            number=1000 + i,
            title=f"Late PR {i}",
            state="closed",
            is_merged=True,
            created_at=NOW - timedelta(days=2, minutes=i),
        )
        db_session.add(pr)
        await db_session.flush()
        db_session.add(PRCheckRun(
            pr_id=pr.id,
            check_name="skinny-trend",
            conclusion="failure" if i < 1 else "success",
            run_attempt=1,
            started_at=NOW - timedelta(days=2, minutes=i),
            duration_s=60,
        ))

    await db_session.commit()

    result = await get_ci_stats(db_session, NOW - timedelta(days=14), NOW)
    skinny = [c for c in result.flaky_checks if c.name == "skinny-trend"]
    assert len(skinny) == 1
    assert skinny[0].trend is None
    assert skinny[0].failure_rate_first_half is None
    assert skinny[0].failure_rate_second_half is None


@pytest.mark.asyncio
async def test_check_failure_details_was_eventually_green(
    db_session: AsyncSession, ci_repo: Repository, ci_dev: Developer
):
    """Drill-down returns failing PRs with correct was_eventually_green + ordering."""
    # PR1: failure (attempt 1), success (attempt 2) — eventually_green True
    pr1 = PullRequest(
        github_id=20001,
        repo_id=ci_repo.id,
        author_id=ci_dev.id,
        number=2001,
        title="Fixed after retry",
        state="closed",
        is_merged=True,
        created_at=NOW - timedelta(days=2),
        html_url="https://github.com/org/ci-repo/pull/2001",
    )
    db_session.add(pr1)
    await db_session.flush()
    db_session.add(PRCheckRun(
        pr_id=pr1.id,
        check_name="drill-target",
        conclusion="failure",
        run_attempt=1,
        started_at=NOW - timedelta(days=2, hours=2),
        html_url="https://github.com/org/ci-repo/runs/1",
    ))
    db_session.add(PRCheckRun(
        pr_id=pr1.id,
        check_name="drill-target",
        conclusion="success",
        run_attempt=2,
        started_at=NOW - timedelta(days=2, hours=1),
    ))

    # PR2: failure only — eventually_green False
    pr2 = PullRequest(
        github_id=20002,
        repo_id=ci_repo.id,
        author_id=ci_dev.id,
        number=2002,
        title="Still broken",
        state="closed",
        is_merged=False,
        created_at=NOW - timedelta(days=1),
        html_url="https://github.com/org/ci-repo/pull/2002",
    )
    db_session.add(pr2)
    await db_session.flush()
    db_session.add(PRCheckRun(
        pr_id=pr2.id,
        check_name="drill-target",
        conclusion="failure",
        run_attempt=1,
        started_at=NOW - timedelta(days=1, hours=1),
        html_url="https://github.com/org/ci-repo/runs/2",
    ))

    await db_session.commit()

    result = await get_check_failure_details(
        db_session,
        check_name="drill-target",
        date_from=NOW - timedelta(days=14),
        date_to=NOW,
    )
    assert result.check_name == "drill-target"
    assert len(result.entries) == 2

    # Ordering: most recent failure first (PR2 failed 1 day ago, PR1 2 days ago)
    assert result.entries[0].pr_number == 2002
    assert result.entries[0].was_eventually_green is False
    assert result.entries[0].author_login == "ci_dev"

    assert result.entries[1].pr_number == 2001
    assert result.entries[1].was_eventually_green is True
    assert result.entries[1].run_html_url == "https://github.com/org/ci-repo/runs/1"


@pytest.mark.asyncio
async def test_check_failure_details_limit(
    db_session: AsyncSession, ci_repo: Repository, ci_dev: Developer
):
    """The limit parameter should cap the number of entries returned."""
    for i in range(5):
        pr = PullRequest(
            github_id=30000 + i,
            repo_id=ci_repo.id,
            author_id=ci_dev.id,
            number=3000 + i,
            title=f"Drill PR {i}",
            state="closed",
            is_merged=True,
            created_at=NOW - timedelta(days=1, minutes=i),
        )
        db_session.add(pr)
        await db_session.flush()
        db_session.add(PRCheckRun(
            pr_id=pr.id,
            check_name="drill-limit",
            conclusion="failure",
            run_attempt=1,
            started_at=NOW - timedelta(days=1, minutes=i),
        ))
    await db_session.commit()

    result = await get_check_failure_details(
        db_session,
        check_name="drill-limit",
        date_from=NOW - timedelta(days=14),
        date_to=NOW,
        limit=2,
    )
    assert len(result.entries) == 2


@pytest.mark.asyncio
async def test_check_failure_details_repo_filter(
    db_session: AsyncSession, ci_repo: Repository, ci_dev: Developer
):
    """repo_id param should scope results."""
    pr = PullRequest(
        github_id=40001,
        repo_id=ci_repo.id,
        author_id=ci_dev.id,
        number=4001,
        title="In-repo PR",
        state="closed",
        is_merged=True,
        created_at=NOW - timedelta(days=1),
    )
    db_session.add(pr)
    await db_session.flush()
    db_session.add(PRCheckRun(
        pr_id=pr.id,
        check_name="drill-repo",
        conclusion="failure",
        run_attempt=1,
        started_at=NOW - timedelta(days=1),
    ))
    await db_session.commit()

    result = await get_check_failure_details(
        db_session,
        check_name="drill-repo",
        date_from=NOW - timedelta(days=14),
        date_to=NOW,
        repo_id=ci_repo.id,
    )
    assert len(result.entries) == 1

    # A non-existent repo should yield empty
    empty = await get_check_failure_details(
        db_session,
        check_name="drill-repo",
        date_from=NOW - timedelta(days=14),
        date_to=NOW,
        repo_id=99999,
    )
    assert len(empty.entries) == 0
