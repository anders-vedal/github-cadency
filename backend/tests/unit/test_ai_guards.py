"""Unit tests for AI guard functions — uses in-memory SQLite DB."""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AIAnalysis, AISettings, AIUsageLog
from app.services.ai_settings import (
    check_budget,
    check_feature_enabled,
    compute_cost,
    find_recent_analysis,
    get_ai_settings,
    update_ai_settings,
)
from app.schemas.schemas import AISettingsUpdate


NOW = datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def ai_settings(db_session: AsyncSession) -> AISettings:
    """Ensure default AI settings row exists."""
    return await get_ai_settings(db_session)


class TestGetAISettings:
    @pytest.mark.asyncio
    async def test_creates_default_row(self, db_session):
        settings = await get_ai_settings(db_session)
        assert settings.id == 1
        assert settings.ai_enabled is True
        assert settings.feature_general_analysis is True
        assert settings.cooldown_minutes == 30
        assert settings.monthly_token_budget is None
        assert settings.input_token_price_per_million == 3.0
        assert settings.output_token_price_per_million == 15.0

    @pytest.mark.asyncio
    async def test_returns_existing_row(self, db_session, ai_settings):
        # Second call returns same row
        settings = await get_ai_settings(db_session)
        assert settings.id == ai_settings.id


class TestUpdateSettings:
    @pytest.mark.asyncio
    async def test_partial_update(self, db_session, ai_settings):
        updates = AISettingsUpdate(ai_enabled=False)
        result = await update_ai_settings(db_session, updates, "admin_user")
        assert result.ai_enabled is False
        assert result.feature_general_analysis is True  # unchanged
        assert result.updated_by == "admin_user"

    @pytest.mark.asyncio
    async def test_pricing_update_sets_timestamp(self, db_session, ai_settings):
        assert ai_settings.pricing_updated_at is None
        updates = AISettingsUpdate(input_token_price_per_million=4.0)
        result = await update_ai_settings(db_session, updates, "admin_user")
        assert result.input_token_price_per_million == 4.0
        assert result.pricing_updated_at is not None

    @pytest.mark.asyncio
    async def test_clear_budget(self, db_session, ai_settings):
        # Set a budget first
        updates = AISettingsUpdate(monthly_token_budget=100000)
        await update_ai_settings(db_session, updates, "admin")
        # Clear it
        updates = AISettingsUpdate(clear_budget=True)
        result = await update_ai_settings(db_session, updates, "admin")
        assert result.monthly_token_budget is None


class TestCheckFeatureEnabled:
    @pytest.mark.asyncio
    async def test_master_off_raises_disabled(self, db_session, ai_settings):
        from app.services.exceptions import AIFeatureDisabledError

        ai_settings.ai_enabled = False
        await db_session.commit()

        with pytest.raises(AIFeatureDisabledError) as exc_info:
            await check_feature_enabled(db_session, "general_analysis")
        assert "disabled" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_feature_off_raises_disabled(self, db_session, ai_settings):
        from app.services.exceptions import AIFeatureDisabledError

        ai_settings.feature_one_on_one_prep = False
        await db_session.commit()

        with pytest.raises(AIFeatureDisabledError) as exc_info:
            await check_feature_enabled(db_session, "one_on_one_prep")
        assert "1:1 Prep Brief" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_both_on_returns_settings(self, db_session, ai_settings):
        result = await check_feature_enabled(db_session, "general_analysis")
        assert result.id == ai_settings.id
        assert result.ai_enabled is True


class TestCheckBudget:
    @pytest.mark.asyncio
    async def test_unlimited_never_over(self, db_session, ai_settings):
        # No budget set → never over
        result = await check_budget(db_session, ai_settings)
        assert result["over_budget"] is False
        assert result["budget_limit"] is None
        assert result["pct_used"] is None

    @pytest.mark.asyncio
    async def test_under_budget(self, db_session, ai_settings):
        ai_settings.monthly_token_budget = 100000
        await db_session.commit()

        # Add some usage this month
        analysis = AIAnalysis(
            analysis_type="communication",
            scope_type="developer",
            scope_id="1",
            tokens_used=5000,
            input_tokens=3500,
            output_tokens=1500,
            created_at=NOW,
        )
        db_session.add(analysis)
        await db_session.commit()

        result = await check_budget(db_session, ai_settings)
        assert result["over_budget"] is False
        assert result["tokens_used"] == 5000
        assert result["pct_used"] == 0.05

    @pytest.mark.asyncio
    async def test_over_budget(self, db_session, ai_settings):
        ai_settings.monthly_token_budget = 1000
        await db_session.commit()

        analysis = AIAnalysis(
            analysis_type="team_health",
            scope_type="team",
            scope_id="all",
            tokens_used=2000,
            input_tokens=1500,
            output_tokens=500,
            created_at=NOW,
        )
        db_session.add(analysis)
        await db_session.commit()

        result = await check_budget(db_session, ai_settings)
        assert result["over_budget"] is True
        assert result["tokens_used"] == 2000

    @pytest.mark.asyncio
    async def test_includes_usage_log_tokens(self, db_session, ai_settings):
        ai_settings.monthly_token_budget = 10000
        await db_session.commit()

        # ai_analyses usage
        analysis = AIAnalysis(
            analysis_type="communication",
            tokens_used=3000,
            created_at=NOW,
        )
        db_session.add(analysis)

        # ai_usage_log usage
        log = AIUsageLog(
            feature="work_categorization",
            input_tokens=1500,
            output_tokens=500,
            items_classified=50,
            created_at=NOW,
        )
        db_session.add(log)
        await db_session.commit()

        result = await check_budget(db_session, ai_settings)
        assert result["tokens_used"] == 5000  # 3000 + 2000

    @pytest.mark.asyncio
    async def test_excludes_reused_from_budget(self, db_session, ai_settings):
        ai_settings.monthly_token_budget = 10000
        await db_session.commit()

        # Real call
        real = AIAnalysis(
            analysis_type="communication",
            tokens_used=5000,
            created_at=NOW,
        )
        db_session.add(real)
        await db_session.flush()

        # Reused call (should not count)
        reused = AIAnalysis(
            analysis_type="communication",
            tokens_used=0,
            reused_from_id=real.id,
            created_at=NOW,
        )
        db_session.add(reused)
        await db_session.commit()

        result = await check_budget(db_session, ai_settings)
        assert result["tokens_used"] == 5000  # only real call counted


class TestFindRecentAnalysis:
    @pytest.mark.asyncio
    async def test_finds_within_cooldown(self, db_session):
        analysis = AIAnalysis(
            analysis_type="communication",
            scope_type="developer",
            scope_id="42",
            tokens_used=5000,
            created_at=NOW - timedelta(minutes=10),
        )
        db_session.add(analysis)
        await db_session.commit()

        result = await find_recent_analysis(
            db_session, "communication", "developer", "42", cooldown_minutes=30
        )
        assert result is not None
        assert result.id == analysis.id

    @pytest.mark.asyncio
    async def test_expired_returns_none(self, db_session):
        analysis = AIAnalysis(
            analysis_type="communication",
            scope_type="developer",
            scope_id="42",
            tokens_used=5000,
            created_at=NOW - timedelta(minutes=60),
        )
        db_session.add(analysis)
        await db_session.commit()

        result = await find_recent_analysis(
            db_session, "communication", "developer", "42", cooldown_minutes=30
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_different_scope_returns_none(self, db_session):
        analysis = AIAnalysis(
            analysis_type="communication",
            scope_type="developer",
            scope_id="42",
            tokens_used=5000,
            created_at=NOW - timedelta(minutes=5),
        )
        db_session.add(analysis)
        await db_session.commit()

        result = await find_recent_analysis(
            db_session, "communication", "developer", "99", cooldown_minutes=30
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_zero_cooldown_skips_check(self, db_session):
        analysis = AIAnalysis(
            analysis_type="communication",
            scope_type="developer",
            scope_id="42",
            tokens_used=5000,
            created_at=NOW,
        )
        db_session.add(analysis)
        await db_session.commit()

        result = await find_recent_analysis(
            db_session, "communication", "developer", "42", cooldown_minutes=0
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_does_not_chain_reuses(self, db_session):
        """A reused result should not be returned as a cache hit."""
        real = AIAnalysis(
            analysis_type="communication",
            scope_type="developer",
            scope_id="42",
            tokens_used=5000,
            created_at=NOW - timedelta(minutes=60),
        )
        db_session.add(real)
        await db_session.flush()

        reused = AIAnalysis(
            analysis_type="communication",
            scope_type="developer",
            scope_id="42",
            tokens_used=0,
            reused_from_id=real.id,
            created_at=NOW - timedelta(minutes=5),
        )
        db_session.add(reused)
        await db_session.commit()

        # Should not find the reused row
        result = await find_recent_analysis(
            db_session, "communication", "developer", "42", cooldown_minutes=30
        )
        assert result is None
