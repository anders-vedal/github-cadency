"""Integration tests for the notification center API."""

import pytest
from datetime import datetime, timedelta, timezone

from app.models.models import (
    Developer,
    Notification,
    NotificationConfig,
    PullRequest,
    Repository,
)

pytestmark = pytest.mark.asyncio


class TestNotificationsAPI:
    async def test_get_notifications_empty(self, client):
        resp = await client.get("/api/notifications")
        assert resp.status_code == 200
        data = resp.json()
        assert data["notifications"] == []
        assert data["unread_count"] == 0
        assert data["total"] == 0

    async def test_get_config(self, client):
        resp = await client.get("/api/notifications/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["alert_stale_pr_enabled"] is True
        assert data["stale_pr_threshold_hours"] == 48
        assert len(data["alert_types"]) > 0
        # Check alert type metadata structure
        stale = next(a for a in data["alert_types"] if a["key"] == "stale_pr")
        assert stale["label"] == "Stale Pull Requests"
        assert stale["enabled"] is True
        assert len(stale["thresholds"]) > 0

    async def test_update_config(self, client):
        resp = await client.patch(
            "/api/notifications/config",
            json={"stale_pr_threshold_hours": 72, "alert_underutilized_enabled": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["stale_pr_threshold_hours"] == 72
        underutilized = next(a for a in data["alert_types"] if a["key"] == "underutilized")
        assert underutilized["enabled"] is False

    async def test_evaluate_endpoint(self, client):
        resp = await client.post("/api/notifications/evaluate")
        assert resp.status_code == 200
        data = resp.json()
        assert "created" in data
        assert "updated" in data
        assert "resolved" in data

    async def test_notification_read_marking(
        self, client, db_session, sample_admin
    ):
        # Create a notification directly
        notif = Notification(
            alert_type="stale_pr",
            alert_key="stale_pr:pr:999",
            severity="warning",
            title="Test notification",
            entity_type="pull_request",
            entity_id=999,
        )
        db_session.add(notif)
        await db_session.commit()
        await db_session.refresh(notif)

        # Should be unread
        resp = await client.get("/api/notifications")
        assert resp.status_code == 200
        data = resp.json()
        assert data["unread_count"] == 1
        assert data["notifications"][0]["is_read"] is False

        # Mark as read
        resp2 = await client.post(f"/api/notifications/{notif.id}/read")
        assert resp2.status_code == 200

        # Should be read now
        resp3 = await client.get("/api/notifications")
        data3 = resp3.json()
        assert data3["unread_count"] == 0
        assert data3["notifications"][0]["is_read"] is True

    async def test_notification_read_all(self, client, db_session):
        for i in range(3):
            db_session.add(Notification(
                alert_type="underutilized",
                alert_key=f"underutilized:developer:{100 + i}",
                severity="info",
                title=f"Test {i}",
            ))
        await db_session.commit()

        resp = await client.post("/api/notifications/read-all")
        assert resp.status_code == 200
        assert resp.json()["marked_read"] == 3

        resp2 = await client.get("/api/notifications")
        assert resp2.json()["unread_count"] == 0

    async def test_notification_dismiss_permanent(self, client, db_session):
        notif = Notification(
            alert_type="review_bottleneck",
            alert_key="review_bottleneck:developer:42",
            severity="warning",
            title="Dismiss test",
        )
        db_session.add(notif)
        await db_session.commit()
        await db_session.refresh(notif)

        # Dismiss permanently
        resp = await client.post(
            f"/api/notifications/{notif.id}/dismiss",
            json={"dismiss_type": "permanent"},
        )
        assert resp.status_code == 200
        assert resp.json()["expires_at"] is None

        # Should not appear in default list
        resp2 = await client.get("/api/notifications")
        ids = [n["id"] for n in resp2.json()["notifications"]]
        assert notif.id not in ids

        # Should appear with include_dismissed
        resp3 = await client.get("/api/notifications?include_dismissed=true")
        ids3 = [n["id"] for n in resp3.json()["notifications"]]
        assert notif.id in ids3

    async def test_notification_dismiss_temporary(self, client, db_session):
        notif = Notification(
            alert_type="bus_factor",
            alert_key="bus_factor:repo:5",
            severity="warning",
            title="Temporary dismiss test",
        )
        db_session.add(notif)
        await db_session.commit()
        await db_session.refresh(notif)

        resp = await client.post(
            f"/api/notifications/{notif.id}/dismiss",
            json={"dismiss_type": "temporary", "duration_days": 7},
        )
        assert resp.status_code == 200
        assert resp.json()["expires_at"] is not None

    async def test_dismiss_alert_type(self, client, db_session):
        for i in range(2):
            db_session.add(Notification(
                alert_type="issue_linkage",
                alert_key=f"issue_linkage:developer:{200 + i}",
                severity="info",
                title=f"Linkage {i}",
            ))
        await db_session.commit()

        # Dismiss entire type
        resp = await client.post(
            "/api/notifications/dismiss-type",
            json={"alert_type": "issue_linkage", "dismiss_type": "permanent"},
        )
        assert resp.status_code == 200

        # None should appear
        resp2 = await client.get("/api/notifications")
        types = [n["alert_type"] for n in resp2.json()["notifications"]]
        assert "issue_linkage" not in types

    async def test_severity_ordering(self, client, db_session):
        db_session.add(Notification(
            alert_type="underutilized", alert_key="ord:info",
            severity="info", title="Info alert",
        ))
        db_session.add(Notification(
            alert_type="stale_pr", alert_key="ord:critical",
            severity="critical", title="Critical alert",
        ))
        db_session.add(Notification(
            alert_type="review_bottleneck", alert_key="ord:warning",
            severity="warning", title="Warning alert",
        ))
        await db_session.commit()

        resp = await client.get("/api/notifications")
        severities = [n["severity"] for n in resp.json()["notifications"]]
        assert severities == ["critical", "warning", "info"]

    async def test_severity_filter(self, client, db_session):
        db_session.add(Notification(
            alert_type="stale_pr", alert_key="filt:c",
            severity="critical", title="C",
        ))
        db_session.add(Notification(
            alert_type="underutilized", alert_key="filt:i",
            severity="info", title="I",
        ))
        await db_session.commit()

        resp = await client.get("/api/notifications?severity=critical")
        assert resp.status_code == 200
        assert all(n["severity"] == "critical" for n in resp.json()["notifications"])

    async def test_contribution_category_filtering(
        self, client, db_session, sample_repo
    ):
        """System account developers should not generate underutilized alerts."""
        # Create a bot developer with system role
        bot = Developer(
            github_username="deploy-bot",
            display_name="Deploy Bot",
            role="system_account",
            app_role="developer",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(bot)
        await db_session.commit()
        await db_session.refresh(bot)

        # Evaluate
        resp = await client.post("/api/notifications/evaluate")
        assert resp.status_code == 200

        # Check that no underutilized alert was created for the bot
        resp2 = await client.get("/api/notifications?alert_type=underutilized&include_dismissed=true")
        dev_ids = [n["developer_id"] for n in resp2.json()["notifications"]]
        assert bot.id not in dev_ids

    async def test_auto_resolve(self, client, db_session, sample_repo, sample_admin):
        """When a condition clears, the notification should be resolved."""
        now = datetime.now(timezone.utc)

        # Create a stale PR (open, no review, old)
        pr = PullRequest(
            github_id=9999,
            repo_id=sample_repo.id,
            author_id=sample_admin.id,
            number=999,
            title="Stale PR for test",
            state="open",
            is_draft=False,
            created_at=now - timedelta(hours=72),
            additions=10,
            deletions=0,
            changed_files=1,
        )
        db_session.add(pr)
        await db_session.commit()

        # Evaluate — should create stale_pr notification
        await client.post("/api/notifications/evaluate")
        resp = await client.get("/api/notifications?alert_type=stale_pr")
        assert resp.json()["total"] >= 1

        # Now "merge" the PR
        pr.state = "closed"
        pr.is_merged = True
        pr.merged_at = now
        await db_session.commit()

        # Re-evaluate — condition cleared, should be auto-resolved
        await client.post("/api/notifications/evaluate")
        resp2 = await client.get("/api/notifications?alert_type=stale_pr")
        stale_keys = [n["alert_type"] for n in resp2.json()["notifications"]
                      if n.get("entity_id") == pr.id]
        # The specific PR should no longer have an active stale alert
        assert len(stale_keys) == 0


class TestNotificationInputValidation:
    async def test_invalid_severity_rejected(self, client):
        resp = await client.get("/api/notifications?severity=bogus")
        assert resp.status_code == 422
        assert "severity" in resp.json()["detail"].lower()

    async def test_valid_severity_accepted(self, client):
        for sev in ("critical", "warning", "info"):
            resp = await client.get(f"/api/notifications?severity={sev}")
            assert resp.status_code == 200

    async def test_invalid_alert_type_rejected(self, client):
        resp = await client.get("/api/notifications?alert_type=nonexistent")
        assert resp.status_code == 422
        assert "alert_type" in resp.json()["detail"].lower()

    async def test_valid_alert_type_accepted(self, client):
        resp = await client.get("/api/notifications?alert_type=stale_pr")
        assert resp.status_code == 200

    async def test_dismiss_type_invalid_alert_type_rejected(self, client):
        resp = await client.post(
            "/api/notifications/dismiss-type",
            json={"alert_type": "nonexistent", "dismiss_type": "permanent"},
        )
        assert resp.status_code == 422
