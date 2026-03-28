"""Integration tests for the /api/webhooks/github endpoint."""
import hashlib
import hmac
import json
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from conftest import WEBHOOK_SECRET


def sign_payload(payload: bytes) -> str:
    sig = hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


@pytest.fixture
def _patch_webhook_session(engine):
    """Patch AsyncSessionLocal in the webhooks module to use the test DB."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    with patch("app.api.webhooks.AsyncSessionLocal", factory):
        yield


class TestWebhookSignatureValidation:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_patch_webhook_session")
    async def test_valid_signature_accepted(self, client, sample_repo):
        payload = json.dumps({
            "action": "opened",
            "issue": {
                "id": 999, "number": 42, "title": "New issue",
                "body": "Issue body", "state": "open", "labels": [],
                "user": {"login": "someone"}, "assignee": None,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "closed_at": None,
                "html_url": "https://github.com/org/test-repo/issues/42",
            },
            "repository": {"id": 12345},
        }).encode()

        resp = await client.post(
            "/api/webhooks/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sign_payload(payload),
                "X-GitHub-Event": "issues",
            },
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_signature_rejected(self, client):
        payload = json.dumps({"action": "opened"}).encode()
        resp = await client.post(
            "/api/webhooks/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=invalid",
                "X-GitHub-Event": "issues",
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_headers_returns_422(self, client):
        resp = await client.post("/api/webhooks/github", content=b"{}")
        assert resp.status_code == 422


class TestWebhookEventHandling:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_patch_webhook_session")
    async def test_untracked_repo_ignored(self, client, db_session):
        """Events for repos not in the DB are silently ignored."""
        from app.models.models import Repository

        repo = Repository(
            github_id=99999, name="untracked", full_name="org/untracked",
            is_tracked=False,
        )
        db_session.add(repo)
        await db_session.commit()

        payload = json.dumps({
            "action": "opened",
            "issue": {
                "id": 888, "number": 1, "title": "test", "body": "",
                "state": "open", "labels": [],
                "user": {"login": "someone"}, "assignee": None,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "closed_at": None, "html_url": "",
            },
            "repository": {"id": 99999},
        }).encode()

        resp = await client.post(
            "/api/webhooks/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sign_payload(payload),
                "X-GitHub-Event": "issues",
            },
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_patch_webhook_session")
    async def test_unknown_repo_ignored(self, client):
        """Events for repos not in the DB at all are ignored."""
        payload = json.dumps({
            "action": "opened",
            "issue": {
                "id": 777, "number": 1, "title": "test", "body": "",
                "state": "open", "labels": [],
                "user": {"login": "someone"}, "assignee": None,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "closed_at": None, "html_url": "",
            },
            "repository": {"id": 77777},
        }).encode()

        resp = await client.post(
            "/api/webhooks/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sign_payload(payload),
                "X-GitHub-Event": "issues",
            },
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_patch_webhook_session")
    async def test_issue_comment_on_pr_skipped(self, client, sample_repo):
        """Issue comments on PRs (have pull_request key) are skipped."""
        payload = json.dumps({
            "action": "created",
            "issue": {
                "id": 666, "number": 5, "title": "PR title", "body": "",
                "state": "open", "labels": [],
                "user": {"login": "someone"}, "assignee": None,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "closed_at": None, "html_url": "",
                "pull_request": {"url": "https://api.github.com/..."},
            },
            "comment": {
                "id": 555, "body": "comment", "user": {"login": "someone"},
                "created_at": "2024-01-01T00:00:00Z",
            },
            "repository": {"id": 12345},
        }).encode()

        resp = await client.post(
            "/api/webhooks/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sign_payload(payload),
                "X-GitHub-Event": "issue_comment",
            },
        )
        assert resp.status_code == 200
