"""Unit tests for enhanced AI cost estimation."""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AISettings, BenchmarkGroupConfig, Developer, PullRequest, Repository
from app.services.ai_settings import estimate_analysis_cost, get_ai_settings


@pytest_asyncio.fixture
async def seed_benchmark_groups(db_session):
    groups = [
        BenchmarkGroupConfig(
            group_key="ics", display_name="IC Engineers", display_order=1,
            roles=["developer", "senior_developer"], metrics=["prs_merged"],
            min_team_size=2, is_default=True,
        ),
    ]
    db_session.add_all(groups)
    await db_session.commit()


NOW = datetime.now(timezone.utc) + timedelta(hours=1)
LONG_AGO = NOW - timedelta(days=60)


@pytest_asyncio.fixture
async def ai_settings(db_session: AsyncSession) -> AISettings:
    return await get_ai_settings(db_session)


class TestEstimateGeneralAnalysis:
    @pytest.mark.asyncio
    async def test_returns_character_count(
        self, db_session, ai_settings, sample_developer, sample_pr,
    ):
        sample_pr.body = "This is a test PR body for estimation"
        await db_session.commit()

        result = await estimate_analysis_cost(
            db_session,
            feature="general_analysis",
            scope_type="developer",
            scope_id=str(sample_developer.id),
            date_from=LONG_AGO.isoformat(),
            date_to=NOW.isoformat(),
        )
        assert result.character_count > 0
        assert result.data_items >= 1
        assert result.estimated_input_tokens > 0
        assert result.estimated_cost_usd > 0
        assert result.system_prompt_tokens > 0

    @pytest.mark.asyncio
    async def test_empty_scope_returns_zero_items(self, db_session, ai_settings, sample_developer):
        result = await estimate_analysis_cost(
            db_session,
            feature="general_analysis",
            scope_type="developer",
            scope_id=str(sample_developer.id),
            date_from=LONG_AGO.isoformat(),
            date_to=NOW.isoformat(),
        )
        assert result.data_items == 0
        # character_count is 2 for "[]" (empty JSON array)
        assert result.character_count <= 2

    @pytest.mark.asyncio
    async def test_missing_scope_returns_note(self, db_session, ai_settings):
        result = await estimate_analysis_cost(
            db_session,
            feature="general_analysis",
        )
        assert "scope_type" in result.note.lower() or "provide" in result.note.lower()

    @pytest.mark.asyncio
    async def test_repo_filter_applied(
        self, db_session, ai_settings, sample_developer, sample_pr, sample_repo,
    ):
        sample_pr.body = "Included PR"
        await db_session.commit()

        # Filter to a non-existent repo — should exclude the PR
        result = await estimate_analysis_cost(
            db_session,
            feature="general_analysis",
            scope_type="developer",
            scope_id=str(sample_developer.id),
            date_from=LONG_AGO.isoformat(),
            date_to=NOW.isoformat(),
            repo_ids=[99999],
        )
        assert result.data_items == 0


class TestEstimateOneOnOnePrep:
    @pytest.mark.asyncio
    async def test_builds_real_context(
        self, db_session, ai_settings, sample_developer, sample_pr, sample_review, seed_benchmark_groups,
    ):
        result = await estimate_analysis_cost(
            db_session,
            feature="one_on_one_prep",
            scope_id=str(sample_developer.id),
            date_from=LONG_AGO.isoformat(),
            date_to=NOW.isoformat(),
        )
        assert result.character_count > 0
        assert result.estimated_input_tokens > 0
        assert result.system_prompt_tokens > 0
        assert "actual context" in result.note.lower()

    @pytest.mark.asyncio
    async def test_no_scope_id_returns_fallback(self, db_session, ai_settings):
        result = await estimate_analysis_cost(
            db_session,
            feature="one_on_one_prep",
        )
        assert result.estimated_input_tokens == 5000
        assert "provide" in result.note.lower() or "scope_id" in result.note.lower()

    @pytest.mark.asyncio
    async def test_nonexistent_developer_returns_gracefully(self, db_session, ai_settings):
        result = await estimate_analysis_cost(
            db_session,
            feature="one_on_one_prep",
            scope_id="99999",
            date_from=LONG_AGO.isoformat(),
            date_to=NOW.isoformat(),
        )
        # Should not crash — returns empty/zero context
        assert result.estimated_input_tokens >= 0


class TestEstimateTeamHealth:
    @pytest.mark.asyncio
    async def test_builds_real_context(
        self, db_session, ai_settings, sample_developer, sample_developer_b, sample_pr, sample_review, seed_benchmark_groups,
    ):
        result = await estimate_analysis_cost(
            db_session,
            feature="team_health",
            scope_id="backend",
            date_from=LONG_AGO.isoformat(),
            date_to=NOW.isoformat(),
        )
        assert result.character_count > 0
        assert result.estimated_input_tokens > 0
        assert result.system_prompt_tokens > 0
        assert "actual context" in result.note.lower()

    @pytest.mark.asyncio
    async def test_all_teams(
        self, db_session, ai_settings, sample_developer, sample_developer_b, sample_pr, sample_review, seed_benchmark_groups,
    ):
        result = await estimate_analysis_cost(
            db_session,
            feature="team_health",
            scope_id="all",
            date_from=LONG_AGO.isoformat(),
            date_to=NOW.isoformat(),
        )
        assert result.character_count > 0


class TestBudgetHeadroom:
    @pytest.mark.asyncio
    async def test_no_budget_set_returns_zero_remaining(self, db_session, ai_settings, sample_developer, sample_pr):
        """When no budget is configured, remaining is 0 and would_exceed is False."""
        sample_pr.body = "Some data"
        await db_session.commit()

        result = await estimate_analysis_cost(
            db_session,
            feature="general_analysis",
            scope_type="developer",
            scope_id=str(sample_developer.id),
            date_from=LONG_AGO.isoformat(),
            date_to=NOW.isoformat(),
        )
        assert result.remaining_budget_tokens == 0
        assert result.would_exceed_budget is False

    @pytest.mark.asyncio
    async def test_within_budget(self, db_session, ai_settings, sample_developer, sample_pr):
        """When budget is large enough, would_exceed is False."""
        ai_settings.monthly_token_budget = 1_000_000
        await db_session.commit()

        sample_pr.body = "Some data"
        await db_session.commit()

        result = await estimate_analysis_cost(
            db_session,
            feature="general_analysis",
            scope_type="developer",
            scope_id=str(sample_developer.id),
            date_from=LONG_AGO.isoformat(),
            date_to=NOW.isoformat(),
        )
        assert result.remaining_budget_tokens > 0
        assert result.would_exceed_budget is False

    @pytest.mark.asyncio
    async def test_exceeds_budget(self, db_session, ai_settings, sample_developer, sample_pr):
        """When budget is tiny, would_exceed is True."""
        ai_settings.monthly_token_budget = 1  # 1 token budget
        await db_session.commit()

        sample_pr.body = "Some data"
        await db_session.commit()

        result = await estimate_analysis_cost(
            db_session,
            feature="general_analysis",
            scope_type="developer",
            scope_id=str(sample_developer.id),
            date_from=LONG_AGO.isoformat(),
            date_to=NOW.isoformat(),
        )
        assert result.would_exceed_budget is True
