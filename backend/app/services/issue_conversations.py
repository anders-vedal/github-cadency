"""Phase 04 — Issue Conversations drill-down service.

Answers: where does dialogue happen, who is engaged, and does chattiness correlate
with bouncy PRs? All queries exclude system-generated comments from engagement
signals by default.
"""

from datetime import datetime, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Developer,
    ExternalIssue,
    ExternalIssueComment,
    ExternalProject,
    PRExternalIssueLink,
    PullRequest,
    Repository,
)
from app.services.utils import default_range

FIRST_RESPONSE_BUCKETS_HOURS = [1, 4, 12, 24, 72, 168]  # <1h, 1-4h, 4-12h, 12h-1d, 1-3d, 3-7d, >7d, never


async def get_chattiest_issues(
    db: AsyncSession,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 20,
    project_id: int | None = None,
    creator_id: int | None = None,
    assignee_id: int | None = None,
    label: str | None = None,
    priority: int | None = None,
    has_linked_pr: bool | None = None,
) -> list[dict]:
    """Top-N issues by non-system comment count with filter support."""
    since, until = default_range(date_from, date_to)

    comment_count_subq = (
        select(
            ExternalIssueComment.issue_id,
            func.count().label("comment_count"),
            func.count(func.distinct(ExternalIssueComment.author_developer_id)).label("participants"),
        )
        .where(ExternalIssueComment.is_system_generated.is_(False))
        .group_by(ExternalIssueComment.issue_id)
        .subquery()
    )

    query = (
        select(
            ExternalIssue,
            comment_count_subq.c.comment_count,
            comment_count_subq.c.participants,
        )
        .outerjoin(comment_count_subq, comment_count_subq.c.issue_id == ExternalIssue.id)
        .where(
            ExternalIssue.created_at >= since,
            ExternalIssue.created_at <= until,
        )
        .order_by(comment_count_subq.c.comment_count.desc().nullslast())
        .limit(limit)
    )

    if project_id is not None:
        query = query.where(ExternalIssue.project_id == project_id)
    if creator_id is not None:
        query = query.where(ExternalIssue.creator_developer_id == creator_id)
    if assignee_id is not None:
        query = query.where(ExternalIssue.assignee_developer_id == assignee_id)
    if priority is not None:
        query = query.where(ExternalIssue.priority == priority)

    rows = (await db.execute(query)).all()

    results: list[dict] = []
    for issue, count, participants in rows:
        if label:
            labels = issue.labels or []
            if label not in labels:
                continue

        creator_name = None
        if issue.creator_developer_id:
            dev = await db.get(Developer, issue.creator_developer_id)
            creator_name = dev.display_name if dev else None
        assignee_name = None
        if issue.assignee_developer_id:
            dev = await db.get(Developer, issue.assignee_developer_id)
            assignee_name = dev.display_name if dev else None
        project_name = None
        if issue.project_id:
            project = await db.get(ExternalProject, issue.project_id)
            project_name = project.name if project else None

        # Linked PRs
        linked_rows = (
            await db.execute(
                select(
                    PullRequest.id,
                    PullRequest.number,
                    PullRequest.review_round_count,
                    PullRequest.merged_at,
                    Repository.full_name,
                )
                .select_from(PRExternalIssueLink)
                .join(PullRequest, PullRequest.id == PRExternalIssueLink.pull_request_id)
                .join(Repository, Repository.id == PullRequest.repo_id)
                .where(PRExternalIssueLink.external_issue_id == issue.id)
            )
        ).all()

        if has_linked_pr is True and not linked_rows:
            continue
        if has_linked_pr is False and linked_rows:
            continue

        linked_prs = [
            {
                "pr_id": r.id,
                "number": r.number,
                "repo": r.full_name,
                "review_round_count": r.review_round_count,
                "merged_at": r.merged_at.isoformat() if r.merged_at else None,
            }
            for r in linked_rows
        ]
        rounds = [r.review_round_count for r in linked_rows if r.review_round_count is not None]
        avg_rounds = sum(rounds) / len(rounds) if rounds else None

        # First-response time — earliest non-creator, non-system comment
        first_response_s = None
        if issue.creator_developer_id:
            first_row = (
                await db.execute(
                    select(func.min(ExternalIssueComment.created_at))
                    .where(
                        ExternalIssueComment.issue_id == issue.id,
                        ExternalIssueComment.is_system_generated.is_(False),
                        ExternalIssueComment.author_developer_id != issue.creator_developer_id,
                    )
                )
            ).scalar()
            if first_row and issue.created_at:
                created = issue.created_at
                created_utc = (
                    created.replace(tzinfo=timezone.utc) if created.tzinfo is None else created
                )
                first_utc = (
                    first_row.replace(tzinfo=timezone.utc)
                    if first_row.tzinfo is None
                    else first_row
                )
                delta = (first_utc - created_utc).total_seconds()
                if delta >= 0:
                    first_response_s = int(delta)

        results.append(
            {
                "issue_id": issue.id,
                "identifier": issue.identifier,
                "title": issue.title,
                "url": issue.url,
                "creator": {"id": issue.creator_developer_id, "name": creator_name}
                if issue.creator_developer_id
                else None,
                "assignee": {"id": issue.assignee_developer_id, "name": assignee_name}
                if issue.assignee_developer_id
                else None,
                "project": {"id": issue.project_id, "name": project_name} if issue.project_id else None,
                "priority_label": issue.priority_label,
                "estimate": issue.estimate,
                "comment_count": int(count) if count else 0,
                "unique_participants": int(participants) if participants else 0,
                "first_response_s": first_response_s,
                "created_at": issue.created_at.isoformat() if issue.created_at else None,
                "status": issue.status,
                "linked_prs": linked_prs,
                "avg_linked_pr_review_rounds": avg_rounds,
            }
        )
    return results


async def get_comment_vs_bounce_scatter(
    db: AsyncSession,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[dict]:
    """Scatter points: (comment_count, review_rounds) per (issue, PR) pair."""
    since, until = default_range(date_from, date_to)

    query = (
        select(
            ExternalIssue.identifier,
            PullRequest.number,
            func.count(ExternalIssueComment.id).label("comments"),
            PullRequest.review_round_count,
        )
        .select_from(ExternalIssue)
        .join(PRExternalIssueLink, PRExternalIssueLink.external_issue_id == ExternalIssue.id)
        .join(PullRequest, PullRequest.id == PRExternalIssueLink.pull_request_id)
        .outerjoin(
            ExternalIssueComment,
            and_(
                ExternalIssueComment.issue_id == ExternalIssue.id,
                ExternalIssueComment.is_system_generated.is_(False),
            ),
        )
        .where(
            ExternalIssue.created_at >= since,
            ExternalIssue.created_at <= until,
            PullRequest.review_round_count.isnot(None),
        )
        .group_by(ExternalIssue.id, PullRequest.id)
    )

    rows = (await db.execute(query)).all()
    points = []
    for identifier, number, comments, rounds in rows:
        if not comments:
            continue
        points.append(
            {
                "comment_count": int(comments),
                "review_rounds": int(rounds),
                "issue_identifier": identifier,
                "pr_number": number,
            }
        )
    return points


async def get_first_response_histogram(
    db: AsyncSession,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    buckets_hours: list[int] | None = None,
) -> list[dict]:
    """Histogram of time from issue creation → first non-creator, non-system comment."""
    since, until = default_range(date_from, date_to)
    buckets = buckets_hours or FIRST_RESPONSE_BUCKETS_HOURS

    # Fetch all issues in range + first-response timestamps
    issues = (
        await db.execute(
            select(
                ExternalIssue.id,
                ExternalIssue.created_at,
                ExternalIssue.creator_developer_id,
            )
            .where(
                ExternalIssue.created_at >= since,
                ExternalIssue.created_at <= until,
            )
        )
    ).all()

    bucket_labels = []
    prev = 0
    for hrs in buckets:
        if prev == 0:
            bucket_labels.append(f"<{hrs}h")
        elif hrs < 24:
            bucket_labels.append(f"{prev}-{hrs}h")
        else:
            days_prev = prev // 24 if prev >= 24 else prev
            days_hrs = hrs // 24
            if prev >= 24:
                bucket_labels.append(f"{days_prev}-{days_hrs}d")
            else:
                bucket_labels.append(f"{prev}h-{days_hrs}d")
        prev = hrs
    bucket_labels.append(f">{buckets[-1]}h")
    bucket_labels.append("never")

    counts = [0] * len(bucket_labels)

    for iid, created_at, creator_id in issues:
        first = (
            await db.execute(
                select(func.min(ExternalIssueComment.created_at))
                .where(
                    ExternalIssueComment.issue_id == iid,
                    ExternalIssueComment.is_system_generated.is_(False),
                    ExternalIssueComment.author_developer_id != creator_id
                    if creator_id
                    else True,
                )
            )
        ).scalar()
        if not first or not created_at:
            counts[-1] += 1  # never (or unknown creation timestamp)
            continue
        c_utc = created_at.replace(tzinfo=timezone.utc) if created_at.tzinfo is None else created_at
        f_utc = first.replace(tzinfo=timezone.utc) if first.tzinfo is None else first
        delta_hours = (f_utc - c_utc).total_seconds() / 3600.0
        if delta_hours < 0:
            counts[-1] += 1
            continue
        placed = False
        for idx, bound in enumerate(buckets):
            if delta_hours < bound:
                counts[idx] += 1
                placed = True
                break
        if not placed:
            counts[-2] += 1  # >last bucket

    return [
        {"bucket": label, "count": count}
        for label, count in zip(bucket_labels, counts)
    ]


async def get_participant_distribution(
    db: AsyncSession,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[dict]:
    """Distribution of unique (non-system) comment participants per issue."""
    since, until = default_range(date_from, date_to)

    query = (
        select(
            ExternalIssue.id,
            func.count(func.distinct(ExternalIssueComment.author_developer_id)).label("pct"),
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

    rows = (await db.execute(query)).all()
    buckets = {"1": 0, "2": 0, "3": 0, "4-5": 0, "6+": 0}
    for _iid, n in rows:
        n = int(n or 0)
        if n <= 0:
            continue  # skip silent issues
        if n == 1:
            buckets["1"] += 1
        elif n == 2:
            buckets["2"] += 1
        elif n == 3:
            buckets["3"] += 1
        elif n <= 5:
            buckets["4-5"] += 1
        else:
            buckets["6+"] += 1

    return [{"participants": label, "count": c} for label, c in buckets.items()]
