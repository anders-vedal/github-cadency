"""Phase 05 — Developer-level Linear creator/worker/shepherd profiles.

Creator: tickets the developer wrote (spec quality signal via downstream PR rounds).
Worker: tickets the developer executed (self-picked vs pushed, cycle time).
Shepherd: developer comments on other people's issues (mentorship / cross-team signal).

All functions respect a date range (default: last 30 days).
"""

from datetime import datetime
from statistics import median

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Developer,
    ExternalIssue,
    ExternalIssueComment,
    ExternalIssueHistoryEvent,
    ExternalProject,
    ExternalSprint,
    PRExternalIssueLink,
    PullRequest,
)
from app.services.utils import default_range


async def get_developer_creator_profile(
    db: AsyncSession,
    developer_id: int,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict:
    """Creator profile — issues written by this developer."""
    since, until = default_range(date_from, date_to)

    issues = (
        await db.execute(
            select(ExternalIssue).where(
                ExternalIssue.creator_developer_id == developer_id,
                ExternalIssue.created_at >= since,
                ExternalIssue.created_at <= until,
            )
        )
    ).scalars().all()
    issue_ids = [i.id for i in issues]

    by_type: dict[str, int] = {}
    desc_lengths: list[int] = []
    self_assigned = 0
    for i in issues:
        t = i.issue_type or "unknown"
        by_type[t] = by_type.get(t, 0) + 1
        if i.description_length:
            desc_lengths.append(i.description_length)
        if i.assignee_developer_id == i.creator_developer_id:
            self_assigned += 1

    avg_desc = int(sum(desc_lengths) / len(desc_lengths)) if desc_lengths else 0
    self_assigned_pct = (self_assigned / len(issues)) if issues else 0.0

    # Labels — top 5
    label_counts: dict[str, int] = {}
    for i in issues:
        for l in (i.labels or []):
            label_counts[l] = label_counts.get(l, 0) + 1
    top_labels = [
        {"label": l, "count": c}
        for l, c in sorted(label_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    ]

    # Avg comments generated on their issues (exc. system)
    avg_comments = 0.0
    if issue_ids:
        comment_rows = (
            await db.execute(
                select(
                    ExternalIssueComment.issue_id,
                    func.count(),
                )
                .where(
                    ExternalIssueComment.issue_id.in_(issue_ids),
                    ExternalIssueComment.is_system_generated.is_(False),
                )
                .group_by(ExternalIssueComment.issue_id)
            )
        ).all()
        total_comments = sum(n for _iid, n in comment_rows)
        avg_comments = total_comments / len(issues) if issues else 0.0

    # Avg downstream PR review rounds (requires links to link_confidence)
    avg_rounds = 0.0
    sample_size = 0
    if issue_ids:
        row = (
            await db.execute(
                select(
                    func.avg(PullRequest.review_round_count),
                    func.count(PullRequest.id),
                )
                .select_from(PRExternalIssueLink)
                .join(PullRequest, PullRequest.id == PRExternalIssueLink.pull_request_id)
                .where(
                    PRExternalIssueLink.external_issue_id.in_(issue_ids),
                    PullRequest.review_round_count.isnot(None),
                )
            )
        ).one_or_none()
        if row:
            avg_rounds_raw, sample_size_raw = row
            avg_rounds = float(avg_rounds_raw) if avg_rounds_raw is not None else 0.0
            sample_size = int(sample_size_raw or 0)

    # Median time-to-close for their issues
    close_times_s: list[int] = []
    for i in issues:
        if i.created_at and i.completed_at:
            delta = int((i.completed_at - i.created_at).total_seconds())
            if delta > 0:
                close_times_s.append(delta)
    median_close_s = int(median(close_times_s)) if close_times_s else None

    return {
        "issues_created": len(issues),
        "issues_created_by_type": by_type,
        "top_labels": top_labels,
        "avg_description_length": avg_desc,
        "avg_comments_generated": avg_comments,
        "avg_downstream_pr_review_rounds": avg_rounds,
        "sample_size_downstream_prs": sample_size,
        "self_assigned_pct": self_assigned_pct,
        "median_time_to_close_for_their_issues_s": median_close_s,
    }


async def get_developer_worker_profile(
    db: AsyncSession,
    developer_id: int,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict:
    """Worker profile — issues assigned to this developer and worked on."""
    since, until = default_range(date_from, date_to)

    # Issues assigned to dev, started or completed in range
    issues = (
        await db.execute(
            select(ExternalIssue).where(
                ExternalIssue.assignee_developer_id == developer_id,
                ExternalIssue.created_at >= since,
                ExternalIssue.created_at <= until,
            )
        )
    ).scalars().all()

    self_picked = 0
    pushed = 0
    for i in issues:
        if i.creator_developer_id == developer_id:
            self_picked += 1
        elif i.creator_developer_id is not None:
            pushed += 1
    total = self_picked + pushed
    self_picked_pct = (self_picked / total) if total else 0.0

    # Triage-to-start (for non-triage issues, created_at → started_at)
    triage_times: list[int] = []
    cycle_times: list[int] = []
    by_status: dict[str, int] = {}
    for i in issues:
        if i.status_category:
            by_status[i.status_category] = by_status.get(i.status_category, 0) + 1
        if i.created_at and i.started_at:
            triage_times.append(int((i.started_at - i.created_at).total_seconds()))
        if i.started_at and i.completed_at:
            cycle_times.append(int((i.completed_at - i.started_at).total_seconds()))
    median_triage = int(median(triage_times)) if triage_times else None
    median_cycle = int(median(cycle_times)) if cycle_times else None

    # Reassigned-to-other count — history events where from_assignee_id was this dev and to_assignee_id is different
    reassigned = (
        await db.execute(
            select(func.count())
            .select_from(ExternalIssueHistoryEvent)
            .where(
                ExternalIssueHistoryEvent.from_assignee_id == developer_id,
                ExternalIssueHistoryEvent.to_assignee_id.isnot(None),
                ExternalIssueHistoryEvent.to_assignee_id != developer_id,
                ExternalIssueHistoryEvent.changed_at >= since,
                ExternalIssueHistoryEvent.changed_at <= until,
            )
        )
    ).scalar() or 0

    return {
        "issues_worked": len(issues),
        "self_picked_count": self_picked,
        "pushed_count": pushed,
        "self_picked_pct": self_picked_pct,
        "median_triage_to_start_s": median_triage,
        "median_cycle_time_s": median_cycle,
        "issues_worked_by_status": by_status,
        "reassigned_to_other_count": int(reassigned),
    }


async def get_developer_shepherd_profile(
    db: AsyncSession,
    developer_id: int,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict:
    """Shepherd profile — comments on other people's issues."""
    since, until = default_range(date_from, date_to)

    # All non-system comments by this dev in range
    rows = (
        await db.execute(
            select(
                ExternalIssueComment.issue_id,
                ExternalIssue.creator_developer_id,
            )
            .join(ExternalIssue, ExternalIssue.id == ExternalIssueComment.issue_id)
            .where(
                ExternalIssueComment.author_developer_id == developer_id,
                ExternalIssueComment.is_system_generated.is_(False),
                ExternalIssueComment.created_at >= since,
                ExternalIssueComment.created_at <= until,
            )
        )
    ).all()

    comments_on_others = 0
    issues_touched: set[int] = set()
    collab_count: dict[int, int] = {}
    for issue_id, creator_id in rows:
        issues_touched.add(issue_id)
        if creator_id and creator_id != developer_id:
            comments_on_others += 1
            collab_count[creator_id] = collab_count.get(creator_id, 0) + 1

    # Top collaborators
    top = sorted(collab_count.items(), key=lambda x: x[1], reverse=True)[:10]
    top_list = []
    for dev_id, count in top:
        dev = await db.get(Developer, dev_id)
        top_list.append(
            {
                "developer_id": dev_id,
                "name": dev.display_name if dev else "Unknown",
                "count": count,
            }
        )

    # Unique teams commented on — join issues → sprints → team_key OR projects → lead's team
    unique_teams = 0
    if issues_touched:
        team_rows = (
            await db.execute(
                select(func.count(func.distinct(ExternalSprint.team_key)))
                .select_from(ExternalIssue)
                .join(ExternalSprint, ExternalSprint.id == ExternalIssue.sprint_id)
                .where(
                    ExternalIssue.id.in_(issues_touched),
                    ExternalSprint.team_key.isnot(None),
                )
            )
        ).scalar() or 0
        unique_teams = int(team_rows)

    # Is shepherd: > 3x team median of comments-on-others
    # Simplified: just flag if > 10 (caller can adjust threshold)
    # Compute team median: count comments-on-others for each active developer
    median_row = (
        await db.execute(
            select(
                ExternalIssueComment.author_developer_id,
                func.count(),
            )
            .join(ExternalIssue, ExternalIssue.id == ExternalIssueComment.issue_id)
            .where(
                ExternalIssueComment.is_system_generated.is_(False),
                ExternalIssueComment.author_developer_id.isnot(None),
                ExternalIssueComment.author_developer_id != ExternalIssue.creator_developer_id,
                ExternalIssueComment.created_at >= since,
                ExternalIssueComment.created_at <= until,
            )
            .group_by(ExternalIssueComment.author_developer_id)
        )
    ).all()
    counts = [n for _d, n in median_row]
    team_median = int(median(counts)) if counts else 0
    is_shepherd = comments_on_others > max(3 * team_median, 10)

    return {
        "comments_on_others_issues": comments_on_others,
        "issues_commented_on": len(issues_touched),
        "unique_teams_commented_on": unique_teams,
        "is_shepherd": is_shepherd,
        "top_collaborators": top_list,
    }
