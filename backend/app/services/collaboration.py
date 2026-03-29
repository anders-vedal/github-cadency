from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Developer, PRReview, PRReviewComment, PullRequest, Repository
from app.schemas.schemas import (
    BusFactorEntry,
    CollaborationInsights,
    CollaborationPair,
    CollaborationPairDetail,
    CollaborationResponse,
    CollaborationTrendPeriod,
    CollaborationTrendsResponse,
    CommentTypeBreakdown,
    PairRelationship,
    PairReviewedPR,
    QualityTierBreakdown,
)


from app.services.utils import default_range as _default_range


# --- Pair Relationship Classification ---

QUALITY_TIER_SCORE = {"minimal": 0, "rubber_stamp": 1, "standard": 2, "thorough": 3}


@dataclass
class PairRelationshipInput:
    total_reviews: int
    reverse_reviews: int
    approval_rate: float  # 0-1
    changes_requested_rate: float  # 0-1
    avg_quality_tier_score: float  # 0-3
    comment_type_counts: dict[str, int]
    total_comments: int


def classify_pair_relationship(stats: PairRelationshipInput) -> PairRelationship:
    """Pure function: classify a reviewer→author pair relationship from aggregate stats.

    Designed with a clear input/output contract so the body can be swapped with
    an AI classifier later (same PairRelationshipInput in, same PairRelationship out).
    """
    if stats.total_reviews == 0:
        return PairRelationship(
            label="none", confidence=1.0, explanation="No review interactions in this period."
        )

    if stats.total_reviews < 3:
        return PairRelationship(
            label="casual",
            confidence=0.5,
            explanation=f"Only {stats.total_reviews} review(s) — insufficient data to classify.",
        )

    total_both = stats.total_reviews + stats.reverse_reviews
    ratio = stats.total_reviews / total_both if total_both > 0 else 1.0

    substantive = stats.comment_type_counts.get("blocker", 0) + stats.comment_type_counts.get("architectural", 0)
    substantive_pct = substantive / stats.total_comments if stats.total_comments > 0 else 0

    # Data-volume confidence boost: more reviews = more confident
    volume_boost = min(stats.total_reviews / 20, 1.0)  # caps at 20 reviews

    # Rubber stamp: high approval, low quality, few comments
    if (
        stats.approval_rate >= 0.9
        and stats.avg_quality_tier_score < 1.0
        and stats.total_comments < stats.total_reviews * 0.5
    ):
        conf = 0.8 + 0.1 * volume_boost
        return PairRelationship(
            label="rubber_stamp",
            confidence=round(conf, 2),
            explanation="High approval rate with minimal review depth — reviews may lack thoroughness.",
        )

    # Mentor: strong asymmetry + substantive comments + high quality
    if ratio >= 0.75 and substantive_pct > 0.3 and stats.avg_quality_tier_score >= 2.0:
        conf = 0.7 + 0.2 * volume_boost
        return PairRelationship(
            label="mentor",
            confidence=round(conf, 2),
            explanation="Heavily one-directional reviews with substantive architectural/blocker feedback and high review quality — consistent with a mentoring relationship.",
        )

    # Gatekeeper: strong asymmetry + high changes_requested rate
    if ratio >= 0.83 and stats.changes_requested_rate >= 0.3:
        conf = 0.7 + 0.15 * volume_boost
        return PairRelationship(
            label="gatekeeper",
            confidence=round(conf, 2),
            explanation="Strongly one-directional reviews with frequent change requests — reviewer acts as a quality gate.",
        )

    # One-way dependency: strong asymmetry, doesn't match mentor/gatekeeper
    if ratio >= 0.8:
        conf = 0.6 + 0.2 * volume_boost
        return PairRelationship(
            label="one_way_dependency",
            confidence=round(conf, 2),
            explanation="Reviews flow primarily in one direction without strong mentoring or gatekeeping signals.",
        )

    # Peer: roughly balanced
    if 0.35 <= ratio <= 0.65 and total_both >= 4:
        conf = 0.6 + 0.25 * volume_boost
        return PairRelationship(
            label="peer",
            confidence=round(conf, 2),
            explanation="Balanced, bidirectional review relationship — typical peer collaboration.",
        )

    # Fallback: weak signal
    return PairRelationship(
        label="peer",
        confidence=round(0.4 + 0.1 * volume_boost, 2),
        explanation="No strong directional or quality signals detected — defaulting to peer.",
    )


# --- Pair Detail Query ---


async def get_collaboration_pair_detail(
    db: AsyncSession,
    reviewer_id: int,
    author_id: int,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> CollaborationPairDetail:
    date_from, date_to = _default_range(date_from, date_to)

    # Validate developers exist
    reviewer = await db.get(Developer, reviewer_id)
    author = await db.get(Developer, author_id)
    if not reviewer or not author:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Developer not found")

    # Query 1: Reviews + PR data
    review_rows = (
        await db.execute(
            select(
                PRReview.id,
                PRReview.state,
                PRReview.quality_tier,
                PRReview.submitted_at,
                PRReview.body_length,
                PullRequest.id.label("pr_id"),
                PullRequest.title,
                PullRequest.html_url,
                PullRequest.additions,
                PullRequest.deletions,
                PullRequest.number,
                Repository.full_name.label("repo_full_name"),
            )
            .join(PullRequest, PRReview.pr_id == PullRequest.id)
            .join(Repository, PullRequest.repo_id == Repository.id)
            .where(
                PRReview.reviewer_id == reviewer_id,
                PullRequest.author_id == author_id,
                PRReview.submitted_at >= date_from,
                PRReview.submitted_at <= date_to,
            )
            .order_by(PRReview.submitted_at.desc())
        )
    ).all()

    total_reviews = len(review_rows)

    if total_reviews == 0:
        relationship = classify_pair_relationship(
            PairRelationshipInput(0, 0, 0, 0, 0, {}, 0)
        )
        return CollaborationPairDetail(
            reviewer_id=reviewer_id,
            reviewer_name=reviewer.display_name,
            reviewer_avatar_url=reviewer.avatar_url,
            reviewer_team=reviewer.team,
            author_id=author_id,
            author_name=author.display_name,
            author_avatar_url=author.avatar_url,
            author_team=author.team,
            total_reviews=0,
            approval_rate=0,
            changes_requested_rate=0,
            avg_quality_tier="minimal",
            quality_tier_breakdown=[],
            comment_type_breakdown=[],
            total_comments=0,
            relationship=relationship,
            recent_prs=[],
        )

    # Compute summary stats from review rows
    approvals = sum(1 for r in review_rows if r.state == "APPROVED")
    changes_requested = sum(1 for r in review_rows if r.state == "CHANGES_REQUESTED")
    approval_rate = approvals / total_reviews if total_reviews > 0 else 0
    cr_rate = changes_requested / total_reviews if total_reviews > 0 else 0

    quality_tiers = Counter(r.quality_tier for r in review_rows)
    quality_tier_breakdown = [
        QualityTierBreakdown(tier=t, count=c) for t, c in quality_tiers.most_common()
    ]
    avg_quality_score = (
        sum(QUALITY_TIER_SCORE.get(r.quality_tier, 0) for r in review_rows) / total_reviews
    )
    avg_quality_tier = quality_tiers.most_common(1)[0][0] if quality_tiers else "minimal"

    # Query 2: Comment type breakdown (reviewer's comments on author's PRs)
    pr_ids = list({r.pr_id for r in review_rows})
    comment_type_rows = (
        await db.execute(
            select(
                PRReviewComment.comment_type,
                func.count().label("cnt"),
            )
            .join(PullRequest, PRReviewComment.pr_id == PullRequest.id)
            .where(
                PRReviewComment.author_github_username == reviewer.github_username,
                PullRequest.author_id == author_id,
                PRReviewComment.pr_id.in_(pr_ids),
            )
            .group_by(PRReviewComment.comment_type)
        )
    ).all()

    comment_type_counts = {row.comment_type: row.cnt for row in comment_type_rows}
    total_comments = sum(comment_type_counts.values())
    comment_type_breakdown = [
        CommentTypeBreakdown(comment_type=ct, count=c)
        for ct, c in sorted(comment_type_counts.items(), key=lambda x: -x[1])
    ]

    # Per-PR comment counts
    per_pr_comment_rows = (
        await db.execute(
            select(
                PRReviewComment.pr_id,
                func.count().label("cnt"),
            )
            .where(
                PRReviewComment.author_github_username == reviewer.github_username,
                PRReviewComment.pr_id.in_(pr_ids),
            )
            .group_by(PRReviewComment.pr_id)
        )
    ).all()
    per_pr_comments = {row.pr_id: row.cnt for row in per_pr_comment_rows}

    # Query 3: Reverse review count (author reviewed reviewer's PRs)
    reverse_count_row = await db.execute(
        select(func.count())
        .select_from(PRReview)
        .join(PullRequest, PRReview.pr_id == PullRequest.id)
        .where(
            PRReview.reviewer_id == author_id,
            PullRequest.author_id == reviewer_id,
            PRReview.submitted_at >= date_from,
            PRReview.submitted_at <= date_to,
        )
    )
    reverse_reviews = reverse_count_row.scalar() or 0

    # Classify relationship
    relationship = classify_pair_relationship(
        PairRelationshipInput(
            total_reviews=total_reviews,
            reverse_reviews=reverse_reviews,
            approval_rate=approval_rate,
            changes_requested_rate=cr_rate,
            avg_quality_tier_score=avg_quality_score,
            comment_type_counts=comment_type_counts,
            total_comments=total_comments,
        )
    )

    # Build recent PRs list (dedupe by PR, take most recent review per PR, limit 30)
    seen_prs: set[int] = set()
    recent_prs: list[PairReviewedPR] = []
    for r in review_rows:
        if r.pr_id in seen_prs:
            continue
        seen_prs.add(r.pr_id)
        recent_prs.append(
            PairReviewedPR(
                pr_id=r.pr_id,
                pr_number=r.number,
                title=r.title or "",
                html_url=r.html_url,
                repo_full_name=r.repo_full_name or "",
                review_state=r.state,
                quality_tier=r.quality_tier,
                comment_count=per_pr_comments.get(r.pr_id, 0),
                additions=r.additions,
                deletions=r.deletions,
                submitted_at=r.submitted_at,
            )
        )
        if len(recent_prs) >= 30:
            break

    return CollaborationPairDetail(
        reviewer_id=reviewer_id,
        reviewer_name=reviewer.display_name,
        reviewer_avatar_url=reviewer.avatar_url,
        reviewer_team=reviewer.team,
        author_id=author_id,
        author_name=author.display_name,
        author_avatar_url=author.avatar_url,
        author_team=author.team,
        total_reviews=total_reviews,
        approval_rate=round(approval_rate, 3),
        changes_requested_rate=round(cr_rate, 3),
        avg_quality_tier=avg_quality_tier,
        quality_tier_breakdown=quality_tier_breakdown,
        comment_type_breakdown=comment_type_breakdown,
        total_comments=total_comments,
        relationship=relationship,
        recent_prs=recent_prs,
    )


async def get_collaboration(
    db: AsyncSession,
    team: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> CollaborationResponse:
    date_from, date_to = _default_range(date_from, date_to)

    # Get active developers (optionally filtered by team)
    dev_query = select(Developer).where(Developer.is_active.is_(True))
    if team:
        dev_query = dev_query.where(Developer.team == team)
    dev_result = await db.execute(dev_query)
    developers = {d.id: d for d in dev_result.scalars().all()}

    if not developers:
        return CollaborationResponse(
            matrix=[],
            insights=CollaborationInsights(
                silos=[], bus_factors=[], isolated_developers=[], strongest_pairs=[]
            ),
        )

    dev_ids = list(developers.keys())

    # Query reviewer-author pairs with state breakdown
    pair_rows = (
        await db.execute(
            select(
                PRReview.reviewer_id,
                PullRequest.author_id,
                PRReview.state,
                func.count().label("cnt"),
            )
            .join(PullRequest, PRReview.pr_id == PullRequest.id)
            .where(
                PRReview.reviewer_id.in_(dev_ids),
                PullRequest.author_id.in_(dev_ids),
                PRReview.reviewer_id != PullRequest.author_id,
                PRReview.submitted_at >= date_from,
                PRReview.submitted_at <= date_to,
            )
            .group_by(PRReview.reviewer_id, PullRequest.author_id, PRReview.state)
        )
    ).all()

    # Aggregate into pairs
    pair_data: dict[tuple[int, int], dict] = defaultdict(
        lambda: {"reviews_count": 0, "approvals": 0, "changes_requested": 0}
    )
    for reviewer_id, author_id, state, cnt in pair_rows:
        key = (reviewer_id, author_id)
        pair_data[key]["reviews_count"] += cnt
        if state == "APPROVED":
            pair_data[key]["approvals"] += cnt
        elif state == "CHANGES_REQUESTED":
            pair_data[key]["changes_requested"] += cnt

    matrix = []
    for (reviewer_id, author_id), counts in pair_data.items():
        reviewer = developers.get(reviewer_id)
        author = developers.get(author_id)
        if not reviewer or not author:
            continue
        matrix.append(
            CollaborationPair(
                reviewer_id=reviewer_id,
                reviewer_name=reviewer.display_name,
                reviewer_team=reviewer.team,
                author_id=author_id,
                author_name=author.display_name,
                author_team=author.team,
                **counts,
            )
        )

    # --- Insights ---
    insights = await _compute_insights(db, developers, matrix, dev_ids, date_from, date_to)

    return CollaborationResponse(
        matrix=matrix,
        insights=insights,
    )


async def _compute_insights(
    db: AsyncSession,
    developers: dict[int, Developer],
    matrix: list[CollaborationPair],
    dev_ids: list[int],
    date_from: datetime,
    date_to: datetime,
) -> CollaborationInsights:
    # --- Silos: team pairs with zero cross-team reviews ---
    teams_with_devs: dict[str, set[int]] = defaultdict(set)
    for dev in developers.values():
        if dev.team:
            teams_with_devs[dev.team].add(dev.id)

    team_names = sorted(teams_with_devs.keys())
    cross_team_reviews: set[tuple[str, str]] = set()
    for pair in matrix:
        if pair.reviewer_team and pair.author_team and pair.reviewer_team != pair.author_team:
            key = tuple(sorted([pair.reviewer_team, pair.author_team]))
            cross_team_reviews.add(key)

    silos = []
    for i, t1 in enumerate(team_names):
        for t2 in team_names[i + 1 :]:
            key = tuple(sorted([t1, t2]))
            if key not in cross_team_reviews:
                silos.append(
                    {"team_a": t1, "team_b": t2, "note": "Zero cross-team reviews"}
                )

    # --- Bus factors: reviewers with >70% of reviews per repo ---
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
                PRReview.submitted_at <= date_to,
            )
            .group_by(PullRequest.repo_id, PRReview.reviewer_id)
        )
    ).all()

    repo_totals: dict[int, int] = defaultdict(int)
    repo_reviewer_counts: dict[int, dict[int, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    for repo_id, reviewer_id, cnt in repo_review_rows:
        repo_totals[repo_id] += cnt
        repo_reviewer_counts[repo_id][reviewer_id] += cnt

    bus_factors: list[BusFactorEntry] = []
    for repo_id, total in repo_totals.items():
        for reviewer_id, cnt in repo_reviewer_counts[repo_id].items():
            share = cnt / total * 100 if total > 0 else 0
            if share > 70 and reviewer_id in developers:
                # Get repo name
                repo = await db.get(Repository, repo_id)
                repo_name = (
                    (repo.full_name or repo.name) if repo else str(repo_id)
                )
                bus_factors.append(
                    BusFactorEntry(
                        repo_name=repo_name,
                        sole_reviewer_id=reviewer_id,
                        sole_reviewer_name=developers[reviewer_id].display_name,
                        review_share_pct=round(share, 1),
                    )
                )

    # --- Isolated developers: 0 reviews given AND received from <= 1 unique reviewer ---
    reviewers_who_gave = {p.reviewer_id for p in matrix}
    reviews_received_from: dict[int, set[int]] = defaultdict(set)
    for p in matrix:
        reviews_received_from[p.author_id].add(p.reviewer_id)

    isolated = []
    for dev_id, dev in developers.items():
        if dev_id not in reviewers_who_gave:
            unique_reviewers = len(reviews_received_from.get(dev_id, set()))
            if unique_reviewers <= 1:
                isolated.append(
                    {"developer_id": dev_id, "display_name": dev.display_name}
                )

    # --- Strongest pairs: top mutual review pairs by combined count ---
    mutual_counts: dict[tuple[int, int], int] = defaultdict(int)
    for p in matrix:
        key = (min(p.reviewer_id, p.author_id), max(p.reviewer_id, p.author_id))
        mutual_counts[key] += p.reviews_count

    strongest_pairs_sorted = sorted(
        mutual_counts.items(), key=lambda x: x[1], reverse=True
    )[:10]
    strongest = []
    for (id_a, id_b), _ in strongest_pairs_sorted:
        # Find the pair entry where id_a reviewed id_b (or either direction)
        for p in matrix:
            if p.reviewer_id == id_a and p.author_id == id_b:
                strongest.append(p)
                break
            if p.reviewer_id == id_b and p.author_id == id_a:
                strongest.append(p)
                break

    return CollaborationInsights(
        silos=silos,
        bus_factors=bus_factors,
        isolated_developers=isolated,
        strongest_pairs=strongest,
    )


async def get_collaboration_trends(
    db: AsyncSession,
    team: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> CollaborationTrendsResponse:
    """Compute bus factor/silo/isolation counts per monthly bucket."""
    date_from, date_to = _default_range(date_from, date_to)

    # Get active developers
    dev_query = select(Developer).where(Developer.is_active.is_(True))
    if team:
        dev_query = dev_query.where(Developer.team == team)
    dev_result = await db.execute(dev_query)
    developers = {d.id: d for d in dev_result.scalars().all()}

    if not developers:
        return CollaborationTrendsResponse(periods=[])

    dev_ids = list(developers.keys())

    # Fetch all reviews in the full range at once
    all_rows = (
        await db.execute(
            select(
                PRReview.reviewer_id,
                PullRequest.author_id,
                PullRequest.repo_id,
                PRReview.submitted_at,
            )
            .join(PullRequest, PRReview.pr_id == PullRequest.id)
            .where(
                PRReview.reviewer_id.in_(dev_ids),
                PullRequest.author_id.in_(dev_ids),
                PRReview.reviewer_id != PullRequest.author_id,
                PRReview.submitted_at >= date_from,
                PRReview.submitted_at <= date_to,
            )
        )
    ).all()

    # Normalize to naive UTC for Python-level datetime comparison
    # (asyncpg returns aware, aiosqlite returns naive — strip tzinfo to unify)
    def _to_naive(dt: datetime) -> datetime:
        if dt.tzinfo is not None:
            return dt.replace(tzinfo=None)
        return dt

    date_from = _to_naive(date_from)
    date_to = _to_naive(date_to)

    # Build monthly buckets
    buckets: list[tuple[datetime, datetime, str]] = []
    cursor = datetime(date_from.year, date_from.month, 1)
    while cursor < date_to:
        next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        bucket_end = min(next_month, date_to)
        label = cursor.strftime("%Y-%m")
        buckets.append((cursor, bucket_end, label))
        cursor = next_month

    # Teams for silo detection
    teams_with_devs: dict[str, set[int]] = defaultdict(set)
    for dev in developers.values():
        if dev.team:
            teams_with_devs[dev.team].add(dev.id)
    team_names = sorted(teams_with_devs.keys())
    team_pairs = [
        tuple(sorted([t1, t2]))
        for i, t1 in enumerate(team_names)
        for t2 in team_names[i + 1 :]
    ]

    # Developer team lookup
    dev_team = {d.id: d.team for d in developers.values()}

    periods = []
    for bucket_start, bucket_end, label in buckets:
        # Filter reviews into this bucket
        bucket_reviews = [
            r for r in all_rows
            if r.submitted_at and bucket_start <= _to_naive(r.submitted_at) < bucket_end
        ]

        # --- Bus factors: repos where one reviewer has >70% share ---
        repo_totals: dict[int, int] = defaultdict(int)
        repo_reviewer_counts: dict[int, dict[int, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        for reviewer_id, _author_id, repo_id, _submitted_at in bucket_reviews:
            repo_totals[repo_id] += 1
            repo_reviewer_counts[repo_id][reviewer_id] += 1

        bus_factor_count = 0
        for repo_id, total in repo_totals.items():
            for reviewer_id, cnt in repo_reviewer_counts[repo_id].items():
                if reviewer_id in developers and total > 0 and (cnt / total) > 0.7:
                    bus_factor_count += 1
                    break  # count each repo once

        # --- Silos & isolated: skip when no activity to avoid misleading spikes ---
        if not bucket_reviews:
            silo_count = 0
            isolated_count = 0
        else:
            # Silos: team pairs with zero cross-reviews
            cross_team_pairs: set[tuple[str, str]] = set()
            for reviewer_id, author_id, _repo_id, _submitted_at in bucket_reviews:
                r_team = dev_team.get(reviewer_id)
                a_team = dev_team.get(author_id)
                if r_team and a_team and r_team != a_team:
                    cross_team_pairs.add(tuple(sorted([r_team, a_team])))

            silo_count = sum(1 for pair in team_pairs if pair not in cross_team_pairs)

            # Isolated developers: 0 reviews given AND received from <= 1 unique reviewer
            reviewers_who_gave: set[int] = set()
            reviews_received_from: dict[int, set[int]] = defaultdict(set)
            for reviewer_id, author_id, _repo_id, _submitted_at in bucket_reviews:
                reviewers_who_gave.add(reviewer_id)
                reviews_received_from[author_id].add(reviewer_id)

            isolated_count = 0
            for dev_id in developers:
                if dev_id not in reviewers_who_gave:
                    if len(reviews_received_from.get(dev_id, set())) <= 1:
                        isolated_count += 1

        periods.append(
            CollaborationTrendPeriod(
                period_start=bucket_start,
                period_end=bucket_end,
                period_label=label,
                bus_factor_count=bus_factor_count,
                silo_count=silo_count,
                isolated_developer_count=isolated_count,
            )
        )

    return CollaborationTrendsResponse(periods=periods)
