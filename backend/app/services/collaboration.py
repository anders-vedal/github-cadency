from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Developer, PRReview, PullRequest, Repository
from app.schemas.schemas import (
    BusFactorEntry,
    CollaborationInsights,
    CollaborationPair,
    CollaborationResponse,
    CollaborationTrendPeriod,
    CollaborationTrendsResponse,
)


def _default_range(
    date_from: datetime | None, date_to: datetime | None
) -> tuple[datetime, datetime]:
    if not date_to:
        date_to = datetime.now(timezone.utc)
    if not date_from:
        date_from = date_to - timedelta(days=30)
    return date_from, date_to


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
