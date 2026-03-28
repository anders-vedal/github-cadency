import statistics
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Developer, Issue, PRReview, PullRequest, Repository
from app.schemas.schemas import (
    BenchmarkMetric,
    BenchmarksResponse,
    DeveloperStatsResponse,
    DeveloperStatsWithPercentilesResponse,
    DeveloperTrendsResponse,
    DeveloperWorkload,
    PercentilePlacement,
    RepoStatsResponse,
    ReviewBreakdown,
    ReviewQualityBreakdown,
    TeamStatsResponse,
    TopContributor,
    TrendDirection,
    TrendPeriod,
    WorkloadAlert,
    WorkloadResponse,
)


def _default_range(
    date_from: datetime | None, date_to: datetime | None
) -> tuple[datetime, datetime]:
    if not date_to:
        date_to = datetime.now(timezone.utc)
    if not date_from:
        date_from = date_to - timedelta(days=30)
    return date_from, date_to


async def get_developer_stats(
    db: AsyncSession,
    developer_id: int,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> DeveloperStatsResponse:
    date_from, date_to = _default_range(date_from, date_to)

    # PRs opened
    prs_opened = await db.scalar(
        select(func.count()).where(
            PullRequest.author_id == developer_id,
            PullRequest.created_at >= date_from,
            PullRequest.created_at <= date_to,
        )
    ) or 0

    # PRs merged
    prs_merged = await db.scalar(
        select(func.count()).where(
            PullRequest.author_id == developer_id,
            PullRequest.is_merged.is_(True),
            PullRequest.merged_at >= date_from,
            PullRequest.merged_at <= date_to,
        )
    ) or 0

    # PRs closed without merge
    prs_closed_no_merge = await db.scalar(
        select(func.count()).where(
            PullRequest.author_id == developer_id,
            PullRequest.state == "closed",
            PullRequest.is_merged.is_(False),
            PullRequest.closed_at >= date_from,
            PullRequest.closed_at <= date_to,
        )
    ) or 0

    # PRs currently open
    prs_open = await db.scalar(
        select(func.count()).where(
            PullRequest.author_id == developer_id,
            PullRequest.state == "open",
        )
    ) or 0

    # Code volume (from PRs in range)
    code_stats = (
        await db.execute(
            select(
                func.coalesce(func.sum(PullRequest.additions), 0),
                func.coalesce(func.sum(PullRequest.deletions), 0),
                func.coalesce(func.sum(PullRequest.changed_files), 0),
            ).where(
                PullRequest.author_id == developer_id,
                PullRequest.created_at >= date_from,
                PullRequest.created_at <= date_to,
            )
        )
    ).one()

    # Reviews given breakdown
    reviews_given_rows = (
        await db.execute(
            select(PRReview.state, func.count()).where(
                PRReview.reviewer_id == developer_id,
                PRReview.submitted_at >= date_from,
                PRReview.submitted_at <= date_to,
            ).group_by(PRReview.state)
        )
    ).all()
    reviews_given = ReviewBreakdown()
    for state, count in reviews_given_rows:
        if state == "APPROVED":
            reviews_given.approved = count
        elif state == "CHANGES_REQUESTED":
            reviews_given.changes_requested = count
        elif state == "COMMENTED":
            reviews_given.commented = count

    # Review quality breakdown
    quality_rows = (
        await db.execute(
            select(PRReview.quality_tier, func.count()).where(
                PRReview.reviewer_id == developer_id,
                PRReview.submitted_at >= date_from,
                PRReview.submitted_at <= date_to,
            ).group_by(PRReview.quality_tier)
        )
    ).all()
    quality_breakdown = ReviewQualityBreakdown()
    for tier, count in quality_rows:
        if tier == "rubber_stamp":
            quality_breakdown.rubber_stamp = count
        elif tier == "minimal":
            quality_breakdown.minimal = count
        elif tier == "standard":
            quality_breakdown.standard = count
        elif tier == "thorough":
            quality_breakdown.thorough = count

    # Review quality score: (rubber_stamp*0 + minimal*1 + standard*3 + thorough*5) / total, normalized 0-10
    total_quality_reviews = (
        quality_breakdown.rubber_stamp
        + quality_breakdown.minimal
        + quality_breakdown.standard
        + quality_breakdown.thorough
    )
    if total_quality_reviews > 0:
        raw_score = (
            quality_breakdown.rubber_stamp * 0
            + quality_breakdown.minimal * 1
            + quality_breakdown.standard * 3
            + quality_breakdown.thorough * 5
        ) / total_quality_reviews
        # Normalize to 0-10 scale (max raw score is 5)
        review_quality_score = round(raw_score * 2, 2)
    else:
        review_quality_score = None

    # Reviews received
    reviews_received = await db.scalar(
        select(func.count())
        .select_from(PRReview)
        .join(PullRequest, PRReview.pr_id == PullRequest.id)
        .where(
            PullRequest.author_id == developer_id,
            PRReview.submitted_at >= date_from,
            PRReview.submitted_at <= date_to,
        )
    ) or 0

    # Avg time to first review
    avg_ttfr = await db.scalar(
        select(func.avg(PullRequest.time_to_first_review_s)).where(
            PullRequest.author_id == developer_id,
            PullRequest.time_to_first_review_s.isnot(None),
            PullRequest.created_at >= date_from,
            PullRequest.created_at <= date_to,
        )
    )

    # Avg time to merge
    avg_ttm = await db.scalar(
        select(func.avg(PullRequest.time_to_merge_s)).where(
            PullRequest.author_id == developer_id,
            PullRequest.is_merged.is_(True),
            PullRequest.time_to_merge_s.isnot(None),
            PullRequest.merged_at >= date_from,
            PullRequest.merged_at <= date_to,
        )
    )

    # Issues assigned
    issues_assigned = await db.scalar(
        select(func.count()).where(
            Issue.assignee_id == developer_id,
            Issue.created_at >= date_from,
            Issue.created_at <= date_to,
        )
    ) or 0

    # Issues closed
    issues_closed = await db.scalar(
        select(func.count()).where(
            Issue.assignee_id == developer_id,
            Issue.closed_at >= date_from,
            Issue.closed_at <= date_to,
        )
    ) or 0

    # Avg time to close issue
    avg_ttc = await db.scalar(
        select(func.avg(Issue.time_to_close_s)).where(
            Issue.assignee_id == developer_id,
            Issue.time_to_close_s.isnot(None),
            Issue.closed_at >= date_from,
            Issue.closed_at <= date_to,
        )
    )

    return DeveloperStatsResponse(
        prs_opened=prs_opened,
        prs_merged=prs_merged,
        prs_closed_without_merge=prs_closed_no_merge,
        prs_open=prs_open,
        total_additions=code_stats[0],
        total_deletions=code_stats[1],
        total_changed_files=code_stats[2],
        reviews_given=reviews_given,
        reviews_received=reviews_received,
        review_quality_breakdown=quality_breakdown,
        review_quality_score=review_quality_score,
        avg_time_to_first_review_hours=avg_ttfr / 3600 if avg_ttfr else None,
        avg_time_to_merge_hours=avg_ttm / 3600 if avg_ttm else None,
        issues_assigned=issues_assigned,
        issues_closed=issues_closed,
        avg_time_to_close_issue_hours=avg_ttc / 3600 if avg_ttc else None,
    )


async def get_team_stats(
    db: AsyncSession,
    team: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> TeamStatsResponse:
    date_from, date_to = _default_range(date_from, date_to)

    # Get team developer IDs
    dev_query = select(Developer.id).where(Developer.is_active.is_(True))
    if team:
        dev_query = dev_query.where(Developer.team == team)
    dev_result = await db.execute(dev_query)
    dev_ids = [row[0] for row in dev_result.all()]
    developer_count = len(dev_ids)

    if not dev_ids:
        return TeamStatsResponse(developer_count=0)

    # Total PRs
    total_prs = await db.scalar(
        select(func.count()).where(
            PullRequest.author_id.in_(dev_ids),
            PullRequest.created_at >= date_from,
            PullRequest.created_at <= date_to,
        )
    ) or 0

    # Total merged
    total_merged = await db.scalar(
        select(func.count()).where(
            PullRequest.author_id.in_(dev_ids),
            PullRequest.is_merged.is_(True),
            PullRequest.merged_at >= date_from,
            PullRequest.merged_at <= date_to,
        )
    ) or 0

    merge_rate = (total_merged / total_prs * 100) if total_prs > 0 else None

    # Avg time to first review
    avg_ttfr = await db.scalar(
        select(func.avg(PullRequest.time_to_first_review_s)).where(
            PullRequest.author_id.in_(dev_ids),
            PullRequest.time_to_first_review_s.isnot(None),
            PullRequest.created_at >= date_from,
            PullRequest.created_at <= date_to,
        )
    )

    # Avg time to merge
    avg_ttm = await db.scalar(
        select(func.avg(PullRequest.time_to_merge_s)).where(
            PullRequest.author_id.in_(dev_ids),
            PullRequest.is_merged.is_(True),
            PullRequest.time_to_merge_s.isnot(None),
            PullRequest.merged_at >= date_from,
            PullRequest.merged_at <= date_to,
        )
    )

    # Total reviews
    total_reviews = await db.scalar(
        select(func.count()).where(
            PRReview.reviewer_id.in_(dev_ids),
            PRReview.submitted_at >= date_from,
            PRReview.submitted_at <= date_to,
        )
    ) or 0

    # Total issues closed
    total_issues_closed = await db.scalar(
        select(func.count()).where(
            Issue.assignee_id.in_(dev_ids),
            Issue.closed_at >= date_from,
            Issue.closed_at <= date_to,
        )
    ) or 0

    return TeamStatsResponse(
        developer_count=developer_count,
        total_prs=total_prs,
        total_merged=total_merged,
        merge_rate=merge_rate,
        avg_time_to_first_review_hours=avg_ttfr / 3600 if avg_ttfr else None,
        avg_time_to_merge_hours=avg_ttm / 3600 if avg_ttm else None,
        total_reviews=total_reviews,
        total_issues_closed=total_issues_closed,
    )


async def get_repo_stats(
    db: AsyncSession,
    repo_id: int,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> RepoStatsResponse:
    date_from, date_to = _default_range(date_from, date_to)

    total_prs = await db.scalar(
        select(func.count()).where(
            PullRequest.repo_id == repo_id,
            PullRequest.created_at >= date_from,
            PullRequest.created_at <= date_to,
        )
    ) or 0

    total_merged = await db.scalar(
        select(func.count()).where(
            PullRequest.repo_id == repo_id,
            PullRequest.is_merged.is_(True),
            PullRequest.merged_at >= date_from,
            PullRequest.merged_at <= date_to,
        )
    ) or 0

    total_issues = await db.scalar(
        select(func.count()).where(
            Issue.repo_id == repo_id,
            Issue.created_at >= date_from,
            Issue.created_at <= date_to,
        )
    ) or 0

    total_issues_closed = await db.scalar(
        select(func.count()).where(
            Issue.repo_id == repo_id,
            Issue.closed_at >= date_from,
            Issue.closed_at <= date_to,
        )
    ) or 0

    total_reviews = await db.scalar(
        select(func.count())
        .select_from(PRReview)
        .join(PullRequest, PRReview.pr_id == PullRequest.id)
        .where(
            PullRequest.repo_id == repo_id,
            PRReview.submitted_at >= date_from,
            PRReview.submitted_at <= date_to,
        )
    ) or 0

    avg_ttm = await db.scalar(
        select(func.avg(PullRequest.time_to_merge_s)).where(
            PullRequest.repo_id == repo_id,
            PullRequest.is_merged.is_(True),
            PullRequest.time_to_merge_s.isnot(None),
            PullRequest.merged_at >= date_from,
            PullRequest.merged_at <= date_to,
        )
    )

    # Top contributors by PR count
    top_rows = (
        await db.execute(
            select(
                Developer.id,
                Developer.github_username,
                Developer.display_name,
                func.count().label("pr_count"),
            )
            .join(PullRequest, PullRequest.author_id == Developer.id)
            .where(
                PullRequest.repo_id == repo_id,
                PullRequest.created_at >= date_from,
                PullRequest.created_at <= date_to,
            )
            .group_by(Developer.id)
            .order_by(func.count().desc())
            .limit(10)
        )
    ).all()

    top_contributors = [
        TopContributor(
            developer_id=row.id,
            github_username=row.github_username,
            display_name=row.display_name,
            pr_count=row.pr_count,
        )
        for row in top_rows
    ]

    return RepoStatsResponse(
        total_prs=total_prs,
        total_merged=total_merged,
        total_issues=total_issues,
        total_issues_closed=total_issues_closed,
        total_reviews=total_reviews,
        avg_time_to_merge_hours=avg_ttm / 3600 if avg_ttm else None,
        top_contributors=top_contributors,
    )


# --- M2: Team Benchmarks ---


async def _compute_per_developer_metrics(
    db: AsyncSession,
    dev_ids: list[int],
    date_from: datetime,
    date_to: datetime,
) -> dict[str, list[float]]:
    """Compute benchmark metrics per developer, returning lists of values for percentile calculation."""
    metrics: dict[str, list[float]] = {
        "time_to_merge_h": [],
        "time_to_first_review_h": [],
        "prs_merged": [],
        "review_turnaround_h": [],
        "reviews_given": [],
        "additions_per_pr": [],
    }

    for dev_id in dev_ids:
        # PRs merged
        prs_merged = await db.scalar(
            select(func.count()).where(
                PullRequest.author_id == dev_id,
                PullRequest.is_merged.is_(True),
                PullRequest.merged_at >= date_from,
                PullRequest.merged_at <= date_to,
            )
        ) or 0
        metrics["prs_merged"].append(float(prs_merged))

        # Avg time to merge (hours)
        avg_ttm = await db.scalar(
            select(func.avg(PullRequest.time_to_merge_s)).where(
                PullRequest.author_id == dev_id,
                PullRequest.is_merged.is_(True),
                PullRequest.time_to_merge_s.isnot(None),
                PullRequest.merged_at >= date_from,
                PullRequest.merged_at <= date_to,
            )
        )
        metrics["time_to_merge_h"].append(avg_ttm / 3600 if avg_ttm else 0.0)

        # Avg time to first review (hours) — for PRs authored by this dev
        avg_ttfr = await db.scalar(
            select(func.avg(PullRequest.time_to_first_review_s)).where(
                PullRequest.author_id == dev_id,
                PullRequest.time_to_first_review_s.isnot(None),
                PullRequest.created_at >= date_from,
                PullRequest.created_at <= date_to,
            )
        )
        metrics["time_to_first_review_h"].append(avg_ttfr / 3600 if avg_ttfr else 0.0)

        # Reviews given count
        reviews_given = await db.scalar(
            select(func.count()).where(
                PRReview.reviewer_id == dev_id,
                PRReview.submitted_at >= date_from,
                PRReview.submitted_at <= date_to,
            )
        ) or 0
        metrics["reviews_given"].append(float(reviews_given))

        # Review turnaround — avg time_to_first_review_s for PRs this dev reviewed
        avg_turnaround = await db.scalar(
            select(func.avg(PullRequest.time_to_first_review_s))
            .select_from(PRReview)
            .join(PullRequest, PRReview.pr_id == PullRequest.id)
            .where(
                PRReview.reviewer_id == dev_id,
                PullRequest.time_to_first_review_s.isnot(None),
                PRReview.submitted_at >= date_from,
                PRReview.submitted_at <= date_to,
            )
        )
        metrics["review_turnaround_h"].append(
            avg_turnaround / 3600 if avg_turnaround else 0.0
        )

        # Additions per PR
        total_additions = await db.scalar(
            select(func.coalesce(func.sum(PullRequest.additions), 0)).where(
                PullRequest.author_id == dev_id,
                PullRequest.is_merged.is_(True),
                PullRequest.merged_at >= date_from,
                PullRequest.merged_at <= date_to,
            )
        ) or 0
        metrics["additions_per_pr"].append(
            total_additions / prs_merged if prs_merged > 0 else 0.0
        )

    return metrics


def _percentiles(values: list[float]) -> BenchmarkMetric:
    """Compute p25, p50, p75 using linear interpolation."""
    if len(values) < 2:
        v = values[0] if values else 0.0
        return BenchmarkMetric(p25=v, p50=v, p75=v)
    quantiles = statistics.quantiles(values, n=4, method="inclusive")
    return BenchmarkMetric(
        p25=round(quantiles[0], 2),
        p50=round(quantiles[1], 2),
        p75=round(quantiles[2], 2),
    )


# Metrics where lower values are better (latency metrics)
_LOWER_IS_BETTER = {"time_to_merge_h", "time_to_first_review_h", "review_turnaround_h"}


def _percentile_band(
    value: float, metric: BenchmarkMetric, metric_name: str = ""
) -> str:
    """Assign percentile band. For lower-is-better metrics, invert so above_p75 = best."""
    if metric_name in _LOWER_IS_BETTER:
        # Invert: low value = good = above_p75
        if value > metric.p75:
            return "below_p25"
        elif value > metric.p50:
            return "p25_to_p50"
        elif value > metric.p25:
            return "p50_to_p75"
        else:
            return "above_p75"
    if value < metric.p25:
        return "below_p25"
    elif value < metric.p50:
        return "p25_to_p50"
    elif value < metric.p75:
        return "p50_to_p75"
    else:
        return "above_p75"


async def get_benchmarks(
    db: AsyncSession,
    team: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> BenchmarksResponse:
    date_from, date_to = _default_range(date_from, date_to)

    dev_query = select(Developer.id).where(Developer.is_active.is_(True))
    if team:
        dev_query = dev_query.where(Developer.team == team)
    dev_result = await db.execute(dev_query)
    dev_ids = [row[0] for row in dev_result.all()]

    if not dev_ids:
        return BenchmarksResponse(
            period_start=date_from,
            period_end=date_to,
            sample_size=0,
            team=team,
            metrics={},
        )

    per_dev = await _compute_per_developer_metrics(db, dev_ids, date_from, date_to)

    return BenchmarksResponse(
        period_start=date_from,
        period_end=date_to,
        sample_size=len(dev_ids),
        team=team,
        metrics={name: _percentiles(values) for name, values in per_dev.items()},
    )


async def get_developer_stats_with_percentiles(
    db: AsyncSession,
    developer_id: int,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> DeveloperStatsWithPercentilesResponse:
    date_from, date_to = _default_range(date_from, date_to)
    base = await get_developer_stats(db, developer_id, date_from, date_to)

    # Get the developer's team for team-relative benchmarks
    dev = await db.get(Developer, developer_id)
    dev_query = select(Developer.id).where(Developer.is_active.is_(True))
    if dev and dev.team:
        dev_query = dev_query.where(Developer.team == dev.team)
    dev_result = await db.execute(dev_query)
    dev_ids = [row[0] for row in dev_result.all()]

    if len(dev_ids) < 2:
        return DeveloperStatsWithPercentilesResponse(**base.model_dump())

    per_dev = await _compute_per_developer_metrics(db, dev_ids, date_from, date_to)
    benchmarks = {name: _percentiles(values) for name, values in per_dev.items()}

    # Map developer stats fields to benchmark metric names
    dev_values = {
        "time_to_merge_h": base.avg_time_to_merge_hours or 0.0,
        "time_to_first_review_h": base.avg_time_to_first_review_hours or 0.0,
        "prs_merged": float(base.prs_merged),
        "reviews_given": float(
            base.reviews_given.approved
            + base.reviews_given.changes_requested
            + base.reviews_given.commented
        ),
        "additions_per_pr": (
            base.total_additions / base.prs_merged
            if base.prs_merged > 0
            else 0.0
        ),
    }

    # Compute review turnaround for this specific developer
    avg_turnaround = await db.scalar(
        select(func.avg(PullRequest.time_to_first_review_s))
        .select_from(PRReview)
        .join(PullRequest, PRReview.pr_id == PullRequest.id)
        .where(
            PRReview.reviewer_id == developer_id,
            PullRequest.time_to_first_review_s.isnot(None),
            PRReview.submitted_at >= date_from,
            PRReview.submitted_at <= date_to,
        )
    )
    dev_values["review_turnaround_h"] = avg_turnaround / 3600 if avg_turnaround else 0.0

    percentiles = {}
    for metric_name, bm in benchmarks.items():
        val = dev_values.get(metric_name, 0.0)
        percentiles[metric_name] = PercentilePlacement(
            value=round(val, 2),
            percentile_band=_percentile_band(val, bm, metric_name),
            team_median=bm.p50,
        )

    return DeveloperStatsWithPercentilesResponse(
        **base.model_dump(), percentiles=percentiles
    )


# --- M3: Trend Lines ---


# Polarity: True = higher is better, False = lower is better, None = neutral
_METRIC_POLARITY: dict[str, bool | None] = {
    "prs_merged": True,
    "avg_time_to_merge_h": False,
    "reviews_given": True,
    "additions": None,
    "deletions": None,
    "issues_closed": True,
}


def _linear_regression(values: list[float]) -> tuple[float, float]:
    """Simple OLS: y = slope*x + intercept. Returns (slope, intercept)."""
    n = len(values)
    if n < 2:
        return 0.0, values[0] if values else 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    if denominator == 0:
        return 0.0, y_mean
    slope = numerator / denominator
    intercept = y_mean - slope * x_mean
    return slope, intercept


def _trend_direction(
    slope: float, n_periods: int, first_val: float, polarity: bool | None
) -> TrendDirection:
    """Classify trend direction using regression slope, respecting metric polarity."""
    # Total change predicted by the regression over all periods
    predicted_change = slope * (n_periods - 1)
    baseline = max(abs(first_val), 1.0)
    change_pct = round(predicted_change / baseline * 100, 1)

    if abs(change_pct) < 5.0:
        direction = "stable"
    elif polarity is None:
        direction = "stable"
    elif polarity:
        direction = "improving" if slope > 0 else "worsening"
    else:
        direction = "improving" if slope < 0 else "worsening"

    return TrendDirection(direction=direction, change_pct=change_pct)


async def get_developer_trends(
    db: AsyncSession,
    developer_id: int,
    periods: int = 8,
    period_type: str = "week",
    sprint_length_days: int = 14,
) -> DeveloperTrendsResponse:
    if period_type == "month":
        period_days = 30
    elif period_type == "sprint":
        period_days = sprint_length_days
    else:
        period_days = 7

    now = datetime.now(timezone.utc)
    period_list: list[TrendPeriod] = []

    for i in range(periods - 1, -1, -1):
        end = now - timedelta(days=i * period_days)
        start = end - timedelta(days=period_days)

        prs_merged = await db.scalar(
            select(func.count()).where(
                PullRequest.author_id == developer_id,
                PullRequest.is_merged.is_(True),
                PullRequest.merged_at >= start,
                PullRequest.merged_at < end,
            )
        ) or 0

        avg_ttm = await db.scalar(
            select(func.avg(PullRequest.time_to_merge_s)).where(
                PullRequest.author_id == developer_id,
                PullRequest.is_merged.is_(True),
                PullRequest.time_to_merge_s.isnot(None),
                PullRequest.merged_at >= start,
                PullRequest.merged_at < end,
            )
        )

        reviews_given = await db.scalar(
            select(func.count()).where(
                PRReview.reviewer_id == developer_id,
                PRReview.submitted_at >= start,
                PRReview.submitted_at < end,
            )
        ) or 0

        code_stats = (
            await db.execute(
                select(
                    func.coalesce(func.sum(PullRequest.additions), 0),
                    func.coalesce(func.sum(PullRequest.deletions), 0),
                ).where(
                    PullRequest.author_id == developer_id,
                    PullRequest.created_at >= start,
                    PullRequest.created_at < end,
                )
            )
        ).one()

        issues_closed = await db.scalar(
            select(func.count()).where(
                Issue.assignee_id == developer_id,
                Issue.closed_at >= start,
                Issue.closed_at < end,
            )
        ) or 0

        period_list.append(
            TrendPeriod(
                start=start,
                end=end,
                prs_merged=prs_merged,
                avg_time_to_merge_h=round(avg_ttm / 3600, 2) if avg_ttm else None,
                reviews_given=reviews_given,
                additions=code_stats[0],
                deletions=code_stats[1],
                issues_closed=issues_closed,
            )
        )

    # Compute trends via linear regression
    trends: dict[str, TrendDirection] = {}
    for metric_name, polarity in _METRIC_POLARITY.items():
        values = []
        for p in period_list:
            val = getattr(p, metric_name, None)
            # Skip None values for optional metrics (e.g., avg_time_to_merge_h)
            values.append(float(val) if val is not None else 0.0)
        non_zero_count = sum(1 for v in values if v != 0.0)
        if non_zero_count < 2:
            trends[metric_name] = TrendDirection(direction="stable", change_pct=0.0)
            continue
        slope, _ = _linear_regression(values)
        trends[metric_name] = _trend_direction(
            slope, len(values), values[0], polarity
        )

    return DeveloperTrendsResponse(
        developer_id=developer_id,
        period_type=period_type,
        periods=period_list,
        trends=trends,
    )


# --- M4: Workload Balance ---


async def get_workload(
    db: AsyncSession,
    team: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> WorkloadResponse:
    date_from, date_to = _default_range(date_from, date_to)

    dev_query = select(Developer).where(Developer.is_active.is_(True))
    if team:
        dev_query = dev_query.where(Developer.team == team)
    dev_result = await db.execute(dev_query)
    developers = list(dev_result.scalars().all())

    if not developers:
        return WorkloadResponse(developers=[], alerts=[])

    workloads: list[DeveloperWorkload] = []
    reviews_given_values: list[tuple[int, int]] = []  # (dev_id, count)
    open_issues_per_dev: list[tuple[int, int]] = []  # (dev_id, count)

    for dev in developers:
        # Open PRs authored
        open_authored = await db.scalar(
            select(func.count()).where(
                PullRequest.author_id == dev.id,
                PullRequest.state == "open",
            )
        ) or 0

        # Open PRs reviewing (has a review on an open PR)
        open_reviewing = await db.scalar(
            select(func.count(func.distinct(PullRequest.id)))
            .select_from(PRReview)
            .join(PullRequest, PRReview.pr_id == PullRequest.id)
            .where(
                PRReview.reviewer_id == dev.id,
                PullRequest.state == "open",
            )
        ) or 0

        # Open issues assigned
        open_issues = await db.scalar(
            select(func.count()).where(
                Issue.assignee_id == dev.id,
                Issue.state == "open",
            )
        ) or 0
        open_issues_per_dev.append((dev.id, open_issues))

        # Reviews given this period
        reviews_given = await db.scalar(
            select(func.count()).where(
                PRReview.reviewer_id == dev.id,
                PRReview.submitted_at >= date_from,
                PRReview.submitted_at <= date_to,
            )
        ) or 0
        reviews_given_values.append((dev.id, reviews_given))

        # Reviews received this period
        reviews_received = await db.scalar(
            select(func.count())
            .select_from(PRReview)
            .join(PullRequest, PRReview.pr_id == PullRequest.id)
            .where(
                PullRequest.author_id == dev.id,
                PRReview.submitted_at >= date_from,
                PRReview.submitted_at <= date_to,
            )
        ) or 0

        # PRs waiting for review (open, authored by dev, no reviews yet)
        prs_waiting = await db.scalar(
            select(func.count()).where(
                PullRequest.author_id == dev.id,
                PullRequest.state == "open",
                PullRequest.first_review_at.is_(None),
            )
        ) or 0

        # Avg review wait — avg time_to_first_review for dev's reviewed PRs in period
        avg_wait = await db.scalar(
            select(func.avg(PullRequest.time_to_first_review_s)).where(
                PullRequest.author_id == dev.id,
                PullRequest.time_to_first_review_s.isnot(None),
                PullRequest.created_at >= date_from,
                PullRequest.created_at <= date_to,
            )
        )

        # Workload score heuristic (open items + review activity)
        total_load = open_authored + open_reviewing + open_issues + reviews_given
        if total_load == 0:
            score = "low"
        elif total_load <= 5:
            score = "balanced"
        elif total_load <= 12:
            score = "high"
        else:
            score = "overloaded"

        workloads.append(
            DeveloperWorkload(
                developer_id=dev.id,
                github_username=dev.github_username,
                display_name=dev.display_name,
                open_prs_authored=open_authored,
                open_prs_reviewing=open_reviewing,
                open_issues_assigned=open_issues,
                reviews_given_this_period=reviews_given,
                reviews_received_this_period=reviews_received,
                prs_waiting_for_review=prs_waiting,
                avg_review_wait_h=round(avg_wait / 3600, 2) if avg_wait else None,
                workload_score=score,
            )
        )

    # Generate alerts
    alerts: list[WorkloadAlert] = []

    # Review bottleneck: reviews_given > 2x team median
    review_counts = [c for _, c in reviews_given_values]
    if review_counts:
        team_median_reviews = statistics.median(review_counts)
        for dev_id, count in reviews_given_values:
            if team_median_reviews > 0 and count > 2 * team_median_reviews:
                dev = next(d for d in developers if d.id == dev_id)
                alerts.append(
                    WorkloadAlert(
                        type="review_bottleneck",
                        developer_id=dev_id,
                        message=f"{dev.display_name} gave {count} reviews "
                        f"(team median: {team_median_reviews:.0f})",
                    )
                )

    # Stale PRs: any PR waiting for first review > 48h
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(hours=48)
    stale_prs_result = await db.execute(
        select(PullRequest.number, PullRequest.title, PullRequest.author_id).where(
            PullRequest.state == "open",
            PullRequest.first_review_at.is_(None),
            PullRequest.created_at <= stale_cutoff,
        )
    )
    for row in stale_prs_result.all():
        alerts.append(
            WorkloadAlert(
                type="stale_prs",
                developer_id=row.author_id,
                message=f"PR #{row.number} ({row.title}) waiting for review > 48h",
            )
        )

    # Uneven assignment: top 20% hold > 50% of open issues
    if open_issues_per_dev:
        sorted_issues = sorted(open_issues_per_dev, key=lambda x: x[1], reverse=True)
        total_open_issues = sum(c for _, c in sorted_issues)
        if total_open_issues > 0:
            top_20_count = max(1, len(sorted_issues) // 5)
            top_20_issues = sum(c for _, c in sorted_issues[:top_20_count])
            if top_20_issues > total_open_issues * 0.5:
                top_names = []
                for dev_id, _ in sorted_issues[:top_20_count]:
                    dev = next(d for d in developers if d.id == dev_id)
                    top_names.append(dev.display_name)
                alerts.append(
                    WorkloadAlert(
                        type="uneven_assignment",
                        message=f"Top {top_20_count} dev(s) ({', '.join(top_names)}) "
                        f"hold {top_20_issues}/{total_open_issues} open issues",
                    )
                )

    # Underutilized: 0 PRs and 0 reviews in period
    for dev in developers:
        dev_prs = await db.scalar(
            select(func.count()).where(
                PullRequest.author_id == dev.id,
                PullRequest.created_at >= date_from,
                PullRequest.created_at <= date_to,
            )
        ) or 0
        dev_reviews = next(
            (c for did, c in reviews_given_values if did == dev.id), 0
        )
        if dev_prs == 0 and dev_reviews == 0:
            alerts.append(
                WorkloadAlert(
                    type="underutilized",
                    developer_id=dev.id,
                    message=f"{dev.display_name} has 0 PRs and 0 reviews in the period",
                )
            )

    return WorkloadResponse(developers=workloads, alerts=alerts)
