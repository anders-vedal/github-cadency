"""Work categorization service (P4-02).

Classifies PRs and Issues into: feature, bugfix, tech_debt, ops, unknown.
Three-tier classification: labels -> title keywords -> AI (optional).
Cross-references PR<->Issue categories for unknowns.
"""

import json
import logging
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Developer, Issue, PullRequest
from app.schemas.schemas import (
    CategoryAllocation,
    DeveloperWorkAllocation,
    IssueCategoryAllocation,
    WorkAllocationPeriod,
    WorkAllocationResponse,
)

logger = logging.getLogger(__name__)

VALID_CATEGORIES = frozenset({"feature", "bugfix", "tech_debt", "ops", "unknown"})

ALL_CATEGORIES = ["feature", "bugfix", "tech_debt", "ops", "unknown"]

# --- Label Mapping (highest precedence) ---

LABEL_CATEGORY_MAP: dict[str, str] = {
    # Feature
    "feature": "feature",
    "enhancement": "feature",
    "feat": "feature",
    "new feature": "feature",
    "story": "feature",
    # Bugfix
    "bug": "bugfix",
    "bugfix": "bugfix",
    "fix": "bugfix",
    "defect": "bugfix",
    "hotfix": "bugfix",
    "regression": "bugfix",
    # Tech debt
    "tech-debt": "tech_debt",
    "tech debt": "tech_debt",
    "refactor": "tech_debt",
    "refactoring": "tech_debt",
    "cleanup": "tech_debt",
    "chore": "tech_debt",
    "dependencies": "tech_debt",
    "dependency": "tech_debt",
    "deps": "tech_debt",
    # Ops
    "ops": "ops",
    "infrastructure": "ops",
    "infra": "ops",
    "ci": "ops",
    "ci/cd": "ops",
    "deploy": "ops",
    "deployment": "ops",
    "devops": "ops",
    "monitoring": "ops",
    "config": "ops",
    "documentation": "ops",
    "docs": "ops",
}

# --- Title Keyword Patterns ---

TITLE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bfix(?:es|ed)?\b|\bbug\b|\bhotfix\b|\bregression\b", re.I), "bugfix"),
    (re.compile(r"\bfeat(?:ure)?\b|\badd(?:s|ed)?\s", re.I), "feature"),
    (re.compile(r"\brefactor\b|\bcleanup\b|\btech.?debt\b|\bchore\b|\bdeps?\b|\bbump\b", re.I), "tech_debt"),
    (re.compile(r"\bci\b|\bcd\b|\bdeploy\b|\binfra\b|\bconfig\b|\bdocs?\b|\bmonitoring\b", re.I), "ops"),
]


from app.services.utils import default_range as _default_range


# --- Pure classification functions ---


def classify_work_item(
    labels: list[str] | None,
    title: str | None,
) -> str:
    """Classify a PR or Issue by labels then title keywords.

    Returns one of: feature, bugfix, tech_debt, ops, unknown.
    """
    if labels:
        for label in labels:
            cat = LABEL_CATEGORY_MAP.get(label.lower().strip())
            if cat:
                return cat

    if title:
        for pattern, cat in TITLE_PATTERNS:
            if pattern.search(title):
                return cat

    return "unknown"


def cross_reference_pr_categories(
    prs: list[dict],
    issues_by_key: dict[tuple[int, int], str],
) -> list[dict]:
    """For PRs with category 'unknown', inherit from linked issues.

    Mutates and returns the same list.
    """
    for pr in prs:
        if pr["category"] != "unknown":
            continue
        linked_numbers = pr.get("closes_issue_numbers") or []
        linked_cats = [
            issues_by_key[(pr["repo_id"], n)]
            for n in linked_numbers
            if (pr["repo_id"], n) in issues_by_key
            and issues_by_key[(pr["repo_id"], n)] != "unknown"
        ]
        if linked_cats:
            pr["category"] = Counter(linked_cats).most_common(1)[0][0]
    return prs


def _auto_granularity(date_from: datetime, date_to: datetime) -> str:
    delta = (date_to - date_from).days
    return "weekly" if delta <= 90 else "monthly"


def _build_period_trend(
    pr_items: list[dict],
    issue_items: list[dict],
    date_from: datetime,
    date_to: datetime,
    granularity: str,
) -> list[WorkAllocationPeriod]:
    """Bucket items by week/month and count per category."""
    buckets: list[tuple[datetime, datetime, str]] = []

    if granularity == "weekly":
        current = date_from
        while current < date_to:
            end = min(current + timedelta(days=7), date_to)
            iso = current.isocalendar()
            label = f"{iso[0]}-W{iso[1]:02d}"
            buckets.append((current, end, label))
            current = end
    else:
        current = date_from.replace(day=1)
        while current < date_to:
            next_month = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
            end = min(next_month, date_to)
            label = current.strftime("%Y-%m")
            buckets.append((max(current, date_from), end, label))
            current = next_month

    periods: list[WorkAllocationPeriod] = []
    for start, end, label in buckets:
        pr_cats: dict[str, int] = {}
        for item in pr_items:
            ts = item.get("merged_at") or item.get("created_at")
            if ts and start <= ts < end:
                cat = item["category"]
                pr_cats[cat] = pr_cats.get(cat, 0) + 1

        issue_cats: dict[str, int] = {}
        for item in issue_items:
            ts = item.get("created_at")
            if ts and start <= ts < end:
                cat = item["category"]
                issue_cats[cat] = issue_cats.get(cat, 0) + 1

        periods.append(
            WorkAllocationPeriod(
                period_start=start,
                period_end=end,
                period_label=label,
                pr_categories=pr_cats,
                issue_categories=issue_cats,
            )
        )
    return periods


# --- AI classification ---


async def ai_classify_batch(
    items: list[dict], db: AsyncSession | None = None
) -> dict[int, str]:
    """Batch-classify unknown items via Claude API.

    Args:
        items: List of dicts with 'index' and 'title'.
        db: Optional async session for guard checks and usage logging.
    Returns:
        Dict mapping index -> category string.
    """
    import anthropic

    from app.config import settings

    if not settings.anthropic_api_key or not items:
        return {}

    # Guard checks if db is provided
    if db is not None:
        from app.services.ai_settings import check_budget, check_feature_enabled

        try:
            ai_settings = await check_feature_enabled(db, "work_categorization")
            budget_info = await check_budget(db, ai_settings)
            if budget_info["over_budget"]:
                logger.warning("AI budget exceeded — skipping work categorization")
                return {}
        except Exception:
            # Feature disabled or other guard failure — skip AI silently
            return {}

    batch = items[:200]

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    item_lines = "\n".join(
        f"{i['index']}: {i['title'] or '(no title)'}" for i in batch
    )

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-0",
            max_tokens=2048,
            system=(
                "You classify software work items into exactly one category: "
                "feature, bugfix, tech_debt, ops, or unknown. "
                "Respond with a JSON array of objects: "
                '[{"index": <int>, "category": "<str>"}]. '
                "Only output valid JSON, no markdown fences."
            ),
            messages=[
                {
                    "role": "user",
                    "content": f"Classify each item:\n\n{item_lines}",
                }
            ],
        )
        results = json.loads(response.content[0].text)
        classified = {
            r["index"]: r["category"]
            for r in results
            if isinstance(r, dict)
            and isinstance(r.get("index"), int)
            and 0 <= r["index"] < len(batch)
            and r.get("category") in VALID_CATEGORIES
        }

        # Log usage if db is provided
        if db is not None and classified:
            from app.models.models import AIUsageLog

            inp = response.usage.input_tokens
            out = response.usage.output_tokens
            log_entry = AIUsageLog(
                feature="work_categorization",
                input_tokens=inp,
                output_tokens=out,
                items_classified=len(classified),
            )
            db.add(log_entry)
            # Don't commit here — caller will commit after writing work_category

        return classified
    except Exception:
        logger.exception("AI batch classification failed")
        return {}


# --- Main service function ---


async def get_work_allocation(
    db: AsyncSession,
    team: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    use_ai: bool = False,
) -> WorkAllocationResponse:
    date_from, date_to = _default_range(date_from, date_to)
    granularity = _auto_granularity(date_from, date_to)

    # Resolve team -> developer IDs
    dev_query = select(Developer.id, Developer.github_username, Developer.display_name, Developer.team).where(
        Developer.is_active.is_(True)
    )
    if team:
        dev_query = dev_query.where(Developer.team == team)
    dev_result = await db.execute(dev_query)
    dev_rows = dev_result.all()
    dev_ids = [r[0] for r in dev_rows]
    dev_info = {r[0]: {"github_username": r[1], "display_name": r[2], "team": r[3]} for r in dev_rows}
    dev_usernames = {r[1] for r in dev_rows}

    empty_response = WorkAllocationResponse(
        period_start=date_from,
        period_end=date_to,
        period_type=granularity,
        pr_allocation=[],
        issue_allocation=[],
        developer_breakdown=[],
        trend=[],
    )

    if not dev_ids:
        return empty_response

    # Fetch merged PRs in period
    pr_query = select(
        PullRequest.id,
        PullRequest.title,
        PullRequest.labels,
        PullRequest.additions,
        PullRequest.deletions,
        PullRequest.author_id,
        PullRequest.repo_id,
        PullRequest.closes_issue_numbers,
        PullRequest.merged_at,
        PullRequest.work_category,
    ).where(
        PullRequest.author_id.in_(dev_ids),
        PullRequest.is_merged.is_(True),
        PullRequest.merged_at >= date_from,
        PullRequest.merged_at <= date_to,
    )
    pr_result = await db.execute(pr_query)
    pr_rows = pr_result.all()

    # Fetch issues created in period (by team members)
    issue_query = select(
        Issue.id,
        Issue.title,
        Issue.labels,
        Issue.repo_id,
        Issue.number,
        Issue.created_at,
        Issue.creator_github_username,
        Issue.work_category,
    ).where(
        Issue.creator_github_username.in_(dev_usernames),
        Issue.created_at >= date_from,
        Issue.created_at <= date_to,
    )
    issue_result = await db.execute(issue_query)
    issue_rows = issue_result.all()

    if not pr_rows and not issue_rows:
        return empty_response

    # Classify issues
    issue_items: list[dict] = []
    for row in issue_rows:
        deterministic_cat = classify_work_item(row[2], row[1])
        # Use stored AI category if deterministic is unknown and stored is valid
        if deterministic_cat == "unknown" and row[7] and row[7] in VALID_CATEGORIES and row[7] != "unknown":
            cat = row[7]
        else:
            cat = deterministic_cat
        issue_items.append({
            "id": row[0],
            "title": row[1],
            "labels": row[2],
            "repo_id": row[3],
            "number": row[4],
            "created_at": row[5],
            "creator_github_username": row[6],
            "category": cat,
            "type": "issue",
        })

    # Build issue lookup for cross-reference
    issues_by_key: dict[tuple[int, int], str] = {
        (item["repo_id"], item["number"]): item["category"] for item in issue_items
    }

    # Classify PRs
    pr_items: list[dict] = []
    for row in pr_rows:
        deterministic_cat = classify_work_item(row[2], row[1])
        if deterministic_cat == "unknown" and row[9] and row[9] in VALID_CATEGORIES and row[9] != "unknown":
            cat = row[9]
        else:
            cat = deterministic_cat
        pr_items.append({
            "id": row[0],
            "title": row[1],
            "labels": row[2],
            "additions": row[3] or 0,
            "deletions": row[4] or 0,
            "author_id": row[5],
            "repo_id": row[6],
            "closes_issue_numbers": row[7],
            "merged_at": row[8],
            "category": cat,
            "type": "pr",
        })

    # Cross-reference: unknown PRs inherit from linked issues
    cross_reference_pr_categories(pr_items, issues_by_key)

    # AI classification for remaining unknowns
    ai_classified_count = 0
    ai_updated_ids: dict[str, list[tuple[int, str]]] = {"pr": [], "issue": []}
    if use_ai:
        unknowns: list[dict] = []
        for i, item in enumerate(pr_items):
            if item["category"] == "unknown":
                unknowns.append({"index": len(unknowns), "pr_idx": i, "title": item["title"], "type": "pr"})
        for i, item in enumerate(issue_items):
            if item["category"] == "unknown":
                unknowns.append({"index": len(unknowns), "issue_idx": i, "title": item["title"], "type": "issue"})

        if unknowns:
            ai_results = await ai_classify_batch(unknowns, db=db)
            for entry in unknowns:
                idx = entry["index"]
                if idx in ai_results:
                    cat = ai_results[idx]
                    if entry["type"] == "pr":
                        pr_items[entry["pr_idx"]]["category"] = cat
                        ai_updated_ids["pr"].append((pr_items[entry["pr_idx"]]["id"], cat))
                    else:
                        issue_items[entry["issue_idx"]]["category"] = cat
                        ai_updated_ids["issue"].append((issue_items[entry["issue_idx"]]["id"], cat))
                    ai_classified_count += 1

    # Write back work_category only for AI-classified items
    if ai_updated_ids["pr"]:
        for item_id, cat in ai_updated_ids["pr"]:
            await db.execute(
                update(PullRequest)
                .where(PullRequest.id == item_id)
                .values(work_category=cat)
            )
    if ai_updated_ids["issue"]:
        for item_id, cat in ai_updated_ids["issue"]:
            await db.execute(
                update(Issue)
                .where(Issue.id == item_id)
                .values(work_category=cat)
            )
    if ai_classified_count > 0:
        await db.commit()

    # --- Aggregate results ---

    total_prs = len(pr_items)
    total_issues = len(issue_items)

    # PR allocation
    pr_cat_counts: dict[str, dict] = {}
    for item in pr_items:
        cat = item["category"]
        if cat not in pr_cat_counts:
            pr_cat_counts[cat] = {"count": 0, "additions": 0, "deletions": 0}
        pr_cat_counts[cat]["count"] += 1
        pr_cat_counts[cat]["additions"] += item["additions"]
        pr_cat_counts[cat]["deletions"] += item["deletions"]

    pr_allocation = [
        CategoryAllocation(
            category=cat,
            count=data["count"],
            additions=data["additions"],
            deletions=data["deletions"],
            pct_of_total=round(data["count"] / total_prs * 100, 1) if total_prs > 0 else 0.0,
        )
        for cat, data in pr_cat_counts.items()
    ]
    pr_allocation.sort(key=lambda a: a.count, reverse=True)

    # Issue allocation
    issue_cat_counts: dict[str, int] = {}
    for item in issue_items:
        cat = item["category"]
        issue_cat_counts[cat] = issue_cat_counts.get(cat, 0) + 1

    issue_allocation = [
        IssueCategoryAllocation(
            category=cat,
            count=count,
            pct_of_total=round(count / total_issues * 100, 1) if total_issues > 0 else 0.0,
        )
        for cat, count in issue_cat_counts.items()
    ]
    issue_allocation.sort(key=lambda a: a.count, reverse=True)

    # Developer breakdown
    dev_pr_cats: dict[int, dict[str, int]] = {}
    for item in pr_items:
        aid = item["author_id"]
        if aid not in dev_pr_cats:
            dev_pr_cats[aid] = {}
        cat = item["category"]
        dev_pr_cats[aid][cat] = dev_pr_cats[aid].get(cat, 0) + 1

    # Map issue creators to developer IDs
    username_to_id = {info["github_username"]: did for did, info in dev_info.items()}
    dev_issue_cats: dict[int, dict[str, int]] = {}
    for item in issue_items:
        did = username_to_id.get(item["creator_github_username"])
        if did is None:
            continue
        if did not in dev_issue_cats:
            dev_issue_cats[did] = {}
        cat = item["category"]
        dev_issue_cats[did][cat] = dev_issue_cats[did].get(cat, 0) + 1

    all_dev_ids = set(dev_pr_cats.keys()) | set(dev_issue_cats.keys())
    developer_breakdown = []
    for did in all_dev_ids:
        info = dev_info.get(did)
        if not info:
            continue
        pr_cats = dev_pr_cats.get(did, {})
        issue_cats = dev_issue_cats.get(did, {})
        developer_breakdown.append(
            DeveloperWorkAllocation(
                developer_id=did,
                github_username=info["github_username"],
                display_name=info["display_name"],
                team=info["team"],
                pr_categories=pr_cats,
                issue_categories=issue_cats,
                total_prs=sum(pr_cats.values()),
                total_issues=sum(issue_cats.values()),
            )
        )
    developer_breakdown.sort(key=lambda d: d.total_prs, reverse=True)

    # Trend
    trend = _build_period_trend(pr_items, issue_items, date_from, date_to, granularity)

    # Unknown percentage
    total_items = total_prs + total_issues
    unknown_count = sum(1 for i in pr_items if i["category"] == "unknown") + sum(
        1 for i in issue_items if i["category"] == "unknown"
    )
    unknown_pct = round(unknown_count / total_items * 100, 1) if total_items > 0 else 0.0

    return WorkAllocationResponse(
        period_start=date_from,
        period_end=date_to,
        period_type=granularity,
        pr_allocation=pr_allocation,
        issue_allocation=issue_allocation,
        developer_breakdown=developer_breakdown,
        trend=trend,
        unknown_pct=unknown_pct,
        ai_classified_count=ai_classified_count,
        total_prs=total_prs,
        total_issues=total_issues,
    )
