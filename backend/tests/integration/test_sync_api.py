"""Integration tests for the /api/sync endpoints."""
from datetime import datetime, timezone
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
        assert data[0]["pr_count"] >= 0
        assert data[0]["issue_count"] >= 0


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
        # New fields present
        assert data[0]["is_resumable"] is False
        assert data[0]["repos_completed"] is not None

    @pytest.mark.asyncio
    async def test_start_sync(self, client):
        with patch("app.api.sync.run_sync", new_callable=AsyncMock):
            resp = await client.post(
                "/api/sync/start",
                json={"sync_type": "full"},
            )
        assert resp.status_code == 202
        assert resp.json()["sync_type"] == "full"

    @pytest.mark.asyncio
    async def test_start_incremental_sync(self, client):
        with patch("app.api.sync.run_sync", new_callable=AsyncMock):
            resp = await client.post(
                "/api/sync/start",
                json={"sync_type": "incremental"},
            )
        assert resp.status_code == 202
        assert resp.json()["sync_type"] == "incremental"

    @pytest.mark.asyncio
    async def test_start_sync_conflict(self, client, db_session):
        """409 if a sync is already running."""
        event = SyncEvent(
            sync_type="full",
            status="started",
            started_at=datetime.now(timezone.utc),
        )
        db_session.add(event)
        await db_session.commit()

        resp = await client.post(
            "/api/sync/start",
            json={"sync_type": "full"},
        )
        assert resp.status_code == 409


class TestSyncStatus:
    @pytest.mark.asyncio
    async def test_status_empty(self, client):
        resp = await client.get("/api/sync/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_sync"] is None
        assert data["last_completed"] is None
        assert data["tracked_repos_count"] == 0
        assert data["total_repos_count"] == 0

    @pytest.mark.asyncio
    async def test_status_with_active_sync(self, client, db_session):
        event = SyncEvent(
            sync_type="full",
            status="started",
            started_at=datetime.now(timezone.utc),
            total_repos=5,
            current_repo_name="org/repo-1",
            repos_completed=[
                {"repo_id": 1, "repo_name": "org/done", "status": "ok", "prs": 3, "issues": 1, "warnings": []}
            ],
        )
        db_session.add(event)
        await db_session.commit()

        resp = await client.get("/api/sync/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_sync"] is not None
        assert data["active_sync"]["current_repo_name"] == "org/repo-1"
        assert data["active_sync"]["total_repos"] == 5


class TestResume:
    @pytest.mark.asyncio
    async def test_resume_not_found(self, client):
        resp = await client.post("/api/sync/resume/999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_resume_not_resumable(self, client, db_session):
        event = SyncEvent(
            sync_type="full",
            status="completed",
            is_resumable=False,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        db_session.add(event)
        await db_session.commit()
        await db_session.refresh(event)

        resp = await client.post(f"/api/sync/resume/{event.id}")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_resume_success(self, client, db_session, sample_repo):
        event = SyncEvent(
            sync_type="incremental",
            status="failed",
            is_resumable=True,
            repo_ids=[sample_repo.id, 999],
            repos_completed=[
                {"repo_id": 999, "repo_name": "org/done", "status": "ok", "prs": 5, "issues": 2, "warnings": []}
            ],
            repos_failed=[],
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        db_session.add(event)
        await db_session.commit()
        await db_session.refresh(event)

        with patch("app.api.sync.run_sync", new_callable=AsyncMock):
            resp = await client.post(f"/api/sync/resume/{event.id}")
        assert resp.status_code == 202
        assert resp.json()["remaining_repos"] == 1
