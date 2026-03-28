"""Integration tests for CI/CD stats API endpoint (P3-07)."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Developer, PRCheckRun, PullRequest, Repository


NOW = datetime.now(timezone.utc)
ONE_WEEK_AGO = NOW - timedelta(days=7)


@pytest_asyncio.fixture
async def ci_data(
    db_session: AsyncSession,
    sample_repo: Repository,
    sample_developer: Developer,
):
    """Seed a merged PR with check runs for API testing."""
    pr = PullRequest(
        github_id=9001,
        repo_id=sample_repo.id,
        author_id=sample_developer.id,
        number=50,
        title="CI Test PR",
        state="closed",
        is_merged=True,
        head_sha="a" * 40,
        created_at=ONE_WEEK_AGO,
        merged_at=NOW - timedelta(days=1),
    )
    db_session.add(pr)
    await db_session.flush()

    db_session.add(PRCheckRun(
        pr_id=pr.id,
        check_name="tests",
        conclusion="success",
        run_attempt=1,
        duration_s=180,
    ))
    db_session.add(PRCheckRun(
        pr_id=pr.id,
        check_name="lint",
        conclusion="failure",
        run_attempt=1,
        duration_s=30,
    ))
    await db_session.commit()
    return pr


@pytest.mark.asyncio
async def test_ci_stats_endpoint(client: AsyncClient, ci_data):
    resp = await client.get("/api/stats/ci")
    assert resp.status_code == 200
    data = resp.json()
    assert data["prs_merged_with_failing_checks"] == 1
    assert data["avg_checks_to_green"] == 1.0  # only "tests" succeeded
    assert data["avg_build_duration_s"] == 105.0  # (180+30)/2
    assert len(data["slowest_checks"]) == 2


@pytest.mark.asyncio
async def test_ci_stats_with_repo_filter(
    client: AsyncClient, ci_data, sample_repo: Repository
):
    resp = await client.get(f"/api/stats/ci?repo_id={sample_repo.id}")
    assert resp.status_code == 200
    assert resp.json()["prs_merged_with_failing_checks"] == 1

    resp_empty = await client.get("/api/stats/ci?repo_id=99999")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_ci_stats_requires_admin(developer_client: AsyncClient):
    resp = await developer_client.get("/api/stats/ci")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_ci_stats_empty(client: AsyncClient):
    """No data should return defaults."""
    resp = await client.get("/api/stats/ci")
    assert resp.status_code == 200
    data = resp.json()
    assert data["prs_merged_with_failing_checks"] == 0
    assert data["avg_checks_to_green"] is None
    assert data["flaky_checks"] == []
