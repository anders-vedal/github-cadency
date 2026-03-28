"""Unit tests for AI usage tracking — feature statuses, daily usage, cost estimation."""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AIAnalysis, AISettings, AIUsageLog
from app.services.ai_settings import (
    compute_cost,
    get_ai_settings,
    get_daily_usage,
    get_feature_statuses,
    FEATURE_META,
)


NOW = datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def ai_settings(db_session: AsyncSession) -> AISettings:
    """Ensure default AI settings row exists."""
    return await get_ai_settings(db_session)


class TestFeatureStatuses:
    @pytest.mark.asyncio
    async def test_all_enabled_returns_four_features(self, db_session, ai_settings):
        statuses = await get_feature_statuses(db_session, ai_settings)
        assert len(statuses) == 4
        feature_keys = {s.feature for s in statuses}
        assert feature_keys == {
            "general_analysis",
            "one_on_one_prep",
            "team_health",
            "work_categorization",
        }
        for s in statuses:
            assert s.enabled is True
            assert len(s.label) > 0
            assert len(s.description) > 20
            assert len(s.disabled_impact) > 20

    @pytest.mark.asyncio
    async def test_some_disabled_reflected(self, db_session, ai_settings):
        ai_settings.feature_one_on_one_prep = False
        ai_settings.feature_work_categorization = False
        await db_session.commit()

        statuses = await get_feature_statuses(db_session, ai_settings)
        by_key = {s.feature: s for s in statuses}
        assert by_key["general_analysis"].enabled is True
        assert by_key["one_on_one_prep"].enabled is False
        assert by_key["team_health"].enabled is True
        assert by_key["work_categorization"].enabled is False

    @pytest.mark.asyncio
    async def test_master_off_disables_all(self, db_session, ai_settings):
        ai_settings.ai_enabled = False
        await db_session.commit()

        statuses = await get_feature_statuses(db_session, ai_settings)
        for s in statuses:
            assert s.enabled is False

    @pytest.mark.asyncio
    async def test_usage_counts_exclude_reused(self, db_session, ai_settings):
        # Real call
        real = AIAnalysis(
            analysis_type="communication",
            scope_type="developer",
            scope_id="1",
            tokens_used=5000,
            input_tokens=3500,
            output_tokens=1500,
            created_at=NOW,
        )
        db_session.add(real)
        await db_session.flush()

        # Reused (should not count)
        reused = AIAnalysis(
            analysis_type="communication",
            scope_type="developer",
            scope_id="1",
            tokens_used=0,
            input_tokens=0,
            output_tokens=0,
            reused_from_id=real.id,
            created_at=NOW,
        )
        db_session.add(reused)
        await db_session.commit()

        statuses = await get_feature_statuses(db_session, ai_settings)
        ga = next(s for s in statuses if s.feature == "general_analysis")
        assert ga.tokens_this_month == 5000  # only real call
        assert ga.call_count_this_month == 1  # reused not counted

    @pytest.mark.asyncio
    async def test_work_categorization_uses_usage_log(self, db_session, ai_settings):
        log = AIUsageLog(
            feature="work_categorization",
            input_tokens=2000,
            output_tokens=800,
            items_classified=50,
            created_at=NOW,
        )
        db_session.add(log)
        await db_session.commit()

        statuses = await get_feature_statuses(db_session, ai_settings)
        wc = next(s for s in statuses if s.feature == "work_categorization")
        assert wc.tokens_this_month == 2800
        assert wc.call_count_this_month == 1
        assert wc.cost_this_month_usd > 0


class TestDailyUsage:
    @pytest.mark.asyncio
    async def test_aggregation_across_tables(self, db_session, ai_settings):
        day1 = NOW.replace(hour=10, minute=0, second=0, microsecond=0)

        # ai_analyses entry
        analysis = AIAnalysis(
            analysis_type="one_on_one_prep",
            scope_type="developer",
            scope_id="1",
            tokens_used=8000,
            input_tokens=5000,
            output_tokens=3000,
            created_at=day1,
        )
        db_session.add(analysis)

        # ai_usage_log entry same day
        log = AIUsageLog(
            feature="work_categorization",
            input_tokens=1500,
            output_tokens=500,
            items_classified=30,
            created_at=day1 + timedelta(hours=2),
        )
        db_session.add(log)
        await db_session.commit()

        daily = await get_daily_usage(db_session, ai_settings, days=7)
        assert len(daily) >= 1

        # Find today's entry
        today_str = day1.date().isoformat()
        today = next((d for d in daily if d.date == today_str), None)
        assert today is not None
        assert today.tokens == 10000  # 8000 + 2000
        assert today.calls == 2
        assert "one_on_one_prep" in today.by_feature
        assert "work_categorization" in today.by_feature

    @pytest.mark.asyncio
    async def test_empty_period_returns_empty_list(self, db_session, ai_settings):
        daily = await get_daily_usage(db_session, ai_settings, days=7)
        assert daily == []


class TestCostComputation:
    def test_accuracy(self):
        # Exact: (10000 * 3.0 / 1M) + (5000 * 15.0 / 1M) = 0.03 + 0.075 = 0.105
        cost = compute_cost(10000, 5000, 3.0, 15.0)
        assert cost == 0.105

    def test_zero_input(self):
        cost = compute_cost(0, 5000, 3.0, 15.0)
        assert cost == 0.075

    def test_zero_output(self):
        cost = compute_cost(10000, 0, 3.0, 15.0)
        assert cost == 0.03
