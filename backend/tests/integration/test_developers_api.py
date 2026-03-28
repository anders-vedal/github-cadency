"""Integration tests for the /api/developers endpoints."""
import pytest


class TestListDevelopers:
    @pytest.mark.asyncio
    async def test_empty_list(self, client):
        resp = await client.get("/api/developers")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_returns_active_developers(self, client, sample_developer):
        resp = await client.get("/api/developers")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["github_username"] == "testuser"
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

        # Should no longer appear in active list
        resp = await client.get("/api/developers")
        assert len(resp.json()) == 0

        # Should appear in inactive list
        resp = await client.get("/api/developers?is_active=false")
        assert len(resp.json()) == 1

    @pytest.mark.asyncio
    async def test_delete_not_found(self, client):
        resp = await client.delete("/api/developers/999")
        assert resp.status_code == 404
