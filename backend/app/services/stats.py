import statistics
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Deployment, Developer, Issue, IssueComment, PRCheckRun, PRFile, PRReview, PRReviewComment, PullRequest, RepoTreeFile, Repository
from app.schemas.schemas import (
    BenchmarkMetric,
    BenchmarksResponse,
    DeveloperStatsResponse,
    DeveloperStatsWithPercentilesResponse,
    DeveloperTrendsResponse,
    DeveloperWorkload,
    IssueCreatorStats,
    IssueCreatorStatsResponse,
    IssueLinkageStats,
    IssueQualityStats,
    PercentilePlacement,
    RepoStatsResponse,
    ReviewBreakdown,
    ReviewQualityBreakdown,
    StalePR,
    StalePRsResponse,
    TeamStatsResponse,
    TopContributor,
    TrendDirection,
    TrendPeriod,
    CIStatsResponse,
    CodeChurnResponse,
    DORAMetricsResponse,
    DeploymentDetail,
    FileChurnEntry,
    FlakyCheck,
    SlowestCheck,
    StaleDirectory,
    WorkloadAlert,
    WorkloadResponse,
)


from app.services.utils import default_range as _default_range


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

    # PRs currently open (exclude drafts)
    prs_open = await db.scalar(
        select(func.count()).where(
            PullRequest.author_id == developer_id,
            PullRequest.state == "open",
            PullRequest.is_draft.isnot(True),
        )
    ) or 0

    # Draft PRs currently open
    prs_draft = await db.scalar(
        select(func.count()).where(
            PullRequest.author_id == developer_id,
            PullRequest.state == "open",
            PullRequest.is_draft.is_(True),
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

    # Comment type distribution (as reviewer)
    comment_type_rows = (
        await db.execute(
            select(PRReviewComment.comment_type, func.count())
            .join(PRReview, PRReviewComment.review_id == PRReview.id)
            .where(
                PRReview.reviewer_id == developer_id,
                PRReview.submitted_at >= date_from,
                PRReview.submitted_at <= date_to,
            )
            .group_by(PRReviewComment.comment_type)
        )
    ).all()
    comment_type_distribution = {ct: count for ct, count in comment_type_rows if ct}
    total_typed_comments = sum(comment_type_distribution.values())
    nit_ratio = (
        round(comment_type_distribution.get("nit", 0) / total_typed_comments, 4)
        if total_typed_comments > 0 else None
    )

    # Blocker catch rate: reviews with ≥1 blocker comment / total reviews given
    total_reviews_given = (
        reviews_given.approved + reviews_given.changes_requested + reviews_given.commented
    )
    if total_reviews_given > 0:
        reviews_with_blocker = await db.scalar(
            select(func.count(func.distinct(PRReviewComment.review_id)))
            .join(PRReview, PRReviewComment.review_id == PRReview.id)
            .where(
                PRReview.reviewer_id == developer_id,
                PRReview.submitted_at >= date_from,
                PRReview.submitted_at <= date_to,
                PRReviewComment.comment_type == "blocker",
            )
        ) or 0
        blocker_catch_rate = round(reviews_with_blocker / total_reviews_given, 4)
    else:
        blocker_catch_rate = None

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

    # Avg time to approve (creation → last approval)
    avg_tta = await db.scalar(
        select(func.avg(PullRequest.time_to_approve_s)).where(
            PullRequest.author_id == developer_id,
            PullRequest.time_to_approve_s.isnot(None),
            PullRequest.created_at >= date_from,
            PullRequest.created_at <= date_to,
        )
    )

    # Avg time after approve (last approval → merge)
    avg_taa = await db.scalar(
        select(func.avg(PullRequest.time_after_approve_s)).where(
            PullRequest.author_id == developer_id,
            PullRequest.is_merged.is_(True),
            PullRequest.time_after_approve_s.isnot(None),
            PullRequest.merged_at >= date_from,
            PullRequest.merged_at <= date_to,
        )
    )

    # PRs merged without approval
    prs_merged_without_approval = await db.scalar(
        select(func.count()).where(
            PullRequest.author_id == developer_id,
            PullRequest.merged_without_approval.is_(True),
            PullRequest.merged_at >= date_from,
            PullRequest.merged_at <= date_to,
        )
    ) or 0

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

    # Avg review rounds (on merged PRs in period)
    avg_review_rounds = await db.scalar(
        select(func.avg(PullRequest.review_round_count)).where(
            PullRequest.author_id == developer_id,
            PullRequest.is_merged.is_(True),
            PullRequest.merged_at >= date_from,
            PullRequest.merged_at <= date_to,
        )
    )

    # PRs merged on first pass (0 changes_requested reviews)
    prs_merged_first_pass = await db.scalar(
        select(func.count()).where(
            PullRequest.author_id == developer_id,
            PullRequest.is_merged.is_(True),
            PullRequest.review_round_count == 0,
            PullRequest.merged_at >= date_from,
            PullRequest.merged_at <= date_to,
        )
    ) or 0

    first_pass_rate = (
        prs_merged_first_pass / prs_merged if prs_merged > 0 else None
    )

    # PRs self-merged (author merged their own PR)
    prs_self_merged = await db.scalar(
        select(func.count()).where(
            PullRequest.author_id == developer_id,
            PullRequest.is_merged.is_(True),
            PullRequest.is_self_merged.is_(True),
            PullRequest.merged_at >= date_from,
            PullRequest.merged_at <= date_to,
        )
    ) or 0

    self_merge_rate = (
        prs_self_merged / prs_merged if prs_merged > 0 else None
    )

    # PRs authored by this developer that were subsequently reverted
    original_pr = PullRequest.__table__.alias("original_pr")
    prs_reverted = await db.scalar(
        select(func.count())
        .select_from(PullRequest.__table__)
        .join(
            original_pr,
            (PullRequest.__table__.c.reverted_pr_number == original_pr.c.number)
            & (PullRequest.__table__.c.repo_id == original_pr.c.repo_id),
        )
        .where(
            PullRequest.__table__.c.is_revert.is_(True),
            PullRequest.__table__.c.reverted_pr_number.isnot(None),
            PullRequest.__table__.c.created_at >= date_from,
            PullRequest.__table__.c.created_at <= date_to,
            original_pr.c.author_id == developer_id,
        )
    ) or 0

    # Revert PRs this developer authored (fixing problems quickly)
    reverts_authored = await db.scalar(
        select(func.count()).where(
            PullRequest.author_id == developer_id,
            PullRequest.is_revert.is_(True),
            PullRequest.created_at >= date_from,
            PullRequest.created_at <= date_to,
        )
    ) or 0

    return DeveloperStatsResponse(
        prs_opened=prs_opened,
        prs_merged=prs_merged,
        prs_closed_without_merge=prs_closed_no_merge,
        prs_open=prs_open,
        prs_draft=prs_draft,
        total_additions=code_stats[0],
        total_deletions=code_stats[1],
        total_changed_files=code_stats[2],
        reviews_given=reviews_given,
        reviews_received=reviews_received,
        review_quality_breakdown=quality_breakdown,
        review_quality_score=review_quality_score,
        avg_time_to_first_review_hours=avg_ttfr / 3600 if avg_ttfr else None,
        avg_time_to_merge_hours=avg_ttm / 3600 if avg_ttm else None,
        avg_time_to_approve_hours=avg_tta / 3600 if avg_tta else None,
        avg_time_after_approve_hours=avg_taa / 3600 if avg_taa else None,
        prs_merged_without_approval=prs_merged_without_approval,
        issues_assigned=issues_assigned,
        issues_closed=issues_closed,
        avg_time_to_close_issue_hours=avg_ttc / 3600 if avg_ttc else None,
        avg_review_rounds=round(avg_review_rounds, 2) if avg_review_rounds is not None else None,
        prs_merged_first_pass=prs_merged_first_pass,
        first_pass_rate=round(first_pass_rate, 4) if first_pass_rate is not None else None,
        prs_self_merged=prs_self_merged,
        self_merge_rate=round(self_merge_rate, 4) if self_merge_rate is not None else None,
        prs_reverted=prs_reverted,
        reverts_authored=reverts_authored,
        comment_type_distribution=comment_type_distribution,
        nit_ratio=nit_ratio,
        blocker_catch_rate=blocker_catch_rate,
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

    # Avg review rounds (team-wide, on merged PRs)
    team_avg_review_rounds = await db.scalar(
        select(func.avg(PullRequest.review_round_count)).where(
            PullRequest.author_id.in_(dev_ids),
            PullRequest.is_merged.is_(True),
            PullRequest.merged_at >= date_from,
            PullRequest.merged_at <= date_to,
        )
    )

    # Team first pass rate (reuse total_merged to avoid redundant query)
    team_first_pass = await db.scalar(
        select(func.count()).where(
            PullRequest.author_id.in_(dev_ids),
            PullRequest.is_merged.is_(True),
            PullRequest.review_round_count == 0,
            PullRequest.merged_at >= date_from,
            PullRequest.merged_at <= date_to,
        )
    ) or 0
    team_first_pass_rate = team_first_pass / total_merged if total_merged > 0 else None

    # Team revert rate: reverted PRs / total merged PRs
    team_reverts = await db.scalar(
        select(func.count()).where(
            PullRequest.author_id.in_(dev_ids),
            PullRequest.is_revert.is_(True),
            PullRequest.created_at >= date_from,
            PullRequest.created_at <= date_to,
        )
    ) or 0
    revert_rate = team_reverts / total_merged if total_merged > 0 else None

    return TeamStatsResponse(
        developer_count=developer_count,
        total_prs=total_prs,
        total_merged=total_merged,
        merge_rate=merge_rate,
        avg_time_to_first_review_hours=avg_ttfr / 3600 if avg_ttfr else None,
        avg_time_to_merge_hours=avg_ttm / 3600 if avg_ttm else None,
        total_reviews=total_reviews,
        total_issues_closed=total_issues_closed,
        avg_review_rounds=round(team_avg_review_rounds, 2) if team_avg_review_rounds is not None else None,
        first_pass_rate=round(team_first_pass_rate, 4) if team_first_pass_rate is not None else None,
        revert_rate=round(revert_rate, 4) if revert_rate is not None else None,
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
                Developer.is_active.is_(True),
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
    """Compute benchmark metrics per developer using batch queries (GROUP BY)."""
    if not dev_ids:
        return {k: [] for k in [
            "time_to_merge_h", "time_to_first_review_h", "time_to_approve_h",
            "time_after_approve_h", "prs_merged", "review_turnaround_h",
            "reviews_given", "additions_per_pr", "review_rounds",
        ]}

    dev_set = set(dev_ids)

    # Batch 1: PR author metrics (merged PRs)
    merged_pr_rows = (await db.execute(
        select(
            PullRequest.author_id,
            func.count().label("prs_merged"),
            func.avg(PullRequest.time_to_merge_s).label("avg_ttm"),
            func.avg(PullRequest.time_after_approve_s).label("avg_taa"),
            func.coalesce(func.sum(PullRequest.additions), 0).label("total_additions"),
            func.avg(PullRequest.review_round_count).label("avg_rounds"),
        ).where(
            PullRequest.author_id.in_(dev_ids),
            PullRequest.is_merged.is_(True),
            PullRequest.merged_at >= date_from,
            PullRequest.merged_at <= date_to,
        ).group_by(PullRequest.author_id)
    )).all()
    merged_map: dict[int, dict] = {}
    for row in merged_pr_rows:
        merged_map[row.author_id] = {
            "prs_merged": row.prs_merged or 0,
            "avg_ttm": row.avg_ttm,
            "avg_taa": row.avg_taa,
            "total_additions": row.total_additions or 0,
            "avg_rounds": row.avg_rounds,
        }

    # Batch 2: PR author metrics (created PRs — time to first review, approve)
    created_pr_rows = (await db.execute(
        select(
            PullRequest.author_id,
            func.avg(PullRequest.time_to_first_review_s).label("avg_ttfr"),
            func.avg(PullRequest.time_to_approve_s).label("avg_tta"),
        ).where(
            PullRequest.author_id.in_(dev_ids),
            PullRequest.created_at >= date_from,
            PullRequest.created_at <= date_to,
        ).group_by(PullRequest.author_id)
    )).all()
    created_map: dict[int, dict] = {}
    for row in created_pr_rows:
        created_map[row.author_id] = {
            "avg_ttfr": row.avg_ttfr,
            "avg_tta": row.avg_tta,
        }

    # Batch 3: Reviews given count
    reviews_rows = (await db.execute(
        select(
            PRReview.reviewer_id,
            func.count().label("reviews_given"),
        ).where(
            PRReview.reviewer_id.in_(dev_ids),
            PRReview.submitted_at >= date_from,
            PRReview.submitted_at <= date_to,
        ).group_by(PRReview.reviewer_id)
    )).all()
    reviews_map: dict[int, int] = {row.reviewer_id: row.reviews_given for row in reviews_rows}

    # Batch 4: Review turnaround (avg time_to_first_review for PRs each dev reviewed)
    turnaround_rows = (await db.execute(
        select(
            PRReview.reviewer_id,
            func.avg(PullRequest.time_to_first_review_s).label("avg_turnaround"),
        )
        .select_from(PRReview)
        .join(PullRequest, PRReview.pr_id == PullRequest.id)
        .where(
            PRReview.reviewer_id.in_(dev_ids),
            PullRequest.time_to_first_review_s.isnot(None),
            PRReview.submitted_at >= date_from,
            PRReview.submitted_at <= date_to,
        ).group_by(PRReview.reviewer_id)
    )).all()
    turnaround_map: dict[int, float] = {row.reviewer_id: row.avg_turnaround for row in turnaround_rows}

    # Assemble per-developer metrics in consistent order
    metrics: dict[str, list[float]] = {
        "time_to_merge_h": [],
        "time_to_first_review_h": [],
        "time_to_approve_h": [],
        "time_after_approve_h": [],
        "prs_merged": [],
        "review_turnaround_h": [],
        "reviews_given": [],
        "additions_per_pr": [],
        "review_rounds": [],
    }

    for dev_id in dev_ids:
        m = merged_map.get(dev_id, {})
        c = created_map.get(dev_id, {})
        prs_merged = m.get("prs_merged", 0)

        metrics["prs_merged"].append(float(prs_merged))
        avg_ttm = m.get("avg_ttm")
        metrics["time_to_merge_h"].append(avg_ttm / 3600 if avg_ttm else 0.0)
        avg_ttfr = c.get("avg_ttfr")
        metrics["time_to_first_review_h"].append(avg_ttfr / 3600 if avg_ttfr else 0.0)
        avg_tta = c.get("avg_tta")
        metrics["time_to_approve_h"].append(avg_tta / 3600 if avg_tta else 0.0)
        avg_taa = m.get("avg_taa")
        metrics["time_after_approve_h"].append(avg_taa / 3600 if avg_taa else 0.0)
        metrics["reviews_given"].append(float(reviews_map.get(dev_id, 0)))
        avg_turnaround = turnaround_map.get(dev_id)
        metrics["review_turnaround_h"].append(avg_turnaround / 3600 if avg_turnaround else 0.0)
        total_additions = m.get("total_additions", 0)
        metrics["additions_per_pr"].append(total_additions / prs_merged if prs_merged > 0 else 0.0)
        avg_rounds = m.get("avg_rounds")
        metrics["review_rounds"].append(float(avg_rounds) if avg_rounds is not None else 0.0)

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
_LOWER_IS_BETTER = {
    "time_to_merge_h", "time_to_first_review_h", "review_turnaround_h",
    "review_rounds", "time_to_approve_h", "time_after_approve_h",
}


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
        "review_rounds": base.avg_review_rounds or 0.0,
        "time_to_approve_h": base.avg_time_to_approve_hours or 0.0,
        "time_after_approve_h": base.avg_time_after_approve_hours or 0.0,
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
        # Open PRs authored (exclude drafts)
        open_authored = await db.scalar(
            select(func.count()).where(
                PullRequest.author_id == dev.id,
                PullRequest.state == "open",
                PullRequest.is_draft.isnot(True),
            )
        ) or 0

        # Draft PRs authored
        drafts_open = await db.scalar(
            select(func.count()).where(
                PullRequest.author_id == dev.id,
                PullRequest.state == "open",
                PullRequest.is_draft.is_(True),
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

        # PRs waiting for review (open, authored by dev, no reviews yet, exclude drafts)
        prs_waiting = await db.scalar(
            select(func.count()).where(
                PullRequest.author_id == dev.id,
                PullRequest.state == "open",
                PullRequest.first_review_at.is_(None),
                PullRequest.is_draft.isnot(True),
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

        # Workload score heuristic (pending work only — completed reviews are output, not load)
        total_load = open_authored + open_reviewing + open_issues
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
                drafts_open=drafts_open,
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
            PullRequest.is_draft.isnot(True),
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

    # Merged without approval: per-developer and team-level alerts
    total_merged_no_approval = 0
    for dev in developers:
        dev_no_approval = await db.scalar(
            select(func.count()).where(
                PullRequest.author_id == dev.id,
                PullRequest.merged_without_approval.is_(True),
                PullRequest.merged_at >= date_from,
                PullRequest.merged_at <= date_to,
            )
        ) or 0
        total_merged_no_approval += dev_no_approval
        if dev_no_approval > 0:
            alerts.append(
                WorkloadAlert(
                    type="merged_without_approval",
                    developer_id=dev.id,
                    message=f"{dev.display_name} has {dev_no_approval} PR(s) "
                    f"merged without approval this period",
                )
            )
    if total_merged_no_approval > 0:
        alerts.append(
            WorkloadAlert(
                type="merged_without_approval",
                message=f"{total_merged_no_approval} PR(s) merged without "
                f"any approval this period",
            )
        )

    # Revert spike: revert rate exceeds 5%
    dev_ids = [d.id for d in developers]
    total_merged_team = await db.scalar(
        select(func.count()).where(
            PullRequest.author_id.in_(dev_ids),
            PullRequest.is_merged.is_(True),
            PullRequest.merged_at >= date_from,
            PullRequest.merged_at <= date_to,
        )
    ) or 0
    total_reverts = await db.scalar(
        select(func.count()).where(
            PullRequest.author_id.in_(dev_ids),
            PullRequest.is_revert.is_(True),
            PullRequest.created_at >= date_from,
            PullRequest.created_at <= date_to,
        )
    ) or 0
    if total_merged_team > 0:
        revert_pct = total_reverts / total_merged_team * 100
        if revert_pct > 5:
            alerts.append(
                WorkloadAlert(
                    type="revert_spike",
                    message=f"Revert rate is {revert_pct:.1f}% "
                    f"({total_reverts} reverts out of {total_merged_team} merged PRs)",
                )
            )

    return WorkloadResponse(developers=workloads, alerts=alerts)


async def get_stale_prs(
    db: AsyncSession,
    team: str | None = None,
    threshold_hours: int = 24,
) -> StalePRsResponse:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=threshold_hours)

    # Build base filter for open, non-draft PRs
    base_filters = [
        PullRequest.state == "open",
        PullRequest.is_draft.isnot(True),
    ]

    # Team filter: restrict to PRs authored by team members
    if team:
        dev_query = select(Developer.id).where(
            Developer.is_active.is_(True),
            Developer.team == team,
        )
        dev_result = await db.execute(dev_query)
        dev_ids = [row[0] for row in dev_result.all()]
        if not dev_ids:
            return StalePRsResponse(stale_prs=[], total_count=0)
        base_filters.append(PullRequest.author_id.in_(dev_ids))

    # --- Category 1: No review (open, not draft, no first review, age > threshold) ---
    no_review_query = (
        select(PullRequest)
        .where(
            *base_filters,
            PullRequest.first_review_at.is_(None),
            PullRequest.created_at <= cutoff,
        )
    )
    no_review_result = await db.execute(no_review_query)
    no_review_prs = no_review_result.scalars().all()

    # --- Category 2: Changes requested, no response ---
    # Find PRs where the most recent review is CHANGES_REQUESTED
    # and the PR hasn't been updated significantly since that review.
    # We fetch candidates in SQL, then filter the "no response" heuristic in Python
    # (timedelta arithmetic on columns isn't portable across SQLite/PostgreSQL).
    latest_review_subq = (
        select(
            PRReview.pr_id,
            func.max(PRReview.submitted_at).label("latest_submitted_at"),
        )
        .group_by(PRReview.pr_id)
        .subquery()
    )

    changes_requested_query = (
        select(PullRequest, PRReview.submitted_at.label("review_submitted_at"))
        .join(PRReview, PRReview.pr_id == PullRequest.id)
        .join(
            latest_review_subq,
            and_(
                latest_review_subq.c.pr_id == PullRequest.id,
                latest_review_subq.c.latest_submitted_at == PRReview.submitted_at,
            ),
        )
        .where(
            *base_filters,
            PRReview.state == "CHANGES_REQUESTED",
            PRReview.submitted_at <= cutoff,
        )
    )
    changes_requested_result = await db.execute(changes_requested_query)
    changes_requested_prs = []
    for row in changes_requested_result.all():
        pr = row[0]
        review_at = row.review_submitted_at
        pr_updated = pr.updated_at
        # Normalize tz for comparison
        if review_at and review_at.tzinfo is None:
            review_at = review_at.replace(tzinfo=timezone.utc)
        if pr_updated and pr_updated.tzinfo is None:
            pr_updated = pr_updated.replace(tzinfo=timezone.utc)
        # No author response: PR updated_at within 1h of the review
        if pr_updated and review_at and pr_updated <= review_at + timedelta(hours=1):
            changes_requested_prs.append(pr)

    # --- Category 3: Approved but not merged ---
    # Has at least one APPROVED review, last approval > threshold ago
    latest_approval_subq = (
        select(
            PRReview.pr_id,
            func.max(PRReview.submitted_at).label("latest_approval_at"),
        )
        .where(PRReview.state == "APPROVED")
        .group_by(PRReview.pr_id)
        .subquery()
    )

    approved_not_merged_query = (
        select(PullRequest)
        .join(
            latest_approval_subq,
            latest_approval_subq.c.pr_id == PullRequest.id,
        )
        .where(
            *base_filters,
            PullRequest.is_merged.isnot(True),
            latest_approval_subq.c.latest_approval_at <= cutoff,
        )
    )
    approved_result = await db.execute(approved_not_merged_query)
    approved_not_merged_prs = approved_result.scalars().all()

    # Deduplicate (a PR could match multiple categories; keep highest priority reason)
    seen_ids: dict[int, str] = {}
    pr_map: dict[int, PullRequest] = {}

    for pr in no_review_prs:
        if pr.id not in seen_ids:
            seen_ids[pr.id] = "no_review"
            pr_map[pr.id] = pr

    for pr in changes_requested_prs:
        if pr.id not in seen_ids:
            seen_ids[pr.id] = "changes_requested_no_response"
            pr_map[pr.id] = pr

    for pr in approved_not_merged_prs:
        if pr.id not in seen_ids:
            seen_ids[pr.id] = "approved_not_merged"
            pr_map[pr.id] = pr

    # Build response objects with review counts and author/repo info
    stale_list: list[StalePR] = []
    for pr_id, reason in seen_ids.items():
        pr = pr_map[pr_id]

        # Get review stats for this PR
        review_count = await db.scalar(
            select(func.count()).select_from(PRReview).where(PRReview.pr_id == pr.id)
        ) or 0
        has_approved = (
            await db.scalar(
                select(func.count())
                .select_from(PRReview)
                .where(PRReview.pr_id == pr.id, PRReview.state == "APPROVED")
            )
            or 0
        ) > 0
        has_changes_requested = (
            await db.scalar(
                select(func.count())
                .select_from(PRReview)
                .where(
                    PRReview.pr_id == pr.id, PRReview.state == "CHANGES_REQUESTED"
                )
            )
            or 0
        ) > 0

        # Get repo name
        repo = await db.get(Repository, pr.repo_id)
        repo_name = repo.full_name or repo.name or "unknown" if repo else "unknown"

        # Get author name
        author_name = None
        if pr.author_id:
            author = await db.get(Developer, pr.author_id)
            if author:
                author_name = author.display_name

        created = pr.created_at
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_hours = (now - created).total_seconds() / 3600 if created else 0

        last_activity = pr.updated_at or pr.created_at or now
        if last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=timezone.utc)

        stale_list.append(
            StalePR(
                pr_id=pr.id,
                number=pr.number,
                title=pr.title or "",
                html_url=pr.html_url or "",
                repo_name=repo_name,
                author_name=author_name,
                author_id=pr.author_id,
                age_hours=round(age_hours, 1),
                is_draft=bool(pr.is_draft),
                review_count=review_count,
                has_approved=has_approved,
                has_changes_requested=has_changes_requested,
                last_activity_at=last_activity,
                stale_reason=reason,
            )
        )

    # Sort by age descending (most stale first)
    stale_list.sort(key=lambda x: x.age_hours, reverse=True)

    return StalePRsResponse(stale_prs=stale_list, total_count=len(stale_list))


# --- P2-04: Issue-PR Linkage ---


async def get_issue_linkage_stats(
    db: AsyncSession,
    team: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> IssueLinkageStats:
    date_from, date_to = _default_range(date_from, date_to)

    # Team filter: get developer IDs if team is specified
    team_dev_ids: list[int] | None = None
    if team:
        dev_result = await db.execute(
            select(Developer.id).where(
                Developer.is_active.is_(True),
                Developer.team == team,
            )
        )
        team_dev_ids = [row[0] for row in dev_result.all()]
        if not team_dev_ids:
            return IssueLinkageStats(
                issues_with_linked_prs=0,
                issues_without_linked_prs=0,
                avg_prs_per_issue=None,
                issues_with_multiple_prs=0,
                prs_without_linked_issues=0,
            )

    # Get all PRs in date range that have closing keywords
    pr_filters = [
        PullRequest.created_at >= date_from,
        PullRequest.created_at <= date_to,
        PullRequest.closes_issue_numbers.isnot(None),
    ]
    if team_dev_ids is not None:
        pr_filters.append(PullRequest.author_id.in_(team_dev_ids))

    pr_result = await db.execute(
        select(PullRequest.repo_id, PullRequest.closes_issue_numbers).where(*pr_filters)
    )
    pr_rows = pr_result.all()

    # Build map: (repo_id, issue_number) → count of PRs referencing it
    issue_ref_counts: dict[tuple[int, int], int] = {}
    prs_with_refs = 0
    prs_without_refs = 0

    for repo_id, issue_nums in pr_rows:
        if issue_nums:
            prs_with_refs += 1
            for num in issue_nums:
                key = (repo_id, num)
                issue_ref_counts[key] = issue_ref_counts.get(key, 0) + 1
        else:
            prs_without_refs += 1

    # Also count PRs with no closing keywords at all
    all_pr_filters = [
        PullRequest.created_at >= date_from,
        PullRequest.created_at <= date_to,
    ]
    if team_dev_ids is not None:
        all_pr_filters.append(PullRequest.author_id.in_(team_dev_ids))

    total_prs = await db.scalar(
        select(func.count()).where(*all_pr_filters)
    ) or 0
    prs_without_linked_issues = total_prs - prs_with_refs

    # Get all closed issues in date range
    issue_filters = [
        Issue.state == "closed",
        Issue.closed_at >= date_from,
        Issue.closed_at <= date_to,
    ]
    if team_dev_ids is not None:
        issue_filters.append(Issue.assignee_id.in_(team_dev_ids))

    issue_result = await db.execute(
        select(Issue.repo_id, Issue.number).where(*issue_filters)
    )
    closed_issues = issue_result.all()

    # Cross-reference closed issues with PR linkage
    issues_with_linked_prs = 0
    issues_without_linked_prs = 0
    issues_with_multiple_prs = 0
    pr_counts_per_issue: list[int] = []

    for repo_id, issue_number in closed_issues:
        key = (repo_id, issue_number)
        ref_count = issue_ref_counts.get(key, 0)
        if ref_count > 0:
            issues_with_linked_prs += 1
            pr_counts_per_issue.append(ref_count)
            if ref_count >= 2:
                issues_with_multiple_prs += 1
        else:
            issues_without_linked_prs += 1

    avg_prs_per_issue = (
        round(sum(pr_counts_per_issue) / len(pr_counts_per_issue), 2)
        if pr_counts_per_issue
        else None
    )

    return IssueLinkageStats(
        issues_with_linked_prs=issues_with_linked_prs,
        issues_without_linked_prs=issues_without_linked_prs,
        avg_prs_per_issue=avg_prs_per_issue,
        issues_with_multiple_prs=issues_with_multiple_prs,
        prs_without_linked_issues=prs_without_linked_issues,
    )


async def get_issue_quality_stats(
    db: AsyncSession,
    team: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> IssueQualityStats:
    date_from, date_to = _default_range(date_from, date_to)

    # Optional team filter
    team_dev_ids: list[int] | None = None
    if team:
        dev_result = await db.execute(
            select(Developer.id).where(
                Developer.is_active.is_(True), Developer.team == team
            )
        )
        team_dev_ids = [row[0] for row in dev_result.all()]
        if not team_dev_ids:
            return IssueQualityStats(
                total_issues_created=0,
                avg_body_length=0.0,
                pct_with_checklist=0.0,
                avg_comment_count=0.0,
                pct_closed_not_planned=0.0,
                avg_reopen_count=0.0,
                issues_without_body=0,
                label_distribution={},
            )

    # Base filters for issues created in period
    filters = [Issue.created_at >= date_from, Issue.created_at <= date_to]
    if team_dev_ids is not None:
        filters.append(Issue.assignee_id.in_(team_dev_ids))

    # Total issues created
    total_issues_created = await db.scalar(
        select(func.count()).select_from(Issue).where(*filters)
    ) or 0

    if total_issues_created == 0:
        return IssueQualityStats(
            total_issues_created=0,
            avg_body_length=0.0,
            pct_with_checklist=0.0,
            avg_comment_count=0.0,
            pct_closed_not_planned=0.0,
            avg_reopen_count=0.0,
            issues_without_body=0,
            label_distribution={},
        )

    # Averages
    avg_body_length = await db.scalar(
        select(func.avg(Issue.body_length)).where(*filters)
    ) or 0.0

    avg_comment_count = await db.scalar(
        select(func.avg(Issue.comment_count)).where(*filters)
    ) or 0.0

    avg_reopen_count = await db.scalar(
        select(func.avg(Issue.reopen_count)).where(*filters)
    ) or 0.0

    # Checklist percentage
    checklist_count = await db.scalar(
        select(func.count()).select_from(Issue).where(
            *filters, Issue.has_checklist.is_(True)
        )
    ) or 0
    pct_with_checklist = round(checklist_count / total_issues_created * 100, 1)

    # Issues without meaningful body (<50 chars)
    issues_without_body = await db.scalar(
        select(func.count()).select_from(Issue).where(*filters, Issue.body_length < 50)
    ) or 0

    # Closed as "not_planned" percentage
    closed_filters = [Issue.created_at >= date_from, Issue.created_at <= date_to,
                      Issue.state == "closed"]
    if team_dev_ids is not None:
        closed_filters.append(Issue.assignee_id.in_(team_dev_ids))

    total_closed = await db.scalar(
        select(func.count()).select_from(Issue).where(*closed_filters)
    ) or 0

    not_planned_count = await db.scalar(
        select(func.count()).select_from(Issue).where(
            *closed_filters, Issue.state_reason == "not_planned"
        )
    ) or 0

    pct_closed_not_planned = (
        round(not_planned_count / total_closed * 100, 1) if total_closed > 0 else 0.0
    )

    # Label distribution — fetch labels JSONB and aggregate in Python
    label_result = await db.execute(
        select(Issue.labels).where(*filters, Issue.labels.isnot(None))
    )
    label_distribution: dict[str, int] = {}
    for (labels,) in label_result.all():
        if isinstance(labels, list):
            for label in labels:
                if isinstance(label, str):
                    label_distribution[label] = label_distribution.get(label, 0) + 1

    return IssueQualityStats(
        total_issues_created=total_issues_created,
        avg_body_length=round(float(avg_body_length), 1),
        pct_with_checklist=pct_with_checklist,
        avg_comment_count=round(float(avg_comment_count), 1),
        pct_closed_not_planned=pct_closed_not_planned,
        avg_reopen_count=round(float(avg_reopen_count), 2),
        issues_without_body=issues_without_body,
        label_distribution=label_distribution,
    )


async def get_issue_label_distribution(
    db: AsyncSession,
    team: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[str, int]:
    date_from, date_to = _default_range(date_from, date_to)

    filters = [Issue.created_at >= date_from, Issue.created_at <= date_to]
    if team:
        dev_result = await db.execute(
            select(Developer.id).where(
                Developer.is_active.is_(True), Developer.team == team
            )
        )
        team_dev_ids = [row[0] for row in dev_result.all()]
        if not team_dev_ids:
            return {}
        filters.append(Issue.assignee_id.in_(team_dev_ids))

    result = await db.execute(
        select(Issue.labels).where(*filters, Issue.labels.isnot(None))
    )
    distribution: dict[str, int] = {}
    for (labels,) in result.all():
        if isinstance(labels, list):
            for label in labels:
                if isinstance(label, str):
                    distribution[label] = distribution.get(label, 0) + 1

    return distribution


async def get_issue_creator_stats(
    db: AsyncSession,
    team: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> IssueCreatorStatsResponse:
    date_from, date_to = _default_range(date_from, date_to)

    # Build a lookup of registered developers by github_username
    dev_result = await db.execute(
        select(
            Developer.github_username,
            Developer.display_name,
            Developer.team,
            Developer.role,
        ).where(Developer.is_active.is_(True))
    )
    dev_lookup: dict[str, tuple[str | None, str | None, str | None]] = {}
    team_usernames: set[str] | None = None
    for row in dev_result.all():
        dev_lookup[row[0]] = (row[1], row[2], row[3])
        if team and row[2] == team:
            if team_usernames is None:
                team_usernames = set()
            team_usernames.add(row[0])

    if team and not team_usernames:
        empty_avg = _empty_creator_stats("__team_average__")
        return IssueCreatorStatsResponse(creators=[], team_averages=empty_avg)

    # Fetch all issues in the date range
    filters = [Issue.created_at >= date_from, Issue.created_at <= date_to]
    if team_usernames is not None:
        filters.append(Issue.creator_github_username.in_(team_usernames))

    issue_result = await db.execute(
        select(
            Issue.id,
            Issue.repo_id,
            Issue.number,
            Issue.creator_github_username,
            Issue.time_to_close_s,
            Issue.has_checklist,
            Issue.reopen_count,
            Issue.state,
            Issue.state_reason,
            Issue.body_length,
            Issue.created_at,
            Issue.closed_at,
        ).where(*filters, Issue.creator_github_username.isnot(None))
    )
    all_issues = issue_result.all()

    if not all_issues:
        empty_avg = _empty_creator_stats("__team_average__")
        return IssueCreatorStatsResponse(creators=[], team_averages=empty_avg)

    # Group issues by creator
    creator_issues: dict[str, list] = {}
    # Also build (repo_id, issue_number) → (issue_id, creator, created_at)
    issue_map: dict[tuple[int, int], tuple[int, str, datetime | None]] = {}
    for row in all_issues:
        username = row[3]
        if username not in creator_issues:
            creator_issues[username] = []
        creator_issues[username].append(row)
        issue_map[(row[1], row[2])] = (row[0], username, row[10])

    # Fetch PRs with closing keywords to compute linkage metrics
    pr_result = await db.execute(
        select(
            PullRequest.repo_id,
            PullRequest.closes_issue_numbers,
            PullRequest.created_at,
        ).where(
            PullRequest.created_at >= date_from,
            PullRequest.created_at <= date_to,
            PullRequest.closes_issue_numbers.isnot(None),
        )
    )

    # Build per-issue: list of linked PR created_at timestamps
    # key: issue_id → list of PR created_at
    issue_pr_dates: dict[int, list[datetime]] = {}
    # key: (repo_id, issue_number) → count of PRs
    issue_pr_counts: dict[tuple[int, int], int] = {}
    for repo_id, close_nums, pr_created_at in pr_result.all():
        if not close_nums or not pr_created_at:
            continue
        for num in close_nums:
            key = (repo_id, num)
            issue_pr_counts[key] = issue_pr_counts.get(key, 0) + 1
            if key in issue_map:
                issue_id = issue_map[key][0]
                if issue_id not in issue_pr_dates:
                    issue_pr_dates[issue_id] = []
                issue_pr_dates[issue_id].append(pr_created_at)

    # Fetch issue comments for avg_comment_count_before_pr
    issue_ids_with_prs = set(issue_pr_dates.keys())
    comment_counts_before_pr: dict[int, int] = {}
    if issue_ids_with_prs:
        comment_result = await db.execute(
            select(
                IssueComment.issue_id,
                IssueComment.created_at,
            ).where(IssueComment.issue_id.in_(issue_ids_with_prs))
        )
        # Group comments by issue_id, count those before earliest linked PR
        issue_comments: dict[int, list[datetime | None]] = {}
        for issue_id, comment_created_at in comment_result.all():
            if issue_id not in issue_comments:
                issue_comments[issue_id] = []
            issue_comments[issue_id].append(comment_created_at)

        for issue_id, comment_dates in issue_comments.items():
            earliest_pr = min(issue_pr_dates[issue_id])
            count = sum(
                1 for d in comment_dates if d is not None and d < earliest_pr
            )
            comment_counts_before_pr[issue_id] = count

    # Compute per-creator stats
    creators: list[IssueCreatorStats] = []
    for username, issues in creator_issues.items():
        stats = _compute_creator_metrics(
            username, issues, issue_map, issue_pr_counts,
            issue_pr_dates, comment_counts_before_pr, dev_lookup,
        )
        creators.append(stats)

    # Sort by issues_created descending
    creators.sort(key=lambda c: c.issues_created, reverse=True)

    # Compute team averages
    team_averages = _compute_team_averages(creators)

    return IssueCreatorStatsResponse(
        creators=creators,
        team_averages=team_averages,
    )


def _compute_creator_metrics(
    username: str,
    issues: list,
    issue_map: dict[tuple[int, int], tuple[int, str, datetime | None]],
    issue_pr_counts: dict[tuple[int, int], int],
    issue_pr_dates: dict[int, list[datetime]],
    comment_counts_before_pr: dict[int, int],
    dev_lookup: dict[str, tuple[str | None, str | None, str | None]],
) -> IssueCreatorStats:
    total = len(issues)

    # Basic aggregates
    close_times = [r[4] for r in issues if r[4] is not None]
    avg_time_to_close_hours = (
        round(statistics.mean(close_times) / 3600, 1) if close_times else None
    )

    checklist_count = sum(1 for r in issues if r[5])
    pct_with_checklist = round(checklist_count / total * 100, 1)

    reopened_count = sum(1 for r in issues if r[6] and r[6] > 0)
    pct_reopened = round(reopened_count / total * 100, 1)

    closed_issues = [r for r in issues if r[7] == "closed"]
    not_planned = sum(1 for r in closed_issues if r[8] == "not_planned")
    pct_closed_not_planned = (
        round(not_planned / len(closed_issues) * 100, 1) if closed_issues else 0.0
    )

    body_under_100 = sum(1 for r in issues if (r[9] or 0) < 100)

    # Linkage metrics
    pr_counts: list[int] = []
    time_to_first_pr: list[float] = []
    comment_before_pr_counts: list[int] = []

    for row in issues:
        repo_id, issue_number = row[1], row[2]
        issue_id = row[0]
        issue_created_at = row[10]
        key = (repo_id, issue_number)

        if key in issue_pr_counts:
            pr_counts.append(issue_pr_counts[key])

        if issue_id in issue_pr_dates and issue_created_at:
            earliest_pr = min(issue_pr_dates[issue_id])
            delta_s = (earliest_pr - issue_created_at).total_seconds()
            if delta_s >= 0:
                time_to_first_pr.append(delta_s)

        if issue_id in comment_counts_before_pr:
            comment_before_pr_counts.append(comment_counts_before_pr[issue_id])

    avg_prs_per_issue = (
        round(statistics.mean(pr_counts), 2) if pr_counts else None
    )
    avg_time_to_first_pr_hours = (
        round(statistics.mean(time_to_first_pr) / 3600, 1)
        if time_to_first_pr else None
    )
    avg_comment_count_before_pr = (
        round(statistics.mean(comment_before_pr_counts), 1)
        if comment_before_pr_counts else None
    )

    dev_info = dev_lookup.get(username)
    display_name = dev_info[0] if dev_info else None
    team = dev_info[1] if dev_info else None
    role = dev_info[2] if dev_info else None

    return IssueCreatorStats(
        github_username=username,
        display_name=display_name,
        team=team,
        role=role,
        issues_created=total,
        avg_time_to_close_hours=avg_time_to_close_hours,
        avg_comment_count_before_pr=avg_comment_count_before_pr,
        pct_with_checklist=pct_with_checklist,
        pct_reopened=pct_reopened,
        pct_closed_not_planned=pct_closed_not_planned,
        avg_prs_per_issue=avg_prs_per_issue,
        issues_with_body_under_100_chars=body_under_100,
        avg_time_to_first_pr_hours=avg_time_to_first_pr_hours,
    )


def _empty_creator_stats(username: str) -> IssueCreatorStats:
    return IssueCreatorStats(
        github_username=username,
        display_name=None,
        team=None,
        role=None,
        issues_created=0,
        avg_time_to_close_hours=None,
        avg_comment_count_before_pr=None,
        pct_with_checklist=0.0,
        pct_reopened=0.0,
        pct_closed_not_planned=0.0,
        avg_prs_per_issue=None,
        issues_with_body_under_100_chars=0,
        avg_time_to_first_pr_hours=None,
    )


def _compute_team_averages(creators: list[IssueCreatorStats]) -> IssueCreatorStats:
    if not creators:
        return _empty_creator_stats("__team_average__")

    n = len(creators)
    total_issues = sum(c.issues_created for c in creators)

    close_hours = [c.avg_time_to_close_hours for c in creators if c.avg_time_to_close_hours is not None]
    comment_before = [c.avg_comment_count_before_pr for c in creators if c.avg_comment_count_before_pr is not None]
    prs_per = [c.avg_prs_per_issue for c in creators if c.avg_prs_per_issue is not None]
    first_pr_hours = [c.avg_time_to_first_pr_hours for c in creators if c.avg_time_to_first_pr_hours is not None]

    return IssueCreatorStats(
        github_username="__team_average__",
        display_name=None,
        team=None,
        role=None,
        issues_created=round(total_issues / n),
        avg_time_to_close_hours=(
            round(statistics.mean(close_hours), 1) if close_hours else None
        ),
        avg_comment_count_before_pr=(
            round(statistics.mean(comment_before), 1) if comment_before else None
        ),
        pct_with_checklist=round(
            statistics.mean(c.pct_with_checklist for c in creators), 1
        ),
        pct_reopened=round(
            statistics.mean(c.pct_reopened for c in creators), 1
        ),
        pct_closed_not_planned=round(
            statistics.mean(c.pct_closed_not_planned for c in creators), 1
        ),
        avg_prs_per_issue=(
            round(statistics.mean(prs_per), 2) if prs_per else None
        ),
        issues_with_body_under_100_chars=round(
            sum(c.issues_with_body_under_100_chars for c in creators) / n
        ),
        avg_time_to_first_pr_hours=(
            round(statistics.mean(first_pr_hours), 1) if first_pr_hours else None
        ),
    )


# --- Code Churn (P3-06) ---


def _extract_top_dir(filename: str) -> str | None:
    """Extract the top-level directory from a file path, or None if top-level file."""
    idx = filename.find("/")
    return filename[:idx] if idx > 0 else None


async def get_code_churn(
    db: AsyncSession,
    repo_id: int,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 50,
) -> CodeChurnResponse:
    date_from, date_to = _default_range(date_from, date_to)

    # Fetch repo
    repo = await db.get(Repository, repo_id)
    repo_name = repo.name or repo.full_name or str(repo_id) if repo else str(repo_id)
    tree_truncated = repo.tree_truncated if repo else False

    # --- Hotspot files ---
    # Join pr_files → pull_requests, filter by repo + date range, aggregate by filename
    hotspot_query = (
        select(
            PRFile.filename,
            func.count(func.distinct(PRFile.pr_id)).label("change_frequency"),
            func.sum(PRFile.additions).label("total_additions"),
            func.sum(PRFile.deletions).label("total_deletions"),
            func.count(func.distinct(PullRequest.author_id)).label(
                "contributor_count"
            ),
            func.max(PullRequest.created_at).label("last_modified_at"),
        )
        .join(PullRequest, PRFile.pr_id == PullRequest.id)
        .where(
            PullRequest.repo_id == repo_id,
            PullRequest.created_at >= date_from,
            PullRequest.created_at <= date_to,
        )
        .group_by(PRFile.filename)
        .order_by(
            func.count(func.distinct(PRFile.pr_id)).desc(),
            (func.sum(PRFile.additions) + func.sum(PRFile.deletions)).desc(),
        )
        .limit(limit)
    )
    result = await db.execute(hotspot_query)
    hotspot_rows = result.all()

    hotspot_files = [
        FileChurnEntry(
            path=row.filename,
            change_frequency=row.change_frequency,
            total_additions=row.total_additions or 0,
            total_deletions=row.total_deletions or 0,
            total_churn=(row.total_additions or 0) + (row.total_deletions or 0),
            contributor_count=row.contributor_count,
            last_modified_at=row.last_modified_at,
        )
        for row in hotspot_rows
    ]

    # --- Total files changed in period ---
    total_files_changed = (
        await db.scalar(
            select(func.count(func.distinct(PRFile.filename)))
            .join(PullRequest, PRFile.pr_id == PullRequest.id)
            .where(
                PullRequest.repo_id == repo_id,
                PullRequest.created_at >= date_from,
                PullRequest.created_at <= date_to,
            )
        )
        or 0
    )

    # --- Repo tree stats ---
    total_files_in_repo = (
        await db.scalar(
            select(func.count()).where(
                RepoTreeFile.repo_id == repo_id,
                RepoTreeFile.type == "blob",
            )
        )
        or 0
    )

    # --- Stale directories (batch approach) ---
    # Get top-level directories from repo tree
    dir_result = await db.execute(
        select(RepoTreeFile.path).where(
            RepoTreeFile.repo_id == repo_id,
            RepoTreeFile.type == "tree",
            ~RepoTreeFile.path.contains("/"),
        )
    )
    top_dirs = [row[0] for row in dir_result.all()]

    stale_directories: list[StaleDirectory] = []
    if top_dirs:
        # Batch query: get all PR file activity in the period, extract top-level dir
        activity_result = await db.execute(
            select(PRFile.filename, PullRequest.created_at)
            .join(PullRequest, PRFile.pr_id == PullRequest.id)
            .where(
                PullRequest.repo_id == repo_id,
                PullRequest.created_at >= date_from,
                PullRequest.created_at <= date_to,
            )
        )
        # Build set of active top-level dirs in the period
        active_dirs_in_period: set[str] = set()
        for filename, _ in activity_result.all():
            top = _extract_top_dir(filename)
            if top:
                active_dirs_in_period.add(top)

        # Batch query: get all PR file activity ever, to find last activity per dir
        all_activity_result = await db.execute(
            select(PRFile.filename, func.max(PullRequest.created_at).label("last_at"))
            .join(PullRequest, PRFile.pr_id == PullRequest.id)
            .where(PullRequest.repo_id == repo_id)
            .group_by(PRFile.filename)
        )
        # Aggregate last activity by top-level directory
        dir_last_activity: dict[str, datetime] = {}
        for filename, last_at in all_activity_result.all():
            top = _extract_top_dir(filename)
            if top and last_at:
                if top not in dir_last_activity or last_at > dir_last_activity[top]:
                    dir_last_activity[top] = last_at

        # Batch query: count files per top-level directory from repo tree
        tree_blobs_result = await db.execute(
            select(RepoTreeFile.path).where(
                RepoTreeFile.repo_id == repo_id,
                RepoTreeFile.type == "blob",
            )
        )
        dir_file_counts: dict[str, int] = {}
        for (path,) in tree_blobs_result.all():
            top = _extract_top_dir(path)
            if top:
                dir_file_counts[top] = dir_file_counts.get(top, 0) + 1

        # Build stale directory list
        for dir_path in top_dirs:
            if dir_path not in active_dirs_in_period:
                stale_directories.append(
                    StaleDirectory(
                        path=dir_path,
                        file_count=dir_file_counts.get(dir_path, 0),
                        last_pr_activity=dir_last_activity.get(dir_path),
                    )
                )

        # Sort: never-touched first, then oldest activity
        stale_directories.sort(
            key=lambda d: (d.last_pr_activity is not None, d.last_pr_activity)
        )

    return CodeChurnResponse(
        repo_id=repo_id,
        repo_name=repo_name,
        hotspot_files=hotspot_files,
        stale_directories=stale_directories,
        total_files_in_repo=total_files_in_repo,
        total_files_changed=total_files_changed,
        tree_truncated=tree_truncated,
    )


# ---------------------------------------------------------------------------
# CI/CD Check-Run Stats (P3-07)
# ---------------------------------------------------------------------------


async def get_ci_stats(
    db: AsyncSession,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    repo_id: int | None = None,
) -> CIStatsResponse:
    date_from, date_to = _default_range(date_from, date_to)

    # Base condition: PRs in date range, optionally filtered by repo
    pr_conditions = [
        PullRequest.created_at >= date_from,
        PullRequest.created_at <= date_to,
    ]
    if repo_id is not None:
        pr_conditions.append(PullRequest.repo_id == repo_id)

    # --- PRs merged with failing checks ---
    # Subquery: PR IDs that have at least one failing check run
    prs_with_failure = (
        select(PRCheckRun.pr_id)
        .join(PullRequest, PRCheckRun.pr_id == PullRequest.id)
        .where(
            *pr_conditions,
            PullRequest.is_merged.is_(True),
            PRCheckRun.conclusion == "failure",
        )
        .group_by(PRCheckRun.pr_id)
        .subquery()
    )
    prs_merged_with_failing = await db.scalar(
        select(func.count()).select_from(prs_with_failure)
    ) or 0

    # --- Avg checks to green ---
    # For each (pr, check_name), find the max run_attempt where conclusion=success.
    # This tells us how many attempts it took to get green.
    max_attempt_to_green = (
        select(
            PRCheckRun.pr_id,
            PRCheckRun.check_name,
            func.max(PRCheckRun.run_attempt).label("attempts"),
        )
        .join(PullRequest, PRCheckRun.pr_id == PullRequest.id)
        .where(
            *pr_conditions,
            PRCheckRun.conclusion == "success",
        )
        .group_by(PRCheckRun.pr_id, PRCheckRun.check_name)
        .subquery()
    )
    avg_to_green = await db.scalar(
        select(func.avg(max_attempt_to_green.c.attempts))
    )
    avg_checks_to_green = round(float(avg_to_green), 2) if avg_to_green else None

    # --- Flaky checks (>10% failure rate) ---
    check_stats_q = (
        select(
            PRCheckRun.check_name,
            func.count().label("total_runs"),
            func.sum(
                case((PRCheckRun.conclusion == "failure", 1), else_=0)
            ).label("failures"),
        )
        .join(PullRequest, PRCheckRun.pr_id == PullRequest.id)
        .where(*pr_conditions)
        .group_by(PRCheckRun.check_name)
        .having(func.count() >= 5)  # need a minimum sample
    )
    check_stats_rows = (await db.execute(check_stats_q)).all()

    flaky_checks: list[FlakyCheck] = []
    for name, total, failures in check_stats_rows:
        rate = failures / total if total else 0
        if rate > 0.1:
            flaky_checks.append(
                FlakyCheck(
                    name=name,
                    failure_rate=round(rate, 3),
                    total_runs=total,
                )
            )
    flaky_checks.sort(key=lambda c: c.failure_rate, reverse=True)

    # --- Avg build duration ---
    avg_dur = await db.scalar(
        select(func.avg(PRCheckRun.duration_s))
        .join(PullRequest, PRCheckRun.pr_id == PullRequest.id)
        .where(*pr_conditions, PRCheckRun.duration_s.isnot(None))
    )
    avg_build_duration_s = round(float(avg_dur), 1) if avg_dur else None

    # --- Slowest checks (top 5 by avg duration) ---
    slowest_q = (
        select(
            PRCheckRun.check_name,
            func.avg(PRCheckRun.duration_s).label("avg_dur"),
        )
        .join(PullRequest, PRCheckRun.pr_id == PullRequest.id)
        .where(*pr_conditions, PRCheckRun.duration_s.isnot(None))
        .group_by(PRCheckRun.check_name)
        .order_by(func.avg(PRCheckRun.duration_s).desc())
        .limit(5)
    )
    slowest_rows = (await db.execute(slowest_q)).all()
    slowest_checks = [
        SlowestCheck(name=name, avg_duration_s=round(float(avg_d), 1))
        for name, avg_d in slowest_rows
    ]

    return CIStatsResponse(
        prs_merged_with_failing_checks=prs_merged_with_failing,
        avg_checks_to_green=avg_checks_to_green,
        flaky_checks=flaky_checks,
        avg_build_duration_s=avg_build_duration_s,
        slowest_checks=slowest_checks,
    )


# ---------------------------------------------------------------------------
# DORA Metrics (P4-01)
# ---------------------------------------------------------------------------


def _deploy_frequency_band(deploys_per_day: float) -> str:
    """Classify deploy frequency per DORA benchmarks."""
    if deploys_per_day > 1.0:
        return "elite"
    if deploys_per_day >= 1.0 / 7:
        return "high"
    if deploys_per_day >= 1.0 / 30:
        return "medium"
    return "low"


def _lead_time_band(hours: float) -> str:
    """Classify change lead time per DORA benchmarks."""
    if hours < 1.0:
        return "elite"
    if hours < 24.0:
        return "high"
    if hours < 168.0:  # 7 days
        return "medium"
    return "low"


def _cfr_band(rate: float) -> str:
    """Classify change failure rate per DORA research thresholds."""
    if rate < 5.0:
        return "elite"
    if rate < 15.0:
        return "high"
    if rate < 45.0:
        return "medium"
    return "low"


def _mttr_band(hours: float) -> str:
    """Classify mean time to recovery per DORA benchmarks."""
    if hours < 1.0:
        return "elite"
    if hours < 24.0:
        return "high"
    if hours < 168.0:  # 7 days
        return "medium"
    return "low"


_BAND_ORDER = {"elite": 0, "high": 1, "medium": 2, "low": 3}
_BAND_NAMES = ["elite", "high", "medium", "low"]


def _overall_dora_band(*bands: str) -> str:
    """Overall DORA rating = lowest (worst) of all metric bands."""
    worst = max(_BAND_ORDER.get(b, 3) for b in bands)
    return _BAND_NAMES[worst]


async def get_dora_metrics(
    db: AsyncSession,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    repo_id: int | None = None,
) -> DORAMetricsResponse:
    date_from, date_to = _default_range(date_from, date_to)

    conditions = [
        Deployment.deployed_at >= date_from,
        Deployment.deployed_at <= date_to,
    ]
    if repo_id is not None:
        conditions.append(Deployment.repo_id == repo_id)

    # Total successful deployments in period
    total = await db.scalar(
        select(func.count()).select_from(
            select(Deployment.id).where(
                *conditions, Deployment.status == "success"
            ).subquery()
        )
    ) or 0

    # Total all deployments (success + failure) for CFR denominator
    total_all = await db.scalar(
        select(func.count()).select_from(
            select(Deployment.id).where(*conditions).subquery()
        )
    ) or 0

    period_days = max((date_to - date_from).days, 1)
    deploy_frequency = round(total / period_days, 3)

    # Average lead time
    avg_lt = await db.scalar(
        select(func.avg(Deployment.lead_time_s)).where(
            *conditions,
            Deployment.status == "success",
            Deployment.lead_time_s.isnot(None),
        )
    )
    avg_lead_time_hours = round(float(avg_lt) / 3600, 2) if avg_lt else None

    # Change Failure Rate
    failure_count = await db.scalar(
        select(func.count()).select_from(
            select(Deployment.id).where(
                *conditions, Deployment.is_failure.is_(True)
            ).subquery()
        )
    ) or 0
    cfr = round(failure_count / total_all * 100, 2) if total_all > 0 else None

    # Mean Time to Recovery
    avg_mttr = await db.scalar(
        select(func.avg(Deployment.recovery_time_s)).where(
            *conditions,
            Deployment.is_failure.is_(True),
            Deployment.recovery_time_s.isnot(None),
        )
    )
    avg_mttr_hours = round(float(avg_mttr) / 3600, 2) if avg_mttr else None

    # Band classifications
    df_band = _deploy_frequency_band(deploy_frequency)
    lt_band = _lead_time_band(avg_lead_time_hours) if avg_lead_time_hours is not None else "low"
    cfr_band_val = _cfr_band(cfr) if cfr is not None else "low"
    mttr_band_val = _mttr_band(avg_mttr_hours) if avg_mttr_hours is not None else "low"
    overall = _overall_dora_band(df_band, lt_band, cfr_band_val, mttr_band_val)

    # Recent deployments (last 20, all statuses)
    dep_rows = (
        await db.execute(
            select(
                Deployment.id,
                Deployment.environment,
                Deployment.sha,
                Deployment.deployed_at,
                Deployment.workflow_name,
                Deployment.status,
                Deployment.lead_time_s,
                Repository.full_name,
                Deployment.is_failure,
                Deployment.failure_detected_via,
                Deployment.recovery_time_s,
            )
            .join(Repository, Deployment.repo_id == Repository.id)
            .where(*conditions)
            .order_by(Deployment.deployed_at.desc())
            .limit(20)
        )
    ).all()

    deployments = [
        DeploymentDetail(
            id=row[0],
            environment=row[1],
            sha=row[2],
            deployed_at=row[3],
            workflow_name=row[4],
            status=row[5],
            lead_time_hours=round(float(row[6]) / 3600, 2) if row[6] else None,
            repo_name=row[7],
            is_failure=row[8],
            failure_detected_via=row[9],
            recovery_time_hours=round(float(row[10]) / 3600, 2) if row[10] else None,
        )
        for row in dep_rows
    ]

    return DORAMetricsResponse(
        deploy_frequency=deploy_frequency,
        deploy_frequency_band=df_band,
        avg_lead_time_hours=avg_lead_time_hours,
        lead_time_band=lt_band,
        total_deployments=total,
        total_all_deployments=total_all,
        period_days=period_days,
        deployments=deployments,
        change_failure_rate=cfr,
        cfr_band=cfr_band_val,
        avg_mttr_hours=avg_mttr_hours,
        mttr_band=mttr_band_val,
        failure_deployments=failure_count,
        overall_band=overall,
    )
