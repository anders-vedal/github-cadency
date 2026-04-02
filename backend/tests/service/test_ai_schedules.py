"""Service tests for AI analysis schedule CRUD and execution."""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AIAnalysisSchedule, AISettings
from app.schemas.schemas import AIScheduleCreate, AIScheduleUpdate
from app.services.ai_schedules import (
    compute_next_run_description,
    create_schedule,
    delete_schedule,
    get_schedule,
    list_schedules,
    update_schedule,
)
from app.services.ai_settings import get_ai_settings


NOW = datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def ai_settings(db_session: AsyncSession) -> AISettings:
    return await get_ai_settings(db_session)


@pytest_asyncio.fixture
async def sample_schedule(db_session: AsyncSession, sample_developer) -> AIAnalysisSchedule:
    data = AIScheduleCreate(
        name="Weekly 1:1 Prep",
        analysis_type="one_on_one_prep",
        scope_type="developer",
        scope_id=str(sample_developer.id),
        time_range_days=30,
        frequency="weekly",
        day_of_week=0,
        hour=8,
        minute=0,
    )
    return await create_schedule(db_session, data, "admin")


class TestCreateSchedule:
    @pytest.mark.asyncio
    async def test_creates_with_valid_data(self, db_session, sample_developer):
        data = AIScheduleCreate(
            name="Daily Sentiment",
            analysis_type="sentiment",
            scope_type="developer",
            scope_id=str(sample_developer.id),
            frequency="daily",
            hour=9,
        )
        schedule = await create_schedule(db_session, data, "admin")
        assert schedule.id is not None
        assert schedule.name == "Daily Sentiment"
        assert schedule.analysis_type == "sentiment"
        assert schedule.frequency == "daily"
        assert schedule.hour == 9
        assert schedule.is_enabled is True
        assert schedule.created_by == "admin"

    @pytest.mark.asyncio
    async def test_rejects_invalid_analysis_type(self, db_session):
        from fastapi import HTTPException

        data = AIScheduleCreate(
            name="Bad",
            analysis_type="invalid_type",
            scope_type="developer",
            scope_id="1",
            frequency="daily",
        )
        with pytest.raises(HTTPException) as exc_info:
            await create_schedule(db_session, data, "admin")
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_rejects_invalid_frequency(self, db_session):
        from fastapi import HTTPException

        data = AIScheduleCreate(
            name="Bad",
            analysis_type="communication",
            scope_type="developer",
            scope_id="1",
            frequency="every_3_days",
        )
        with pytest.raises(HTTPException) as exc_info:
            await create_schedule(db_session, data, "admin")
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_weekly_requires_day_of_week(self, db_session):
        from fastapi import HTTPException

        data = AIScheduleCreate(
            name="Weekly",
            analysis_type="team_health",
            scope_type="team",
            scope_id="backend",
            frequency="weekly",
            # day_of_week not set
        )
        with pytest.raises(HTTPException) as exc_info:
            await create_schedule(db_session, data, "admin")
        assert exc_info.value.status_code == 422
        assert "day_of_week" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_biweekly_requires_day_of_week(self, db_session):
        from fastapi import HTTPException

        data = AIScheduleCreate(
            name="Biweekly",
            analysis_type="team_health",
            scope_type="team",
            scope_id="backend",
            frequency="biweekly",
        )
        with pytest.raises(HTTPException) as exc_info:
            await create_schedule(db_session, data, "admin")
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_monthly_does_not_require_day_of_week(self, db_session):
        data = AIScheduleCreate(
            name="Monthly",
            analysis_type="team_health",
            scope_type="team",
            scope_id="backend",
            frequency="monthly",
            hour=6,
        )
        schedule = await create_schedule(db_session, data, "admin")
        assert schedule.frequency == "monthly"
        assert schedule.day_of_week is None


class TestListSchedules:
    @pytest.mark.asyncio
    async def test_returns_empty_initially(self, db_session):
        schedules = await list_schedules(db_session)
        assert schedules == []

    @pytest.mark.asyncio
    async def test_returns_created_schedules(self, db_session, sample_schedule):
        schedules = await list_schedules(db_session)
        assert len(schedules) == 1
        assert schedules[0].name == "Weekly 1:1 Prep"


class TestGetSchedule:
    @pytest.mark.asyncio
    async def test_returns_by_id(self, db_session, sample_schedule):
        schedule = await get_schedule(db_session, sample_schedule.id)
        assert schedule.name == "Weekly 1:1 Prep"

    @pytest.mark.asyncio
    async def test_not_found_raises_404(self, db_session):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_schedule(db_session, 99999)
        assert exc_info.value.status_code == 404


class TestUpdateSchedule:
    @pytest.mark.asyncio
    async def test_toggle_enabled(self, db_session, sample_schedule):
        updated = await update_schedule(
            db_session, sample_schedule.id,
            AIScheduleUpdate(is_enabled=False),
        )
        assert updated.is_enabled is False

    @pytest.mark.asyncio
    async def test_update_name(self, db_session, sample_schedule):
        updated = await update_schedule(
            db_session, sample_schedule.id,
            AIScheduleUpdate(name="Renamed Schedule"),
        )
        assert updated.name == "Renamed Schedule"

    @pytest.mark.asyncio
    async def test_change_to_weekly_without_day_rejects(self, db_session, sample_developer):
        """Changing frequency to weekly when day_of_week is None should fail."""
        from fastapi import HTTPException

        # Create a daily schedule first (no day_of_week)
        data = AIScheduleCreate(
            name="Daily",
            analysis_type="communication",
            scope_type="developer",
            scope_id=str(sample_developer.id),
            frequency="daily",
        )
        schedule = await create_schedule(db_session, data, "admin")

        # Try changing to weekly without setting day_of_week
        with pytest.raises(HTTPException) as exc_info:
            await update_schedule(
                db_session, schedule.id,
                AIScheduleUpdate(frequency="weekly"),
            )
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_validates_before_mutating(self, db_session, sample_developer):
        """Invalid update should NOT leave dirty state on the schedule."""
        from fastapi import HTTPException

        data = AIScheduleCreate(
            name="Daily",
            analysis_type="communication",
            scope_type="developer",
            scope_id=str(sample_developer.id),
            frequency="daily",
        )
        schedule = await create_schedule(db_session, data, "admin")
        original_frequency = schedule.frequency

        with pytest.raises(HTTPException):
            await update_schedule(
                db_session, schedule.id,
                AIScheduleUpdate(frequency="weekly"),
            )

        # Re-fetch from DB — frequency should still be "daily"
        await db_session.refresh(schedule)
        assert schedule.frequency == original_frequency


class TestDeleteSchedule:
    @pytest.mark.asyncio
    async def test_deletes_existing(self, db_session, sample_schedule):
        await delete_schedule(db_session, sample_schedule.id)
        schedules = await list_schedules(db_session)
        assert len(schedules) == 0

    @pytest.mark.asyncio
    async def test_not_found_raises_404(self, db_session):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await delete_schedule(db_session, 99999)
        assert exc_info.value.status_code == 404


class TestComputeNextRunDescription:
    def test_daily(self):
        schedule = AIAnalysisSchedule(frequency="daily", hour=8, minute=0)
        desc = compute_next_run_description(schedule)
        assert "Daily" in desc
        assert "8:00 AM" in desc

    def test_weekly_monday(self):
        schedule = AIAnalysisSchedule(frequency="weekly", day_of_week=0, hour=9, minute=30)
        desc = compute_next_run_description(schedule)
        assert "Weekly" in desc
        assert "Monday" in desc
        assert "9:30 AM" in desc

    def test_biweekly_friday(self):
        schedule = AIAnalysisSchedule(frequency="biweekly", day_of_week=4, hour=14, minute=0)
        desc = compute_next_run_description(schedule)
        assert "2 weeks" in desc.lower() or "biweekly" in desc.lower()
        assert "Friday" in desc
        assert "2:00 PM" in desc

    def test_monthly(self):
        schedule = AIAnalysisSchedule(frequency="monthly", hour=6, minute=0)
        desc = compute_next_run_description(schedule)
        assert "Monthly" in desc
        assert "6:00 AM" in desc

    def test_pm_hours(self):
        schedule = AIAnalysisSchedule(frequency="daily", hour=23, minute=0)
        desc = compute_next_run_description(schedule)
        assert "11:00 PM" in desc

    def test_midnight(self):
        schedule = AIAnalysisSchedule(frequency="daily", hour=0, minute=0)
        desc = compute_next_run_description(schedule)
        assert "12:00 AM" in desc
