"""Tests for rate limiting middleware."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.main import app
from app.models.database import get_db
from app.rate_limit import limiter


@pytest_asyncio.fixture
async def rate_limited_client(engine, sample_admin):
    """Client with rate limiting enabled for testing."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Temporarily enable rate limiting
    limiter.enabled = True

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    limiter.enabled = False
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(autouse=True)
async def reset_limiter():
    """Reset rate limiter state between tests."""
    yield
    limiter.reset()


@pytest.mark.asyncio
async def test_log_ingest_rate_limited(rate_limited_client):
    """POST /logs/ingest returns 429 after exceeding 10 requests/minute."""
    payload = {"entries": [{"level": "error", "message": "test", "event_type": "frontend.error"}]}
    for i in range(10):
        resp = await rate_limited_client.post("/api/logs/ingest", json=payload)
        assert resp.status_code == 204, f"Request {i+1} failed with {resp.status_code}"

    # 11th request should be rate limited
    resp = await rate_limited_client.post("/api/logs/ingest", json=payload)
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_response_body(rate_limited_client):
    """429 responses include error detail."""
    payload = {"entries": [{"level": "error", "message": "test", "event_type": "frontend.error"}]}
    for _ in range(11):
        resp = await rate_limited_client.post("/api/logs/ingest", json=payload)

    assert resp.status_code == 429
    body = resp.json()
    assert "error" in body or "detail" in body


@pytest.mark.asyncio
async def test_rate_limiting_disabled_in_test_mode(client):
    """With RATE_LIMIT_ENABLED=false (test default), no 429 is returned."""
    payload = {"entries": [{"level": "error", "message": "test", "event_type": "frontend.error"}]}
    for _ in range(15):
        resp = await client.post("/api/logs/ingest", json=payload)
        assert resp.status_code == 204


@pytest.mark.asyncio
async def test_default_rate_limit_on_health(rate_limited_client):
    """Default 120/minute limit applies to undecorated endpoints."""
    for i in range(120):
        resp = await rate_limited_client.get("/api/health")
        assert resp.status_code == 200, f"Request {i+1} failed with {resp.status_code}"

    resp = await rate_limited_client.get("/api/health")
    assert resp.status_code == 429
