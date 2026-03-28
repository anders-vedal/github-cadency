"""Service tests for GitHub sync with mocked HTTP responses."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.models.models import Developer, PullRequest, Repository
from app.services.github_sync import (
    check_rate_limit,
    classify_review_quality,
    resolve_author,
    upsert_issue,
    upsert_pull_request,
    upsert_repo,
    upsert_review,
)


class TestResolveAuthor:
    @pytest.mark.asyncio
    async def test_resolve_known_user(self, db_session, sample_developer):
        result = await resolve_author(db_session, "testuser")
        assert result == sample_developer.id

    @pytest.mark.asyncio
    async def test_resolve_unknown_user(self, db_session):
        result = await resolve_author(db_session, "unknown_user")
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_none_username(self, db_session):
        result = await resolve_author(db_session, None)
        assert result is None


class TestUpsertRepo:
    @pytest.mark.asyncio
    async def test_create_new_repo(self, db_session):
        repo_data = {
            "id": 99999,
            "name": "new-repo",
            "full_name": "org/new-repo",
            "description": "A new repo",
            "language": "Go",
        }
        repo = await upsert_repo(db_session, repo_data)
        assert repo.github_id == 99999
        assert repo.name == "new-repo"
        assert repo.full_name == "org/new-repo"

    @pytest.mark.asyncio
    async def test_update_existing_repo(self, db_session, sample_repo):
        repo_data = {
            "id": 12345,  # matches sample_repo.github_id
            "name": "updated-name",
            "full_name": "org/updated-name",
            "description": "Updated description",
            "language": "Rust",
        }
        repo = await upsert_repo(db_session, repo_data)
        assert repo.id == sample_repo.id  # same row
        assert repo.name == "updated-name"


class TestUpsertPullRequest:
    @pytest.mark.asyncio
    async def test_create_pr_with_detail_fetch(self, db_session, sample_repo):
        """Test PR upsert with mocked detail API call."""
        pr_data = {
            "id": 500,
            "number": 42,
            "title": "New feature",
            "body": "Adds cool stuff",
            "state": "open",
            "merged": False,
            "draft": False,
            "comments": 2,
            "review_comments": 1,
            "html_url": "https://github.com/org/test-repo/pull/42",
            "user": {"login": "testuser"},
            "created_at": "2024-06-01T10:00:00Z",
            "updated_at": "2024-06-02T10:00:00Z",
            "merged_at": None,
            "closed_at": None,
        }

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = {
            "additions": 100,
            "deletions": 20,
            "changed_files": 5,
            "merged": False,
            "merged_at": None,
        }

        with patch("app.services.github_sync.github_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            pr = await upsert_pull_request(db_session, MagicMock(), pr_data, sample_repo)

        assert pr.number == 42
        assert pr.title == "New feature"
        assert pr.additions == 100
        assert pr.deletions == 20

    @pytest.mark.asyncio
    async def test_compute_time_to_merge(self, db_session, sample_repo):
        """Merged PR should compute time_to_merge_s."""
        created = datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
        merged = datetime(2024, 6, 3, 10, 0, 0, tzinfo=timezone.utc)

        pr_data = {
            "id": 501,
            "number": 43,
            "title": "Merged PR",
            "body": "",
            "state": "closed",
            "merged": True,
            "draft": False,
            "comments": 0,
            "review_comments": 0,
            "html_url": "",
            "user": {"login": "unknown"},
            "created_at": created.isoformat(),
            "updated_at": merged.isoformat(),
            "merged_at": merged.isoformat(),
            "closed_at": merged.isoformat(),
            "additions": 10,
            "deletions": 5,
            "changed_files": 1,
        }

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = {
            "additions": 10, "deletions": 5, "changed_files": 1,
            "merged": True, "merged_at": merged.isoformat(),
        }

        with patch("app.services.github_sync.github_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            pr = await upsert_pull_request(db_session, MagicMock(), pr_data, sample_repo)

        expected_seconds = int((merged - created).total_seconds())
        assert pr.time_to_merge_s == expected_seconds


class TestUpsertReview:
    @pytest.mark.asyncio
    async def test_creates_review_and_updates_first_review(
        self, db_session, sample_repo
    ):
        # Create a PR first
        pr = PullRequest(
            github_id=600, repo_id=sample_repo.id, number=50,
            title="Test PR", state="open",
            created_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )
        db_session.add(pr)
        await db_session.flush()

        review_data = {
            "id": 700,
            "state": "APPROVED",
            "body": "LGTM",
            "user": {"login": "reviewer"},
            "submitted_at": "2024-06-02T10:00:00Z",
        }

        review = await upsert_review(db_session, review_data, pr)
        assert review.state == "APPROVED"
        assert review.body_length == 4
        assert pr.first_review_at is not None
        assert pr.time_to_first_review_s is not None


class TestCheckRateLimit:
    @pytest.mark.asyncio
    async def test_no_backoff_when_sufficient(self):
        response = MagicMock(spec=httpx.Response)
        response.headers = {"X-RateLimit-Remaining": "1000", "X-RateLimit-Reset": "0"}
        await check_rate_limit(response)  # should not raise or sleep

    @pytest.mark.asyncio
    async def test_backoff_when_low(self):
        import time

        response = MagicMock(spec=httpx.Response)
        response.headers = {
            "X-RateLimit-Remaining": "50",
            "X-RateLimit-Reset": str(int(time.time()) + 1),
        }
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await check_rate_limit(response)
            mock_sleep.assert_called_once()


class TestUpsertIssue:
    @pytest.mark.asyncio
    async def test_create_issue_with_time_to_close(self, db_session, sample_repo):
        issue_data = {
            "id": 900,
            "number": 20,
            "title": "Bug",
            "body": "Something broke",
            "state": "closed",
            "labels": [{"name": "bug"}, {"name": "priority"}],
            "assignee": None,
            "created_at": "2024-06-01T00:00:00Z",
            "updated_at": "2024-06-05T00:00:00Z",
            "closed_at": "2024-06-05T00:00:00Z",
            "html_url": "",
        }
        issue = await upsert_issue(db_session, issue_data, sample_repo)
        assert issue.number == 20
        assert issue.labels == ["bug", "priority"]
        assert issue.time_to_close_s == 4 * 86400  # 4 days in seconds
