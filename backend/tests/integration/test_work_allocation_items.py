"""Integration tests for work allocation items drill-down and recategorization."""
import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Developer, Issue, PullRequest, Repository


NOW = datetime.now(timezone.utc)
ONE_DAY_AGO = NOW - timedelta(days=1)
ONE_WEEK_AGO = NOW - timedelta(days=7)


@pytest.fixture
def date_params():
    return {
        "date_from": (NOW - timedelta(days=30)).isoformat(),
        "date_to": NOW.isoformat(),
    }


@pytest_asyncio.fixture
async def pr_unknown(db_session: AsyncSession, sample_developer, sample_repo):
    """A PR with no matching labels or title keywords — should be classified as unknown."""
    pr = PullRequest(
        github_id=501,
        repo_id=sample_repo.id,
        author_id=sample_developer.id,
        number=50,
        title="Update README",
        body="",
        state="closed",
        is_merged=True,
        additions=5,
        deletions=2,
        changed_files=1,
        created_at=ONE_WEEK_AGO,
        merged_at=ONE_DAY_AGO,
        labels=[],
        html_url="https://github.com/org/test-repo/pull/50",
    )
    db_session.add(pr)
    await db_session.commit()
    await db_session.refresh(pr)
    return pr


@pytest_asyncio.fixture
async def pr_feature(db_session: AsyncSession, sample_developer, sample_repo):
    """A PR with feature label."""
    pr = PullRequest(
        github_id=502,
        repo_id=sample_repo.id,
        author_id=sample_developer.id,
        number=51,
        title="Add new dashboard widget",
        body="",
        state="closed",
        is_merged=True,
        additions=100,
        deletions=10,
        changed_files=5,
        created_at=ONE_WEEK_AGO,
        merged_at=ONE_DAY_AGO,
        labels=["feature"],
        html_url="https://github.com/org/test-repo/pull/51",
    )
    db_session.add(pr)
    await db_session.commit()
    await db_session.refresh(pr)
    return pr


@pytest_asyncio.fixture
async def pr_manual_override(db_session: AsyncSession, sample_developer, sample_repo):
    """A PR with manual override that should persist."""
    pr = PullRequest(
        github_id=503,
        repo_id=sample_repo.id,
        author_id=sample_developer.id,
        number=52,
        title="Some changes",
        body="",
        state="closed",
        is_merged=True,
        additions=20,
        deletions=5,
        changed_files=2,
        created_at=ONE_WEEK_AGO,
        merged_at=ONE_DAY_AGO,
        labels=[],
        work_category="tech_debt",
        work_category_source="manual",
        html_url="https://github.com/org/test-repo/pull/52",
    )
    db_session.add(pr)
    await db_session.commit()
    await db_session.refresh(pr)
    return pr


@pytest_asyncio.fixture
async def issue_unknown(db_session: AsyncSession, sample_developer, sample_repo):
    """An issue with no matching labels."""
    issue = Issue(
        github_id=601,
        repo_id=sample_repo.id,
        number=60,
        title="Investigate flaky test",
        body="",
        state="open",
        labels=[],
        created_at=ONE_DAY_AGO,
        creator_github_username=sample_developer.github_username,
        html_url="https://github.com/org/test-repo/issues/60",
    )
    db_session.add(issue)
    await db_session.commit()
    await db_session.refresh(issue)
    return issue


class TestWorkAllocationItems:
    @pytest.mark.asyncio
    async def test_get_items_by_category(
        self, client, sample_developer, sample_repo, pr_unknown, pr_feature, date_params
    ):
        resp = await client.get("/api/stats/work-allocation/items", params={
            "category": "unknown",
            **date_params,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        # All returned items should be unknown
        for item in data["items"]:
            assert item["category"] == "unknown"
        # PR #50 should be in the list
        numbers = [i["number"] for i in data["items"]]
        assert 50 in numbers

    @pytest.mark.asyncio
    async def test_get_items_feature_category(
        self, client, sample_developer, sample_repo, pr_feature, date_params
    ):
        resp = await client.get("/api/stats/work-allocation/items", params={
            "category": "feature",
            **date_params,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        numbers = [i["number"] for i in data["items"]]
        assert 51 in numbers

    @pytest.mark.asyncio
    async def test_get_items_type_filter(
        self, client, sample_developer, sample_repo, pr_unknown, issue_unknown, date_params
    ):
        # PR only
        resp = await client.get("/api/stats/work-allocation/items", params={
            "category": "unknown",
            "type": "pr",
            **date_params,
        })
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["type"] == "pr"

        # Issue only
        resp = await client.get("/api/stats/work-allocation/items", params={
            "category": "unknown",
            "type": "issue",
            **date_params,
        })
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["type"] == "issue"

    @pytest.mark.asyncio
    async def test_pagination(
        self, client, sample_developer, sample_repo, pr_unknown, date_params
    ):
        resp = await client.get("/api/stats/work-allocation/items", params={
            "category": "unknown",
            "page": 1,
            "page_size": 1,
            **date_params,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 1
        assert len(data["items"]) <= 1

    @pytest.mark.asyncio
    async def test_items_accessible_by_developer(
        self, developer_client, sample_developer, sample_repo, pr_unknown, date_params
    ):
        """Any authenticated user can access items endpoint."""
        resp = await developer_client.get("/api/stats/work-allocation/items", params={
            "category": "unknown",
            **date_params,
        })
        assert resp.status_code == 200


class TestRecategorize:
    @pytest.mark.asyncio
    async def test_recategorize_pr(
        self, client, sample_developer, sample_repo, pr_unknown, date_params
    ):
        resp = await client.patch(
            f"/api/stats/work-allocation/items/pr/{pr_unknown.id}/category",
            json={"category": "tech_debt"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["category"] == "tech_debt"
        assert data["category_source"] == "manual"

    @pytest.mark.asyncio
    async def test_recategorize_issue(
        self, client, sample_developer, sample_repo, issue_unknown, date_params
    ):
        resp = await client.patch(
            f"/api/stats/work-allocation/items/issue/{issue_unknown.id}/category",
            json={"category": "bugfix"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["category"] == "bugfix"
        assert data["category_source"] == "manual"

    @pytest.mark.asyncio
    async def test_recategorize_rejects_unknown(
        self, client, sample_developer, sample_repo, pr_unknown
    ):
        resp = await client.patch(
            f"/api/stats/work-allocation/items/pr/{pr_unknown.id}/category",
            json={"category": "unknown"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_recategorize_rejects_invalid_category(
        self, client, sample_developer, sample_repo, pr_unknown
    ):
        resp = await client.patch(
            f"/api/stats/work-allocation/items/pr/{pr_unknown.id}/category",
            json={"category": "not_a_category"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_recategorize_rejects_invalid_type(self, client):
        resp = await client.patch(
            "/api/stats/work-allocation/items/commit/1/category",
            json={"category": "bugfix"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_recategorize_not_found(self, client):
        resp = await client.patch(
            "/api/stats/work-allocation/items/pr/99999/category",
            json={"category": "bugfix"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_manual_override_persists(
        self, client, sample_developer, sample_repo, pr_manual_override, date_params
    ):
        """Manual override should show as tech_debt, not unknown."""
        resp = await client.get("/api/stats/work-allocation/items", params={
            "category": "tech_debt",
            **date_params,
        })
        assert resp.status_code == 200
        data = resp.json()
        numbers = [i["number"] for i in data["items"]]
        assert 52 in numbers

        # It should NOT appear in unknown
        resp = await client.get("/api/stats/work-allocation/items", params={
            "category": "unknown",
            **date_params,
        })
        assert resp.status_code == 200
        data = resp.json()
        numbers = [i["number"] for i in data["items"]]
        assert 52 not in numbers

    @pytest.mark.asyncio
    async def test_recategorize_rejected_for_developer(
        self, developer_client, sample_developer, sample_repo, pr_unknown
    ):
        """Non-admin users cannot recategorize items."""
        resp = await developer_client.patch(
            f"/api/stats/work-allocation/items/pr/{pr_unknown.id}/category",
            json={"category": "feature"},
        )
        assert resp.status_code == 403
