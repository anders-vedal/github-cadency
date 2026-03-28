"""Integration tests for the /api/sync endpoints."""
from unittest.mock import AsyncMock, patch

import pytest

from app.models.models import Repository, SyncEvent


class TestListRepos:
    @pytest.mark.asyncio
    async def test_list_empty(self, client):
        resp = await client.get("/api/sync/repos")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_repos(self, client, sample_repo):
        resp = await client.get("/api/sync/repos")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["full_name"] == "org/test-repo"
        assert data[0]["is_tracked"] is True


class TestToggleTracking:
    @pytest.mark.asyncio
    async def test_toggle_off(self, client, sample_repo):
        resp = await client.patch(
            f"/api/sync/repos/{sample_repo.id}/track",
            json={"is_tracked": False},
        )
        assert resp.status_code == 200
        assert resp.json()["is_tracked"] is False

    @pytest.mark.asyncio
    async def test_toggle_on(self, client, db_session):
        repo = Repository(
            github_id=55555, name="untracked", full_name="org/untracked",
            is_tracked=False,
        )
        db_session.add(repo)
        await db_session.commit()
        await db_session.refresh(repo)

        resp = await client.patch(
            f"/api/sync/repos/{repo.id}/track",
            json={"is_tracked": True},
        )
        assert resp.status_code == 200
        assert resp.json()["is_tracked"] is True

    @pytest.mark.asyncio
    async def test_toggle_not_found(self, client):
        resp = await client.patch(
            "/api/sync/repos/999/track",
            json={"is_tracked": True},
        )
        assert resp.status_code == 404


class TestSyncEvents:
    @pytest.mark.asyncio
    async def test_list_empty(self, client):
        resp = await client.get("/api/sync/events")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_events(self, client, db_session):
        from datetime import datetime, timezone

        event = SyncEvent(
            sync_type="full",
            status="completed",
            repos_synced=3,
            prs_upserted=10,
            issues_upserted=5,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            duration_s=120,
        )
        db_session.add(event)
        await db_session.commit()

        resp = await client.get("/api/sync/events")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["sync_type"] == "full"
        assert data[0]["status"] == "completed"
        assert data[0]["repos_synced"] == 3

    @pytest.mark.asyncio
    async def test_trigger_full_sync(self, client):
        with patch("app.api.sync.run_sync", new_callable=AsyncMock):
            resp = await client.post("/api/sync/full")
        assert resp.status_code == 202
        assert resp.json()["sync_type"] == "full"

    @pytest.mark.asyncio
    async def test_trigger_incremental_sync(self, client):
        with patch("app.api.sync.run_sync", new_callable=AsyncMock):
            resp = await client.post("/api/sync/incremental")
        assert resp.status_code == 202
        assert resp.json()["sync_type"] == "incremental"
