"""Service tests for AI context builders and repo filtering."""

import json
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    BenchmarkGroupConfig,
    Developer,
    DeveloperGoal,
    Issue,
    IssueComment,
    PRReview,
    PullRequest,
    Repository,
)
from app.services.ai_analysis import (
    _gather_developer_texts,
    _gather_scope_texts,
    _gather_team_texts,
    build_one_on_one_context,
    build_team_health_context,
)

NOW = datetime.now(timezone.utc) + timedelta(hours=1)  # future to ensure all fixtures included
LONG_AGO = NOW - timedelta(days=60)  # well before any fixture data


@pytest_asyncio.fixture
async def second_repo(db_session: AsyncSession) -> Repository:
    repo = Repository(
        github_id=99999,
        name="other-repo",
        full_name="org/other-repo",
        description="Another repo",
        language="TypeScript",
        is_tracked=True,
        created_at=NOW,
    )
    db_session.add(repo)
    await db_session.commit()
    await db_session.refresh(repo)
    return repo


@pytest_asyncio.fixture
async def pr_in_second_repo(
    db_session: AsyncSession,
    sample_developer: Developer,
    second_repo: Repository,
) -> PullRequest:
    pr = PullRequest(
        github_id=200,
        repo_id=second_repo.id,
        author_id=sample_developer.id,
        number=2,
        title="Add feature",
        body="This adds a new feature to the other repo",
        state="closed",
        is_merged=True,
        additions=30,
        deletions=5,
        changed_files=2,
        created_at=LONG_AGO + timedelta(hours=1),
        merged_at=NOW - timedelta(days=1),
        time_to_merge_s=500000,
        labels=["feature"],
        head_branch="feature/new",
        base_branch="main",
    )
    db_session.add(pr)
    await db_session.commit()
    await db_session.refresh(pr)
    return pr


@pytest_asyncio.fixture
async def seed_benchmark_groups(db_session: AsyncSession):
    groups = [
        BenchmarkGroupConfig(
            group_key="ics",
            display_name="IC Engineers",
            display_order=1,
            roles=["developer", "senior_developer", "architect", "intern"],
            metrics=["prs_merged", "time_to_merge_h", "reviews_given"],
            min_team_size=2,
            is_default=True,
        ),
    ]
    db_session.add_all(groups)
    await db_session.commit()
    return groups


class TestGatherDeveloperTexts:
    @pytest.mark.asyncio
    async def test_returns_pr_descriptions(self, db_session, sample_developer, sample_pr):
        sample_pr.body = "This PR fixes auth"
        await db_session.commit()

        items, summary = await _gather_developer_texts(
            db_session, sample_developer.id, LONG_AGO, NOW,
        )
        assert len(items) >= 1
        pr_items = [i for i in items if i["type"] == "pr_description"]
        assert len(pr_items) == 1
        assert "auth" in pr_items[0]["text"]
        assert f"Developer {sample_developer.id}" in summary

    @pytest.mark.asyncio
    async def test_empty_when_no_data(self, db_session, sample_developer):
        items, _ = await _gather_developer_texts(
            db_session, sample_developer.id, LONG_AGO, NOW,
        )
        assert items == []

    @pytest.mark.asyncio
    async def test_repo_filter_includes_matching(
        self, db_session, sample_developer, sample_pr, pr_in_second_repo, sample_repo, second_repo,
    ):
        """When repo_ids is provided, only PRs from those repos are included."""
        sample_pr.body = "Fix in first repo"
        pr_in_second_repo.body = "Feature in second repo"
        await db_session.commit()

        # Filter to first repo only
        items, _ = await _gather_developer_texts(
            db_session, sample_developer.id, LONG_AGO, NOW,
            repo_ids=[sample_repo.id],
        )
        pr_items = [i for i in items if i["type"] == "pr_description"]
        assert len(pr_items) == 1
        assert "first repo" in pr_items[0]["text"]

    @pytest.mark.asyncio
    async def test_repo_filter_excludes_non_matching(
        self, db_session, sample_developer, sample_pr, pr_in_second_repo, second_repo,
    ):
        sample_pr.body = "Fix in first repo"
        pr_in_second_repo.body = "Feature in second repo"
        await db_session.commit()

        # Filter to second repo only
        items, _ = await _gather_developer_texts(
            db_session, sample_developer.id, LONG_AGO, NOW,
            repo_ids=[second_repo.id],
        )
        pr_items = [i for i in items if i["type"] == "pr_description"]
        assert len(pr_items) == 1
        assert "second repo" in pr_items[0]["text"]

    @pytest.mark.asyncio
    async def test_no_repo_filter_returns_all(
        self, db_session, sample_developer, sample_pr, pr_in_second_repo,
    ):
        sample_pr.body = "PR one"
        pr_in_second_repo.body = "PR two"
        await db_session.commit()

        items, _ = await _gather_developer_texts(
            db_session, sample_developer.id, LONG_AGO, NOW,
        )
        pr_items = [i for i in items if i["type"] == "pr_description"]
        assert len(pr_items) == 2

    @pytest.mark.asyncio
    async def test_nonexistent_developer_returns_empty(self, db_session):
        items, summary = await _gather_developer_texts(
            db_session, 99999, LONG_AGO, NOW,
        )
        assert items == []
        assert "not found" in summary


class TestGatherTeamTexts:
    @pytest.mark.asyncio
    async def test_returns_team_reviews(
        self, db_session, sample_developer, sample_developer_b, sample_pr, sample_review,
    ):
        sample_review.body = "This needs refactoring"
        await db_session.commit()

        items, summary = await _gather_team_texts(
            db_session, "backend", LONG_AGO, NOW,
        )
        assert len(items) >= 1
        assert "backend" in summary

    @pytest.mark.asyncio
    async def test_repo_filter(
        self, db_session, sample_developer, sample_developer_b, sample_pr, sample_review, sample_repo, second_repo,
    ):
        sample_review.body = "Review body"
        await db_session.commit()

        # Filter to a repo that doesn't have this PR
        items, _ = await _gather_team_texts(
            db_session, "backend", LONG_AGO, NOW,
            repo_ids=[second_repo.id],
        )
        assert len(items) == 0


class TestGatherScopeTexts:
    @pytest.mark.asyncio
    async def test_routes_to_developer(self, db_session, sample_developer, sample_pr):
        sample_pr.body = "Test body"
        await db_session.commit()

        items, _ = await _gather_scope_texts(
            db_session, "developer", str(sample_developer.id), LONG_AGO, NOW,
        )
        assert len(items) >= 1

    @pytest.mark.asyncio
    async def test_routes_to_team(
        self, db_session, sample_developer, sample_developer_b, sample_pr, sample_review,
    ):
        sample_review.body = "Review text"
        await db_session.commit()

        items, _ = await _gather_scope_texts(
            db_session, "team", "backend", LONG_AGO, NOW,
        )
        assert len(items) >= 1

    @pytest.mark.asyncio
    async def test_passes_repo_ids_through(
        self, db_session, sample_developer, sample_pr, second_repo,
    ):
        sample_pr.body = "PR body"
        await db_session.commit()

        # Filter to a non-matching repo
        items, _ = await _gather_scope_texts(
            db_session, "developer", str(sample_developer.id), LONG_AGO, NOW,
            repo_ids=[second_repo.id],
        )
        pr_items = [i for i in items if i["type"] == "pr_description"]
        assert len(pr_items) == 0

    @pytest.mark.asyncio
    async def test_unknown_scope_returns_empty(self, db_session):
        items, summary = await _gather_scope_texts(
            db_session, "unknown", "1", LONG_AGO, NOW,
        )
        assert items == []
        assert "Unknown" in summary


class TestBuildOneOnOneContext:
    @pytest.mark.asyncio
    async def test_returns_expected_keys(
        self, db_session, sample_developer, sample_pr, sample_review, seed_benchmark_groups,
    ):
        context, summary = await build_one_on_one_context(
            db_session, sample_developer.id, LONG_AGO, NOW,
        )
        assert "developer" in context
        assert "period" in context
        assert "stats" in context
        assert "trends" in context
        assert "prs" in context
        assert "review_quality" in context
        assert "goals" in context
        assert context["developer"]["name"] == "Test User"
        assert context["developer"]["team"] == "backend"
        assert sample_developer.display_name in summary

    @pytest.mark.asyncio
    async def test_nonexistent_developer_returns_empty(self, db_session):
        context, summary = await build_one_on_one_context(
            db_session, 99999, LONG_AGO, NOW,
        )
        assert context == {}
        assert "not found" in summary

    @pytest.mark.asyncio
    async def test_repo_filter_limits_prs(
        self, db_session, sample_developer, sample_pr, pr_in_second_repo, second_repo, seed_benchmark_groups,
    ):
        context, _ = await build_one_on_one_context(
            db_session, sample_developer.id, LONG_AGO, NOW,
            repo_ids=[second_repo.id],
        )
        # Only the PR in second_repo should be included
        assert len(context["prs"]) == 1
        assert context["prs"][0]["title"] == "Add feature"

    @pytest.mark.asyncio
    async def test_context_is_json_serializable(
        self, db_session, sample_developer, sample_pr, seed_benchmark_groups,
    ):
        context, _ = await build_one_on_one_context(
            db_session, sample_developer.id, LONG_AGO, NOW,
        )
        # Must not raise
        serialized = json.dumps(context, default=str)
        assert len(serialized) > 0


class TestBuildTeamHealthContext:
    @pytest.mark.asyncio
    async def test_returns_expected_keys(
        self, db_session, sample_developer, sample_developer_b, sample_pr, sample_review, seed_benchmark_groups,
    ):
        context, summary = await build_team_health_context(
            db_session, "backend", LONG_AGO, NOW,
        )
        assert "team" in context
        assert "period" in context
        assert "team_stats" in context
        assert "workload" in context
        assert "collaboration" in context
        assert "changes_requested_reviews" in context
        assert "heated_threads" in context
        assert "team_goals" in context
        assert context["team"] == "backend"
        assert "backend" in summary

    @pytest.mark.asyncio
    async def test_all_teams_scope(
        self, db_session, sample_developer, sample_developer_b, sample_pr, sample_review, seed_benchmark_groups,
    ):
        context, summary = await build_team_health_context(
            db_session, None, LONG_AGO, NOW,
        )
        assert context["team"] == "all"
        assert "all" in summary

    @pytest.mark.asyncio
    async def test_context_is_json_serializable(
        self, db_session, sample_developer, sample_developer_b, sample_pr, sample_review, seed_benchmark_groups,
    ):
        context, _ = await build_team_health_context(
            db_session, "backend", LONG_AGO, NOW,
        )
        serialized = json.dumps(context, default=str)
        assert len(serialized) > 0
