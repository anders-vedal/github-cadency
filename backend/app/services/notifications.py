"""Notification center: alert evaluation, lifecycle management, and config."""

import statistics
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger
from app.models.models import (
    AISettings,
    Developer,
    ExternalIssue,
    ExternalSprint,
    IntegrationConfig,
    Issue,
    Notification,
    NotificationConfig,
    NotificationDismissal,
    NotificationRead,
    NotificationTypeDismissal,
    PRReview,
    PullRequest,
    Repository,
    RoleDefinition,
    SyncEvent,
)
from app.schemas.schemas import (
    NotificationConfigResponse,
    NotificationConfigUpdate,
    NotificationResponse,
    NotificationsListResponse,
)

logger = get_logger(__name__)

# ── Alert type metadata registry ──────────────────────────────────────────

ALERT_TYPE_META: dict[str, dict] = {
    "stale_pr": {
        "label": "Stale Pull Requests",
        "description": "PRs waiting too long for review, with unresolved changes, or approved but not merged",
        "thresholds": [{"field": "stale_pr_threshold_hours", "label": "Threshold", "unit": "hours", "min": 1, "max": 720}],
    },
    "review_bottleneck": {
        "label": "Review Bottlenecks",
        "description": "Developers handling disproportionately more reviews than the team median",
        "thresholds": [{"field": "review_bottleneck_multiplier", "label": "Multiplier", "unit": "x median", "min": 1.5, "max": 10}],
    },
    "underutilized": {
        "label": "Underutilized Developers",
        "description": "Developers with zero PRs and zero reviews in the evaluation period",
        "thresholds": [],
    },
    "uneven_assignment": {
        "label": "Uneven Issue Assignment",
        "description": "Top 20% of developers hold more than 50% of open issues",
        "thresholds": [],
    },
    "merged_without_approval": {
        "label": "Merged Without Approval",
        "description": "PRs merged without any approving review",
        "thresholds": [],
    },
    "revert_spike": {
        "label": "Revert Spike",
        "description": "Team revert rate exceeds threshold percentage of merged PRs",
        "thresholds": [{"field": "revert_spike_threshold_pct", "label": "Threshold", "unit": "%", "min": 1, "max": 50}],
    },
    "high_risk_pr": {
        "label": "High-Risk Pull Requests",
        "description": "Open PRs with risk score at or above the configured level",
        "thresholds": [{"field": "high_risk_pr_min_level", "label": "Minimum level", "unit": "", "min": 0, "max": 0}],
    },
    "bus_factor": {
        "label": "Bus Factor Risk",
        "description": "A single reviewer handles >70% of reviews for a repository",
        "thresholds": [],
    },
    "team_silo": {
        "label": "Team Silos",
        "description": "Two teams with zero cross-team code reviews",
        "thresholds": [],
    },
    "isolated_developer": {
        "label": "Isolated Developers",
        "description": "Developers with minimal review interaction",
        "thresholds": [],
    },
    "declining_trend": {
        "label": "Declining Developer Trends",
        "description": "Developer metrics dropped significantly vs previous period",
        "thresholds": [
            {"field": "declining_trend_pr_drop_pct", "label": "PR drop", "unit": "%", "min": 10, "max": 90},
            {"field": "declining_trend_quality_drop_pct", "label": "Quality drop", "unit": "%", "min": 10, "max": 90},
        ],
    },
    "issue_linkage": {
        "label": "Low Issue Linkage",
        "description": "Developers with PR-to-issue linkage rate below threshold",
        "thresholds": [{"field": "issue_linkage_threshold_pct", "label": "Threshold", "unit": "%", "min": 0, "max": 100}],
    },
    "ai_budget": {
        "label": "AI Budget Warning",
        "description": "AI token usage approaching or exceeding the configured budget",
        "thresholds": [],
    },
    "sync_failure": {
        "label": "Sync Failures",
        "description": "Most recent sync failed or completed with errors",
        "thresholds": [],
    },
    "unassigned_roles": {
        "label": "Unassigned Roles",
        "description": "Active developers without a role assignment",
        "thresholds": [],
    },
    "missing_config": {
        "label": "Missing Configuration",
        "description": "Required configuration values not set (GitHub App, API keys, etc.)",
        "thresholds": [],
    },
    "velocity_declining": {
        "label": "Velocity Declining",
        "description": "Sprint velocity has declined significantly over recent sprints",
        "thresholds": [{"field": "velocity_decline_pct", "label": "Decline threshold", "unit": "%", "min": 5, "max": 80}],
    },
    "scope_creep_high": {
        "label": "High Scope Creep",
        "description": "Recent sprint had excessive mid-cycle scope additions",
        "thresholds": [{"field": "scope_creep_threshold_pct", "label": "Threshold", "unit": "%", "min": 5, "max": 80}],
    },
    "sprint_at_risk": {
        "label": "Sprint At Risk",
        "description": "Active sprint is behind on completion with limited time remaining",
        "thresholds": [{"field": "sprint_risk_completion_pct", "label": "Min completion", "unit": "%", "min": 10, "max": 90}],
    },
    "triage_queue_growing": {
        "label": "Triage Queue Growing",
        "description": "Too many issues waiting for triage or taking too long to triage",
        "thresholds": [
            {"field": "triage_queue_max", "label": "Max queue size", "unit": "issues", "min": 1, "max": 200},
            {"field": "triage_duration_hours_max", "label": "Max duration", "unit": "hours", "min": 1, "max": 720},
        ],
    },
    "estimation_accuracy_low": {
        "label": "Estimation Accuracy Low",
        "description": "Sprint estimation accuracy is trending below acceptable levels",
        "thresholds": [{"field": "estimation_accuracy_min_pct", "label": "Min accuracy", "unit": "%", "min": 10, "max": 95}],
    },
    "linear_sync_failure": {
        "label": "Linear Sync Failed",
        "description": "Most recent Linear data sync failed",
        "thresholds": [],
    },
}


# ── Config CRUD (singleton pattern) ──────────────────────────────────────


async def get_notification_config(db: AsyncSession) -> NotificationConfig:
    row = await db.get(NotificationConfig, 1)
    if not row:
        row = NotificationConfig(id=1)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


async def update_notification_config(
    db: AsyncSession, updates: NotificationConfigUpdate, updated_by: str
) -> NotificationConfig:
    row = await get_notification_config(db)
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = datetime.now(timezone.utc)
    row.updated_by = updated_by
    await db.commit()
    await db.refresh(row)
    return row


def build_config_response(config: NotificationConfig) -> NotificationConfigResponse:
    alert_types = []
    for key, meta in ALERT_TYPE_META.items():
        toggle_field = f"alert_{key}_enabled"
        enabled = getattr(config, toggle_field, True)
        thresholds = []
        for t in meta.get("thresholds", []):
            thresholds.append({**t, "value": getattr(config, t["field"], None)})
        alert_types.append({
            "key": key,
            "label": meta["label"],
            "description": meta["description"],
            "enabled": enabled,
            "thresholds": thresholds,
        })

    resp = NotificationConfigResponse.model_validate(config)
    resp.alert_types = alert_types
    return resp


# ── Excluded developer resolution ────────────────────────────────────────


async def _get_excluded_developer_ids(
    db: AsyncSession, excluded_categories: list[str] | None
) -> set[int]:
    if not excluded_categories:
        return set()
    excluded_roles = await db.execute(
        select(RoleDefinition.role_key).where(
            RoleDefinition.contribution_category.in_(excluded_categories)
        )
    )
    role_keys = [r[0] for r in excluded_roles.all()]
    if not role_keys:
        return set()
    dev_result = await db.execute(
        select(Developer.id).where(
            Developer.role.in_(role_keys),
            Developer.is_active.is_(True),
        )
    )
    return {row[0] for row in dev_result.all()}


# ── Upsert + auto-resolve helpers ────────────────────────────────────────


async def _upsert_notification(
    db: AsyncSession,
    alert_key: str,
    alert_type: str,
    severity: str,
    title: str,
    body: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    link_path: str | None = None,
    developer_id: int | None = None,
    metadata: dict | None = None,
) -> tuple[str, Notification]:
    """Create or update a notification. Returns ("created"|"updated", notification)."""
    existing = await db.execute(
        select(Notification).where(Notification.alert_key == alert_key)
    )
    notif = existing.scalar_one_or_none()

    if notif:
        notif.severity = severity
        notif.title = title
        notif.body = body
        notif.link_path = link_path
        notif.metadata_ = metadata
        notif.updated_at = datetime.now(timezone.utc)
        if notif.resolved_at is not None:
            notif.resolved_at = None  # re-open
        return ("updated", notif)
    else:
        notif = Notification(
            alert_type=alert_type,
            alert_key=alert_key,
            severity=severity,
            title=title,
            body=body,
            entity_type=entity_type,
            entity_id=entity_id,
            link_path=link_path,
            developer_id=developer_id,
            metadata_=metadata,
        )
        db.add(notif)
        return ("created", notif)


async def _auto_resolve_stale(
    db: AsyncSession, alert_type: str, active_keys: set[str]
) -> int:
    """Resolve notifications whose condition has cleared."""
    now = datetime.now(timezone.utc)
    stmt = select(Notification).where(
        Notification.alert_type == alert_type,
        Notification.resolved_at.is_(None),
    )
    if active_keys:
        stmt = stmt.where(Notification.alert_key.notin_(active_keys))
    result = await db.execute(stmt)
    stale = result.scalars().all()
    for n in stale:
        n.resolved_at = now
    return len(stale)


# ── Individual evaluators ────────────────────────────────────────────────


def _ensure_tz(dt: datetime | None) -> datetime | None:
    """Ensure a datetime is timezone-aware (SQLite stores naive datetimes)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def _evaluate_stale_pr_alerts(
    db: AsyncSession, config: NotificationConfig, excluded_dev_ids: set[int]
) -> set[str]:
    active_keys: set[str] = set()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=config.stale_pr_threshold_hours)

    # No review
    stmt = (
        select(PullRequest)
        .where(
            PullRequest.state == "open",
            PullRequest.is_draft.isnot(True),
            PullRequest.first_review_at.is_(None),
            PullRequest.created_at <= cutoff,
        )
    )
    result = await db.execute(stmt)
    for pr in result.scalars().all():
        if pr.author_id and pr.author_id in excluded_dev_ids:
            continue
        created = _ensure_tz(pr.created_at)
        age_h = (now - created).total_seconds() / 3600 if created else 0
        severity = "critical" if age_h >= 72 else "warning"
        key = f"stale_pr:pr:{pr.id}"
        active_keys.add(key)
        await _upsert_notification(
            db, alert_key=key, alert_type="stale_pr", severity=severity,
            title=f"PR #{pr.number} waiting {age_h:.0f}h for review",
            body=pr.title, entity_type="pull_request", entity_id=pr.id,
            link_path=pr.html_url, developer_id=pr.author_id,
            metadata={"age_hours": round(age_h, 1), "reason": "no_review"},
        )

    # Changes requested, no response
    subq = (
        select(
            PRReview.pr_id,
            func.max(PRReview.submitted_at).label("last_review_at"),
        )
        .where(PRReview.state == "CHANGES_REQUESTED")
        .group_by(PRReview.pr_id)
        .subquery()
    )
    stmt2 = (
        select(PullRequest, subq.c.last_review_at)
        .join(subq, PullRequest.id == subq.c.pr_id)
        .where(
            PullRequest.state == "open",
            PullRequest.is_draft.isnot(True),
            subq.c.last_review_at <= cutoff,
        )
    )
    result2 = await db.execute(stmt2)
    for pr, last_review_at in result2.all():
        if pr.author_id and pr.author_id in excluded_dev_ids:
            continue
        if pr.updated_at and last_review_at:
            delta = abs((_ensure_tz(pr.updated_at) - _ensure_tz(last_review_at)).total_seconds())
            if delta > 3600:
                continue  # Author has responded
        key = f"stale_pr:pr:{pr.id}"
        if key in active_keys:
            continue
        lr = _ensure_tz(last_review_at)
        age_h = (now - lr).total_seconds() / 3600 if lr else 0
        severity = "critical" if age_h >= 72 else "warning"
        active_keys.add(key)
        await _upsert_notification(
            db, alert_key=key, alert_type="stale_pr", severity=severity,
            title=f"PR #{pr.number} has unresolved changes ({age_h:.0f}h)",
            body=pr.title, entity_type="pull_request", entity_id=pr.id,
            link_path=pr.html_url, developer_id=pr.author_id,
            metadata={"age_hours": round(age_h, 1), "reason": "changes_requested"},
        )

    # Approved but not merged
    subq3 = (
        select(
            PRReview.pr_id,
            func.max(PRReview.submitted_at).label("last_approval_at"),
        )
        .where(PRReview.state == "APPROVED")
        .group_by(PRReview.pr_id)
        .subquery()
    )
    stmt3 = (
        select(PullRequest, subq3.c.last_approval_at)
        .join(subq3, PullRequest.id == subq3.c.pr_id)
        .where(
            PullRequest.state == "open",
            PullRequest.is_draft.isnot(True),
            subq3.c.last_approval_at <= cutoff,
        )
    )
    result3 = await db.execute(stmt3)
    for pr, last_approval_at in result3.all():
        if pr.author_id and pr.author_id in excluded_dev_ids:
            continue
        key = f"stale_pr:pr:{pr.id}"
        if key in active_keys:
            continue
        la = _ensure_tz(last_approval_at)
        age_h = (now - la).total_seconds() / 3600 if la else 0
        active_keys.add(key)
        await _upsert_notification(
            db, alert_key=key, alert_type="stale_pr", severity="info",
            title=f"PR #{pr.number} approved but not merged ({age_h:.0f}h)",
            body=pr.title, entity_type="pull_request", entity_id=pr.id,
            link_path=pr.html_url, developer_id=pr.author_id,
            metadata={"age_hours": round(age_h, 1), "reason": "approved_not_merged"},
        )

    resolved = await _auto_resolve_stale(db, "stale_pr", active_keys)
    return active_keys


async def _evaluate_workload_alerts(
    db: AsyncSession, config: NotificationConfig, excluded_dev_ids: set[int]
) -> set[str]:
    """Evaluate review_bottleneck, underutilized, uneven_assignment, merged_without_approval."""
    active_keys: set[str] = set()
    now = datetime.now(timezone.utc)
    date_from = now - timedelta(days=30)

    devs_result = await db.execute(
        select(Developer).where(Developer.is_active.is_(True))
    )
    developers = [d for d in devs_result.scalars().all() if d.id not in excluded_dev_ids]
    if not developers:
        return active_keys

    dev_ids = [d.id for d in developers]

    # Review bottleneck
    if config.alert_review_bottleneck_enabled:
        review_counts: list[tuple[int, int]] = []
        for dev in developers:
            cnt = await db.scalar(
                select(func.count()).where(
                    PRReview.reviewer_id == dev.id,
                    PRReview.submitted_at >= date_from,
                    PRReview.submitted_at <= now,
                )
            ) or 0
            review_counts.append((dev.id, cnt))

        counts_only = [c for _, c in review_counts]
        if counts_only:
            median_reviews = statistics.median(counts_only)
            if median_reviews > 0:
                for dev_id, cnt in review_counts:
                    if cnt > config.review_bottleneck_multiplier * median_reviews:
                        dev = next(d for d in developers if d.id == dev_id)
                        key = f"review_bottleneck:developer:{dev_id}"
                        active_keys.add(key)
                        await _upsert_notification(
                            db, alert_key=key, alert_type="review_bottleneck",
                            severity="warning",
                            title=f"{dev.display_name} gave {cnt} reviews (median: {median_reviews:.0f})",
                            entity_type="developer", entity_id=dev_id,
                            link_path=f"/team/{dev_id}", developer_id=dev_id,
                            metadata={"review_count": cnt, "team_median": median_reviews},
                        )
        await _auto_resolve_stale(db, "review_bottleneck", active_keys)

    # Underutilized
    if config.alert_underutilized_enabled:
        underutilized_keys: set[str] = set()
        for dev in developers:
            prs = await db.scalar(
                select(func.count()).where(
                    PullRequest.author_id == dev.id,
                    PullRequest.created_at >= date_from,
                    PullRequest.created_at <= now,
                )
            ) or 0
            reviews = await db.scalar(
                select(func.count()).where(
                    PRReview.reviewer_id == dev.id,
                    PRReview.submitted_at >= date_from,
                    PRReview.submitted_at <= now,
                )
            ) or 0
            if prs == 0 and reviews == 0:
                key = f"underutilized:developer:{dev.id}"
                underutilized_keys.add(key)
                active_keys.add(key)
                await _upsert_notification(
                    db, alert_key=key, alert_type="underutilized",
                    severity="info",
                    title=f"{dev.display_name} has 0 PRs and 0 reviews in the last 30 days",
                    entity_type="developer", entity_id=dev.id,
                    link_path=f"/team/{dev.id}", developer_id=dev.id,
                )
        await _auto_resolve_stale(db, "underutilized", underutilized_keys)

    # Uneven assignment
    if config.alert_uneven_assignment_enabled:
        uneven_keys: set[str] = set()
        issue_counts: list[tuple[int, int]] = []
        for dev in developers:
            cnt = await db.scalar(
                select(func.count()).where(
                    Issue.assignee_id == dev.id,
                    Issue.state == "open",
                )
            ) or 0
            issue_counts.append((dev.id, cnt))

        total_issues = sum(c for _, c in issue_counts)
        if total_issues > 0:
            sorted_issues = sorted(issue_counts, key=lambda x: x[1], reverse=True)
            top_20_count = max(1, len(sorted_issues) // 5)
            top_20_total = sum(c for _, c in sorted_issues[:top_20_count])
            if top_20_total > total_issues * 0.5:
                top_names = []
                for dev_id, _ in sorted_issues[:top_20_count]:
                    dev = next(d for d in developers if d.id == dev_id)
                    top_names.append(dev.display_name)
                key = "uneven_assignment:team:all"
                uneven_keys.add(key)
                active_keys.add(key)
                await _upsert_notification(
                    db, alert_key=key, alert_type="uneven_assignment",
                    severity="warning",
                    title=f"Top {top_20_count} dev(s) hold {top_20_total}/{total_issues} open issues",
                    body=f"Developers: {', '.join(top_names)}",
                    entity_type="team", link_path="/insights/workload",
                )
        await _auto_resolve_stale(db, "uneven_assignment", uneven_keys)

    # Merged without approval
    if config.alert_merged_without_approval_enabled:
        mwa_keys: set[str] = set()
        for dev in developers:
            cnt = await db.scalar(
                select(func.count()).where(
                    PullRequest.author_id == dev.id,
                    PullRequest.merged_without_approval.is_(True),
                    PullRequest.merged_at >= date_from,
                    PullRequest.merged_at <= now,
                )
            ) or 0
            if cnt > 0:
                key = f"merged_without_approval:developer:{dev.id}"
                mwa_keys.add(key)
                active_keys.add(key)
                await _upsert_notification(
                    db, alert_key=key, alert_type="merged_without_approval",
                    severity="warning",
                    title=f"{dev.display_name} has {cnt} PR(s) merged without approval",
                    entity_type="developer", entity_id=dev.id,
                    link_path=f"/team/{dev.id}", developer_id=dev.id,
                    metadata={"count": cnt},
                )
        await _auto_resolve_stale(db, "merged_without_approval", mwa_keys)

    return active_keys


async def _evaluate_revert_spike_alert(
    db: AsyncSession, config: NotificationConfig, excluded_dev_ids: set[int]
) -> set[str]:
    active_keys: set[str] = set()
    now = datetime.now(timezone.utc)
    date_from = now - timedelta(days=30)

    dev_ids_q = select(Developer.id).where(
        Developer.is_active.is_(True),
        Developer.id.notin_(excluded_dev_ids) if excluded_dev_ids else True,
    )

    total_merged = await db.scalar(
        select(func.count()).where(
            PullRequest.author_id.in_(dev_ids_q),
            PullRequest.is_merged.is_(True),
            PullRequest.merged_at >= date_from,
            PullRequest.merged_at <= now,
        )
    ) or 0

    total_reverts = await db.scalar(
        select(func.count()).where(
            PullRequest.author_id.in_(dev_ids_q),
            PullRequest.is_revert.is_(True),
            PullRequest.created_at >= date_from,
            PullRequest.created_at <= now,
        )
    ) or 0

    if total_merged > 0:
        revert_pct = total_reverts / total_merged * 100
        if revert_pct > config.revert_spike_threshold_pct:
            key = "revert_spike:team:all"
            active_keys.add(key)
            await _upsert_notification(
                db, alert_key=key, alert_type="revert_spike",
                severity="critical",
                title=f"Revert rate is {revert_pct:.1f}% ({total_reverts}/{total_merged} merged PRs)",
                entity_type="team", link_path="/insights/code-churn",
                metadata={"revert_pct": round(revert_pct, 1), "total_reverts": total_reverts},
            )

    await _auto_resolve_stale(db, "revert_spike", active_keys)
    return active_keys


async def _evaluate_risk_alerts(
    db: AsyncSession, config: NotificationConfig, excluded_dev_ids: set[int]
) -> set[str]:
    from app.services.risk import LEVEL_ORDER, compute_pr_risk

    active_keys: set[str] = set()
    min_level_order = LEVEL_ORDER.get(config.high_risk_pr_min_level, 2)

    from sqlalchemy.orm import selectinload
    stmt = (
        select(PullRequest)
        .options(selectinload(PullRequest.reviews))
        .where(
            PullRequest.state == "open",
            PullRequest.is_draft.isnot(True),
        )
    )
    result = await db.execute(stmt)
    prs = result.scalars().all()

    for pr in prs:
        if pr.author_id and pr.author_id in excluded_dev_ids:
            continue

        author_merged = await db.scalar(
            select(func.count()).where(
                PullRequest.author_id == pr.author_id,
                PullRequest.repo_id == pr.repo_id,
                PullRequest.is_merged.is_(True),
            )
        ) if pr.author_id else None

        factors, score = compute_pr_risk(pr, author_merged)
        level = "low"
        if score >= 0.7:
            level = "critical"
        elif score >= 0.5:
            level = "high"
        elif score >= 0.3:
            level = "medium"

        if LEVEL_ORDER.get(level, 0) >= min_level_order:
            key = f"high_risk_pr:pr:{pr.id}"
            active_keys.add(key)
            severity = "critical" if level == "critical" else "warning"
            await _upsert_notification(
                db, alert_key=key, alert_type="high_risk_pr",
                severity=severity,
                title=f"PR #{pr.number} has {level} risk ({score:.0%})",
                body=pr.title, entity_type="pull_request", entity_id=pr.id,
                link_path=pr.html_url, developer_id=pr.author_id,
                metadata={
                    "risk_score": round(score, 3),
                    "risk_level": level,
                    "factors": [f.factor for f in factors[:5]],
                },
            )

    await _auto_resolve_stale(db, "high_risk_pr", active_keys)
    return active_keys


async def _evaluate_collaboration_alerts(
    db: AsyncSession, config: NotificationConfig, excluded_dev_ids: set[int]
) -> set[str]:
    active_keys: set[str] = set()
    now = datetime.now(timezone.utc)
    date_from = now - timedelta(days=90)

    devs_result = await db.execute(
        select(Developer).where(Developer.is_active.is_(True))
    )
    developers = {d.id: d for d in devs_result.scalars().all() if d.id not in excluded_dev_ids}
    dev_ids = list(developers.keys())
    if not dev_ids:
        return active_keys

    # Bus factors
    if config.alert_bus_factor_enabled:
        bus_keys: set[str] = set()
        repo_review_rows = (
            await db.execute(
                select(
                    PullRequest.repo_id,
                    PRReview.reviewer_id,
                    func.count().label("cnt"),
                )
                .join(PullRequest, PRReview.pr_id == PullRequest.id)
                .where(
                    PRReview.reviewer_id.in_(dev_ids),
                    PRReview.submitted_at >= date_from,
                    PRReview.submitted_at <= now,
                )
                .group_by(PullRequest.repo_id, PRReview.reviewer_id)
            )
        ).all()

        from collections import defaultdict
        repo_totals: dict[int, int] = defaultdict(int)
        repo_reviewer: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        for repo_id, reviewer_id, cnt in repo_review_rows:
            repo_totals[repo_id] += cnt
            repo_reviewer[repo_id][reviewer_id] += cnt

        for repo_id, total in repo_totals.items():
            for reviewer_id, cnt in repo_reviewer[repo_id].items():
                share = cnt / total * 100 if total > 0 else 0
                if share > 70 and reviewer_id in developers:
                    repo = await db.get(Repository, repo_id)
                    repo_name = (repo.full_name or repo.name) if repo else str(repo_id)
                    key = f"bus_factor:repo:{repo_id}"
                    bus_keys.add(key)
                    active_keys.add(key)
                    await _upsert_notification(
                        db, alert_key=key, alert_type="bus_factor",
                        severity="warning",
                        title=f"{developers[reviewer_id].display_name} handles {share:.0f}% of reviews for {repo_name}",
                        entity_type="repository", entity_id=repo_id,
                        link_path="/insights/collaboration",
                        metadata={"reviewer_id": reviewer_id, "share_pct": round(share, 1)},
                    )
        await _auto_resolve_stale(db, "bus_factor", bus_keys)

    # Team silos
    if getattr(config, "alert_team_silo_enabled", True):
        silo_keys: set[str] = set()
        teams_with_devs: dict[str, set[int]] = defaultdict(set)
        for dev in developers.values():
            if dev.team:
                teams_with_devs[dev.team].add(dev.id)

        team_names = sorted(teams_with_devs.keys())

        review_rows = (
            await db.execute(
                select(PRReview.reviewer_id, PullRequest.author_id)
                .join(PullRequest, PRReview.pr_id == PullRequest.id)
                .where(
                    PRReview.submitted_at >= date_from,
                    PRReview.submitted_at <= now,
                )
            )
        ).all()

        cross_team: set[tuple[str, str]] = set()
        for reviewer_id, author_id in review_rows:
            r_dev = developers.get(reviewer_id)
            a_dev = developers.get(author_id)
            if r_dev and a_dev and r_dev.team and a_dev.team and r_dev.team != a_dev.team:
                cross_team.add(tuple(sorted([r_dev.team, a_dev.team])))

        for i, t1 in enumerate(team_names):
            for t2 in team_names[i + 1:]:
                pair = tuple(sorted([t1, t2]))
                if pair not in cross_team:
                    key = f"team_silo:team:{pair[0]}:{pair[1]}"
                    silo_keys.add(key)
                    active_keys.add(key)
                    await _upsert_notification(
                        db, alert_key=key, alert_type="team_silo",
                        severity="info",
                        title=f"No cross-team reviews between {pair[0]} and {pair[1]}",
                        entity_type="team", link_path="/insights/collaboration",
                    )
        await _auto_resolve_stale(db, "team_silo", silo_keys)

    # Isolated developers
    if getattr(config, "alert_isolated_developer_enabled", True):
        iso_keys: set[str] = set()
        reviewers_who_gave: set[int] = set()
        reviews_received: dict[int, set[int]] = defaultdict(set)

        review_pairs = (
            await db.execute(
                select(PRReview.reviewer_id, PullRequest.author_id)
                .join(PullRequest, PRReview.pr_id == PullRequest.id)
                .where(
                    PRReview.reviewer_id.in_(dev_ids),
                    PullRequest.author_id.in_(dev_ids),
                    PRReview.submitted_at >= date_from,
                    PRReview.submitted_at <= now,
                )
            )
        ).all()

        for reviewer_id, author_id in review_pairs:
            reviewers_who_gave.add(reviewer_id)
            reviews_received[author_id].add(reviewer_id)

        for dev_id, dev in developers.items():
            if dev_id not in reviewers_who_gave and len(reviews_received.get(dev_id, set())) <= 1:
                key = f"isolated_developer:developer:{dev_id}"
                iso_keys.add(key)
                active_keys.add(key)
                await _upsert_notification(
                    db, alert_key=key, alert_type="isolated_developer",
                    severity="info",
                    title=f"{dev.display_name} has minimal review interaction",
                    entity_type="developer", entity_id=dev_id,
                    link_path=f"/team/{dev_id}", developer_id=dev_id,
                )
        await _auto_resolve_stale(db, "isolated_developer", iso_keys)

    return active_keys


async def _evaluate_trend_alerts(
    db: AsyncSession, config: NotificationConfig, excluded_dev_ids: set[int]
) -> set[str]:
    active_keys: set[str] = set()
    now = datetime.now(timezone.utc)
    current_from = now - timedelta(days=30)
    prev_from = now - timedelta(days=60)
    prev_to = current_from

    devs_result = await db.execute(
        select(Developer).where(Developer.is_active.is_(True))
    )
    developers = [d for d in devs_result.scalars().all() if d.id not in excluded_dev_ids]

    for dev in developers:
        reasons: list[str] = []

        # PRs merged comparison
        current_prs = await db.scalar(
            select(func.count()).where(
                PullRequest.author_id == dev.id,
                PullRequest.is_merged.is_(True),
                PullRequest.merged_at >= current_from,
                PullRequest.merged_at <= now,
            )
        ) or 0
        prev_prs = await db.scalar(
            select(func.count()).where(
                PullRequest.author_id == dev.id,
                PullRequest.is_merged.is_(True),
                PullRequest.merged_at >= prev_from,
                PullRequest.merged_at <= prev_to,
            )
        ) or 0

        if prev_prs > 0:
            drop_pct = (prev_prs - current_prs) / prev_prs * 100
            if drop_pct >= config.declining_trend_pr_drop_pct:
                reasons.append(f"PRs merged dropped {drop_pct:.0f}% ({prev_prs} → {current_prs})")

        if reasons:
            key = f"declining_trend:developer:{dev.id}"
            active_keys.add(key)
            await _upsert_notification(
                db, alert_key=key, alert_type="declining_trend",
                severity="warning",
                title=f"{dev.display_name} has declining metrics",
                body="; ".join(reasons),
                entity_type="developer", entity_id=dev.id,
                link_path=f"/team/{dev.id}", developer_id=dev.id,
                metadata={"reasons": reasons},
            )

    await _auto_resolve_stale(db, "declining_trend", active_keys)
    return active_keys


async def _evaluate_issue_linkage_alerts(
    db: AsyncSession, config: NotificationConfig, excluded_dev_ids: set[int]
) -> set[str]:
    from app.models.models import PRExternalIssueLink
    from app.services.linear_sync import get_primary_issue_source

    active_keys: set[str] = set()
    issue_source = await get_primary_issue_source(db)

    devs_result = await db.execute(
        select(Developer).where(Developer.is_active.is_(True))
    )
    developers = [d for d in devs_result.scalars().all() if d.id not in excluded_dev_ids]

    for dev in developers:
        total_prs = await db.scalar(
            select(func.count()).where(
                PullRequest.author_id == dev.id,
                PullRequest.is_merged.is_(True),
            )
        ) or 0

        if total_prs < 5:
            continue  # Not enough data

        if issue_source == "linear":
            # A PR is "linked" if it has at least one row in pr_external_issue_links
            linked_prs = await db.scalar(
                select(func.count(func.distinct(PRExternalIssueLink.pull_request_id)))
                .join(PullRequest, PRExternalIssueLink.pull_request_id == PullRequest.id)
                .where(
                    PullRequest.author_id == dev.id,
                    PullRequest.is_merged.is_(True),
                )
            ) or 0
        else:
            # Count PRs with linked issues (closes_issue_numbers is not null)
            linked_prs = await db.scalar(
                select(func.count()).where(
                    PullRequest.author_id == dev.id,
                    PullRequest.is_merged.is_(True),
                    PullRequest.closes_issue_numbers.isnot(None),
                )
            ) or 0

        linkage_rate = linked_prs / total_prs * 100 if total_prs > 0 else 0
        if linkage_rate < config.issue_linkage_threshold_pct:
            key = f"issue_linkage:developer:{dev.id}"
            active_keys.add(key)
            await _upsert_notification(
                db, alert_key=key, alert_type="issue_linkage",
                severity="info",
                title=f"{dev.display_name} has {linkage_rate:.0f}% issue linkage rate",
                body=f"{linked_prs} of {total_prs} merged PRs linked to issues",
                entity_type="developer", entity_id=dev.id,
                link_path=f"/team/{dev.id}", developer_id=dev.id,
                metadata={"linkage_rate": round(linkage_rate, 1), "total_prs": total_prs},
            )

    await _auto_resolve_stale(db, "issue_linkage", active_keys)
    return active_keys


async def _evaluate_ai_budget_alert(
    db: AsyncSession, config: NotificationConfig
) -> set[str]:
    active_keys: set[str] = set()
    ai_settings = await db.get(AISettings, 1)
    if not ai_settings or not ai_settings.monthly_token_budget:
        await _auto_resolve_stale(db, "ai_budget", active_keys)
        return active_keys

    from app.services.ai_settings import _compute_usage_summary
    usage = await _compute_usage_summary(db)
    budget_pct = usage.total_cost / (
        ai_settings.monthly_token_budget
        * ai_settings.input_token_price_per_million / 1_000_000
    ) if ai_settings.monthly_token_budget else 0

    if budget_pct >= ai_settings.budget_warning_threshold:
        key = "ai_budget:system:1"
        active_keys.add(key)
        await _upsert_notification(
            db, alert_key=key, alert_type="ai_budget",
            severity="warning",
            title=f"AI budget at {budget_pct:.0%} of monthly limit",
            entity_type="system", link_path="/admin/ai/settings",
            metadata={"budget_pct": round(budget_pct * 100, 1)},
        )

    await _auto_resolve_stale(db, "ai_budget", active_keys)
    return active_keys


async def _evaluate_sync_failure_alert(
    db: AsyncSession, config: NotificationConfig
) -> set[str]:
    active_keys: set[str] = set()

    result = await db.execute(
        select(SyncEvent)
        .where(SyncEvent.sync_type != "contributors")
        .order_by(SyncEvent.started_at.desc())
        .limit(1)
    )
    latest = result.scalar_one_or_none()

    if latest and latest.status in ("failed", "completed_with_errors"):
        key = f"sync_failure:sync:{latest.id}"
        active_keys.add(key)
        severity = "critical" if latest.status == "failed" else "warning"
        await _upsert_notification(
            db, alert_key=key, alert_type="sync_failure",
            severity=severity,
            title=f"Last sync {latest.status.replace('_', ' ')}",
            body=f"Sync #{latest.id} started at {latest.started_at}",
            entity_type="system", entity_id=latest.id,
            link_path=f"/admin/sync/{latest.id}",
        )

    await _auto_resolve_stale(db, "sync_failure", active_keys)
    return active_keys


async def _evaluate_config_alerts(
    db: AsyncSession, config: NotificationConfig
) -> set[str]:
    active_keys: set[str] = set()

    # Unassigned roles
    if config.alert_unassigned_roles_enabled:
        count = await db.scalar(
            select(func.count()).where(
                Developer.is_active.is_(True),
                Developer.role.is_(None),
            )
        ) or 0
        unassigned_keys: set[str] = set()
        if count > 0:
            key = "unassigned_roles:system:count"
            unassigned_keys.add(key)
            active_keys.add(key)
            await _upsert_notification(
                db, alert_key=key, alert_type="unassigned_roles",
                severity="info",
                title=f"{count} developer(s) have no role assigned",
                entity_type="system", link_path="/admin/team",
                metadata={"count": count},
            )
        await _auto_resolve_stale(db, "unassigned_roles", unassigned_keys)

    # Missing config
    if config.alert_missing_config_enabled:
        from app.config import validate_github_config
        missing_keys: set[str] = set()
        checks = validate_github_config()
        for check in checks:
            if check["status"] in ("error", "warn"):
                key = f"missing_config:system:{check['field']}"
                missing_keys.add(key)
                active_keys.add(key)
                severity = "critical" if check["status"] == "error" else "warning"
                await _upsert_notification(
                    db, alert_key=key, alert_type="missing_config",
                    severity=severity,
                    title=f"{check['field']}: {check['message'][:100]}",
                    entity_type="system", link_path="/admin/sync",
                )
        await _auto_resolve_stale(db, "missing_config", missing_keys)

    return active_keys


# ── Planning / sprint evaluators ────────────────────────────────────────


async def _has_active_linear_integration(db: AsyncSession) -> bool:
    """Check if an active Linear integration exists."""
    result = await db.scalar(
        select(IntegrationConfig.id).where(
            IntegrationConfig.type == "linear",
            IntegrationConfig.status == "active",
        ).limit(1)
    )
    return result is not None


async def _evaluate_planning_alerts(
    db: AsyncSession, config: NotificationConfig
) -> set[str]:
    """Evaluate sprint/planning alerts. No-op if Linear not configured."""
    active_keys: set[str] = set()

    if not await _has_active_linear_integration(db):
        return active_keys

    from datetime import date as date_type

    now = datetime.now(timezone.utc)

    # ── velocity_declining ──
    if config.alert_velocity_declining_enabled:
        velocity_keys: set[str] = set()
        from app.services.sprint_stats import get_sprint_velocity
        velocity = await get_sprint_velocity(db, limit=5)
        sprints = velocity.get("sprints", [])
        if len(sprints) >= 4:
            values = [s.get("completed_scope", 0) or 0 for s in sprints]
            # sprints are newest-first; compare older half to newer half
            older = values[len(values) // 2:]
            newer = values[:len(values) // 2]
            avg_older = sum(older) / len(older) if older else 0
            avg_newer = sum(newer) / len(newer) if newer else 0
            if avg_older > 0:
                decline_pct = (avg_older - avg_newer) / avg_older * 100
                threshold = config.velocity_decline_pct
                if decline_pct >= threshold:
                    key = "velocity_declining:system:trend"
                    velocity_keys.add(key)
                    active_keys.add(key)
                    await _upsert_notification(
                        db, alert_key=key, alert_type="velocity_declining",
                        severity="warning",
                        title=f"Sprint velocity declined {decline_pct:.0f}% over last {len(sprints)} sprints",
                        entity_type="system",
                        link_path="/insights/sprints",
                        metadata={"decline_pct": round(decline_pct, 1), "sprint_count": len(sprints)},
                    )
        await _auto_resolve_stale(db, "velocity_declining", velocity_keys)

    # ── scope_creep_high ──
    if config.alert_scope_creep_high_enabled:
        creep_keys: set[str] = set()
        from app.services.sprint_stats import get_scope_creep
        scope = await get_scope_creep(db, limit=1)
        sprints = scope.get("sprints", [])
        if sprints:
            latest = sprints[0]
            creep_pct = latest.get("scope_creep_pct", 0) or 0
            threshold = config.scope_creep_threshold_pct
            if creep_pct >= threshold:
                sprint_name = latest.get("name", "Sprint")
                key = f"scope_creep_high:sprint:{latest.get('sprint_id', 0)}"
                creep_keys.add(key)
                active_keys.add(key)
                await _upsert_notification(
                    db, alert_key=key, alert_type="scope_creep_high",
                    severity="warning",
                    title=f"{sprint_name}: {creep_pct:.0f}% scope creep",
                    entity_type="sprint",
                    link_path="/insights/sprints",
                    metadata={"scope_creep_pct": round(creep_pct, 1), "sprint_name": sprint_name},
                )
        await _auto_resolve_stale(db, "scope_creep_high", creep_keys)

    # ── sprint_at_risk ──
    if config.alert_sprint_at_risk_enabled:
        risk_keys: set[str] = set()
        active_sprints = (await db.execute(
            select(ExternalSprint).where(ExternalSprint.state == "active")
        )).scalars().all()
        for sprint in active_sprints:
            if sprint.start_date and sprint.end_date:
                today = now.date()
                total_days = (sprint.end_date - sprint.start_date).days
                elapsed_days = (today - sprint.start_date).days
                if total_days > 0 and elapsed_days > 0:
                    elapsed_pct = elapsed_days / total_days * 100
                    if elapsed_pct >= 50:
                        planned = sprint.planned_scope or 0
                        completed = sprint.completed_scope or 0
                        completion_pct = (completed / planned * 100) if planned > 0 else 100
                        threshold = config.sprint_risk_completion_pct
                        if completion_pct < threshold:
                            key = f"sprint_at_risk:sprint:{sprint.id}"
                            risk_keys.add(key)
                            active_keys.add(key)
                            severity = "critical" if elapsed_pct >= 75 and completion_pct < 50 else "warning"
                            name = sprint.name or f"Sprint #{sprint.number}"
                            await _upsert_notification(
                                db, alert_key=key, alert_type="sprint_at_risk",
                                severity=severity,
                                title=f"{name}: {completion_pct:.0f}% done with {max(0, (sprint.end_date - today).days)}d left",
                                entity_type="sprint", entity_id=sprint.id,
                                link_path="/insights/sprints",
                                metadata={
                                    "completion_pct": round(completion_pct, 1),
                                    "elapsed_pct": round(elapsed_pct, 1),
                                    "days_remaining": max(0, (sprint.end_date - today).days),
                                },
                            )
        await _auto_resolve_stale(db, "sprint_at_risk", risk_keys)

    # ── triage_queue_growing ──
    if config.alert_triage_queue_growing_enabled:
        triage_keys: set[str] = set()
        from app.services.sprint_stats import get_triage_metrics
        triage = await get_triage_metrics(db)
        queue_depth = triage.get("current_queue_depth", 0) or 0
        avg_hours = triage.get("avg_triage_hours", 0) or 0
        q_max = config.triage_queue_max
        d_max = config.triage_duration_hours_max
        if queue_depth >= q_max or avg_hours >= d_max:
            key = "triage_queue_growing:system:triage"
            triage_keys.add(key)
            active_keys.add(key)
            parts = []
            if queue_depth >= q_max:
                parts.append(f"{queue_depth} issues in triage")
            if avg_hours >= d_max:
                parts.append(f"avg {avg_hours:.0f}h triage time")
            await _upsert_notification(
                db, alert_key=key, alert_type="triage_queue_growing",
                severity="warning",
                title="; ".join(parts),
                entity_type="system",
                link_path="/insights/planning",
                metadata={"queue_depth": queue_depth, "avg_triage_hours": round(avg_hours, 1)},
            )
        await _auto_resolve_stale(db, "triage_queue_growing", triage_keys)

    # ── estimation_accuracy_low ──
    if config.alert_estimation_accuracy_low_enabled:
        est_keys: set[str] = set()
        from app.services.sprint_stats import get_estimation_accuracy
        accuracy = await get_estimation_accuracy(db, limit=5)
        sprints = accuracy.get("sprints", [])
        if sprints:
            accuracies = [s.get("accuracy_pct", 100) or 100 for s in sprints]
            avg_accuracy = sum(accuracies) / len(accuracies)
            threshold = config.estimation_accuracy_min_pct
            if avg_accuracy < threshold:
                key = "estimation_accuracy_low:system:trend"
                est_keys.add(key)
                active_keys.add(key)
                await _upsert_notification(
                    db, alert_key=key, alert_type="estimation_accuracy_low",
                    severity="info",
                    title=f"Estimation accuracy at {avg_accuracy:.0f}% over last {len(sprints)} sprints",
                    entity_type="system",
                    link_path="/insights/planning",
                    metadata={"avg_accuracy_pct": round(avg_accuracy, 1), "sprint_count": len(sprints)},
                )
        await _auto_resolve_stale(db, "estimation_accuracy_low", est_keys)

    # ── linear_sync_failure ──
    if config.alert_linear_sync_failure_enabled:
        lsf_keys: set[str] = set()
        result = await db.execute(
            select(SyncEvent)
            .where(SyncEvent.sync_type == "linear")
            .order_by(SyncEvent.started_at.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        if latest and latest.status in ("failed", "completed_with_errors"):
            key = f"linear_sync_failure:sync:{latest.id}"
            lsf_keys.add(key)
            active_keys.add(key)
            severity = "critical" if latest.status == "failed" else "warning"
            await _upsert_notification(
                db, alert_key=key, alert_type="linear_sync_failure",
                severity=severity,
                title=f"Linear sync {latest.status.replace('_', ' ')}",
                body=f"Sync #{latest.id} started at {latest.started_at}",
                entity_type="system", entity_id=latest.id,
                link_path="/admin/integrations",
            )
        await _auto_resolve_stale(db, "linear_sync_failure", lsf_keys)

    return active_keys


# ── Main evaluation orchestrator ─────────────────────────────────────────


async def evaluate_all_alerts(db: AsyncSession) -> dict[str, int]:
    """Run all alert evaluators. Returns counts of created/updated/resolved."""
    config = await get_notification_config(db)
    excluded_dev_ids = await _get_excluded_developer_ids(
        db, config.exclude_contribution_categories
    )

    counts = {"created": 0, "updated": 0, "resolved": 0}

    evaluators = [
        ("stale_pr", _evaluate_stale_pr_alerts, config.alert_stale_pr_enabled),
        ("workload", _evaluate_workload_alerts, True),  # has sub-toggles
        ("revert_spike", _evaluate_revert_spike_alert, config.alert_revert_spike_enabled),
        ("high_risk_pr", _evaluate_risk_alerts, config.alert_high_risk_pr_enabled),
        ("collaboration", _evaluate_collaboration_alerts, True),  # has sub-toggles
        ("declining_trend", _evaluate_trend_alerts, config.alert_declining_trends_enabled),
        ("issue_linkage", _evaluate_issue_linkage_alerts, config.alert_issue_linkage_enabled),
        ("ai_budget", _evaluate_ai_budget_alert, config.alert_ai_budget_enabled),
        ("sync_failure", _evaluate_sync_failure_alert, config.alert_sync_failure_enabled),
        ("planning", _evaluate_planning_alerts, True),  # has sub-toggles, short-circuits if no Linear
        ("config", _evaluate_config_alerts, True),  # has sub-toggles
    ]

    for name, evaluator, enabled in evaluators:
        if not enabled:
            continue
        try:
            if evaluator in (_evaluate_ai_budget_alert, _evaluate_sync_failure_alert, _evaluate_planning_alerts):
                await evaluator(db, config)
            elif evaluator == _evaluate_config_alerts:
                await evaluator(db, config)
            elif evaluator == _evaluate_collaboration_alerts:
                await evaluator(db, config, excluded_dev_ids)
            else:
                await evaluator(db, config, excluded_dev_ids)
        except Exception as e:
            from app.main import _classifier, _reporter

            classified = _classifier.classify(e)
            log_level = logger.error if classified.category.value == "app_bug" else logger.warning
            log_level(
                "Notification evaluator failed",
                evaluator=name,
                error=str(e)[:200],
                exc_type=type(e).__name__,
                error_category=classified.category.value,
                event_type="system.notifications",
            )
            if classified.category.value == "app_bug" and _reporter:
                _reporter.record(exc=e, component=f"services.notifications.{name}", trigger_type="scheduled")

    await db.commit()

    # Count results (approximate — count active + resolved)
    active = await db.scalar(
        select(func.count()).where(Notification.resolved_at.is_(None))
    ) or 0
    logger.info(
        "Notification evaluation complete",
        active_count=active,
        event_type="system.notifications",
    )

    return counts


# ── Query helpers for API ────────────────────────────────────────────────


async def get_active_notifications(
    db: AsyncSession,
    user_id: int,
    severity: str | None = None,
    alert_type: str | None = None,
    include_dismissed: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> NotificationsListResponse:
    now = datetime.now(timezone.utc)

    # Base: active (not resolved) notifications
    base = select(Notification).where(Notification.resolved_at.is_(None))

    if severity:
        base = base.where(Notification.severity == severity)
    if alert_type:
        base = base.where(Notification.alert_type == alert_type)

    # Get all active notifications first for counting
    all_result = await db.execute(base)
    all_notifs = all_result.scalars().all()

    # Load user's reads and dismissals
    read_ids: set[int] = set()
    read_result = await db.execute(
        select(NotificationRead.notification_id).where(
            NotificationRead.user_id == user_id
        )
    )
    read_ids = {r[0] for r in read_result.all()}

    dismissed_ids: set[int] = set()
    dismiss_result = await db.execute(
        select(NotificationDismissal.notification_id).where(
            NotificationDismissal.user_id == user_id,
            or_(
                NotificationDismissal.dismiss_type == "permanent",
                and_(
                    NotificationDismissal.dismiss_type == "temporary",
                    NotificationDismissal.expires_at > now,
                ),
            ),
        )
    )
    dismissed_ids = {r[0] for r in dismiss_result.all()}

    # Type-level dismissals
    type_dismiss_result = await db.execute(
        select(NotificationTypeDismissal.alert_type).where(
            NotificationTypeDismissal.user_id == user_id,
            or_(
                NotificationTypeDismissal.dismiss_type == "permanent",
                and_(
                    NotificationTypeDismissal.dismiss_type == "temporary",
                    NotificationTypeDismissal.expires_at > now,
                ),
            ),
        )
    )
    dismissed_types = {r[0] for r in type_dismiss_result.all()}

    # Build response notifications
    notifications: list[NotificationResponse] = []
    unread_count = 0
    counts_by_severity: dict[str, int] = {"critical": 0, "warning": 0, "info": 0}

    # Sort: severity priority, then newest first
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    sorted_notifs = sorted(
        all_notifs,
        key=lambda n: (severity_order.get(n.severity, 9), -(n.created_at.timestamp() if n.created_at else 0)),
    )

    for n in sorted_notifs:
        is_read = n.id in read_ids
        is_dismissed = n.id in dismissed_ids or n.alert_type in dismissed_types

        if not include_dismissed and is_dismissed:
            continue

        counts_by_severity[n.severity] = counts_by_severity.get(n.severity, 0) + 1
        if not is_read and not is_dismissed:
            unread_count += 1

        notifications.append(NotificationResponse(
            id=n.id,
            alert_type=n.alert_type,
            severity=n.severity,
            title=n.title,
            body=n.body,
            entity_type=n.entity_type,
            entity_id=n.entity_id,
            link_path=n.link_path,
            developer_id=n.developer_id,
            metadata=n.metadata_,
            is_read=is_read,
            is_dismissed=is_dismissed,
            created_at=n.created_at,
            updated_at=n.updated_at,
        ))

    # Apply pagination
    total = len(notifications)
    paginated = notifications[offset:offset + limit]

    return NotificationsListResponse(
        notifications=paginated,
        unread_count=unread_count,
        counts_by_severity=counts_by_severity,
        total=total,
    )


async def mark_read(db: AsyncSession, notification_id: int, user_id: int) -> None:
    existing = await db.execute(
        select(NotificationRead).where(
            NotificationRead.notification_id == notification_id,
            NotificationRead.user_id == user_id,
        )
    )
    if not existing.scalar_one_or_none():
        db.add(NotificationRead(notification_id=notification_id, user_id=user_id))
        await db.commit()


async def mark_all_read(db: AsyncSession, user_id: int) -> int:
    # Get all active unread notification IDs
    already_read = select(NotificationRead.notification_id).where(
        NotificationRead.user_id == user_id
    )
    active = await db.execute(
        select(Notification.id).where(
            Notification.resolved_at.is_(None),
            Notification.id.notin_(already_read),
        )
    )
    ids = [r[0] for r in active.all()]
    for nid in ids:
        db.add(NotificationRead(notification_id=nid, user_id=user_id))
    if ids:
        await db.commit()
    return len(ids)


async def dismiss_notification(
    db: AsyncSession, notification_id: int, user_id: int,
    dismiss_type: str, duration_days: int | None,
) -> dict:
    expires_at = None
    if dismiss_type == "temporary" and duration_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=duration_days)

    # Upsert dismissal
    existing = await db.execute(
        select(NotificationDismissal).where(
            NotificationDismissal.notification_id == notification_id,
            NotificationDismissal.user_id == user_id,
        )
    )
    row = existing.scalar_one_or_none()
    if row:
        row.dismiss_type = dismiss_type
        row.expires_at = expires_at
    else:
        db.add(NotificationDismissal(
            notification_id=notification_id,
            user_id=user_id,
            dismiss_type=dismiss_type,
            expires_at=expires_at,
        ))

    # Also mark as read
    await mark_read(db, notification_id, user_id)
    await db.commit()
    return {"success": True, "expires_at": expires_at}


async def dismiss_alert_type(
    db: AsyncSession, alert_type_str: str, user_id: int,
    dismiss_type: str, duration_days: int | None,
) -> dict:
    expires_at = None
    if dismiss_type == "temporary" and duration_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=duration_days)

    existing = await db.execute(
        select(NotificationTypeDismissal).where(
            NotificationTypeDismissal.alert_type == alert_type_str,
            NotificationTypeDismissal.user_id == user_id,
        )
    )
    row = existing.scalar_one_or_none()
    if row:
        row.dismiss_type = dismiss_type
        row.expires_at = expires_at
    else:
        db.add(NotificationTypeDismissal(
            alert_type=alert_type_str,
            user_id=user_id,
            dismiss_type=dismiss_type,
            expires_at=expires_at,
        ))

    await db.commit()
    return {"success": True, "alert_type": alert_type_str, "expires_at": expires_at}


async def undismiss_notification(db: AsyncSession, dismissal_id: int, user_id: int) -> None:
    result = await db.execute(
        select(NotificationDismissal).where(
            NotificationDismissal.id == dismissal_id,
            NotificationDismissal.user_id == user_id,
        )
    )
    row = result.scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()


async def undismiss_alert_type(db: AsyncSession, dismissal_id: int, user_id: int) -> None:
    result = await db.execute(
        select(NotificationTypeDismissal).where(
            NotificationTypeDismissal.id == dismissal_id,
            NotificationTypeDismissal.user_id == user_id,
        )
    )
    row = result.scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()
