"""Integration tests for DORA metrics API endpoint (P4-01)."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Deployment, Repository


NOW = datetime.now(timezone.utc)
ONE_WEEK_AGO = NOW - timedelta(days=7)


@pytest_asyncio.fixture
async def dora_data(db_session: AsyncSession, sample_repo: Repository):
    """Seed deployments for API testing."""
    db_session.add(Deployment(
        repo_id=sample_repo.id,
        workflow_run_id=10001,
        environment="production",
        status="success",
        sha="b" * 40,
        deployed_at=NOW - timedelta(days=1),
        workflow_name="deploy",
        lead_time_s=7200,
    ))
    db_session.add(Deployment(
        repo_id=sample_repo.id,
        workflow_run_id=10002,
        environment="production",
        status="success",
        sha="c" * 40,
        deployed_at=NOW - timedelta(days=3),
        workflow_name="deploy",
        lead_time_s=3600,
    ))
    await db_session.commit()


@pytest.mark.asyncio
async def test_dora_endpoint(client: AsyncClient, dora_data):
    resp = await client.get("/api/stats/dora")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_deployments"] == 2
    assert data["deploy_frequency"] > 0
    assert data["avg_lead_time_hours"] == 1.5  # (2+1)/2
    assert len(data["deployments"]) == 2


@pytest.mark.asyncio
async def test_dora_with_repo_filter(
    client: AsyncClient, dora_data, sample_repo: Repository
):
    resp = await client.get(f"/api/stats/dora?repo_id={sample_repo.id}")
    assert resp.status_code == 200
    assert resp.json()["total_deployments"] == 2

    resp_empty = await client.get("/api/stats/dora?repo_id=99999")
    assert resp_empty.status_code == 200
    assert resp_empty.json()["total_deployments"] == 0


@pytest.mark.asyncio
async def test_dora_requires_admin(developer_client: AsyncClient):
    resp = await developer_client.get("/api/stats/dora")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_dora_empty(client: AsyncClient):
    """No deployments should return defaults."""
    resp = await client.get("/api/stats/dora")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_deployments"] == 0
    assert data["deploy_frequency"] == 0.0
    assert data["avg_lead_time_hours"] is None
    assert data["deployments"] == []
    # New CFR/MTTR fields should be present with defaults
    assert data["change_failure_rate"] is None
    assert data["cfr_band"] == "low"
    assert data["avg_mttr_hours"] is None
    assert data["mttr_band"] == "low"
    assert data["failure_deployments"] == 0
    assert data["overall_band"] == "low"


@pytest.mark.asyncio
async def test_dora_cfr_fields_in_response(
    client: AsyncClient, dora_data, sample_repo: Repository
):
    """API should include CFR/MTTR fields."""
    resp = await client.get("/api/stats/dora")
    assert resp.status_code == 200
    data = resp.json()
    assert "change_failure_rate" in data
    assert "cfr_band" in data
    assert "avg_mttr_hours" in data
    assert "mttr_band" in data
    assert "failure_deployments" in data
    assert "overall_band" in data
