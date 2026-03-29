"""Integration tests for JWT authentication and role-based access."""
import pytest

from conftest import make_admin_token, make_developer_token


class TestJWTAuth:
    @pytest.mark.asyncio
    async def test_no_auth_header_returns_401(self, raw_client):
        resp = await raw_client.get("/api/developers")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_deactivated_user_returns_401(self, raw_client, db_session, sample_developer):
        """A deactivated developer's existing JWT should be rejected."""
        token = make_developer_token(
            developer_id=sample_developer.id,
            github_username=sample_developer.github_username,
        )
        # Deactivate the developer
        sample_developer.is_active = False
        db_session.add(sample_developer)
        await db_session.commit()

        resp = await raw_client.get(
            f"/api/stats/developer/{sample_developer.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401
        assert "deactivated" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_deleted_developer_returns_401(self, raw_client):
        """A JWT for a non-existent developer_id should be rejected."""
        token = make_developer_token(developer_id=99999, github_username="ghost")
        resp = await raw_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_jwt_returns_401(self, raw_client):
        resp = await raw_client.get(
            "/api/developers",
            headers={"Authorization": "Bearer not-a-valid-jwt"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_admin_jwt_returns_200(self, client):
        resp = await client.get("/api/developers")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_health_endpoint_no_auth_required(self, raw_client):
        resp = await raw_client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_webhooks_no_bearer_auth_needed(self, raw_client):
        resp = await raw_client.post("/api/webhooks/github")
        assert resp.status_code == 422  # Missing required headers


class TestDeveloperAccess:
    @pytest.mark.asyncio
    async def test_developer_can_view_own_stats(self, developer_client, sample_developer):
        resp = await developer_client.get(f"/api/stats/developer/{sample_developer.id}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_developer_cannot_view_other_stats(self, developer_client, sample_admin):
        resp = await developer_client.get(f"/api/stats/developer/{sample_admin.id}")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_developer_cannot_access_team_stats(self, developer_client):
        resp = await developer_client.get("/api/stats/team")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_developer_cannot_access_benchmarks(self, developer_client):
        resp = await developer_client.get("/api/stats/benchmarks")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_developer_cannot_access_workload(self, developer_client):
        resp = await developer_client.get("/api/stats/workload")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_developer_cannot_access_collaboration(self, developer_client):
        resp = await developer_client.get("/api/stats/collaboration")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_developer_can_view_repo_stats(self, developer_client, sample_repo):
        resp = await developer_client.get(f"/api/stats/repo/{sample_repo.id}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_developer_can_view_own_profile(self, developer_client, sample_developer):
        resp = await developer_client.get(f"/api/developers/{sample_developer.id}")
        assert resp.status_code == 200
        assert resp.json()["github_username"] == "testuser"

    @pytest.mark.asyncio
    async def test_developer_cannot_view_other_profile(self, developer_client, sample_admin):
        resp = await developer_client.get(f"/api/developers/{sample_admin.id}")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_developer_cannot_list_developers(self, developer_client):
        resp = await developer_client.get("/api/developers")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_developer_cannot_create_developer(self, developer_client):
        resp = await developer_client.post(
            "/api/developers",
            json={"github_username": "newuser", "display_name": "New"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_developer_cannot_update_developer(self, developer_client, sample_developer):
        resp = await developer_client.patch(
            f"/api/developers/{sample_developer.id}",
            json={"team": "frontend"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_developer_cannot_delete_developer(self, developer_client, sample_developer):
        resp = await developer_client.delete(f"/api/developers/{sample_developer.id}")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_developer_can_view_own_goals(self, developer_client, sample_developer):
        resp = await developer_client.get(f"/api/goals?developer_id={sample_developer.id}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_developer_cannot_view_other_goals(self, developer_client, sample_admin):
        resp = await developer_client.get(f"/api/goals?developer_id={sample_admin.id}")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_developer_cannot_create_goal(self, developer_client, sample_developer):
        resp = await developer_client.post(
            "/api/goals",
            json={
                "developer_id": sample_developer.id,
                "title": "My goal",
                "metric_key": "prs_merged",
                "target_value": 10,
            },
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_developer_cannot_access_sync(self, developer_client):
        resp = await developer_client.get("/api/sync/repos")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_developer_cannot_access_ai(self, developer_client):
        resp = await developer_client.get("/api/ai/history")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_developer_can_view_own_trends(self, developer_client, sample_developer):
        resp = await developer_client.get(f"/api/stats/developer/{sample_developer.id}/trends")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_developer_cannot_view_other_trends(self, developer_client, sample_admin):
        resp = await developer_client.get(f"/api/stats/developer/{sample_admin.id}/trends")
        assert resp.status_code == 403


class TestAdminAccess:
    @pytest.mark.asyncio
    async def test_admin_can_list_developers(self, client):
        resp = await client.get("/api/developers")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_can_view_any_developer(self, client, sample_developer):
        resp = await client.get(f"/api/developers/{sample_developer.id}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_can_access_team_stats(self, client):
        resp = await client.get("/api/stats/team")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_can_promote_developer(self, client, sample_developer):
        resp = await client.patch(
            f"/api/developers/{sample_developer.id}",
            json={"app_role": "admin"},
        )
        assert resp.status_code == 200
        assert resp.json()["app_role"] == "admin"

    @pytest.mark.asyncio
    async def test_admin_can_access_sync(self, client):
        resp = await client.get("/api/sync/repos")
        assert resp.status_code == 200


class TestAuthMe:
    @pytest.mark.asyncio
    async def test_auth_me_returns_user_info(self, client, sample_admin):
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["github_username"] == "admin"
        assert data["app_role"] == "admin"

    @pytest.mark.asyncio
    async def test_auth_me_developer(self, developer_client, sample_developer):
        resp = await developer_client.get("/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["github_username"] == "testuser"
        assert data["app_role"] == "developer"

    @pytest.mark.asyncio
    async def test_auth_me_no_token_returns_401(self, raw_client):
        resp = await raw_client.get("/api/auth/me")
        assert resp.status_code in (401, 403)
