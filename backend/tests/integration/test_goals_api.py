"""Integration tests for the /api/goals endpoints."""
import pytest


class TestCreateGoal:
    @pytest.mark.asyncio
    async def test_create_goal(self, client, sample_developer):
        payload = {
            "developer_id": sample_developer.id,
            "title": "Merge 10 PRs",
            "metric_key": "prs_merged",
            "target_value": 10.0,
            "target_direction": "above",
        }
        resp = await client.post("/api/goals", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Merge 10 PRs"
        assert data["metric_key"] == "prs_merged"
        assert data["target_value"] == 10.0
        assert data["target_direction"] == "above"
        assert data["status"] == "active"
        assert data["baseline_value"] is not None

    @pytest.mark.asyncio
    async def test_create_goal_developer_not_found(self, client):
        payload = {
            "developer_id": 999,
            "title": "Test goal",
            "metric_key": "prs_merged",
            "target_value": 5.0,
        }
        resp = await client.post("/api/goals", json=payload)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_goal_with_baseline(
        self, client, sample_developer, sample_pr
    ):
        """Baseline should be computed from last 30 days of data."""
        payload = {
            "developer_id": sample_developer.id,
            "title": "Increase PRs",
            "metric_key": "prs_merged",
            "target_value": 20.0,
        }
        resp = await client.post("/api/goals", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        # Should have a baseline from existing PR data
        assert data["baseline_value"] >= 0


class TestListGoals:
    @pytest.mark.asyncio
    async def test_list_empty(self, client, sample_developer):
        resp = await client.get(
            f"/api/goals?developer_id={sample_developer.id}"
        )
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_with_goals(self, client, sample_developer):
        # Create a goal first
        await client.post("/api/goals", json={
            "developer_id": sample_developer.id,
            "title": "Goal 1",
            "metric_key": "prs_merged",
            "target_value": 5.0,
        })

        resp = await client.get(
            f"/api/goals?developer_id={sample_developer.id}"
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    @pytest.mark.asyncio
    async def test_list_developer_not_found(self, client):
        resp = await client.get("/api/goals?developer_id=999")
        assert resp.status_code == 404


class TestUpdateGoal:
    @pytest.mark.asyncio
    async def test_update_status(self, client, sample_developer):
        create_resp = await client.post("/api/goals", json={
            "developer_id": sample_developer.id,
            "title": "Test goal",
            "metric_key": "reviews_given",
            "target_value": 10.0,
        })
        goal_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/goals/{goal_id}",
            json={"status": "achieved"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "achieved"
        assert resp.json()["achieved_at"] is not None

    @pytest.mark.asyncio
    async def test_update_notes(self, client, sample_developer):
        create_resp = await client.post("/api/goals", json={
            "developer_id": sample_developer.id,
            "title": "Test goal",
            "metric_key": "reviews_given",
            "target_value": 10.0,
        })
        goal_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/goals/{goal_id}",
            json={"notes": "Making good progress"},
        )
        assert resp.status_code == 200
        assert resp.json()["notes"] == "Making good progress"

    @pytest.mark.asyncio
    async def test_update_not_found(self, client):
        resp = await client.patch("/api/goals/999", json={"status": "abandoned"})
        assert resp.status_code == 404


class TestGoalProgress:
    @pytest.mark.asyncio
    async def test_progress(self, client, sample_developer, sample_pr):
        create_resp = await client.post("/api/goals", json={
            "developer_id": sample_developer.id,
            "title": "Merge PRs",
            "metric_key": "prs_merged",
            "target_value": 5.0,
        })
        goal_id = create_resp.json()["id"]

        resp = await client.get(f"/api/goals/{goal_id}/progress")
        assert resp.status_code == 200
        data = resp.json()
        assert data["goal_id"] == goal_id
        assert data["title"] == "Merge PRs"
        assert data["target_value"] == 5.0
        assert len(data["history"]) == 8  # 8 weekly periods

    @pytest.mark.asyncio
    async def test_progress_not_found(self, client):
        resp = await client.get("/api/goals/999/progress")
        assert resp.status_code == 404
