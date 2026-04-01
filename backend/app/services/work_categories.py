"""Configurable work categories — CRUD, classification, and reclassification.

Replaces the hardcoded LABEL_CATEGORY_MAP/TITLE_PATTERNS with admin-configurable
rules stored in work_categories + work_category_rules tables.
"""

import re
import time
from collections import Counter

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger
from app.models.models import (
    Issue,
    PullRequest,
    WorkCategory as WorkCategoryModel,
    WorkCategoryRule,
)
from app.schemas.schemas import (
    VALID_MATCH_TYPES,
    WorkCategoryCreate,
    WorkCategoryRuleCreate,
    WorkCategoryRuleUpdate,
    WorkCategoryUpdate,
)

logger = get_logger(__name__)

# Pattern that detects nested quantifiers — a leading cause of catastrophic
# backtracking (ReDoS).  Examples: ``(a+)+``, ``(x*)*``, ``(a|b+)+$``.
_NESTED_QUANTIFIER_RE = re.compile(
    r"\([^)]*[+*][^)]*\)[+*?]|\([^)]*[+*][^)]*\)\{",
)


def _validate_regex_safe(pattern: str) -> None:
    """Validate a regex pattern: must compile and must not contain nested quantifiers."""
    try:
        re.compile(pattern)
    except re.error as e:
        raise ValueError(f"Invalid regex pattern: {e}")
    if _NESTED_QUANTIFIER_RE.search(pattern):
        raise ValueError(
            "Pattern contains nested quantifiers which may cause performance issues"
        )


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------


async def get_all_categories(db: AsyncSession) -> list[WorkCategoryModel]:
    """Return all work categories ordered by display_order."""
    result = await db.execute(
        select(WorkCategoryModel).order_by(WorkCategoryModel.display_order)
    )
    return list(result.scalars().all())


async def get_all_rules(db: AsyncSession) -> list[WorkCategoryRule]:
    """Return all classification rules ordered by priority."""
    result = await db.execute(
        select(WorkCategoryRule).order_by(WorkCategoryRule.priority)
    )
    return list(result.scalars().all())


async def load_valid_categories(db: AsyncSession) -> set[str]:
    """Return the set of all category keys."""
    result = await db.execute(select(WorkCategoryModel.category_key))
    return {row[0] for row in result.all()}


async def get_excluded_categories(db: AsyncSession) -> set[str]:
    """Return category keys where exclude_from_stats is True."""
    result = await db.execute(
        select(WorkCategoryModel.category_key).where(
            WorkCategoryModel.exclude_from_stats.is_(True)
        )
    )
    return {row[0] for row in result.all()}


# ---------------------------------------------------------------------------
# Pure classification function
# ---------------------------------------------------------------------------


def classify_work_item_with_rules(
    labels: list[str] | None,
    title: str | None,
    rules: list[WorkCategoryRule],
    issue_type: str | None = None,
) -> tuple[str, str]:
    """Classify a PR or issue using the given rules.

    Returns (category_key, source) where source is "label", "title", "prefix",
    "issue_type", or "" for unknown.
    Rules must be pre-sorted by priority (ascending).
    """
    for rule in rules:
        if rule.match_type == "label" and labels:
            for label in labels:
                compare_label = label if rule.case_sensitive else label.lower().strip()
                compare_value = rule.match_value if rule.case_sensitive else rule.match_value.lower().strip()
                if compare_label == compare_value:
                    return rule.category_key, "label"

        elif rule.match_type == "issue_type" and issue_type:
            compare_type = issue_type if rule.case_sensitive else issue_type.lower().strip()
            compare_value = rule.match_value if rule.case_sensitive else rule.match_value.lower().strip()
            if compare_type == compare_value:
                return rule.category_key, "issue_type"

        elif rule.match_type == "title_regex" and title:
            flags = 0 if rule.case_sensitive else re.IGNORECASE
            try:
                if re.search(rule.match_value, title, flags):
                    return rule.category_key, "title"
            except re.error:
                logger.warning(
                    "Invalid regex in rule, skipping",
                    rule_id=rule.id, pattern=rule.match_value,
                    event_type="system.config",
                )

        elif rule.match_type == "prefix" and title:
            compare_title = title if rule.case_sensitive else title.lower()
            compare_value = rule.match_value if rule.case_sensitive else rule.match_value.lower()
            if compare_title.startswith(compare_value):
                return rule.category_key, "prefix"

    return "unknown", ""


# ---------------------------------------------------------------------------
# Category CRUD
# ---------------------------------------------------------------------------

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,48}$")
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


async def create_category(db: AsyncSession, data: WorkCategoryCreate) -> WorkCategoryModel:
    if not _KEY_RE.match(data.category_key):
        raise ValueError(
            "category_key must be lowercase alphanumeric with underscores, 2-49 chars, starting with a letter"
        )
    if not _COLOR_RE.match(data.color):
        raise ValueError("color must be a hex color like #3b82f6")

    existing = await db.get(WorkCategoryModel, data.category_key)
    if existing:
        raise ValueError(f"Category '{data.category_key}' already exists")

    max_order = await db.scalar(select(func.max(WorkCategoryModel.display_order)))

    cat = WorkCategoryModel(
        category_key=data.category_key,
        display_name=data.display_name,
        description=data.description,
        color=data.color,
        exclude_from_stats=data.exclude_from_stats,
        display_order=(max_order or 0) + 1,
        is_default=False,
    )
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return cat


async def update_category(
    db: AsyncSession, category_key: str, data: WorkCategoryUpdate,
) -> WorkCategoryModel:
    cat = await db.get(WorkCategoryModel, category_key)
    if not cat:
        raise ValueError(f"Category '{category_key}' not found")

    # "unknown" can never be excluded from stats
    if category_key == "unknown" and data.exclude_from_stats is True:
        raise ValueError("Cannot exclude 'unknown' category from stats")

    if data.display_name is not None:
        cat.display_name = data.display_name
    if data.description is not None:
        cat.description = data.description
    if data.color is not None:
        if not _COLOR_RE.match(data.color):
            raise ValueError("color must be a hex color like #3b82f6")
        cat.color = data.color
    if data.exclude_from_stats is not None:
        cat.exclude_from_stats = data.exclude_from_stats
    if data.display_order is not None:
        cat.display_order = data.display_order

    await db.commit()
    await db.refresh(cat)
    return cat


async def delete_category(db: AsyncSession, category_key: str) -> None:
    cat = await db.get(WorkCategoryModel, category_key)
    if not cat:
        raise ValueError(f"Category '{category_key}' not found")
    if cat.is_default:
        raise ValueError(f"Cannot delete default category '{category_key}'")

    # Check for PRs/issues using this category
    pr_count = await db.scalar(
        select(func.count()).select_from(PullRequest).where(
            PullRequest.work_category == category_key,
        )
    ) or 0
    issue_count = await db.scalar(
        select(func.count()).select_from(Issue).where(
            Issue.work_category == category_key,
        )
    ) or 0
    if pr_count or issue_count:
        raise ValueError(
            f"Cannot delete category '{category_key}': {pr_count} PR(s) and {issue_count} issue(s) still assigned. "
            "Reclassify items first."
        )

    # Rules cascade-deleted via relationship
    await db.execute(
        delete(WorkCategoryRule).where(WorkCategoryRule.category_key == category_key)
    )
    await db.execute(
        delete(WorkCategoryModel).where(WorkCategoryModel.category_key == category_key)
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Rule CRUD
# ---------------------------------------------------------------------------


async def create_rule(db: AsyncSession, data: WorkCategoryRuleCreate) -> WorkCategoryRule:
    if data.match_type not in VALID_MATCH_TYPES:
        raise ValueError(f"match_type must be one of: {', '.join(sorted(VALID_MATCH_TYPES))}")

    # Validate category exists
    cat = await db.get(WorkCategoryModel, data.category_key)
    if not cat:
        raise ValueError(f"Category '{data.category_key}' not found")

    # Validate regex if title_regex (includes ReDoS check)
    if data.match_type == "title_regex":
        _validate_regex_safe(data.match_value)

    rule = WorkCategoryRule(
        match_type=data.match_type,
        match_value=data.match_value,
        description=data.description,
        case_sensitive=data.case_sensitive,
        category_key=data.category_key,
        priority=data.priority,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def update_rule(
    db: AsyncSession, rule_id: int, data: WorkCategoryRuleUpdate,
) -> WorkCategoryRule:
    rule = await db.get(WorkCategoryRule, rule_id)
    if not rule:
        raise ValueError(f"Rule {rule_id} not found")

    if data.match_type is not None:
        if data.match_type not in VALID_MATCH_TYPES:
            raise ValueError(f"match_type must be one of: {', '.join(sorted(VALID_MATCH_TYPES))}")
        rule.match_type = data.match_type

    if data.match_value is not None:
        match_type = data.match_type or rule.match_type
        if match_type == "title_regex":
            _validate_regex_safe(data.match_value)
        rule.match_value = data.match_value

    if data.description is not None:
        rule.description = data.description
    if data.case_sensitive is not None:
        rule.case_sensitive = data.case_sensitive
    if data.category_key is not None:
        cat = await db.get(WorkCategoryModel, data.category_key)
        if not cat:
            raise ValueError(f"Category '{data.category_key}' not found")
        rule.category_key = data.category_key
    if data.priority is not None:
        rule.priority = data.priority

    await db.commit()
    await db.refresh(rule)
    return rule


async def delete_rule(db: AsyncSession, rule_id: int) -> None:
    rule = await db.get(WorkCategoryRule, rule_id)
    if not rule:
        raise ValueError(f"Rule {rule_id} not found")

    await db.execute(delete(WorkCategoryRule).where(WorkCategoryRule.id == rule_id))
    await db.commit()


# ---------------------------------------------------------------------------
# Batch reclassification
# ---------------------------------------------------------------------------


async def reclassify_all(db: AsyncSession) -> dict:
    """Reclassify all non-manual PRs and issues using current DB rules.

    Returns dict with prs_updated, issues_updated, duration_s.
    """
    start = time.monotonic()
    rules = await get_all_rules(db)

    # --- PRs ---
    pr_result = await db.execute(
        select(
            PullRequest.id, PullRequest.labels, PullRequest.title,
            PullRequest.closes_issue_numbers, PullRequest.repo_id,
        ).where(
            or_(
                PullRequest.work_category_source != "manual",
                PullRequest.work_category_source.is_(None),
            )
        )
    )
    pr_rows = pr_result.all()
    BATCH_SIZE = 500
    pr_count = 0
    for row in pr_rows:
        cat, source = classify_work_item_with_rules(row.labels, row.title, rules)
        await db.execute(
            update(PullRequest).where(PullRequest.id == row.id).values(
                work_category=cat,
                work_category_source=source if source else None,
            )
        )
        pr_count += 1
        if pr_count % BATCH_SIZE == 0:
            await db.commit()

    # --- Issues ---
    issue_result = await db.execute(
        select(Issue.id, Issue.labels, Issue.title, Issue.repo_id, Issue.number, Issue.issue_type).where(
            or_(
                Issue.work_category_source != "manual",
                Issue.work_category_source.is_(None),
            )
        )
    )
    issue_rows = issue_result.all()
    issue_count = 0
    for row in issue_rows:
        cat, source = classify_work_item_with_rules(row.labels, row.title, rules, issue_type=row.issue_type)
        await db.execute(
            update(Issue).where(Issue.id == row.id).values(
                work_category=cat,
                work_category_source=source if source else None,
            )
        )
        issue_count += 1
        if issue_count % BATCH_SIZE == 0:
            await db.commit()

    # --- Cross-reference: unknown PRs inherit from linked issues ---
    # Build issue lookup from stored categories
    issue_cats_result = await db.execute(
        select(Issue.repo_id, Issue.number, Issue.work_category).where(
            Issue.work_category.isnot(None),
            Issue.work_category != "unknown",
        )
    )
    issues_by_key: dict[tuple[int, int], str] = {
        (row.repo_id, row.number): row.work_category
        for row in issue_cats_result.all()
    }

    # Find unknown PRs with linked issues
    unknown_prs = await db.execute(
        select(PullRequest.id, PullRequest.repo_id, PullRequest.closes_issue_numbers).where(
            PullRequest.work_category == "unknown",
            PullRequest.closes_issue_numbers.isnot(None),
            or_(
                PullRequest.work_category_source != "manual",
                PullRequest.work_category_source.is_(None),
            ),
        )
    )
    for row in unknown_prs.all():
        linked_numbers = row.closes_issue_numbers or []
        linked_cats = [
            issues_by_key[(row.repo_id, n)]
            for n in linked_numbers
            if (row.repo_id, n) in issues_by_key
        ]
        if linked_cats:
            best_cat = Counter(linked_cats).most_common(1)[0][0]
            await db.execute(
                update(PullRequest).where(PullRequest.id == row.id).values(
                    work_category=best_cat,
                    work_category_source="cross_ref",
                )
            )

    await db.commit()

    duration = round(time.monotonic() - start, 2)
    logger.info(
        "Reclassification complete",
        prs=pr_count, issues=issue_count, duration_s=duration,
        event_type="system.config",
    )

    return {
        "prs_updated": pr_count,
        "issues_updated": issue_count,
        "duration_s": duration,
    }


# ---------------------------------------------------------------------------
# Suggestions: scan GitHub data for uncovered labels / issue types
# ---------------------------------------------------------------------------

# Keyword hints for suggesting a category from a label name.
# Keys are category_keys, values are substrings to look for (case-insensitive).
_CATEGORY_HINTS: dict[str, list[str]] = {
    "feature": ["feature", "feat", "enhancement", "story"],
    "bugfix": ["bug", "defect", "hotfix", "regression"],
    "tech_debt": ["refactor", "cleanup", "chore", "dependencies", "dependency", "deps", "tech-debt", "debt", "bump", "lint"],
    "ops": ["ops", "infra", "ci/cd", "deploy", "devops", "monitor", "config", "documentation", "docs", "pipeline"],
}


def _suggest_category(value: str) -> str:
    """Guess a category for a label/issue-type based on keyword substring matching."""
    lower = value.lower()
    for cat_key, hints in _CATEGORY_HINTS.items():
        for hint in hints:
            if hint in lower:
                return cat_key
    return "unknown"


async def scan_suggestions(db: AsyncSession) -> list[dict]:
    """Scan synced PR/issue data for labels and issue types not covered by rules.

    Returns a list of dicts with match_type, match_value, suggested_category,
    usage_count — sorted by usage_count descending.
    """
    rules = await get_all_rules(db)

    # Build sets of already-covered values per match_type (case-insensitive for labels)
    covered_labels: set[str] = set()
    covered_issue_types: set[str] = set()
    for rule in rules:
        if rule.match_type == "label":
            covered_labels.add(rule.match_value.lower().strip())
        elif rule.match_type == "issue_type":
            covered_issue_types.add(rule.match_value.lower().strip())

    suggestions: list[dict] = []

    # --- Collect labels from PRs + issues (Python-side for SQLite compat) ---
    label_counts: dict[str, int] = {}

    pr_label_rows = await db.execute(
        select(PullRequest.labels).where(PullRequest.labels.isnot(None))
    )
    for (labels,) in pr_label_rows.all():
        for lbl in (labels or []):
            lbl = lbl.strip()
            if lbl:
                label_counts[lbl] = label_counts.get(lbl, 0) + 1

    issue_label_rows = await db.execute(
        select(Issue.labels).where(Issue.labels.isnot(None))
    )
    for (labels,) in issue_label_rows.all():
        for lbl in (labels or []):
            lbl = lbl.strip()
            if lbl:
                label_counts[lbl] = label_counts.get(lbl, 0) + 1

    # Filter to uncovered labels
    for lbl, count in label_counts.items():
        if lbl.lower().strip() not in covered_labels:
            suggestions.append({
                "match_type": "label",
                "match_value": lbl,
                "suggested_category": _suggest_category(lbl),
                "usage_count": count,
            })

    # --- Distinct issue types ---
    issue_type_rows = await db.execute(
        select(Issue.issue_type, func.count().label("cnt")).where(
            Issue.issue_type.isnot(None),
        ).group_by(Issue.issue_type)
    )
    for row in issue_type_rows.all():
        it = row.issue_type.strip()
        if it and it.lower() not in covered_issue_types:
            suggestions.append({
                "match_type": "issue_type",
                "match_value": it,
                "suggested_category": _suggest_category(it),
                "usage_count": row.cnt,
            })

    # Sort by usage count descending
    suggestions.sort(key=lambda s: s["usage_count"], reverse=True)
    return suggestions


async def bulk_create_rules(
    db: AsyncSession, rules_data: list[WorkCategoryRuleCreate],
) -> int:
    """Create multiple classification rules in one transaction.

    Returns the count of rules created.
    """
    valid_categories = await load_valid_categories(db)

    for data in rules_data:
        if data.match_type not in VALID_MATCH_TYPES:
            raise ValueError(f"match_type must be one of: {', '.join(sorted(VALID_MATCH_TYPES))}")
        if data.category_key not in valid_categories:
            raise ValueError(f"Category '{data.category_key}' not found")
        if data.match_type == "title_regex":
            _validate_regex_safe(data.match_value)

    created = 0
    for data in rules_data:
        rule = WorkCategoryRule(
            match_type=data.match_type,
            match_value=data.match_value,
            description=data.description,
            case_sensitive=data.case_sensitive,
            category_key=data.category_key,
            priority=data.priority,
        )
        db.add(rule)
        created += 1

    await db.commit()

    logger.info(
        "Bulk-created work category rules",
        count=created,
        event_type="system.config",
    )
    return created
