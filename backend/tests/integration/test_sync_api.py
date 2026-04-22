"""Integration tests for the /api/sync endpoints."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from app.models.models import (
    Issue,
    PRReview,
    PullRequest,
    Repository,
    SyncEvent,
    SyncScheduleConfig,
)


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


class TestDeleteRepoData:
    @pytest.mark.asyncio
    async def test_purges_target_only(
        self, client, db_session, sample_repo, sample_pr, sample_review, sample_issue
    ):
        """Delete target repo's synced data; untouched repo keeps everything."""
        # Add a sibling repo with its own PR + issue — must survive the purge
        sibling = Repository(
            github_id=99999, name="keep", full_name="org/keep", is_tracked=True,
        )
        db_session.add(sibling)
        await db_session.commit()
        await db_session.refresh(sibling)

        sibling_pr = PullRequest(
            github_id=9001, repo_id=sibling.id, number=1,
            title="keep me", state="open", is_merged=False,
            created_at=datetime.now(timezone.utc),
        )
        sibling_issue = Issue(
            github_id=9002, repo_id=sibling.id, number=1,
            title="keep this issue", state="open",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add_all([sibling_pr, sibling_issue])
        await db_session.commit()

        resp = await client.delete(f"/api/sync/repos/{sample_repo.id}/data")
        assert resp.status_code == 200
        body = resp.json()
        assert body["repo_id"] == sample_repo.id
        assert body["deleted"]["pull_requests"] == 1
        assert body["deleted"]["pr_reviews"] == 1
        assert body["deleted"]["issues"] == 1

        # Target repo's data gone
        assert (
            await db_session.scalar(
                select(func.count()).select_from(PullRequest).where(
                    PullRequest.repo_id == sample_repo.id
                )
            )
        ) == 0
        assert (
            await db_session.scalar(
                select(func.count()).select_from(PRReview).where(
                    PRReview.pr_id == sample_pr.id
                )
            )
        ) == 0
        assert (
            await db_session.scalar(
                select(func.count()).select_from(Issue).where(
                    Issue.repo_id == sample_repo.id
                )
            )
        ) == 0

        # Repo row kept, tracking reset
        await db_session.refresh(sample_repo)
        assert sample_repo.is_tracked is False
        assert sample_repo.last_synced_at is None

        # Sibling untouched
        assert (
            await db_session.scalar(
                select(func.count()).select_from(PullRequest).where(
                    PullRequest.repo_id == sibling.id
                )
            )
        ) == 1
        assert (
            await db_session.scalar(
                select(func.count()).select_from(Issue).where(
                    Issue.repo_id == sibling.id
                )
            )
        ) == 1

    @pytest.mark.asyncio
    async def test_not_found(self, client):
        resp = await client.delete("/api/sync/repos/99999/data")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_empty_repo_succeeds(self, client, sample_repo):
        """Repo with no synced data — endpoint still returns 200, all counts 0."""
        resp = await client.delete(f"/api/sync/repos/{sample_repo.id}/data")
        assert resp.status_code == 200
        body = resp.json()
        for v in body["deleted"].values():
            assert v == 0


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
        data = resp.json()
        assert data["status"] == "started"
        assert data["resumed_from_id"] == event.id


class TestSyncSchedule:
    @pytest.mark.asyncio
    async def test_get_schedule_defaults(self, client):
        """GET /sync/schedule returns defaults when no config row exists."""
        resp = await client.get("/api/sync/schedule")
        assert resp.status_code == 200
        data = resp.json()
        assert data["auto_sync_enabled"] is True
        assert data["incremental_interval_minutes"] == 15
        assert data["full_sync_cron_hour"] == 2

    @pytest.mark.asyncio
    async def test_update_schedule(self, client, db_session):
        """PATCH /sync/schedule creates/updates the singleton config."""
        with patch("app.main.reschedule_sync_jobs"):
            resp = await client.patch(
                "/api/sync/schedule",
                json={"incremental_interval_minutes": 30, "full_sync_cron_hour": 4},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["incremental_interval_minutes"] == 30
        assert data["full_sync_cron_hour"] == 4
        assert data["auto_sync_enabled"] is True

    @pytest.mark.asyncio
    async def test_disable_auto_sync(self, client, db_session):
        """PATCH /sync/schedule can disable auto-sync."""
        with patch("app.main.reschedule_sync_jobs"):
            resp = await client.patch(
                "/api/sync/schedule",
                json={"auto_sync_enabled": False},
            )
        assert resp.status_code == 200
        assert resp.json()["auto_sync_enabled"] is False

    @pytest.mark.asyncio
    async def test_update_schedule_min_interval(self, client):
        """PATCH /sync/schedule rejects interval < 5."""
        with patch("app.main.reschedule_sync_jobs"):
            resp = await client.patch(
                "/api/sync/schedule",
                json={"incremental_interval_minutes": 2},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_update_schedule_invalid_hour(self, client):
        """PATCH /sync/schedule rejects hour outside 0-23."""
        with patch("app.main.reschedule_sync_jobs"):
            resp = await client.patch(
                "/api/sync/schedule",
                json={"full_sync_cron_hour": 25},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_status_includes_schedule(self, client, db_session):
        """GET /sync/status includes the schedule config."""
        config = SyncScheduleConfig(
            id=1, auto_sync_enabled=True,
            incremental_interval_minutes=20,
            full_sync_cron_hour=3,
        )
        db_session.add(config)
        await db_session.commit()

        resp = await client.get("/api/sync/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["schedule"] is not None
        assert data["schedule"]["incremental_interval_minutes"] == 20
        assert data["schedule"]["full_sync_cron_hour"] == 3


class TestSyncScopeAndTriggeredBy:
    @pytest.mark.asyncio
    async def test_start_sync_with_scope(self, client):
        """POST /sync/start passes sync_scope and triggered_by to run_sync."""
        with patch("app.api.sync.run_sync", new_callable=AsyncMock) as mock_run:
            resp = await client.post(
                "/api/sync/start",
                json={
                    "sync_type": "full",
                    "sync_scope": "3 repos \u00b7 30 days",
                },
            )
        assert resp.status_code == 202
        # Check run_sync was called with the right args
        mock_run.assert_called_once()
        call_kwargs_or_args = mock_run.call_args
        # positional args: sync_type, repo_ids, since, resumed_from_id, triggered_by, sync_scope, sync_event_id
        assert call_kwargs_or_args[0][4] == "manual"
        assert call_kwargs_or_args[0][5] == "3 repos \u00b7 30 days"
        assert call_kwargs_or_args[0][6] is not None  # sync_event_id

    @pytest.mark.asyncio
    async def test_event_returns_scope_fields(self, client, db_session):
        """Sync events include triggered_by and sync_scope in response."""
        event = SyncEvent(
            sync_type="full",
            status="completed",
            repos_synced=1,
            prs_upserted=5,
            issues_upserted=2,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            duration_s=60,
            triggered_by="scheduled",
            sync_scope="All tracked repos \u00b7 incremental",
        )
        db_session.add(event)
        await db_session.commit()

        resp = await client.get("/api/sync/events")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["triggered_by"] == "scheduled"
        assert data[0]["sync_scope"] == "All tracked repos \u00b7 incremental"
