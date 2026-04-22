"""Phase 06 — Flow analytics from Linear history.

Turns external_issue_history events into workflow-diagnostic signals:
- Time spent in each status (p50/p75/p90/p95)
- Status regressions (went backwards)
- Triage bounces (out-and-back-to-triage)
- Refinement churn (estimate/priority/project changes before work started)

Feature-flagged by `has_sufficient_history` — UI hides the page until enough
history has accumulated (default 14 days, 100 issues).
"""

from datetime import datetime, timezone
from statistics import mean

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Developer,
    ExternalIssue,
    ExternalIssueHistoryEvent,
)
from app.services.utils import default_range

# Status category order for regression detection
STATUS_ORDER = [
    "triage",
    "backlog",
    "todo",
    "in_progress",
    "in_review",
    "done",
]

THRESHOLD_DAYS = 14
THRESHOLD_ISSUES = 100


def _percentile(values: list[int], p: float) -> int:
    if not values:
        return 0
    values_sorted = sorted(values)
    k = int(len(values_sorted) * p)
    k = max(0, min(len(values_sorted) - 1, k))
    return values_sorted[k]


async def has_sufficient_history(db: AsyncSession) -> dict:
    """Return readiness for flow analytics (used to gate UI)."""
    earliest = (
        await db.execute(select(func.min(ExternalIssueHistoryEvent.changed_at)))
    ).scalar()
    issue_count = (
        await db.execute(
            select(func.count(func.distinct(ExternalIssueHistoryEvent.issue_id)))
        )
    ).scalar() or 0

    days_of_history = 0
    if earliest:
        earliest_utc = (
            earliest.replace(tzinfo=timezone.utc) if earliest.tzinfo is None else earliest
        )
        days_of_history = max(
            0, int((datetime.now(timezone.utc) - earliest_utc).total_seconds() / 86400)
        )

    ready = days_of_history >= THRESHOLD_DAYS and issue_count >= THRESHOLD_ISSUES

    return {
        "ready": ready,
        "days_of_history": days_of_history,
        "issues_with_history": int(issue_count),
        "threshold_days": THRESHOLD_DAYS,
        "threshold_issues": THRESHOLD_ISSUES,
    }


async def get_status_time_distribution(
    db: AsyncSession,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    group_by: str = "all",
) -> list[dict]:
    """For each status category, compute p50/p75/p90/p95 time-in-state in seconds.

    Walks history events per issue; successive transitions define how long each
    status was held. Includes a final open-interval for issues still in their
    current state.
    """
    since, until = default_range(date_from, date_to)

    rows = (
        await db.execute(
            select(
                ExternalIssueHistoryEvent.issue_id,
                ExternalIssueHistoryEvent.changed_at,
                ExternalIssueHistoryEvent.from_state_category,
                ExternalIssueHistoryEvent.to_state_category,
            )
            .where(
                ExternalIssueHistoryEvent.changed_at >= since,
                ExternalIssueHistoryEvent.changed_at <= until,
            )
            .order_by(ExternalIssueHistoryEvent.issue_id, ExternalIssueHistoryEvent.changed_at)
        )
    ).all()

    # Group events per issue; compute durations where from->to status changes
    events_by_issue: dict[int, list[tuple]] = {}
    for iid, changed_at, from_cat, to_cat in rows:
        if from_cat and to_cat and from_cat != to_cat:
            events_by_issue.setdefault(iid, []).append((changed_at, from_cat, to_cat))

    # For each issue, accumulate time-in-state across the full window.
    #
    # We bracket the event sequence so the first state's duration (from ``since``
    # until the first transition) and the final open interval (from the last
    # transition until ``until``) are both counted. Without this, the initial
    # state — usually the largest bucket, e.g. time in triage/backlog — is always
    # lost, and issues still in their current state contribute zero to it.
    durations_by_state: dict[str, list[int]] = {}
    for iid, events in events_by_issue.items():
        events.sort(key=lambda x: x[0])
        if not events:
            continue
        # Seed with the first event's from_state so its duration (since → first ts)
        # is accumulated on the first iteration.
        prev_time = since
        current_state = events[0][1]
        for ts, from_cat, to_cat in events:
            ts_utc = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
            if prev_time is not None and current_state:
                delta = int((ts_utc - prev_time).total_seconds())
                if delta > 0:
                    durations_by_state.setdefault(current_state, []).append(delta)
            prev_time = ts_utc
            current_state = to_cat
        # Trailing open interval: time spent in the current state from the last
        # transition up to ``until``.
        if prev_time is not None and current_state:
            delta = int((until - prev_time).total_seconds())
            if delta > 0:
                durations_by_state.setdefault(current_state, []).append(delta)

    results = []
    for state in STATUS_ORDER + ["cancelled"]:
        vals = durations_by_state.get(state, [])
        if not vals:
            continue
        results.append(
            {
                "status_category": state,
                "p50_s": _percentile(vals, 0.50),
                "p75_s": _percentile(vals, 0.75),
                "p90_s": _percentile(vals, 0.90),
                "p95_s": _percentile(vals, 0.95),
                "sample_size": len(vals),
            }
        )
    return results


async def get_status_regressions(
    db: AsyncSession,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[dict]:
    """Return issues with a backwards transition: in_progress→todo, in_review→in_progress, done→in_progress."""
    since, until = default_range(date_from, date_to)

    rows = (
        await db.execute(
            select(
                ExternalIssueHistoryEvent.issue_id,
                ExternalIssueHistoryEvent.changed_at,
                ExternalIssueHistoryEvent.from_state_category,
                ExternalIssueHistoryEvent.to_state_category,
                ExternalIssueHistoryEvent.actor_developer_id,
            )
            .where(
                ExternalIssueHistoryEvent.changed_at >= since,
                ExternalIssueHistoryEvent.changed_at <= until,
                ExternalIssueHistoryEvent.from_state_category.isnot(None),
                ExternalIssueHistoryEvent.to_state_category.isnot(None),
            )
        )
    ).all()

    # First pass: identify rows that are actual regressions so we know which
    # issues + actors we need metadata for, then bulk-load both in one query each.
    regression_rows: list = []
    issue_ids_needed: set[int] = set()
    actor_ids_needed: set[int] = set()
    for iid, changed_at, from_cat, to_cat, actor_id in rows:
        if from_cat not in STATUS_ORDER or to_cat not in STATUS_ORDER:
            continue
        if STATUS_ORDER.index(to_cat) < STATUS_ORDER.index(from_cat):
            regression_rows.append((iid, changed_at, from_cat, to_cat, actor_id))
            issue_ids_needed.add(iid)
            if actor_id:
                actor_ids_needed.add(actor_id)

    issues_by_id: dict[int, ExternalIssue] = {}
    if issue_ids_needed:
        result = await db.execute(
            select(ExternalIssue).where(ExternalIssue.id.in_(issue_ids_needed))
        )
        issues_by_id = {iss.id: iss for iss in result.scalars().all()}

    actor_names_by_id: dict[int, str | None] = {}
    if actor_ids_needed:
        result = await db.execute(
            select(Developer.id, Developer.display_name).where(
                Developer.id.in_(actor_ids_needed)
            )
        )
        actor_names_by_id = {row[0]: row[1] for row in result.all()}

    regressions = []
    for iid, changed_at, from_cat, to_cat, actor_id in regression_rows:
        issue = issues_by_id.get(iid)
        if not issue:
            continue
        regressions.append(
            {
                "issue_id": iid,
                "identifier": issue.identifier,
                "title": issue.title,
                "url": issue.url,
                "from_status": from_cat,
                "to_status": to_cat,
                "changed_at": changed_at.isoformat() if changed_at else None,
                "actor_id": actor_id,
                "actor_name": actor_names_by_id.get(actor_id) if actor_id else None,
            }
        )
    return regressions


async def get_triage_bounces(
    db: AsyncSession,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[dict]:
    """Issues that left triage then came back — unclear scope signal."""
    since, until = default_range(date_from, date_to)

    rows = (
        await db.execute(
            select(
                ExternalIssueHistoryEvent.issue_id,
                ExternalIssueHistoryEvent.changed_at,
                ExternalIssueHistoryEvent.from_state_category,
                ExternalIssueHistoryEvent.to_state_category,
            )
            .where(
                ExternalIssueHistoryEvent.changed_at >= since,
                ExternalIssueHistoryEvent.changed_at <= until,
            )
            .order_by(ExternalIssueHistoryEvent.issue_id, ExternalIssueHistoryEvent.changed_at)
        )
    ).all()

    by_issue: dict[int, list] = {}
    for iid, changed_at, from_cat, to_cat in rows:
        by_issue.setdefault(iid, []).append((changed_at, from_cat, to_cat))

    # First pass: identify bouncing issue IDs — batch-load their metadata next.
    bouncing_ids: list[int] = []
    for iid, events in by_issue.items():
        left_triage = False
        for _ts, from_cat, to_cat in events:
            if from_cat == "triage" and to_cat != "triage":
                left_triage = True
            elif left_triage and to_cat == "triage":
                bouncing_ids.append(iid)
                break

    if not bouncing_ids:
        return []

    issues_result = await db.execute(
        select(ExternalIssue).where(ExternalIssue.id.in_(bouncing_ids))
    )
    issues_by_id = {iss.id: iss for iss in issues_result.scalars().all()}
    bounces = []
    for iid in bouncing_ids:
        issue = issues_by_id.get(iid)
        if issue:
            bounces.append(
                {
                    "issue_id": iid,
                    "identifier": issue.identifier,
                    "title": issue.title,
                    "url": issue.url,
                }
            )
    return bounces


async def get_refinement_churn(
    db: AsyncSession,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 20,
) -> dict:
    """For each issue, count estimate/priority/project changes before work started.

    Returns both per-issue churn scores (top N) and the aggregate distribution.
    """
    since, until = default_range(date_from, date_to)

    # Each history row counts as 1 churn event if any of estimate/priority/project changed
    rows = (
        await db.execute(
            select(
                ExternalIssueHistoryEvent.issue_id,
                ExternalIssueHistoryEvent.changed_at,
                ExternalIssueHistoryEvent.from_estimate,
                ExternalIssueHistoryEvent.to_estimate,
                ExternalIssueHistoryEvent.from_priority,
                ExternalIssueHistoryEvent.to_priority,
                ExternalIssueHistoryEvent.from_project_id,
                ExternalIssueHistoryEvent.to_project_id,
            )
            .where(
                ExternalIssueHistoryEvent.changed_at >= since,
                ExternalIssueHistoryEvent.changed_at <= until,
            )
            .order_by(ExternalIssueHistoryEvent.issue_id, ExternalIssueHistoryEvent.changed_at)
        )
    ).all()

    # Batch-load started_at for all candidate issues in a single query rather
    # than iterating db.get() per row (the prior N-query pattern).
    issue_ids = list({r.issue_id for r in rows})
    started_at: dict[int, datetime | None] = {}
    if issue_ids:
        iss_result = await db.execute(
            select(ExternalIssue.id, ExternalIssue.started_at).where(
                ExternalIssue.id.in_(issue_ids)
            )
        )
        started_at = {iid: st for iid, st in iss_result.all()}

    churn_by_issue: dict[int, int] = {}
    for r in rows:
        start = started_at.get(r.issue_id)
        if start:
            changed = r.changed_at
            if changed and changed.tzinfo is None:
                changed = changed.replace(tzinfo=timezone.utc)
            start_utc = start.replace(tzinfo=timezone.utc) if start.tzinfo is None else start
            if changed and changed >= start_utc:
                continue  # only count pre-start churn
        changed_fields = 0
        if (r.from_estimate, r.to_estimate) != (None, None) and r.from_estimate != r.to_estimate:
            changed_fields += 1
        if (r.from_priority, r.to_priority) != (None, None) and r.from_priority != r.to_priority:
            changed_fields += 1
        if (r.from_project_id, r.to_project_id) != (None, None) and r.from_project_id != r.to_project_id:
            changed_fields += 1
        if changed_fields:
            churn_by_issue[r.issue_id] = churn_by_issue.get(r.issue_id, 0) + changed_fields

    # Top-N outliers — batch-load their metadata in one round trip
    top = sorted(churn_by_issue.items(), key=lambda x: x[1], reverse=True)[:limit]
    top_ids = [iid for iid, _ in top]
    issues_by_id: dict[int, ExternalIssue] = {}
    if top_ids:
        iss_result = await db.execute(
            select(ExternalIssue).where(ExternalIssue.id.in_(top_ids))
        )
        issues_by_id = {iss.id: iss for iss in iss_result.scalars().all()}
    outliers = []
    for iid, score in top:
        issue = issues_by_id.get(iid)
        if not issue:
            continue
        outliers.append(
            {
                "issue_id": iid,
                "identifier": issue.identifier,
                "title": issue.title,
                "url": issue.url,
                "churn_events": score,
            }
        )

    values = list(churn_by_issue.values())
    distribution = {
        "p50": _percentile(values, 0.50),
        "p90": _percentile(values, 0.90),
        "mean": float(mean(values)) if values else 0.0,
        "total_issues_with_churn": len(values),
    }

    return {"distribution": distribution, "top": outliers}
