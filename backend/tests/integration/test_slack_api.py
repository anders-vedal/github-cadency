"""Integration tests for Slack API endpoints."""

import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest.mark.asyncio
class TestSlackConfigEndpoints:
    async def test_get_config_admin(self, client: AsyncClient):
        resp = await client.get("/api/slack/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["slack_enabled"] is False
        assert data["bot_token_configured"] is False
        assert "bot_token" not in data
        assert data["stale_pr_days_threshold"] == 3

    async def test_get_config_developer_forbidden(self, developer_client: AsyncClient):
        resp = await developer_client.get("/api/slack/config")
        assert resp.status_code == 403

    async def test_patch_config(self, client: AsyncClient):
        resp = await client.patch("/api/slack/config", json={
            "slack_enabled": True,
            "bot_token": "xoxb-test-token-123",
            "default_channel": "#engineering",
            "stale_pr_days_threshold": 5,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["slack_enabled"] is True
        assert data["bot_token_configured"] is True
        assert data["default_channel"] == "#engineering"
        assert data["stale_pr_days_threshold"] == 5

    async def test_patch_config_developer_forbidden(self, developer_client: AsyncClient):
        resp = await developer_client.patch("/api/slack/config", json={
            "slack_enabled": True,
        })
        assert resp.status_code == 403

    async def test_patch_preserves_unset_fields(self, client: AsyncClient):
        # First set threshold
        await client.patch("/api/slack/config", json={
            "stale_pr_days_threshold": 7,
        })
        # Then update channel without touching threshold
        resp = await client.patch("/api/slack/config", json={
            "default_channel": "#alerts",
        })
        data = resp.json()
        assert data["stale_pr_days_threshold"] == 7
        assert data["default_channel"] == "#alerts"


@pytest.mark.asyncio
class TestSlackTestEndpoint:
    async def test_test_requires_admin(self, developer_client: AsyncClient):
        resp = await developer_client.post("/api/slack/test")
        assert resp.status_code == 403

    async def test_test_fails_when_disabled(self, client: AsyncClient):
        # Slack is disabled by default → 403
        resp = await client.post("/api/slack/test")
        assert resp.status_code == 403

    async def test_test_fails_when_no_token(self, client: AsyncClient):
        # Enable Slack but no token → 503
        await client.patch("/api/slack/config", json={"slack_enabled": True})
        resp = await client.post("/api/slack/test")
        assert resp.status_code == 503


@pytest.mark.asyncio
class TestSlackUserSettingsEndpoints:
    async def test_get_own_settings(self, developer_client: AsyncClient):
        resp = await developer_client.get("/api/slack/user-settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["slack_user_id"] is None
        assert data["notify_stale_prs"] is True

    async def test_patch_own_settings(self, developer_client: AsyncClient):
        resp = await developer_client.patch("/api/slack/user-settings", json={
            "slack_user_id": "U0123456789",
            "notify_stale_prs": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["slack_user_id"] == "U0123456789"
        assert data["notify_stale_prs"] is False
        assert data["notify_high_risk_prs"] is True

    async def test_admin_can_view_any_developer(self, client: AsyncClient, sample_developer):
        resp = await client.get(f"/api/slack/user-settings/{sample_developer.id}")
        assert resp.status_code == 200

    async def test_developer_cannot_view_others(self, developer_client: AsyncClient):
        resp = await developer_client.get("/api/slack/user-settings/999")
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestNotificationHistoryEndpoint:
    async def test_get_notifications_admin(self, client: AsyncClient):
        resp = await client.get("/api/slack/notifications")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["notifications"] == []

    async def test_get_notifications_developer_forbidden(self, developer_client: AsyncClient):
        resp = await developer_client.get("/api/slack/notifications")
        assert resp.status_code == 403
