"""Integration tests for collaboration trends API endpoint (P4-04)."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Developer, PRReview, PullRequest, Repository


NOW = datetime.now(timezone.utc)
TWO_MONTHS_AGO = NOW - timedelta(days=60)


@pytest_asyncio.fixture
async def collab_data(
    db_session: AsyncSession,
    sample_repo: Repository,
    sample_developer: Developer,
    sample_developer_b: Developer,
):
    """Seed review data across 2 months for trend testing."""
    # PR authored by sample_developer, reviewed by sample_developer_b
    pr1 = PullRequest(
        github_id=5001,
        repo_id=sample_repo.id,
        author_id=sample_developer.id,
        number=101,
        title="Feature A",
        state="closed",
        is_merged=True,
        created_at=TWO_MONTHS_AGO,
        merged_at=TWO_MONTHS_AGO + timedelta(days=1),
    )
    pr2 = PullRequest(
        github_id=5002,
        repo_id=sample_repo.id,
        author_id=sample_developer.id,
        number=102,
        title="Feature B",
        state="closed",
        is_merged=True,
        created_at=NOW - timedelta(days=10),
        merged_at=NOW - timedelta(days=9),
    )
    db_session.add_all([pr1, pr2])
    await db_session.flush()

    # Reviews: dev_b reviews dev's PRs in both months
    review1 = PRReview(
        github_id=6001,
        pr_id=pr1.id,
        reviewer_id=sample_developer_b.id,
        state="APPROVED",
        body="LGTM",
        body_length=4,
        submitted_at=TWO_MONTHS_AGO + timedelta(hours=5),
    )
    review2 = PRReview(
        github_id=6002,
        pr_id=pr2.id,
        reviewer_id=sample_developer_b.id,
        state="APPROVED",
        body="Looks good",
        body_length=10,
        submitted_at=NOW - timedelta(days=9),
    )
    db_session.add_all([review1, review2])
    await db_session.commit()


@pytest.mark.asyncio
async def test_collaboration_trends_endpoint(client: AsyncClient, collab_data):
    """Basic endpoint returns 200 with period data."""
    date_from = (TWO_MONTHS_AGO - timedelta(days=1)).strftime("%Y-%m-%d")
    date_to = NOW.strftime("%Y-%m-%d")
    resp = await client.get(
        f"/api/stats/collaboration/trends?date_from={date_from}&date_to={date_to}"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "periods" in data
    assert len(data["periods"]) >= 2  # at least 2 monthly buckets

    # Each period should have the expected fields
    for period in data["periods"]:
        assert "period_start" in period
        assert "period_end" in period
        assert "period_label" in period
        assert "bus_factor_count" in period
        assert "silo_count" in period
        assert "isolated_developer_count" in period
        assert isinstance(period["bus_factor_count"], int)
        assert isinstance(period["silo_count"], int)


@pytest.mark.asyncio
async def test_collaboration_trends_empty(client: AsyncClient):
    """Returns empty periods when no data exists."""
    resp = await client.get("/api/stats/collaboration/trends")
    assert resp.status_code == 200
    data = resp.json()
    assert "periods" in data


@pytest.mark.asyncio
async def test_collaboration_trends_bus_factor_detection(
    client: AsyncClient, collab_data
):
    """Bus factor detected when one reviewer dominates a repo."""
    date_from = (TWO_MONTHS_AGO - timedelta(days=1)).strftime("%Y-%m-%d")
    date_to = NOW.strftime("%Y-%m-%d")
    resp = await client.get(
        f"/api/stats/collaboration/trends?date_from={date_from}&date_to={date_to}"
    )
    data = resp.json()
    # sample_developer_b is the sole reviewer → should be a bus factor in periods with reviews
    periods_with_bus = [p for p in data["periods"] if p["bus_factor_count"] > 0]
    assert len(periods_with_bus) > 0


@pytest.mark.asyncio
async def test_collaboration_trends_requires_admin(
    developer_client: AsyncClient, collab_data
):
    """Non-admin users should get 403."""
    resp = await developer_client.get("/api/stats/collaboration/trends")
    assert resp.status_code == 403
