"""AI Analysis Schedule CRUD and execution service."""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger
from app.models.models import AIAnalysisSchedule
from app.schemas.schemas import AIScheduleCreate, AIScheduleUpdate
from app.services.ai_analysis import run_analysis, run_one_on_one_prep, run_team_health
from app.services.exceptions import AIBudgetExceededError, AIFeatureDisabledError

logger = get_logger(__name__)

VALID_ANALYSIS_TYPES = {"communication", "conflict", "sentiment", "one_on_one_prep", "team_health"}
VALID_FREQUENCIES = {"daily", "weekly", "biweekly", "monthly"}
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


async def list_schedules(db: AsyncSession) -> list[AIAnalysisSchedule]:
    """List all AI analysis schedules ordered by creation date descending."""
    result = await db.execute(
        select(AIAnalysisSchedule).order_by(AIAnalysisSchedule.created_at.desc())
    )
    return list(result.scalars().all())


async def get_schedule(db: AsyncSession, schedule_id: int) -> AIAnalysisSchedule:
    """Get a schedule by ID or raise 404."""
    schedule = await db.get(AIAnalysisSchedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule


async def create_schedule(
    db: AsyncSession,
    data: AIScheduleCreate,
    created_by: str,
) -> AIAnalysisSchedule:
    """Create a new AI analysis schedule with validation."""
    # Validate analysis_type
    if data.analysis_type not in VALID_ANALYSIS_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid analysis_type '{data.analysis_type}'. Must be one of: {', '.join(sorted(VALID_ANALYSIS_TYPES))}",
        )

    # Validate frequency
    if data.frequency not in VALID_FREQUENCIES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid frequency '{data.frequency}'. Must be one of: {', '.join(sorted(VALID_FREQUENCIES))}",
        )

    # Require day_of_week for weekly/biweekly
    if data.frequency in ("weekly", "biweekly") and data.day_of_week is None:
        raise HTTPException(
            status_code=422,
            detail="day_of_week is required for weekly and biweekly frequencies",
        )

    schedule = AIAnalysisSchedule(
        name=data.name,
        analysis_type=data.analysis_type,
        general_type=data.general_type,
        scope_type=data.scope_type,
        scope_id=data.scope_id,
        repo_ids=data.repo_ids,
        time_range_days=data.time_range_days,
        frequency=data.frequency,
        day_of_week=data.day_of_week,
        hour=data.hour,
        minute=data.minute,
        created_by=created_by,
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)

    logger.info(
        "Created AI analysis schedule",
        schedule_id=schedule.id,
        name=schedule.name,
        analysis_type=schedule.analysis_type,
        frequency=schedule.frequency,
        created_by=created_by,
        event_type="ai.schedule",
    )
    return schedule


async def update_schedule(
    db: AsyncSession,
    schedule_id: int,
    data: AIScheduleUpdate,
) -> AIAnalysisSchedule:
    """Update an existing schedule. Only non-None fields are applied."""
    schedule = await get_schedule(db, schedule_id)

    update_data = data.model_dump(exclude_unset=True)

    # Validate before mutating ORM state
    effective_frequency = update_data.get("frequency", schedule.frequency)
    if effective_frequency not in VALID_FREQUENCIES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid frequency '{effective_frequency}'. Must be one of: {', '.join(sorted(VALID_FREQUENCIES))}",
        )
    effective_day = update_data.get("day_of_week", schedule.day_of_week)
    if effective_frequency in ("weekly", "biweekly") and effective_day is None:
        raise HTTPException(
            status_code=422,
            detail="day_of_week is required for weekly and biweekly frequencies",
        )

    for field, value in update_data.items():
        setattr(schedule, field, value)

    schedule.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(schedule)

    logger.info(
        "Updated AI analysis schedule",
        schedule_id=schedule.id,
        updated_fields=list(update_data.keys()),
        event_type="ai.schedule",
    )
    return schedule


async def delete_schedule(db: AsyncSession, schedule_id: int) -> None:
    """Delete a schedule by ID."""
    schedule = await get_schedule(db, schedule_id)
    await db.delete(schedule)
    await db.commit()

    logger.info(
        "Deleted AI analysis schedule",
        schedule_id=schedule_id,
        name=schedule.name,
        event_type="ai.schedule",
    )


async def run_scheduled_analysis(db: AsyncSession, schedule: AIAnalysisSchedule):
    """Execute the analysis defined by a schedule and update its run status."""
    now = datetime.now(timezone.utc)
    date_to = now
    date_from = now - timedelta(days=schedule.time_range_days)

    logger.info(
        "Running scheduled AI analysis",
        schedule_id=schedule.id,
        name=schedule.name,
        analysis_type=schedule.analysis_type,
        event_type="ai.schedule",
    )

    try:
        if schedule.analysis_type in ("communication", "conflict", "sentiment"):
            result = await run_analysis(
                db=db,
                analysis_type=schedule.general_type or schedule.analysis_type,
                scope_type=schedule.scope_type,
                scope_id=schedule.scope_id,
                date_from=date_from,
                date_to=date_to,
                repo_ids=schedule.repo_ids,
                triggered_by="scheduled",
            )
        elif schedule.analysis_type == "one_on_one_prep":
            result = await run_one_on_one_prep(
                db=db,
                developer_id=int(schedule.scope_id),
                date_from=date_from,
                date_to=date_to,
                repo_ids=schedule.repo_ids,
            )
        elif schedule.analysis_type == "team_health":
            result = await run_team_health(
                db=db,
                team=schedule.scope_id if schedule.scope_id != "all" else None,
                date_from=date_from,
                date_to=date_to,
                repo_ids=schedule.repo_ids,
            )
        else:
            raise ValueError(f"Unknown analysis_type: {schedule.analysis_type}")

        schedule.last_run_at = now
        schedule.last_run_analysis_id = result.id
        schedule.last_run_status = "success"
        await db.commit()

        logger.info(
            "Scheduled AI analysis completed",
            schedule_id=schedule.id,
            analysis_id=result.id,
            event_type="ai.schedule",
        )
        return result

    except AIFeatureDisabledError:
        schedule.last_run_at = now
        schedule.last_run_status = "feature_disabled"
        await db.commit()
        logger.warning(
            "Scheduled AI analysis skipped — feature disabled",
            schedule_id=schedule.id,
            event_type="ai.schedule",
        )
        raise

    except AIBudgetExceededError:
        schedule.last_run_at = now
        schedule.last_run_status = "budget_exceeded"
        await db.commit()
        logger.warning(
            "Scheduled AI analysis skipped — budget exceeded",
            schedule_id=schedule.id,
            event_type="ai.schedule",
        )
        raise

    except Exception as e:
        schedule.last_run_at = now
        schedule.last_run_status = "failed"
        await db.commit()
        logger.error(
            "Scheduled AI analysis failed",
            schedule_id=schedule.id,
            error=str(e),
            event_type="ai.schedule",
        )
        raise


def compute_next_run_description(schedule: AIAnalysisSchedule) -> str:
    """Return a human-readable description of the schedule frequency."""
    h = schedule.hour
    m = schedule.minute
    period = "AM" if h < 12 else "PM"
    display_hour = h % 12
    if display_hour == 0:
        display_hour = 12
    time_str = f"{display_hour}:{m:02d} {period}"

    if schedule.frequency == "daily":
        return f"Daily at {time_str}"
    elif schedule.frequency == "weekly":
        day = DAY_NAMES[schedule.day_of_week] if schedule.day_of_week is not None else "?"
        return f"Weekly on {day} at {time_str}"
    elif schedule.frequency == "biweekly":
        day = DAY_NAMES[schedule.day_of_week] if schedule.day_of_week is not None else "?"
        return f"Every 2 weeks on {day} at {time_str}"
    elif schedule.frequency == "monthly":
        return f"Monthly on the 1st at {time_str}"
    else:
        return f"{schedule.frequency} at {time_str}"
