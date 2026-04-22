"""Phase 03 — Linear Usage Health dashboard service.

Computes 5 narrative signals: adoption, spec quality, autonomy, dialogue health,
creator-outcome. Each signal returns a status ("healthy" | "warning" | "critical")
and the underlying numeric values for display.

All functions respect an optional date range (default: last 30 days).
"""

from datetime import datetime, timezone
from statistics import median

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Developer,
    ExternalIssue,
    ExternalIssueComment,
    ExternalIssueHistoryEvent,
    IntegrationConfig,
    PRExternalIssueLink,
    PullRequest,
)
from app.services.utils import default_range

# Thresholds (tunable via module constants)
ADOPTION_HEALTHY = 0.70
ADOPTION_WARNING = 0.50

SPEC_MIN_DESC_LENGTH_HEALTHY = 120
SPEC_MIN_DESC_LENGTH_WARNING = 40
SPEC_COMMENTS_PER_ISSUE_HEALTHY = 5
SPEC_COMMENTS_PER_ISSUE_WARNING = 12

AUTONOMY_PUSHED_PCT_WARNING = 0.75  # >=75% pushed = high handoff overhead

DIALOGUE_MIN_COMMENTS_HEALTHY = 1.5
DIALOGUE_SILENT_PCT_WARNING = 0.40

CREATOR_MIN_SAMPLE_SIZE = 5


def _status(value: float, healthy_threshold: float, warning_threshold: float, higher_is_better: bool = True) -> str:
    """Return status label based on thresholds."""
    if higher_is_better:
        if value >= healthy_threshold:
            return "healthy"
        if value >= warning_threshold:
            return "warning"
        return "critical"
    else:
        if value <= healthy_threshold:
            return "healthy"
        if value <= warning_threshold:
            return "warning"
        return "critical"


async def _compute_adoption(
    db: AsyncSession, since: datetime, until: datetime
) -> dict:
    """Signal 1: what % of merged PRs are linked to a Linear issue?"""
    total = (
        await db.execute(
            select(func.count()).select_from(PullRequest).where(
                PullRequest.merged_at >= since,
                PullRequest.merged_at <= until,
            )
        )
    ).scalar() or 0

    linked = (
        await db.execute(
            select(func.count(func.distinct(PullRequest.id)))
            .select_from(PullRequest)
            .join(PRExternalIssueLink, PRExternalIssueLink.pull_request_id == PullRequest.id)
            .where(
                PullRequest.merged_at >= since,
                PullRequest.merged_at <= until,
            )
        )
    ).scalar() or 0

    rate = (linked / total) if total else 0.0
    return {
        "linked_pr_count": linked,
        "total_pr_count": total,
        "linkage_rate": rate,
        "target": ADOPTION_HEALTHY,
        "status": _status(rate, ADOPTION_HEALTHY, ADOPTION_WARNING, higher_is_better=True),
    }


async def _compute_spec_quality(
    db: AsyncSession, since: datetime, until: datetime
) -> dict:
    """Signal 2: median description length + comments per issue + high-chatter rate."""
    desc_rows = (
        await db.execute(
            select(ExternalIssue.description_length).where(
                ExternalIssue.created_at >= since,
                ExternalIssue.created_at <= until,
                ExternalIssue.description_length.isnot(None),
            )
        )
    ).scalars().all()
    median_desc = int(median(desc_rows)) if desc_rows else 0

    # Comments per issue (exclude system) — issues created in range
    issue_comment_counts = (
        await db.execute(
            select(
                ExternalIssue.id,
                func.count(ExternalIssueComment.id),
            )
            .select_from(ExternalIssue)
            .join(
                ExternalIssueComment,
                and_(
                    ExternalIssueComment.issue_id == ExternalIssue.id,
                    ExternalIssueComment.is_system_generated.is_(False),
                ),
                isouter=True,
            )
            .where(
                ExternalIssue.created_at >= since,
                ExternalIssue.created_at <= until,
            )
            .group_by(ExternalIssue.id)
        )
    ).all()
    counts = [c for _iid, c in issue_comment_counts]
    median_comments = float(median(counts)) if counts else 0.0

    # High-chatter issues = top 10% bucket
    high_threshold = 0
    if counts:
        sorted_counts = sorted(counts)
        idx = max(0, int(len(sorted_counts) * 0.9) - 1)
        high_threshold = sorted_counts[idx]
    high_issues = sum(1 for c in counts if c >= max(1, high_threshold))
    high_pct = (high_issues / len(counts)) if counts else 0.0

    # Status: healthy if desc length OK AND median comments low
    desc_status = _status(
        median_desc,
        SPEC_MIN_DESC_LENGTH_HEALTHY,
        SPEC_MIN_DESC_LENGTH_WARNING,
        higher_is_better=True,
    )
    comments_status = _status(
        median_comments,
        SPEC_COMMENTS_PER_ISSUE_HEALTHY,
        SPEC_COMMENTS_PER_ISSUE_WARNING,
        higher_is_better=False,
    )
    # Combine: worst of the two
    tier_rank = {"healthy": 2, "warning": 1, "critical": 0}
    status = min((desc_status, comments_status), key=lambda s: tier_rank[s])

    return {
        "median_description_length": median_desc,
        "median_comments_before_first_pr": median_comments,
        "high_comment_issue_pct": high_pct,
        "status": status,
    }


async def _compute_autonomy(
    db: AsyncSession, since: datetime, until: datetime
) -> dict:
    """Signal 3: self-picked vs pushed issues + median time-to-assign."""
    issues = (
        await db.execute(
            select(
                ExternalIssue.id,
                ExternalIssue.creator_developer_id,
                ExternalIssue.assignee_developer_id,
                ExternalIssue.created_at,
            )
            .where(
                ExternalIssue.created_at >= since,
                ExternalIssue.created_at <= until,
                ExternalIssue.assignee_developer_id.isnot(None),
                ExternalIssue.creator_developer_id.isnot(None),
            )
        )
    ).all()

    self_picked = 0
    pushed = 0
    for iid, cid, aid, _ in issues:
        if cid == aid:
            self_picked += 1
        else:
            pushed += 1
    total = self_picked + pushed
    self_picked_pct = (self_picked / total) if total else 0.0

    # Median time-to-assign: from history events where to_assignee_id was first set
    assign_rows = (
        await db.execute(
            select(
                ExternalIssueHistoryEvent.issue_id,
                func.min(ExternalIssueHistoryEvent.changed_at).label("first_assign"),
            )
            .where(ExternalIssueHistoryEvent.to_assignee_id.isnot(None))
            .group_by(ExternalIssueHistoryEvent.issue_id)
        )
    ).all()
    issue_ids_in_range = {iid for iid, _cid, _aid, _ in issues}
    deltas: list[int] = []
    issue_created_by_id = {iid: created for iid, _cid, _aid, created in issues}
    for iid, first_assign in assign_rows:
        if iid not in issue_ids_in_range:
            continue
        created = issue_created_by_id.get(iid)
        if not created or not first_assign:
            continue
        c = created.replace(tzinfo=timezone.utc) if created.tzinfo is None else created
        f = first_assign.replace(tzinfo=timezone.utc) if first_assign.tzinfo is None else first_assign
        delta = int((f - c).total_seconds())
        if delta >= 0:
            deltas.append(delta)
    median_time_to_assign_s = int(median(deltas)) if deltas else None

    pushed_pct = 1.0 - self_picked_pct
    return {
        "self_picked_count": self_picked,
        "pushed_count": pushed,
        "self_picked_pct": self_picked_pct,
        "median_time_to_assign_s": median_time_to_assign_s,
        "status": _status(
            pushed_pct, AUTONOMY_PUSHED_PCT_WARNING, 1.0, higher_is_better=False
        )
        if total
        else "healthy",
    }


async def _compute_dialogue_health(
    db: AsyncSession, since: datetime, until: datetime
) -> dict:
    """Signal 4: distribution of (non-system) comments per issue."""
    rows = (
        await db.execute(
            select(
                ExternalIssue.id,
                func.count(ExternalIssueComment.id),
            )
            .select_from(ExternalIssue)
            .join(
                ExternalIssueComment,
                and_(
                    ExternalIssueComment.issue_id == ExternalIssue.id,
                    ExternalIssueComment.is_system_generated.is_(False),
                ),
                isouter=True,
            )
            .where(
                ExternalIssue.created_at >= since,
                ExternalIssue.created_at <= until,
            )
            .group_by(ExternalIssue.id)
        )
    ).all()
    counts = [c for _iid, c in rows]
    if not counts:
        return {
            "median_comments_per_issue": 0.0,
            "p90_comments_per_issue": 0,
            "silent_issue_pct": 0.0,
            "distribution_shape": "healthy",
        }

    median_val = float(median(counts))
    counts_sorted = sorted(counts)
    p90_idx = min(len(counts_sorted) - 1, int(len(counts_sorted) * 0.9))
    p90 = counts_sorted[p90_idx]

    silent = sum(1 for c in counts if c == 0)
    silent_pct = silent / len(counts)

    # Heuristic shape classification
    if p90 >= 10 and median_val <= 1:
        shape = "heavy_tailed"
    elif silent_pct > DIALOGUE_SILENT_PCT_WARNING:
        shape = "monomodal"
    else:
        shape = "healthy"

    # Status: silent_pct too high = warning; very heavy-tailed = warning
    if silent_pct > DIALOGUE_SILENT_PCT_WARNING or shape == "heavy_tailed":
        status = "warning"
    elif silent_pct > 0.6:
        status = "critical"
    elif median_val < DIALOGUE_MIN_COMMENTS_HEALTHY:
        status = "warning"
    else:
        status = "healthy"

    return {
        "median_comments_per_issue": median_val,
        "p90_comments_per_issue": p90,
        "silent_issue_pct": silent_pct,
        "distribution_shape": shape,
        "status": status,
    }


async def _compute_creator_outcome(
    db: AsyncSession, since: datetime, until: datetime
) -> dict:
    """Signal 5: top creators with ticket-clarity metric (avg downstream PR review rounds)."""
    # For each creator in range, count issues + avg comments + avg linked-PR review rounds
    results = (
        await db.execute(
            select(
                ExternalIssue.creator_developer_id,
                func.count(ExternalIssue.id),
            )
            .where(
                ExternalIssue.created_at >= since,
                ExternalIssue.created_at <= until,
                ExternalIssue.creator_developer_id.isnot(None),
            )
            .group_by(ExternalIssue.creator_developer_id)
            .order_by(func.count(ExternalIssue.id).desc())
            .limit(5)
        )
    ).all()

    top: list[dict] = []
    for dev_id, issues_created in results:
        # Avg comments on their issues (exclude system)
        comments_row = (
            await db.execute(
                select(func.avg(func.coalesce(
                    (
                        select(func.count())
                        .select_from(ExternalIssueComment)
                        .where(
                            ExternalIssueComment.issue_id == ExternalIssue.id,
                            ExternalIssueComment.is_system_generated.is_(False),
                        )
                        .scalar_subquery()
                    ),
                    0,
                )))
                .where(
                    ExternalIssue.creator_developer_id == dev_id,
                    ExternalIssue.created_at >= since,
                    ExternalIssue.created_at <= until,
                )
            )
        ).scalar()
        avg_comments = float(comments_row) if comments_row is not None else 0.0

        # Avg downstream PR review rounds — join issue -> link -> PR
        pr_stats = (
            await db.execute(
                select(
                    func.avg(PullRequest.review_round_count),
                    func.count(PullRequest.id),
                )
                .select_from(ExternalIssue)
                .join(PRExternalIssueLink, PRExternalIssueLink.external_issue_id == ExternalIssue.id)
                .join(PullRequest, PullRequest.id == PRExternalIssueLink.pull_request_id)
                .where(
                    ExternalIssue.creator_developer_id == dev_id,
                    ExternalIssue.created_at >= since,
                    ExternalIssue.created_at <= until,
                    PullRequest.review_round_count.isnot(None),
                )
            )
        ).one_or_none()
        if pr_stats:
            avg_rounds_raw, sample_size = pr_stats
            avg_rounds = float(avg_rounds_raw) if avg_rounds_raw is not None else 0.0
            sample_size = int(sample_size or 0)
        else:
            avg_rounds = 0.0
            sample_size = 0

        dev = await db.get(Developer, dev_id) if dev_id else None

        top.append(
            {
                "developer_id": dev_id,
                "developer_name": dev.display_name if dev else "Unknown",
                "issues_created": issues_created,
                "avg_comments_on_their_issues": avg_comments,
                "avg_downstream_pr_review_rounds": avg_rounds,
                "sample_size": sample_size,
            }
        )

    return {"top_creators": top}


async def get_linear_usage_health(
    db: AsyncSession,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict:
    """Compute all 5 Linear Usage Health signals.

    Only meaningful when a Linear integration is active and primary issue source.
    The caller (endpoint) should check those preconditions; this function returns
    zeroed data gracefully if no issues exist in range.
    """
    since, until = default_range(date_from, date_to)

    adoption = await _compute_adoption(db, since, until)
    spec_quality = await _compute_spec_quality(db, since, until)
    autonomy = await _compute_autonomy(db, since, until)
    dialogue = await _compute_dialogue_health(db, since, until)
    creator = await _compute_creator_outcome(db, since, until)

    return {
        "adoption": adoption,
        "spec_quality": spec_quality,
        "autonomy": autonomy,
        "dialogue_health": dialogue,
        "creator_outcome": creator,
    }


async def is_linear_primary(db: AsyncSession) -> bool:
    """True iff a Linear integration is active AND marked as primary issue source."""
    config = (
        await db.execute(
            select(IntegrationConfig).where(
                IntegrationConfig.type == "linear",
                IntegrationConfig.status == "active",
                IntegrationConfig.is_primary_issue_source.is_(True),
            )
        )
    ).scalar_one_or_none()
    return config is not None
