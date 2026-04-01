"""Integration tests for the /api/developers endpoints."""
import pytest


class TestListDevelopers:
    @pytest.mark.asyncio
    async def test_list_includes_admin(self, client, sample_admin):
        """With only the admin user, list should have 1 entry."""
        resp = await client.get("/api/developers")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["github_username"] == "admin"

    @pytest.mark.asyncio
    async def test_list_returns_active_developers(self, client, sample_developer):
        resp = await client.get("/api/developers")
        assert resp.status_code == 200
        data = resp.json()
        # admin + sample_developer
        assert len(data) == 2
        usernames = {d["github_username"] for d in data}
        assert "testuser" in usernames
        assert data[0]["is_active"] is True

    @pytest.mark.asyncio
    async def test_filter_by_team(self, client, sample_developer):
        resp = await client.get("/api/developers?team=backend")
        assert len(resp.json()) == 1

        resp = await client.get("/api/developers?team=frontend")
        assert len(resp.json()) == 0

    @pytest.mark.asyncio
    async def test_filter_inactive(self, client, sample_developer):
        resp = await client.get("/api/developers?is_active=false")
        assert len(resp.json()) == 0


class TestCreateDeveloper:
    @pytest.mark.asyncio
    async def test_create_developer(self, client):
        payload = {
            "github_username": "newdev",
            "display_name": "New Developer",
            "team": "frontend",
        }
        resp = await client.post("/api/developers", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["github_username"] == "newdev"
        assert data["display_name"] == "New Developer"
        assert data["team"] == "frontend"
        assert data["is_active"] is True
        assert data["app_role"] == "developer"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_duplicate_username_returns_409(self, client, sample_developer):
        payload = {
            "github_username": "testuser",  # already exists
            "display_name": "Duplicate",
        }
        resp = await client.post("/api/developers", json=payload)
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_create_with_all_fields(self, client):
        payload = {
            "github_username": "fulldev",
            "display_name": "Full Developer",
            "email": "full@example.com",
            "role": "lead",
            "skills": ["python", "rust"],
            "specialty": "backend",
            "location": "NYC",
            "timezone": "America/New_York",
            "team": "platform",
            "notes": "test notes",
        }
        resp = await client.post("/api/developers", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "full@example.com"
        assert data["role"] == "lead"
        assert data["skills"] == ["python", "rust"]


class TestGetDeveloper:
    @pytest.mark.asyncio
    async def test_get_existing(self, client, sample_developer):
        resp = await client.get(f"/api/developers/{sample_developer.id}")
        assert resp.status_code == 200
        assert resp.json()["github_username"] == "testuser"

    @pytest.mark.asyncio
    async def test_get_not_found(self, client):
        resp = await client.get("/api/developers/999")
        assert resp.status_code == 404


class TestUpdateDeveloper:
    @pytest.mark.asyncio
    async def test_partial_update(self, client, sample_developer):
        resp = await client.patch(
            f"/api/developers/{sample_developer.id}",
            json={"team": "frontend"},
        )
        assert resp.status_code == 200
        assert resp.json()["team"] == "frontend"
        # Other fields unchanged
        assert resp.json()["display_name"] == "Test User"

    @pytest.mark.asyncio
    async def test_update_not_found(self, client):
        resp = await client.patch(
            "/api/developers/999",
            json={"team": "frontend"},
        )
        assert resp.status_code == 404


class TestDeleteDeveloper:
    @pytest.mark.asyncio
    async def test_soft_delete(self, client, sample_developer):
        resp = await client.delete(f"/api/developers/{sample_developer.id}")
        assert resp.status_code == 204

        # Should no longer appear in active list (admin still there)
        resp = await client.get("/api/developers")
        usernames = [d["github_username"] for d in resp.json()]
        assert "testuser" not in usernames

        # Should appear in inactive list
        resp = await client.get("/api/developers?is_active=false")
        assert len(resp.json()) == 1
        assert resp.json()[0]["github_username"] == "testuser"

    @pytest.mark.asyncio
    async def test_delete_not_found(self, client):
        resp = await client.delete("/api/developers/999")
        assert resp.status_code == 404


class TestDeveloperSchemaValidation:
    @pytest.mark.asyncio
    async def test_display_name_255_accepted(self, client):
        resp = await client.post("/api/developers", json={
            "github_username": "longname",
            "display_name": "A" * 255,
        })
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_display_name_too_long_rejected(self, client):
        resp = await client.post("/api/developers", json={
            "github_username": "toolong",
            "display_name": "A" * 256,
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_notes_too_long_rejected(self, client):
        resp = await client.post("/api/developers", json={
            "github_username": "longnotes",
            "display_name": "Test",
            "notes": "x" * 5001,
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_skill_item_too_long_rejected(self, client):
        resp = await client.post("/api/developers", json={
            "github_username": "longskill",
            "display_name": "Test",
            "skills": ["x" * 101],
        })
        assert resp.status_code == 422
