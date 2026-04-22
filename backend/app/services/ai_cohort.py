"""Phase 10 — AI cohort classification for DORA v2 cohort split.

Classifies each PR as `"human"`, `"ai_reviewed"`, `"ai_authored"`, or `"hybrid"`
based on admin-configurable signals on reviewer usernames, commit email patterns,
and PR labels.
"""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import PRReview, PullRequest

AICohort = Literal["human", "ai_reviewed", "ai_authored", "hybrid"]

# Default AI reviewer username patterns (bot suffixes / known AI reviewers)
DEFAULT_AI_REVIEWER_USERNAMES = {
    "github-copilot[bot]",
    "github-copilot-preview[bot]",
    "copilot[bot]",
    "copilot-autofix[bot]",
    "coderabbitai[bot]",
    "claude[bot]",
    "sourcery-ai[bot]",
    "graphite-app[bot]",
    "qodo-ai[bot]",
}

# Default AI-authored label patterns (case-insensitive substring match on labels)
DEFAULT_AI_AUTHOR_LABELS = {
    "ai-authored",
    "copilot",
    "copilot-generated",
    "claude-generated",
    "ai-assisted",
}

# Default AI-author commit email patterns
DEFAULT_AI_AUTHOR_EMAIL_PATTERNS = {
    "copilot@github.com",
    "noreply@anthropic.com",
}


@dataclass
class AIDetectionRules:
    reviewer_usernames: set[str]
    author_labels: set[str]
    author_email_patterns: set[str]


def default_rules() -> AIDetectionRules:
    return AIDetectionRules(
        reviewer_usernames={u.lower() for u in DEFAULT_AI_REVIEWER_USERNAMES},
        author_labels={l.lower() for l in DEFAULT_AI_AUTHOR_LABELS},
        author_email_patterns={p.lower() for p in DEFAULT_AI_AUTHOR_EMAIL_PATTERNS},
    )


async def classify_ai_cohort(
    db: AsyncSession,
    pr: PullRequest,
    rules: AIDetectionRules | None = None,
) -> AICohort:
    """Classify a single PR. Returns one of 'human', 'ai_reviewed', 'ai_authored', 'hybrid'.

    Cheap — reads the PR's reviews and labels; no GraphQL calls.
    """
    r = rules or default_rules()

    ai_reviewed = False
    ai_authored = False

    # Check reviewers
    review_usernames = (
        await db.execute(
            select(PRReview.reviewer_github_username).where(
                PRReview.pr_id == pr.id,
                PRReview.reviewer_github_username.isnot(None),
            )
        )
    ).scalars().all()
    for u in review_usernames:
        if u and u.lower() in r.reviewer_usernames:
            ai_reviewed = True
            break

    # Check labels
    labels = pr.labels if isinstance(pr.labels, list) else []
    for lbl in labels:
        if isinstance(lbl, str) and lbl.lower() in r.author_labels:
            ai_authored = True
            break

    # (Future) check commit author emails — requires fetched commit data, not in PullRequest directly

    if ai_reviewed and ai_authored:
        return "hybrid"
    if ai_reviewed:
        return "ai_reviewed"
    if ai_authored:
        return "ai_authored"
    return "human"


async def classify_ai_cohorts_batch(
    db: AsyncSession,
    pr_ids: list[int],
    rules: AIDetectionRules | None = None,
) -> dict[int, AICohort]:
    """Classify many PRs in one pass. Uses a single review-scan query."""
    if not pr_ids:
        return {}
    r = rules or default_rules()

    # Build set of PRs with any AI reviewer
    ai_reviewed_ids = {
        pid
        for pid, username in (
            await db.execute(
                select(PRReview.pr_id, PRReview.reviewer_github_username).where(
                    PRReview.pr_id.in_(pr_ids),
                    PRReview.reviewer_github_username.isnot(None),
                )
            )
        ).all()
        if username and username.lower() in r.reviewer_usernames
    }

    # Fetch PR labels
    prs = (
        await db.execute(
            select(PullRequest.id, PullRequest.labels).where(PullRequest.id.in_(pr_ids))
        )
    ).all()

    result: dict[int, AICohort] = {}
    for pid, labels in prs:
        ai_authored = False
        if isinstance(labels, list):
            for lbl in labels:
                if isinstance(lbl, str) and lbl.lower() in r.author_labels:
                    ai_authored = True
                    break
        ai_reviewed = pid in ai_reviewed_ids
        if ai_reviewed and ai_authored:
            result[pid] = "hybrid"
        elif ai_reviewed:
            result[pid] = "ai_reviewed"
        elif ai_authored:
            result[pid] = "ai_authored"
        else:
            result[pid] = "human"
    return result
