from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import DeveloperGoal, Issue, PRReview, PullRequest
from app.schemas.schemas import (
    GoalCreate,
    GoalProgressPoint,
    GoalProgressResponse,
    GoalUpdate,
)


async def _get_metric_value(
    db: AsyncSession, developer_id: int, metric_key: str,
    date_from: datetime, date_to: datetime,
) -> float:
    """Compute a single metric value for a developer in a date range."""

    if metric_key == "prs_merged":
        return await db.scalar(
            select(func.count()).where(
                PullRequest.author_id == developer_id,
                PullRequest.is_merged.is_(True),
                PullRequest.merged_at >= date_from,
                PullRequest.merged_at <= date_to,
            )
        ) or 0

    if metric_key == "prs_opened":
        return await db.scalar(
            select(func.count()).where(
                PullRequest.author_id == developer_id,
                PullRequest.created_at >= date_from,
                PullRequest.created_at <= date_to,
            )
        ) or 0

    if metric_key == "time_to_merge_h":
        val = await db.scalar(
            select(func.avg(PullRequest.time_to_merge_s)).where(
                PullRequest.author_id == developer_id,
                PullRequest.is_merged.is_(True),
                PullRequest.time_to_merge_s.isnot(None),
                PullRequest.merged_at >= date_from,
                PullRequest.merged_at <= date_to,
            )
        )
        return val / 3600 if val else 0.0

    if metric_key == "time_to_first_review_h":
        val = await db.scalar(
            select(func.avg(PullRequest.time_to_first_review_s)).where(
                PullRequest.author_id == developer_id,
                PullRequest.time_to_first_review_s.isnot(None),
                PullRequest.created_at >= date_from,
                PullRequest.created_at <= date_to,
            )
        )
        return val / 3600 if val else 0.0

    if metric_key == "reviews_given":
        return await db.scalar(
            select(func.count()).where(
                PRReview.reviewer_id == developer_id,
                PRReview.submitted_at >= date_from,
                PRReview.submitted_at <= date_to,
            )
        ) or 0

    if metric_key == "review_quality_score":

        rows = (
            await db.execute(
                select(PRReview.quality_tier, func.count()).where(
                    PRReview.reviewer_id == developer_id,
                    PRReview.submitted_at >= date_from,
                    PRReview.submitted_at <= date_to,
                ).group_by(PRReview.quality_tier)
            )
        ).all()
        tier_counts = {tier: cnt for tier, cnt in rows}
        total = sum(tier_counts.values())
        if total == 0:
            return 0.0
        raw = (
            tier_counts.get("rubber_stamp", 0) * 0
            + tier_counts.get("minimal", 0) * 1
            + tier_counts.get("standard", 0) * 3
            + tier_counts.get("thorough", 0) * 5
        ) / total
        return round(raw * 2, 2)

    if metric_key == "issues_closed":
        return await db.scalar(
            select(func.count()).where(
                Issue.assignee_id == developer_id,
                Issue.closed_at >= date_from,
                Issue.closed_at <= date_to,
            )
        ) or 0

    if metric_key == "avg_pr_additions":

        prs_merged = await db.scalar(
            select(func.count()).where(
                PullRequest.author_id == developer_id,
                PullRequest.is_merged.is_(True),
                PullRequest.merged_at >= date_from,
                PullRequest.merged_at <= date_to,
            )
        ) or 0
        if prs_merged == 0:
            return 0.0
        total_add = await db.scalar(
            select(func.coalesce(func.sum(PullRequest.additions), 0)).where(
                PullRequest.author_id == developer_id,
                PullRequest.is_merged.is_(True),
                PullRequest.merged_at >= date_from,
                PullRequest.merged_at <= date_to,
            )
        ) or 0
        return total_add / prs_merged

    return 0.0


async def create_goal(
    db: AsyncSession, goal_data: GoalCreate
) -> DeveloperGoal:
    now = datetime.now(timezone.utc)
    date_from = now - timedelta(days=30)

    # Compute baseline from current period
    baseline = await _get_metric_value(
        db, goal_data.developer_id, goal_data.metric_key, date_from, now
    )

    goal = DeveloperGoal(
        developer_id=goal_data.developer_id,
        title=goal_data.title,
        description=goal_data.description,
        metric_key=goal_data.metric_key,
        target_value=goal_data.target_value,
        target_direction=goal_data.target_direction,
        baseline_value=baseline,
        target_date=goal_data.target_date,
    )
    db.add(goal)
    await db.commit()
    await db.refresh(goal)
    return goal


async def list_goals(
    db: AsyncSession, developer_id: int
) -> list[DeveloperGoal]:
    result = await db.execute(
        select(DeveloperGoal)
        .where(DeveloperGoal.developer_id == developer_id)
        .order_by(DeveloperGoal.created_at.desc())
    )
    return list(result.scalars().all())


async def update_goal(
    db: AsyncSession, goal_id: int, update: GoalUpdate
) -> DeveloperGoal | None:
    goal = await db.get(DeveloperGoal, goal_id)
    if not goal:
        return None

    if update.status is not None:
        goal.status = update.status
        if update.status == "achieved" and not goal.achieved_at:
            goal.achieved_at = datetime.now(timezone.utc)
    if update.notes is not None:
        goal.notes = update.notes

    await db.commit()
    await db.refresh(goal)
    return goal


async def get_goal_progress(
    db: AsyncSession, goal_id: int
) -> GoalProgressResponse | None:
    goal = await db.get(DeveloperGoal, goal_id)
    if not goal:
        return None

    now = datetime.now(timezone.utc)

    # Build history: last 8 weekly periods
    history: list[GoalProgressPoint] = []
    for i in range(7, -1, -1):
        period_end = now - timedelta(weeks=i)
        period_start = period_end - timedelta(weeks=1)
        value = await _get_metric_value(
            db, goal.developer_id, goal.metric_key, period_start, period_end
        )
        history.append(GoalProgressPoint(period_end=period_end, value=round(value, 2)))

    current_value = history[-1].value if history else None

    # Auto-achievement: if metric crosses target for last 2 periods
    if goal.status == "active" and len(history) >= 2 and current_value is not None:
        prev_value = history[-2].value
        achieved = False
        if goal.target_direction == "above":
            achieved = current_value >= goal.target_value and prev_value >= goal.target_value
        elif goal.target_direction == "below":
            achieved = current_value <= goal.target_value and prev_value <= goal.target_value
        if achieved:
            goal.status = "achieved"
            goal.achieved_at = now
            await db.commit()
            await db.refresh(goal)

    return GoalProgressResponse(
        goal_id=goal.id,
        title=goal.title,
        target_value=goal.target_value,
        target_direction=goal.target_direction,
        baseline_value=goal.baseline_value,
        current_value=current_value,
        status=goal.status,
        history=history,
    )
