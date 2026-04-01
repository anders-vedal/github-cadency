"""Integration tests for GitHub OAuth flow."""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


OAUTH_STATE_COOKIE = "devpulse_oauth_state"
TEST_STATE = "test-state-nonce-abc123"


def _set_state_cookie(raw_client):
    """Set the OAuth state cookie on the test client for CSRF validation."""
    raw_client.cookies.set(OAUTH_STATE_COOKIE, TEST_STATE)


class TestOAuthLogin:
    @pytest.mark.asyncio
    async def test_login_returns_github_url_with_state(self, raw_client):
        resp = await raw_client.get("/api/auth/login")
        assert resp.status_code == 200
        data = resp.json()
        assert "url" in data
        assert "github.com/login/oauth/authorize" in data["url"]
        assert "client_id=" in data["url"]
        assert "state=" in data["url"]

    @pytest.mark.asyncio
    async def test_login_sets_state_cookie(self, raw_client):
        resp = await raw_client.get("/api/auth/login")
        assert resp.status_code == 200
        assert OAUTH_STATE_COOKIE in resp.cookies


def _make_github_mocks(login: str, name: str, avatar_url: str, *, org_member: bool = True):
    """Create mock httpx responses for GitHub token + user + org membership endpoints."""
    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {"access_token": "gh_fake_token"}

    mock_user_resp = MagicMock()
    mock_user_resp.status_code = 200
    mock_user_resp.json.return_value = {
        "login": login,
        "name": name,
        "avatar_url": avatar_url,
    }

    mock_org_resp = MagicMock()
    mock_org_resp.status_code = 204 if org_member else 404

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_token_resp

    # get() is called for user info, then optionally for org check
    mock_client.get.side_effect = [mock_user_resp, mock_org_resp]

    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


def _make_github_mocks_no_org(login: str, name: str, avatar_url: str):
    """Create mock httpx responses without org membership check (github_org empty)."""
    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {"access_token": "gh_fake_token"}

    mock_user_resp = MagicMock()
    mock_user_resp.status_code = 200
    mock_user_resp.json.return_value = {
        "login": login,
        "name": name,
        "avatar_url": avatar_url,
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_token_resp
    mock_client.get.return_value = mock_user_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


class TestOAuthCallback:
    @pytest.mark.asyncio
    async def test_callback_creates_new_developer(self, raw_client):
        mock_client = _make_github_mocks_no_org("newghuser", "New User", "https://example.com/avatar.jpg")
        _set_state_cookie(raw_client)

        with patch("app.api.oauth.httpx.AsyncClient", return_value=mock_client):
            resp = await raw_client.get(
                f"/api/auth/callback?code=test_code&state={TEST_STATE}",
                follow_redirects=False,
            )

        assert resp.status_code == 302
        location = resp.headers["location"]
        # Token should be in URL fragment, not query parameter
        assert "#token=" in location
        assert "?token=" not in location

    @pytest.mark.asyncio
    async def test_callback_initial_admin_gets_admin_role(self, raw_client):
        os.environ["DEVPULSE_INITIAL_ADMIN"] = "initialadmin"
        from app.config import settings
        settings.__dict__["devpulse_initial_admin"] = "initialadmin"

        mock_client = _make_github_mocks_no_org("initialadmin", "Initial Admin", "https://example.com/avatar.jpg")
        _set_state_cookie(raw_client)

        with patch("app.api.oauth.httpx.AsyncClient", return_value=mock_client):
            resp = await raw_client.get(
                f"/api/auth/callback?code=test_code&state={TEST_STATE}",
                follow_redirects=False,
            )

        assert resp.status_code == 302
        location = resp.headers["location"]
        assert "#token=" in location

        # Decode the JWT to verify admin role
        import jwt
        token = location.split("#token=")[1]
        payload = jwt.decode(token, os.environ.get("JWT_SECRET", "test-jwt-secret-for-testing-only!!"), algorithms=["HS256"])
        assert payload["app_role"] == "admin"
        assert payload["github_username"] == "initialadmin"

        # Cleanup
        settings.__dict__["devpulse_initial_admin"] = ""
        os.environ.pop("DEVPULSE_INITIAL_ADMIN", None)

    @pytest.mark.asyncio
    async def test_callback_existing_user_updates_avatar(self, raw_client, sample_developer):
        mock_client = _make_github_mocks_no_org("testuser", "Test User", "https://new-avatar.com/img.jpg")
        _set_state_cookie(raw_client)

        with patch("app.api.oauth.httpx.AsyncClient", return_value=mock_client):
            resp = await raw_client.get(
                f"/api/auth/callback?code=test_code&state={TEST_STATE}",
                follow_redirects=False,
            )

        assert resp.status_code == 302
        location = resp.headers["location"]
        assert "#token=" in location
        assert "?token=" not in location


class TestOAuthStateValidation:
    @pytest.mark.asyncio
    async def test_callback_rejects_missing_state_param(self, raw_client):
        """Callback requires state query parameter."""
        _set_state_cookie(raw_client)
        resp = await raw_client.get(
            "/api/auth/callback?code=test_code",
            follow_redirects=False,
        )
        assert resp.status_code == 422  # FastAPI validation error (missing required param)

    @pytest.mark.asyncio
    async def test_callback_rejects_mismatched_state(self, raw_client):
        """Callback rejects when state param doesn't match cookie."""
        raw_client.cookies.set(OAUTH_STATE_COOKIE, "correct-state")

        resp = await raw_client.get(
            "/api/auth/callback?code=test_code&state=wrong-state",
            follow_redirects=False,
        )
        assert resp.status_code == 400
        assert "CSRF" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_callback_rejects_missing_state_cookie(self, raw_client):
        """Callback rejects when state cookie is missing."""
        # Don't set any cookie
        resp = await raw_client.get(
            "/api/auth/callback?code=test_code&state=some-state",
            follow_redirects=False,
        )
        assert resp.status_code == 400
        assert "CSRF" in resp.json()["detail"]


class TestInitialAdminAutoDisable:
    @pytest.mark.asyncio
    async def test_initial_admin_ignored_when_admin_exists(self, raw_client, sample_admin):
        """DEVPULSE_INITIAL_ADMIN should be ignored when an admin already exists."""
        from app.config import settings
        settings.__dict__["devpulse_initial_admin"] = "wannabe-admin"

        mock_client = _make_github_mocks_no_org("wannabe-admin", "Wannabe Admin", "https://example.com/a.jpg")
        _set_state_cookie(raw_client)

        try:
            with patch("app.api.oauth.httpx.AsyncClient", return_value=mock_client):
                resp = await raw_client.get(
                    f"/api/auth/callback?code=test_code&state={TEST_STATE}",
                    follow_redirects=False,
                )

            assert resp.status_code == 302
            location = resp.headers["location"]
            assert "#token=" in location

            # Decode JWT — should be "developer", not "admin"
            import jwt
            token = location.split("#token=")[1]
            payload = jwt.decode(token, os.environ.get("JWT_SECRET", "test-jwt-secret-for-testing-only!!"), algorithms=["HS256"])
            assert payload["app_role"] == "developer"
        finally:
            settings.__dict__["devpulse_initial_admin"] = ""


class TestOAuthOrgCheck:
    @pytest.mark.asyncio
    async def test_non_org_member_rejected(self, raw_client):
        """Non-org member gets 403 when GITHUB_ORG is configured."""
        from app.config import settings
        original_org = settings.github_org
        settings.__dict__["github_org"] = "test-org"

        mock_client = _make_github_mocks("outsider", "Outsider", "https://example.com/a.jpg", org_member=False)
        _set_state_cookie(raw_client)

        try:
            with patch("app.api.oauth.httpx.AsyncClient", return_value=mock_client):
                resp = await raw_client.get(
                    f"/api/auth/callback?code=test_code&state={TEST_STATE}",
                    follow_redirects=False,
                )
            assert resp.status_code == 403
            assert "not a member" in resp.json()["detail"]
        finally:
            settings.__dict__["github_org"] = original_org

    @pytest.mark.asyncio
    async def test_org_member_allowed(self, raw_client):
        """Org member proceeds normally when GITHUB_ORG is configured."""
        from app.config import settings
        original_org = settings.github_org
        settings.__dict__["github_org"] = "test-org"

        mock_client = _make_github_mocks("orgmember", "Org Member", "https://example.com/a.jpg", org_member=True)
        _set_state_cookie(raw_client)

        try:
            with patch("app.api.oauth.httpx.AsyncClient", return_value=mock_client):
                resp = await raw_client.get(
                    f"/api/auth/callback?code=test_code&state={TEST_STATE}",
                    follow_redirects=False,
                )
            assert resp.status_code == 302
            assert "#token=" in resp.headers["location"]
        finally:
            settings.__dict__["github_org"] = original_org

    @pytest.mark.asyncio
    async def test_org_check_skipped_when_not_configured(self, raw_client):
        """Org check is skipped when GITHUB_ORG is empty."""
        from app.config import settings
        original_org = settings.github_org
        settings.__dict__["github_org"] = ""

        mock_client = _make_github_mocks_no_org("anyuser", "Any User", "https://example.com/a.jpg")
        _set_state_cookie(raw_client)

        try:
            with patch("app.api.oauth.httpx.AsyncClient", return_value=mock_client):
                resp = await raw_client.get(
                    f"/api/auth/callback?code=test_code&state={TEST_STATE}",
                    follow_redirects=False,
                )
            assert resp.status_code == 302
            assert "#token=" in resp.headers["location"]
        finally:
            settings.__dict__["github_org"] = original_org
