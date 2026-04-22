"""Phase 02 — PR↔issue linkage quality analytics.

Summarizes link coverage, confidence distribution, source breakdown, and
identifies unlinked recent PRs + disagreement PRs (multiple links at same confidence).
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    ExternalIssue,
    IntegrationConfig,
    PRExternalIssueLink,
    PullRequest,
    Repository,
)


async def get_link_quality_summary(db: AsyncSession, integration_id: int | None = None) -> dict:
    """Return a summary of PR↔issue linkage health.

    Shape:
        {
            "total_prs": int,
            "linked_prs": int,
            "linkage_rate": float,  # 0..1
            "by_confidence": {"high": int, "medium": int, "low": int},
            "by_source": {"linear_attachment": int, "branch": int, "title": int, "body": int,
                          "commit_message": int},
            "unlinked_recent": [ {pr summary...} ],
            "disagreement_prs": [ {pr summary with issues...} ],
        }

    If ``integration_id`` is provided, scoping is limited to issues of that integration.
    """
    # Total PRs (count all PRs)
    total_prs = (
        await db.execute(select(func.count()).select_from(PullRequest))
    ).scalar() or 0

    # Distinct PRs that have at least one link (optionally filtered by integration via join)
    linked_pr_query = select(func.count(func.distinct(PRExternalIssueLink.pull_request_id)))
    if integration_id is not None:
        linked_pr_query = linked_pr_query.select_from(PRExternalIssueLink).join(
            ExternalIssue, PRExternalIssueLink.external_issue_id == ExternalIssue.id
        ).where(ExternalIssue.integration_id == integration_id)
    linked_prs = (await db.execute(linked_pr_query)).scalar() or 0

    linkage_rate = (linked_prs / total_prs) if total_prs else 0.0

    # Confidence breakdown — count *link rows*, not PRs, because one PR may have multiple links
    conf_query = (
        select(PRExternalIssueLink.link_confidence, func.count())
        .group_by(PRExternalIssueLink.link_confidence)
    )
    if integration_id is not None:
        conf_query = conf_query.join(
            ExternalIssue, PRExternalIssueLink.external_issue_id == ExternalIssue.id
        ).where(ExternalIssue.integration_id == integration_id)
    by_confidence = {"high": 0, "medium": 0, "low": 0}
    for conf, n in (await db.execute(conf_query)).all():
        if conf in by_confidence:
            by_confidence[conf] = n

    # Source breakdown
    src_query = (
        select(PRExternalIssueLink.link_source, func.count())
        .group_by(PRExternalIssueLink.link_source)
    )
    if integration_id is not None:
        src_query = src_query.join(
            ExternalIssue, PRExternalIssueLink.external_issue_id == ExternalIssue.id
        ).where(ExternalIssue.integration_id == integration_id)
    by_source: dict[str, int] = {}
    for src, n in (await db.execute(src_query)).all():
        by_source[src or "unknown"] = n

    # Unlinked recent PRs (last 30 days, up to 50)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    unlinked_subq = (
        select(PRExternalIssueLink.pull_request_id).scalar_subquery()
    )
    unlinked_query = (
        select(
            PullRequest.id,
            PullRequest.number,
            PullRequest.title,
            PullRequest.created_at,
            PullRequest.html_url,
            PullRequest.author_github_username,
            Repository.full_name,
        )
        .join(Repository, PullRequest.repo_id == Repository.id)
        .where(
            PullRequest.created_at >= cutoff,
            PullRequest.id.notin_(unlinked_subq),
        )
        .order_by(PullRequest.created_at.desc())
        .limit(50)
    )
    unlinked_rows = (await db.execute(unlinked_query)).all()
    unlinked_recent = [
        {
            "pr_id": r.id,
            "number": r.number,
            "title": r.title,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "html_url": r.html_url,
            "author_github_username": r.author_github_username,
            "repo": r.full_name or "",
        }
        for r in unlinked_rows
    ]

    # Disagreement PRs: PRs with multiple links at equal confidence
    # Strategy: find (pr_id, link_confidence) groups with count >= 2
    dis_query = (
        select(
            PRExternalIssueLink.pull_request_id,
            PRExternalIssueLink.link_confidence,
            func.count(),
        )
        .group_by(PRExternalIssueLink.pull_request_id, PRExternalIssueLink.link_confidence)
        .having(func.count() >= 2)
    )
    dis_pairs = (await db.execute(dis_query)).all()
    disagreement_pr_ids = {pr_id for pr_id, _conf, _n in dis_pairs}

    disagreement_prs: list[dict] = []
    if disagreement_pr_ids:
        dis_query = (
            select(
                PullRequest.id,
                PullRequest.number,
                PullRequest.title,
                PullRequest.html_url,
                Repository.full_name,
            )
            .join(Repository, PullRequest.repo_id == Repository.id)
            .where(PullRequest.id.in_(disagreement_pr_ids))
            .limit(50)
        )
        pr_rows = (await db.execute(dis_query)).all()
        # Load all links for those PRs grouped by PR
        links_query = (
            select(
                PRExternalIssueLink.pull_request_id,
                PRExternalIssueLink.external_issue_id,
                PRExternalIssueLink.link_source,
                PRExternalIssueLink.link_confidence,
                ExternalIssue.identifier,
            )
            .join(ExternalIssue, PRExternalIssueLink.external_issue_id == ExternalIssue.id)
            .where(PRExternalIssueLink.pull_request_id.in_(disagreement_pr_ids))
        )
        by_pr: dict[int, list[dict]] = {}
        for pr_id, issue_id, source, conf, ident in (await db.execute(links_query)).all():
            by_pr.setdefault(pr_id, []).append(
                {
                    "external_issue_id": issue_id,
                    "identifier": ident,
                    "link_source": source,
                    "link_confidence": conf,
                }
            )
        for r in pr_rows:
            disagreement_prs.append(
                {
                    "pr_id": r.id,
                    "number": r.number,
                    "title": r.title,
                    "html_url": r.html_url,
                    "repo": r.full_name or "",
                    "links": by_pr.get(r.id, []),
                }
            )

    return {
        "total_prs": total_prs,
        "linked_prs": linked_prs,
        "linkage_rate": linkage_rate,
        "by_confidence": by_confidence,
        "by_source": by_source,
        "unlinked_recent": unlinked_recent,
        "disagreement_prs": disagreement_prs,
    }


async def check_integration_is_linear(
    db: AsyncSession, integration_id: int
) -> IntegrationConfig:
    """Verify the integration exists and is Linear; raise ValueError otherwise."""
    config = await db.get(IntegrationConfig, integration_id)
    if not config or config.type != "linear":
        raise ValueError(f"Linear integration {integration_id} not found")
    return config


async def get_linkage_rate_trend(
    db: AsyncSession,
    *,
    integration_id: int | None = None,
    weeks: int = 12,
) -> list[dict]:
    """Weekly linkage-rate buckets for the last ``weeks`` weeks.

    Bucket boundaries are Monday-to-Sunday in UTC. A PR's bucket is its
    ``created_at`` week; the rate is ``linked / total`` for PRs created in
    that week. This is computed from existing data (no history table needed)
    and is therefore a reliable post-hoc view, not a live time series.
    """
    # Walk the last N weeks from today backward, snap each to UTC Monday.
    now = datetime.now(timezone.utc)
    today = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    most_recent_monday = today - timedelta(days=today.weekday())
    earliest = most_recent_monday - timedelta(weeks=weeks - 1)

    # Pull minimal PR rows within range; integration-scoped if requested by
    # joining through the links.
    pr_query = select(
        PullRequest.id,
        PullRequest.created_at,
    ).where(
        PullRequest.created_at >= earliest,
        PullRequest.created_at < most_recent_monday + timedelta(weeks=1),
    )
    pr_rows = (await db.execute(pr_query)).all()

    # All PR ids with at least one link (optionally scoped to integration)
    linked_query = select(func.distinct(PRExternalIssueLink.pull_request_id))
    if integration_id is not None:
        linked_query = linked_query.join(
            ExternalIssue, PRExternalIssueLink.external_issue_id == ExternalIssue.id
        ).where(ExternalIssue.integration_id == integration_id)
    linked_ids = {
        row[0] for row in (await db.execute(linked_query)).all() if row[0]
    }

    # Bucket PRs by Monday
    buckets: dict[datetime, dict[str, int]] = {}
    for pr_id, created_at in pr_rows:
        if created_at is None:
            continue
        ca = created_at
        if ca.tzinfo is None:
            ca = ca.replace(tzinfo=timezone.utc)
        week_start = datetime(ca.year, ca.month, ca.day, tzinfo=timezone.utc)
        week_start = week_start - timedelta(days=week_start.weekday())
        if week_start < earliest:
            continue
        stats = buckets.setdefault(week_start, {"total": 0, "linked": 0})
        stats["total"] += 1
        if pr_id in linked_ids:
            stats["linked"] += 1

    # Emit every week in range, even empty ones, so the chart renders a
    # continuous line instead of gapping on low-activity weeks.
    out: list[dict] = []
    current = earliest
    while current <= most_recent_monday:
        stats = buckets.get(current, {"total": 0, "linked": 0})
        total = stats["total"]
        linked = stats["linked"]
        rate = (linked / total) if total else None
        out.append(
            {
                "week_start": current.isoformat(),
                "total": total,
                "linked": linked,
                "linkage_rate": rate,
            }
        )
        current = current + timedelta(weeks=1)
    return out
