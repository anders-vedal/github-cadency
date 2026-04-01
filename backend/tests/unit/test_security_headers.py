"""Tests for security headers middleware and OpenAPI docs toggle."""

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_security_headers_present():
    """All responses should include security headers."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/health")

    assert resp.status_code == 200
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["X-XSS-Protection"] == "0"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


@pytest.mark.asyncio
async def test_no_hsts_in_development():
    """HSTS header should NOT be present in development (default)."""
    from app.config import settings
    from app.main import app

    assert settings.environment != "production"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/health")

    assert "Strict-Transport-Security" not in resp.headers


@pytest.mark.asyncio
async def test_hsts_in_production(monkeypatch):
    """HSTS header should be present when environment is production."""
    from app.config import settings

    monkeypatch.setattr(settings, "environment", "production")

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/health")

    assert resp.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"

    # Restore
    monkeypatch.setattr(settings, "environment", "development")


@pytest.mark.asyncio
async def test_docs_available_in_development():
    """/docs should be accessible in development."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/docs")

    # In development, /docs should return 200 (HTML page)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_security_headers_on_404():
    """Security headers should be present even on error responses."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/nonexistent-route")

    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
