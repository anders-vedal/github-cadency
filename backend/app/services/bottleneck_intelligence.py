"""Phase 07 — Bottleneck and flow intelligence service.

Unified surface answering: where is work stuck, who is overloaded, where are silos?
Combines Linear flow + GitHub review data. All functions are standalone and composable.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Developer,
    ExternalIssue,
    ExternalIssueHistoryEvent,
    ExternalIssueRelation,
    ExternalSprint,
    PRExternalIssueLink,
    PRFile,
    PRReview,
    PullRequest,
    Repository,
)
from app.services.utils import default_range


def _percentile(values: list, p: float) -> float:
    if not values:
        return 0.0
    sv = sorted(values)
    k = max(0, min(len(sv) - 1, int(len(sv) * p)))
    return sv[k]


async def get_cumulative_flow(
    db: AsyncSession,
    *,
    cycle_id: int | None = None,
    project_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[dict]:
    """Cumulative Flow Diagram — day-by-day counts of issues in each status category.

    Reconstructs historical state by walking ExternalIssueHistoryEvent backwards
    from the current state. Returns: [{"date": str, "triage": n, "todo": n,
    "in_progress": n, "in_review": n, "done": n, "cancelled": n}, ...]
    """
    since, until = default_range(date_from, date_to)

    # Scope: issues in the selected cycle/project (or all)
    issue_query = select(ExternalIssue.id, ExternalIssue.status_category)
    if cycle_id is not None:
        issue_query = issue_query.where(ExternalIssue.sprint_id == cycle_id)
    if project_id is not None:
        issue_query = issue_query.where(ExternalIssue.project_id == project_id)

    issues = {i: cat for i, cat in (await db.execute(issue_query)).all()}
    if not issues:
        return []

    # Load history events for these issues within range
    events_rows = (
        await db.execute(
            select(
                ExternalIssueHistoryEvent.issue_id,
                ExternalIssueHistoryEvent.changed_at,
                ExternalIssueHistoryEvent.from_state_category,
                ExternalIssueHistoryEvent.to_state_category,
            )
            .where(
                ExternalIssueHistoryEvent.issue_id.in_(issues.keys()),
                ExternalIssueHistoryEvent.to_state_category.isnot(None),
            )
            .order_by(ExternalIssueHistoryEvent.issue_id, ExternalIssueHistoryEvent.changed_at)
        )
    ).all()

    # For each day in range, compute the state each issue was in at EOD
    days: list[datetime] = []
    cur = since
    while cur <= until:
        days.append(cur)
        cur += timedelta(days=1)

    # Per-issue history sorted by time
    events_by_issue: dict[int, list] = defaultdict(list)
    for iid, ts, from_cat, to_cat in events_rows:
        events_by_issue[iid].append((ts, from_cat, to_cat))

    result = []
    status_cats = ["triage", "backlog", "todo", "in_progress", "in_review", "done", "cancelled"]

    for d in days:
        day_end = d.replace(hour=23, minute=59, second=59, tzinfo=timezone.utc) if d.tzinfo is None else d
        counts = {cat: 0 for cat in status_cats}
        for iid, current_cat in issues.items():
            issue_events = events_by_issue.get(iid, [])
            # Walk events up to day_end; state is the latest to_state_category at/before that time
            state = None
            first_event_from = None
            for ts, from_cat, to_cat in issue_events:
                ts_utc = ts.replace(tzinfo=timezone.utc) if ts and ts.tzinfo is None else ts
                if first_event_from is None:
                    first_event_from = from_cat  # state BEFORE the first known transition
                if ts_utc and ts_utc <= day_end:
                    state = to_cat
                else:
                    break
            if state is None:
                # Day predates all known events for this issue.
                # Use the from_state of the first event (the state before any transition);
                # if the issue has no history at all, fall back to current state.
                state = first_event_from or current_cat
            if state in counts:
                counts[state] += 1
        result.append({"date": d.strftime("%Y-%m-%d"), **counts})
    return result


async def get_wip_per_developer(
    db: AsyncSession,
    *,
    as_of: datetime | None = None,
    limit: int = 4,
) -> list[dict]:
    """Developers with current in_progress issue count > limit (configurable)."""
    rows = (
        await db.execute(
            select(
                ExternalIssue.assignee_developer_id,
                func.count(ExternalIssue.id),
            )
            .where(
                ExternalIssue.status_category == "in_progress",
                ExternalIssue.assignee_developer_id.isnot(None),
            )
            .group_by(ExternalIssue.assignee_developer_id)
            .having(func.count(ExternalIssue.id) > limit)
            .order_by(func.count(ExternalIssue.id).desc())
        )
    ).all()

    out = []
    for dev_id, count in rows:
        dev = await db.get(Developer, dev_id)
        # Fetch the issues for drill-down
        issues = (
            await db.execute(
                select(ExternalIssue.id, ExternalIssue.identifier, ExternalIssue.title)
                .where(
                    ExternalIssue.assignee_developer_id == dev_id,
                    ExternalIssue.status_category == "in_progress",
                )
            )
        ).all()
        out.append(
            {
                "developer_id": dev_id,
                "developer_name": dev.display_name if dev else "Unknown",
                "in_progress_count": int(count),
                "threshold": limit,
                "issues": [
                    {"id": i, "identifier": ident, "title": title}
                    for i, ident, title in issues
                ],
            }
        )
    return out


def _gini_coefficient(values: list[int]) -> float:
    """Compute Gini coefficient. 0 = perfect equality, 1 = maximal inequality."""
    if not values or sum(values) == 0:
        return 0.0
    sv = sorted(values)
    n = len(sv)
    cum = 0
    total = 0
    for i, v in enumerate(sv, start=1):
        cum += i * v
        total += v
    return (2 * cum) / (n * total) - (n + 1) / n


async def get_review_load_gini(
    db: AsyncSession,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    top_k: int = 10,
) -> dict:
    """Gini coefficient of PR-review counts across active reviewers, plus top-K list."""
    since, until = default_range(date_from, date_to)

    rows = (
        await db.execute(
            select(PRReview.reviewer_id, func.count(PRReview.id))
            .where(
                PRReview.submitted_at >= since,
                PRReview.submitted_at <= until,
                PRReview.reviewer_id.isnot(None),
            )
            .group_by(PRReview.reviewer_id)
        )
    ).all()

    counts = [c for _r, c in rows]
    gini = _gini_coefficient(counts)

    top = sorted(rows, key=lambda x: x[1], reverse=True)[:top_k]
    top_list = []
    for rid, n in top:
        dev = await db.get(Developer, rid)
        top_list.append(
            {
                "reviewer_id": rid,
                "reviewer_name": dev.display_name if dev else "Unknown",
                "review_count": int(n),
            }
        )

    total_reviews = sum(counts)
    top_share = sum(c for _r, c in top) / total_reviews if total_reviews else 0.0

    return {
        "gini": gini,
        "total_reviews": total_reviews,
        "total_reviewers": len(rows),
        "top_k_share": top_share,
        "top_reviewers": top_list,
    }


async def get_review_network(
    db: AsyncSession,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict:
    """Edges: reviewer_id → author_id weighted by review count. Client runs community detection."""
    since, until = default_range(date_from, date_to)

    rows = (
        await db.execute(
            select(
                PRReview.reviewer_id,
                PullRequest.author_id,
                func.count(PRReview.id),
            )
            .join(PullRequest, PullRequest.id == PRReview.pr_id)
            .where(
                PRReview.submitted_at >= since,
                PRReview.submitted_at <= until,
                PRReview.reviewer_id.isnot(None),
                PullRequest.author_id.isnot(None),
                PRReview.reviewer_id != PullRequest.author_id,
            )
            .group_by(PRReview.reviewer_id, PullRequest.author_id)
        )
    ).all()

    # Collect unique developer ids
    dev_ids = {r for r, _a, _n in rows} | {a for _r, a, _n in rows}
    devs = {}
    if dev_ids:
        dev_rows = (await db.execute(select(Developer).where(Developer.id.in_(dev_ids)))).scalars().all()
        devs = {d.id: d for d in dev_rows}

    nodes = [
        {"id": d.id, "name": d.display_name or d.github_username, "team": d.team}
        for d in devs.values()
    ]
    edges = [
        {"reviewer_id": r, "author_id": a, "weight": int(n)}
        for r, a, n in rows
    ]
    return {"nodes": nodes, "edges": edges}


async def get_cross_team_handoffs(
    db: AsyncSession,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[dict]:
    """Issues that moved between cycles belonging to different teams."""
    since, until = default_range(date_from, date_to)

    rows = (
        await db.execute(
            select(
                ExternalIssueHistoryEvent.issue_id,
                ExternalIssueHistoryEvent.changed_at,
                ExternalIssueHistoryEvent.from_cycle_id,
                ExternalIssueHistoryEvent.to_cycle_id,
            )
            .where(
                ExternalIssueHistoryEvent.changed_at >= since,
                ExternalIssueHistoryEvent.changed_at <= until,
                ExternalIssueHistoryEvent.from_cycle_id.isnot(None),
                ExternalIssueHistoryEvent.to_cycle_id.isnot(None),
            )
        )
    ).all()

    handoffs = []
    for iid, ts, from_cycle_id, to_cycle_id in rows:
        from_cycle = await db.get(ExternalSprint, from_cycle_id)
        to_cycle = await db.get(ExternalSprint, to_cycle_id)
        if not (from_cycle and to_cycle):
            continue
        if (from_cycle.team_key or "") == (to_cycle.team_key or ""):
            continue
        issue = await db.get(ExternalIssue, iid)
        handoffs.append(
            {
                "issue_id": iid,
                "identifier": issue.identifier if issue else None,
                "title": issue.title if issue else None,
                "from_team": from_cycle.team_name or from_cycle.team_key,
                "to_team": to_cycle.team_name or to_cycle.team_key,
                "changed_at": ts.isoformat() if ts else None,
            }
        )
    return handoffs


async def get_blocked_chains(db: AsyncSession) -> list[dict]:
    """Longest blocked-by chains among OPEN issues. Chains depth 3+ are serialized risks."""
    # Load all blocks relations over open issues
    rows = (
        await db.execute(
            select(
                ExternalIssueRelation.issue_id,
                ExternalIssueRelation.related_issue_id,
            )
            .join(ExternalIssue, ExternalIssue.id == ExternalIssueRelation.issue_id)
            .where(
                ExternalIssueRelation.relation_type == "blocked_by",
                ExternalIssue.status_category.notin_(["done", "cancelled"]),
            )
        )
    ).all()

    # Adjacency list: issue -> list of issues that block it
    blocked_by: dict[int, list[int]] = defaultdict(list)
    for iid, related_id in rows:
        blocked_by[iid].append(related_id)

    # Compute depth of blocked-by chain rooted at each issue
    depths: dict[int, int] = {}

    def compute_depth(iid: int, visited: set) -> int:
        if iid in visited:
            return 0  # cycle guard
        if iid in depths:
            return depths[iid]
        visited.add(iid)
        blockers = blocked_by.get(iid, [])
        d = 0
        for b in blockers:
            d = max(d, 1 + compute_depth(b, visited.copy()))
        depths[iid] = d
        return d

    for iid in blocked_by.keys():
        compute_depth(iid, set())

    results = []
    for iid, depth in sorted(depths.items(), key=lambda x: x[1], reverse=True):
        if depth < 2:
            continue
        issue = await db.get(ExternalIssue, iid)
        if not issue:
            continue
        results.append(
            {
                "issue_id": iid,
                "identifier": issue.identifier,
                "title": issue.title,
                "status": issue.status,
                "blocker_depth": depth,
            }
        )
    return results


async def get_review_ping_pong(
    db: AsyncSession,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[dict]:
    """PRs with review_round_count > 3 — strong friction signal."""
    since, until = default_range(date_from, date_to)

    rows = (
        await db.execute(
            select(
                PullRequest.id,
                PullRequest.number,
                PullRequest.title,
                PullRequest.review_round_count,
                PullRequest.author_id,
                PullRequest.state,
                PullRequest.html_url,
                Repository.full_name,
            )
            .join(Repository, Repository.id == PullRequest.repo_id)
            .where(
                PullRequest.review_round_count > 3,
                PullRequest.created_at >= since,
                PullRequest.created_at <= until,
            )
            .order_by(PullRequest.review_round_count.desc())
        )
    ).all()

    out = []
    for r in rows:
        out.append(
            {
                "pr_id": r.id,
                "number": r.number,
                "title": r.title,
                "review_round_count": r.review_round_count,
                "author_id": r.author_id,
                "state": r.state,
                "html_url": r.html_url,
                "repo": r.full_name,
            }
        )
    return out


async def get_bus_factor_by_file(
    db: AsyncSession,
    *,
    since_days: int = 90,
    min_authors: int = 2,
    top_limit: int = 50,
) -> list[dict]:
    """Files with fewer than min_authors distinct PR authors in the last N days."""
    since = datetime.now(timezone.utc) - timedelta(days=since_days)

    rows = (
        await db.execute(
            select(
                PRFile.filename,
                func.count(func.distinct(PullRequest.author_id)).label("authors"),
            )
            .join(PullRequest, PullRequest.id == PRFile.pr_id)
            .where(
                PullRequest.created_at >= since,
                PullRequest.author_id.isnot(None),
            )
            .group_by(PRFile.filename)
            .having(func.count(func.distinct(PullRequest.author_id)) < min_authors)
            .order_by(func.count(PRFile.id).desc())
            .limit(top_limit)
        )
    ).all()

    results = []
    for filename, author_count in rows:
        # Find the single owner
        owner_row = (
            await db.execute(
                select(PullRequest.author_id, func.count())
                .join(PRFile, PRFile.pr_id == PullRequest.id)
                .where(
                    PRFile.filename == filename,
                    PullRequest.created_at >= since,
                )
                .group_by(PullRequest.author_id)
                .order_by(func.count().desc())
                .limit(1)
            )
        ).first()
        owner_name = None
        if owner_row:
            owner_id = owner_row[0]
            if owner_id:
                dev = await db.get(Developer, owner_id)
                owner_name = dev.display_name if dev else None
        results.append(
            {
                "filename": filename,
                "distinct_authors": int(author_count),
                "owner_name": owner_name,
            }
        )
    return results


def _detect_bimodal(values: list[float]) -> dict:
    """Simple bimodality detection: find two peaks separated by a trough > 20% of lower peak."""
    if len(values) < 10:
        return {"is_bimodal": False, "peaks": [], "trough_ratio": None}

    sv = sorted(values)
    # Bin into 10 buckets
    n_bins = 10
    lo, hi = sv[0], sv[-1]
    if lo == hi:
        return {"is_bimodal": False, "peaks": [], "trough_ratio": None}
    span = hi - lo
    bucket_size = span / n_bins
    bins = [0] * n_bins
    for v in sv:
        idx = min(n_bins - 1, int((v - lo) / bucket_size))
        bins[idx] += 1

    # Find local maxima
    peaks = []
    for i in range(1, n_bins - 1):
        if bins[i] > bins[i - 1] and bins[i] > bins[i + 1] and bins[i] >= 2:
            peaks.append((i, bins[i]))
    if bins[0] > bins[1] and bins[0] >= 2:
        peaks.insert(0, (0, bins[0]))
    if bins[-1] > bins[-2] and bins[-1] >= 2:
        peaks.append((n_bins - 1, bins[-1]))

    if len(peaks) < 2:
        return {"is_bimodal": False, "peaks": peaks, "trough_ratio": None}

    # Sort peaks by magnitude desc, pick top 2
    peaks_sorted = sorted(peaks, key=lambda x: x[1], reverse=True)[:2]
    peaks_sorted.sort(key=lambda x: x[0])
    (idx1, h1), (idx2, h2) = peaks_sorted
    trough = min(bins[idx1 + 1 : idx2] or [0])
    lower_peak = min(h1, h2)
    ratio = trough / lower_peak if lower_peak else 1.0

    return {
        "is_bimodal": ratio < 0.8 and (idx2 - idx1) > 1,
        "peaks": [{"bin": idx1, "count": h1}, {"bin": idx2, "count": h2}],
        "trough_ratio": ratio,
        "bins": bins,
        "bucket_size": bucket_size,
        "min": lo,
        "max": hi,
    }


async def get_cycle_time_histogram(
    db: AsyncSession,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict:
    """Cycle time histogram + bimodality detection."""
    since, until = default_range(date_from, date_to)

    rows = (
        await db.execute(
            select(PullRequest.time_to_merge_s)
            .where(
                PullRequest.merged_at >= since,
                PullRequest.merged_at <= until,
                PullRequest.time_to_merge_s.isnot(None),
            )
        )
    ).all()
    values = [r[0] for r in rows if r[0] is not None and r[0] > 0]

    return {
        "sample_size": len(values),
        "p50_s": int(_percentile(values, 0.50)),
        "p90_s": int(_percentile(values, 0.90)),
        "bimodal_analysis": _detect_bimodal([float(v) for v in values]),
    }


async def get_bottleneck_summary(db: AsyncSession) -> list[dict]:
    """Single-digest: top 5 active bottlenecks with one-line summaries.

    Deterministic scoring rule (documented inline):
      - Review load Gini > 0.4 → "Review load imbalance"
      - WIP over 4 per developer for any dev → "WIP violation"
      - Blocked chain depth >= 3 → "Blocked serialization"
      - Ping-pong PRs > 0 → "Review ping-pong"
      - Cross-team handoffs in last 30d > 5 → "Cross-team friction"
    """
    digest = []

    # Gini
    try:
        gini_result = await get_review_load_gini(db)
        if gini_result["gini"] > 0.4:
            digest.append(
                {
                    "title": "Review load imbalance",
                    "severity": "warning",
                    "detail": (
                        f"{gini_result['total_reviewers']} reviewers; top {len(gini_result['top_reviewers'])} "
                        f"handle {int(gini_result['top_k_share'] * 100)}% of reviews "
                        f"(Gini {gini_result['gini']:.2f})"
                    ),
                    "drill_path": "/insights/bottlenecks#review-load",
                }
            )
    except Exception:
        pass

    # WIP
    try:
        wip = await get_wip_per_developer(db, limit=4)
        if wip:
            digest.append(
                {
                    "title": "WIP violation",
                    "severity": "critical" if len(wip) >= 3 else "warning",
                    "detail": f"{len(wip)} developer(s) have >4 in-progress issues",
                    "drill_path": "/insights/bottlenecks#wip",
                }
            )
    except Exception:
        pass

    # Blocked chains
    try:
        chains = await get_blocked_chains(db)
        deep = [c for c in chains if c["blocker_depth"] >= 3]
        if deep:
            digest.append(
                {
                    "title": "Blocked serialization",
                    "severity": "warning",
                    "detail": f"{len(deep)} issues in blocking chains of depth 3+",
                    "drill_path": "/insights/bottlenecks#blocked-chains",
                }
            )
    except Exception:
        pass

    # Ping-pong
    try:
        pp = await get_review_ping_pong(db)
        open_pp = [p for p in pp if p["state"] != "merged"]
        if open_pp:
            digest.append(
                {
                    "title": "Review ping-pong",
                    "severity": "warning",
                    "detail": f"{len(open_pp)} open PRs with >3 review rounds",
                    "drill_path": "/insights/bottlenecks#ping-pong",
                }
            )
    except Exception:
        pass

    # Cross-team handoffs
    try:
        handoffs = await get_cross_team_handoffs(db)
        if len(handoffs) > 5:
            digest.append(
                {
                    "title": "Cross-team friction",
                    "severity": "info",
                    "detail": f"{len(handoffs)} issues bounced between teams recently",
                    "drill_path": "/insights/bottlenecks#cross-team",
                }
            )
    except Exception:
        pass

    return digest[:5]
