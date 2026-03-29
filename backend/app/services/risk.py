"""PR risk scoring service (P3-05).

Scores PRs by risk level based on size, review quality, author experience,
and merge patterns. All factors are computed from existing PR/review data.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import Developer, PRReview, PullRequest, Repository
from app.schemas.schemas import (
    RiskAssessment,
    RiskFactor,
    RiskSummaryResponse,
)


from app.services.utils import default_range as _default_range


def _risk_level(score: float) -> str:
    if score >= 0.8:
        return "critical"
    if score >= 0.6:
        return "high"
    if score >= 0.3:
        return "medium"
    return "low"


LEVEL_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def compute_pr_risk(
    pr: PullRequest,
    author_merged_count: int | None,
    reviews: list[PRReview] | None = None,
) -> tuple[list[RiskFactor], float]:
    """Pure function: compute risk factors and score for a single PR.

    Args:
        pr: PullRequest ORM object (with relationships loaded or not needed).
        author_merged_count: Number of merged PRs by this author in the same
            repo, or None if author is not in the team registry.
        reviews: List of PRReview objects for this PR. If None, uses pr.reviews.

    Returns:
        Tuple of (risk_factors list, risk_score float 0.0-1.0).
    """
    factors: list[RiskFactor] = []
    reviews = reviews if reviews is not None else pr.reviews

    # Size factors
    additions = pr.additions or 0
    if additions > 1000:
        factors.append(RiskFactor(
            factor="very_large_pr",
            weight=0.35,
            description=f"Very large PR with {additions:,} additions",
        ))
    elif additions > 500:
        factors.append(RiskFactor(
            factor="large_pr",
            weight=0.20,
            description=f"Large PR with {additions:,} additions",
        ))

    changed = pr.changed_files or 0
    if changed > 15:
        factors.append(RiskFactor(
            factor="many_files",
            weight=0.10,
            description=f"Touches {changed} files",
        ))

    # Author experience
    if author_merged_count is None:
        # External contributor — not in team registry
        factors.append(RiskFactor(
            factor="new_contributor",
            weight=0.15,
            description="Author is not in the team registry",
        ))
    elif author_merged_count < 5:
        factors.append(RiskFactor(
            factor="new_contributor",
            weight=0.15,
            description=f"Author has only {author_merged_count} merged PR(s) in this repo",
        ))

    # Review factors
    approved_reviews = [r for r in reviews if r.state == "APPROVED"]
    if pr.is_merged is True and len(approved_reviews) == 0:
        factors.append(RiskFactor(
            factor="no_review",
            weight=0.25,
            description="Merged without any approved review",
        ))
    elif len(reviews) > 0 and all(r.quality_tier == "rubber_stamp" for r in reviews):
        factors.append(RiskFactor(
            factor="rubber_stamp_only",
            weight=0.20,
            description="All reviews are rubber-stamp quality",
        ))

    # Merge speed
    if pr.is_merged is True and pr.time_to_merge_s is not None and pr.time_to_merge_s < 7200:
        hours = pr.time_to_merge_s / 3600
        factors.append(RiskFactor(
            factor="fast_tracked",
            weight=0.15,
            description=f"Merged in {hours:.1f}h (under 2h threshold)",
        ))

    # Self-merged
    if pr.is_self_merged:
        factors.append(RiskFactor(
            factor="self_merged",
            weight=0.10,
            description="PR was merged by its own author",
        ))

    # Review rounds
    if pr.review_round_count >= 3:
        factors.append(RiskFactor(
            factor="high_review_rounds",
            weight=0.10,
            description=f"{pr.review_round_count} review round-trips",
        ))

    # Hotfix branch
    branch = (pr.head_branch or "").lower()
    if branch.startswith("hotfix/") or branch.startswith("fix/"):
        factors.append(RiskFactor(
            factor="hotfix_branch",
            weight=0.10,
            description=f"Branch '{pr.head_branch}' indicates a hotfix",
        ))

    score = min(1.0, sum(f.weight for f in factors))
    return factors, score


async def get_pr_risk(db: AsyncSession, pr_id: int) -> RiskAssessment | None:
    """Compute risk assessment for a single PR by its DB id."""
    pr = await db.get(
        PullRequest,
        pr_id,
        options=[selectinload(PullRequest.reviews), selectinload(PullRequest.repo)],
    )
    if not pr:
        return None

    author_merged_count = await _author_merged_count(db, pr)
    factors, score = compute_pr_risk(pr, author_merged_count)

    author_name = None
    if pr.author_id:
        author = await db.get(Developer, pr.author_id)
        if author:
            author_name = author.display_name or author.github_username

    return RiskAssessment(
        pr_id=pr.id,
        number=pr.number,
        title=pr.title or "",
        html_url=pr.html_url or "",
        repo_name=pr.repo.name if pr.repo else "",
        author_name=author_name,
        author_id=pr.author_id,
        risk_score=round(score, 2),
        risk_level=_risk_level(score),
        risk_factors=factors,
        is_open=pr.state == "open",
    )


async def get_risk_summary(
    db: AsyncSession,
    team: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    min_risk_level: str = "medium",
    scope: str = "all",
) -> RiskSummaryResponse:
    """Compute risk summary for PRs in the given period.

    Args:
        scope: "all" (default), "open", or "merged"
        min_risk_level: Only include PRs at or above this level in high_risk_prs
    """
    date_from, date_to = _default_range(date_from, date_to)
    min_level_order = LEVEL_ORDER.get(min_risk_level, 1)

    # Build base query
    stmt = (
        select(PullRequest)
        .options(selectinload(PullRequest.reviews), selectinload(PullRequest.repo))
        .where(PullRequest.created_at >= date_from)
        .where(PullRequest.created_at <= date_to)
        .where(PullRequest.is_draft.isnot(True))
    )

    if scope == "open":
        stmt = stmt.where(PullRequest.state == "open")
    elif scope == "merged":
        stmt = stmt.where(PullRequest.is_merged.is_(True))

    if team:
        dev_ids = (
            select(Developer.id).where(
                Developer.team == team,
                Developer.is_active.is_(True),
            )
        )
        stmt = stmt.where(PullRequest.author_id.in_(dev_ids))

    result = await db.execute(stmt)
    prs = result.scalars().all()

    # Pre-compute author merged counts in bulk
    author_counts = await _bulk_author_merged_counts(db, prs)

    # Pre-fetch author names
    author_names = await _bulk_author_names(db, prs)

    # Score all PRs
    assessments: list[RiskAssessment] = []
    level_counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    total_score = 0.0

    for pr in prs:
        merged_count = author_counts.get((pr.author_id, pr.repo_id))
        factors, score = compute_pr_risk(pr, merged_count)
        level = _risk_level(score)
        level_counts[level] += 1
        total_score += score

        if LEVEL_ORDER[level] >= min_level_order:
            assessments.append(RiskAssessment(
                pr_id=pr.id,
                number=pr.number,
                title=pr.title or "",
                html_url=pr.html_url or "",
                repo_name=pr.repo.name if pr.repo else "",
                author_name=author_names.get(pr.author_id),
                author_id=pr.author_id,
                risk_score=round(score, 2),
                risk_level=level,
                risk_factors=factors,
                is_open=pr.state == "open",
            ))

    # Sort by risk score descending
    assessments.sort(key=lambda a: a.risk_score, reverse=True)

    total = len(prs)
    return RiskSummaryResponse(
        high_risk_prs=assessments,
        total_scored=total,
        avg_risk_score=round(total_score / total, 2) if total > 0 else 0.0,
        prs_by_level=level_counts,
    )


async def _author_merged_count(db: AsyncSession, pr: PullRequest) -> int | None:
    """Count merged PRs by this PR's author in the same repo."""
    if pr.author_id is None:
        return None
    count = await db.scalar(
        select(func.count())
        .select_from(PullRequest)
        .where(
            and_(
                PullRequest.author_id == pr.author_id,
                PullRequest.repo_id == pr.repo_id,
                PullRequest.is_merged.is_(True),
            )
        )
    )
    return count or 0


async def _bulk_author_merged_counts(
    db: AsyncSession, prs: list[PullRequest]
) -> dict[tuple[int | None, int], int | None]:
    """Bulk-fetch merged PR counts per (author_id, repo_id) pair."""
    # Collect unique (author_id, repo_id) pairs
    pairs = {(pr.author_id, pr.repo_id) for pr in prs}
    result: dict[tuple[int | None, int], int | None] = {}

    # Authors not in registry → None
    for author_id, repo_id in pairs:
        if author_id is None:
            result[(None, repo_id)] = None

    # Registered authors — single grouped query
    registered_pairs = [(a, r) for a, r in pairs if a is not None]
    if registered_pairs:
        author_ids = list({a for a, _ in registered_pairs})
        repo_ids = list({r for _, r in registered_pairs})
        stmt = (
            select(
                PullRequest.author_id,
                PullRequest.repo_id,
                func.count().label("cnt"),
            )
            .where(
                and_(
                    PullRequest.author_id.in_(author_ids),
                    PullRequest.repo_id.in_(repo_ids),
                    PullRequest.is_merged.is_(True),
                )
            )
            .group_by(PullRequest.author_id, PullRequest.repo_id)
        )
        rows = await db.execute(stmt)
        for row in rows:
            result[(row.author_id, row.repo_id)] = row.cnt

        # Fill in zeros for pairs with no merged PRs
        for author_id, repo_id in registered_pairs:
            if (author_id, repo_id) not in result:
                result[(author_id, repo_id)] = 0

    return result


async def _bulk_author_names(
    db: AsyncSession, prs: list[PullRequest]
) -> dict[int | None, str | None]:
    """Bulk-fetch author display names."""
    author_ids = list({pr.author_id for pr in prs if pr.author_id is not None})
    if not author_ids:
        return {}

    stmt = select(Developer.id, Developer.display_name, Developer.github_username).where(
        Developer.id.in_(author_ids)
    )
    rows = await db.execute(stmt)
    return {
        row.id: row.display_name or row.github_username
        for row in rows
    }
