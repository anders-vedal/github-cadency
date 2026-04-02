"""Integration tests for AI schedule API endpoints."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.models import BenchmarkGroupConfig


@pytest_asyncio.fixture
async def seed_benchmark_groups(engine):
    """Seed benchmark groups needed by the estimate endpoint."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add(BenchmarkGroupConfig(
            group_key="ics", display_name="IC Engineers", display_order=1,
            roles=["developer", "senior_developer"], metrics=["prs_merged"],
            min_team_size=2, is_default=True,
        ))
        await session.commit()


class TestListSchedules:
    @pytest.mark.asyncio
    async def test_returns_empty_list(self, client):
        resp = await client.get("/api/ai/schedules")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_returns_created_schedule(self, client, sample_developer):
        # Create one first
        create_resp = await client.post("/api/ai/schedules", json={
            "name": "Weekly Health",
            "analysis_type": "team_health",
            "scope_type": "team",
            "scope_id": "backend",
            "frequency": "weekly",
            "day_of_week": 0,
            "hour": 8,
        })
        assert create_resp.status_code == 201

        resp = await client.get("/api/ai/schedules")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Weekly Health"
        assert data[0]["next_run_description"] is not None


class TestCreateSchedule:
    @pytest.mark.asyncio
    async def test_create_valid_schedule(self, client, sample_developer):
        resp = await client.post("/api/ai/schedules", json={
            "name": "Daily Sentiment",
            "analysis_type": "sentiment",
            "scope_type": "developer",
            "scope_id": str(sample_developer.id),
            "frequency": "daily",
            "hour": 9,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Daily Sentiment"
        assert data["analysis_type"] == "sentiment"
        assert data["is_enabled"] is True
        assert data["created_by"] is not None
        assert data["next_run_description"] is not None

    @pytest.mark.asyncio
    async def test_create_weekly_requires_day_of_week(self, client):
        resp = await client.post("/api/ai/schedules", json={
            "name": "Weekly",
            "analysis_type": "team_health",
            "scope_type": "team",
            "scope_id": "backend",
            "frequency": "weekly",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_invalid_analysis_type(self, client):
        resp = await client.post("/api/ai/schedules", json={
            "name": "Bad",
            "analysis_type": "nonexistent",
            "scope_type": "developer",
            "scope_id": "1",
            "frequency": "daily",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_with_repo_ids(self, client, sample_developer, sample_repo):
        resp = await client.post("/api/ai/schedules", json={
            "name": "Repo-filtered",
            "analysis_type": "communication",
            "scope_type": "developer",
            "scope_id": str(sample_developer.id),
            "frequency": "monthly",
            "repo_ids": [sample_repo.id],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["repo_ids"] == [sample_repo.id]


class TestUpdateSchedule:
    @pytest.mark.asyncio
    async def test_toggle_enabled(self, client, sample_developer):
        create_resp = await client.post("/api/ai/schedules", json={
            "name": "Test",
            "analysis_type": "communication",
            "scope_type": "developer",
            "scope_id": str(sample_developer.id),
            "frequency": "daily",
        })
        schedule_id = create_resp.json()["id"]

        resp = await client.patch(f"/api/ai/schedules/{schedule_id}", json={
            "is_enabled": False,
        })
        assert resp.status_code == 200
        assert resp.json()["is_enabled"] is False

    @pytest.mark.asyncio
    async def test_update_name(self, client, sample_developer):
        create_resp = await client.post("/api/ai/schedules", json={
            "name": "Original",
            "analysis_type": "communication",
            "scope_type": "developer",
            "scope_id": str(sample_developer.id),
            "frequency": "daily",
        })
        schedule_id = create_resp.json()["id"]

        resp = await client.patch(f"/api/ai/schedules/{schedule_id}", json={
            "name": "Renamed",
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed"

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_404(self, client):
        resp = await client.patch("/api/ai/schedules/99999", json={
            "name": "Nope",
        })
        assert resp.status_code == 404


class TestDeleteSchedule:
    @pytest.mark.asyncio
    async def test_delete_existing(self, client, sample_developer):
        create_resp = await client.post("/api/ai/schedules", json={
            "name": "To Delete",
            "analysis_type": "communication",
            "scope_type": "developer",
            "scope_id": str(sample_developer.id),
            "frequency": "daily",
        })
        schedule_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/ai/schedules/{schedule_id}")
        assert resp.status_code == 204

        # Verify it's gone
        list_resp = await client.get("/api/ai/schedules")
        assert len(list_resp.json()) == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(self, client):
        resp = await client.delete("/api/ai/schedules/99999")
        assert resp.status_code == 404


class TestEstimateEndpoint:
    @pytest.mark.asyncio
    async def test_general_analysis_estimate(self, client, sample_developer, sample_pr):
        resp = await client.post(
            f"/api/ai/estimate?feature=general_analysis&scope_type=developer&scope_id={sample_developer.id}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "estimated_input_tokens" in data
        assert "character_count" in data
        assert "system_prompt_tokens" in data
        assert "remaining_budget_tokens" in data
        assert "would_exceed_budget" in data

    @pytest.mark.asyncio
    async def test_one_on_one_estimate(self, client, sample_developer, sample_pr, sample_review, seed_benchmark_groups):
        resp = await client.post(
            f"/api/ai/estimate?feature=one_on_one_prep&scope_id={sample_developer.id}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["character_count"] > 0
        assert data["system_prompt_tokens"] > 0

    @pytest.mark.asyncio
    async def test_team_health_estimate(
        self, client, sample_developer, sample_developer_b, sample_pr, sample_review, seed_benchmark_groups,
    ):
        resp = await client.post(
            "/api/ai/estimate?feature=team_health&scope_id=backend"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["character_count"] > 0

    @pytest.mark.asyncio
    async def test_estimate_with_repo_ids(self, client, sample_developer, sample_pr, sample_repo):
        resp = await client.post(
            f"/api/ai/estimate?feature=general_analysis&scope_type=developer&scope_id={sample_developer.id}&repo_ids={sample_repo.id}"
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_estimate_nonexistent_developer(self, client):
        resp = await client.post(
            "/api/ai/estimate?feature=one_on_one_prep&scope_id=99999"
        )
        # Should not 500 — gracefully returns empty estimate
        assert resp.status_code == 200


class TestScheduleRunEndpoint:
    @pytest.mark.asyncio
    async def test_run_nonexistent_schedule_returns_404(self, client):
        resp = await client.post("/api/ai/schedules/99999/run")
        assert resp.status_code == 404
