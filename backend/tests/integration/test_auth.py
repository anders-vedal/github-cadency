"""Integration tests for authentication behavior."""
import pytest

from conftest import TEST_TOKEN


class TestAuth:
    @pytest.mark.asyncio
    async def test_no_auth_header_returns_401(self, raw_client):
        resp = await raw_client.get("/api/developers")
        # FastAPI's HTTPBearer returns 401 when no credentials provided
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_token_returns_401(self, raw_client):
        resp = await raw_client.get(
            "/api/developers",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_token_returns_200(self, raw_client):
        resp = await raw_client.get(
            "/api/developers",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_health_endpoint_no_auth_required(self, raw_client):
        resp = await raw_client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_webhooks_no_bearer_auth_needed(self, raw_client):
        # Webhooks use HMAC, not bearer — should get 422 (missing headers), not 403
        resp = await raw_client.post("/api/webhooks/github")
        assert resp.status_code == 422  # Missing required headers
