"""Enhanced multi-signal collaboration scoring, works-with, over-tagged, communication scores."""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Developer,
    DeveloperCollaborationScore,
    Issue,
    IssueComment,
    PRReview,
    PRReviewComment,
    PullRequest,
)
from app.schemas.schemas import (
    CommunicationScoreEntry,
    CommunicationScoresResponse,
    OverTaggedDeveloper,
    OverTaggedResponse,
    WorksWithEntry,
    WorksWithResponse,
)

# --- Signal weights ---
W_REVIEW = 0.35
W_COAUTHOR = 0.15
W_ISSUE_COMMENT = 0.20
W_MENTION = 0.15
W_CO_ASSIGNED = 0.15

# --- Normalization caps ---
CAP_REVIEW = 20
CAP_COAUTHOR = 5
CAP_ISSUE_COMMENT = 10
CAP_MENTION = 10
CAP_CO_ASSIGNED = 5


def _normalize(count: int, cap: int) -> float:
    return min(count / cap, 1.0) if cap > 0 else 0.0


def _canonical_pair(a: int, b: int) -> tuple[int, int]:
    return (min(a, b), max(a, b))


from app.services.utils import default_range as _default_range


async def recompute_collaboration_scores(
    db: AsyncSession,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> int:
    """Recompute all pairwise collaboration scores. Returns pair count."""
    date_from, date_to = _default_range(date_from, date_to)

    # Raw counts per pair for each signal
    pair_reviews: dict[tuple[int, int], int] = defaultdict(int)
    pair_coauthor: dict[tuple[int, int], int] = defaultdict(int)
    pair_issue_comments: dict[tuple[int, int], int] = defaultdict(int)
    pair_mentions: dict[tuple[int, int], int] = defaultdict(int)
    pair_co_assigned: dict[tuple[int, int], int] = defaultdict(int)

    # --- Signal 1: PR Reviews ---
    review_rows = await db.execute(
        select(PRReview.reviewer_id, PullRequest.author_id)
        .join(PullRequest, PRReview.pr_id == PullRequest.id)
        .where(
            PRReview.reviewer_id.isnot(None),
            PullRequest.author_id.isnot(None),
            PRReview.reviewer_id != PullRequest.author_id,
            PRReview.submitted_at >= date_from,
            PRReview.submitted_at <= date_to,
        )
    )
    for reviewer_id, author_id in review_rows:
        pair = _canonical_pair(reviewer_id, author_id)
        pair_reviews[pair] += 1

    # --- Signal 2: Co-authoring (same repo) ---
    # Get all devs who merged PRs in each repo
    coauthor_rows = await db.execute(
        select(PullRequest.repo_id, PullRequest.author_id)
        .where(
            PullRequest.author_id.isnot(None),
            PullRequest.is_merged.is_(True),
            PullRequest.merged_at >= date_from,
            PullRequest.merged_at <= date_to,
        )
        .distinct()
    )
    repo_authors: dict[int, set[int]] = defaultdict(set)
    for repo_id, author_id in coauthor_rows:
        repo_authors[repo_id].add(author_id)

    for authors in repo_authors.values():
        author_list = sorted(authors)
        for i, a in enumerate(author_list):
            for b in author_list[i + 1:]:
                pair_coauthor[_canonical_pair(a, b)] += 1

    # --- Signal 3: Issue co-comments ---
    # Find devs who commented on the same issue
    # First resolve github usernames to developer IDs
    dev_rows = await db.execute(
        select(Developer.id, Developer.github_username).where(
            Developer.is_active.is_(True)
        )
    )
    username_to_id = {row.github_username: row.id for row in dev_rows}

    issue_comment_rows = await db.execute(
        select(IssueComment.issue_id, IssueComment.author_github_username)
        .where(
            IssueComment.author_github_username.isnot(None),
            IssueComment.created_at >= date_from,
            IssueComment.created_at <= date_to,
        )
    )
    issue_commenters: dict[int, set[int]] = defaultdict(set)
    for issue_id, username in issue_comment_rows:
        dev_id = username_to_id.get(username)
        if dev_id:
            issue_commenters[issue_id].add(dev_id)

    for commenters in issue_commenters.values():
        commenter_list = sorted(commenters)
        for i, a in enumerate(commenter_list):
            for b in commenter_list[i + 1:]:
                pair_issue_comments[_canonical_pair(a, b)] += 1

    # --- Signal 4: @mentions ---
    # PR review comments
    prc_mention_rows = await db.execute(
        select(PRReviewComment.author_github_username, PRReviewComment.mentions)
        .where(
            PRReviewComment.mentions.isnot(None),
            PRReviewComment.created_at >= date_from,
            PRReviewComment.created_at <= date_to,
        )
    )
    for author_username, mentions in prc_mention_rows:
        author_id = username_to_id.get(author_username) if author_username else None
        if not author_id or not mentions:
            continue
        for mentioned_username in mentions:
            mentioned_id = username_to_id.get(mentioned_username)
            if mentioned_id and mentioned_id != author_id:
                pair = _canonical_pair(author_id, mentioned_id)
                pair_mentions[pair] += 1

    # Issue comments
    ic_mention_rows = await db.execute(
        select(IssueComment.author_github_username, IssueComment.mentions)
        .where(
            IssueComment.mentions.isnot(None),
            IssueComment.created_at >= date_from,
            IssueComment.created_at <= date_to,
        )
    )
    for author_username, mentions in ic_mention_rows:
        author_id = username_to_id.get(author_username) if author_username else None
        if not author_id or not mentions:
            continue
        for mentioned_username in mentions:
            mentioned_id = username_to_id.get(mentioned_username)
            if mentioned_id and mentioned_id != author_id:
                pair = _canonical_pair(author_id, mentioned_id)
                pair_mentions[pair] += 1

    # --- Signal 5: Co-assigned issues ---
    # GitHub only supports single assignee, but we also count issue creator + assignee
    co_assign_rows = await db.execute(
        select(Issue.id, Issue.assignee_id, Issue.creator_github_username)
        .where(
            Issue.assignee_id.isnot(None),
            Issue.created_at >= date_from,
            Issue.created_at <= date_to,
        )
    )
    for _, assignee_id, creator_username in co_assign_rows:
        creator_id = username_to_id.get(creator_username) if creator_username else None
        if creator_id and creator_id != assignee_id:
            pair = _canonical_pair(creator_id, assignee_id)
            pair_co_assigned[pair] += 1

    # --- Combine all signals ---
    all_pairs = (
        set(pair_reviews)
        | set(pair_coauthor)
        | set(pair_issue_comments)
        | set(pair_mentions)
        | set(pair_co_assigned)
    )

    if not all_pairs:
        return 0

    # Delete existing scores for this period and bulk insert new ones
    await db.execute(
        delete(DeveloperCollaborationScore).where(
            DeveloperCollaborationScore.period_start == date_from,
            DeveloperCollaborationScore.period_end == date_to,
        )
    )

    count = 0
    for a_id, b_id in all_pairs:
        rv = pair_reviews.get((a_id, b_id), 0)
        ca = pair_coauthor.get((a_id, b_id), 0)
        ic = pair_issue_comments.get((a_id, b_id), 0)
        mn = pair_mentions.get((a_id, b_id), 0)
        co = pair_co_assigned.get((a_id, b_id), 0)

        rv_norm = _normalize(rv, CAP_REVIEW)
        ca_norm = _normalize(ca, CAP_COAUTHOR)
        ic_norm = _normalize(ic, CAP_ISSUE_COMMENT)
        mn_norm = _normalize(mn, CAP_MENTION)
        co_norm = _normalize(co, CAP_CO_ASSIGNED)

        total = (
            W_REVIEW * rv_norm
            + W_COAUTHOR * ca_norm
            + W_ISSUE_COMMENT * ic_norm
            + W_MENTION * mn_norm
            + W_CO_ASSIGNED * co_norm
        )
        interaction_count = rv + ca + ic + mn + co

        score = DeveloperCollaborationScore(
            developer_a_id=a_id,
            developer_b_id=b_id,
            period_start=date_from,
            period_end=date_to,
            review_score=rv_norm,
            coauthor_score=ca_norm,
            issue_comment_score=ic_norm,
            mention_score=mn_norm,
            co_assigned_score=co_norm,
            total_score=total,
            interaction_count=interaction_count,
        )
        db.add(score)
        count += 1

    await db.commit()
    return count


async def get_works_with(
    db: AsyncSession,
    developer_id: int,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 10,
) -> WorksWithResponse:
    """Get top collaborators for a developer from materialized scores."""
    date_from, date_to = _default_range(date_from, date_to)

    # Query scores where this dev is either A or B
    result = await db.execute(
        select(DeveloperCollaborationScore)
        .where(
            (DeveloperCollaborationScore.developer_a_id == developer_id)
            | (DeveloperCollaborationScore.developer_b_id == developer_id),
            DeveloperCollaborationScore.period_start <= date_to,
            DeveloperCollaborationScore.period_end >= date_from,
        )
        .order_by(DeveloperCollaborationScore.total_score.desc())
        .limit(limit)
    )
    scores = result.scalars().all()

    collaborators: list[WorksWithEntry] = []
    for s in scores:
        other_id = s.developer_b_id if s.developer_a_id == developer_id else s.developer_a_id
        dev = await db.get(Developer, other_id)
        if not dev or not dev.is_active:
            continue
        collaborators.append(
            WorksWithEntry(
                developer_id=dev.id,
                display_name=dev.display_name,
                github_username=dev.github_username,
                avatar_url=dev.avatar_url,
                team=dev.team,
                total_score=s.total_score,
                interaction_count=s.interaction_count,
                review_score=s.review_score,
                coauthor_score=s.coauthor_score,
                issue_comment_score=s.issue_comment_score,
                mention_score=s.mention_score,
                co_assigned_score=s.co_assigned_score,
            )
        )

    return WorksWithResponse(developer_id=developer_id, collaborators=collaborators)


async def get_over_tagged(
    db: AsyncSession,
    team: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> OverTaggedResponse:
    """Detect developers who appear on an unusually high % of PRs/issues."""
    date_from, date_to = _default_range(date_from, date_to)

    # Load active developers
    dev_query = select(Developer).where(Developer.is_active.is_(True))
    if team:
        dev_query = dev_query.where(Developer.team == team)
    dev_result = await db.execute(dev_query)
    devs = {d.id: d for d in dev_result.scalars().all()}

    if not devs:
        return OverTaggedResponse(developers=[])

    dev_ids = set(devs.keys())

    # Total PRs and issues in period
    total_prs_result = await db.execute(
        select(func.count(PullRequest.id)).where(
            PullRequest.created_at >= date_from,
            PullRequest.created_at <= date_to,
        )
    )
    total_prs = total_prs_result.scalar() or 0

    total_issues_result = await db.execute(
        select(func.count(Issue.id)).where(
            Issue.created_at >= date_from,
            Issue.created_at <= date_to,
        )
    )
    total_issues = total_issues_result.scalar() or 0

    if total_prs + total_issues == 0:
        return OverTaggedResponse(developers=[])

    # Count PRs per developer (authored or reviewed)
    pr_authored = await db.execute(
        select(PullRequest.author_id, func.count(PullRequest.id))
        .where(
            PullRequest.author_id.isnot(None),
            PullRequest.created_at >= date_from,
            PullRequest.created_at <= date_to,
        )
        .group_by(PullRequest.author_id)
    )
    dev_pr_count: dict[int, int] = defaultdict(int)
    for dev_id, count in pr_authored:
        if dev_id in dev_ids:
            dev_pr_count[dev_id] += count

    pr_reviewed = await db.execute(
        select(PRReview.reviewer_id, func.count(func.distinct(PRReview.pr_id)))
        .join(PullRequest, PRReview.pr_id == PullRequest.id)
        .where(
            PRReview.reviewer_id.isnot(None),
            PullRequest.created_at >= date_from,
            PullRequest.created_at <= date_to,
        )
        .group_by(PRReview.reviewer_id)
    )
    for dev_id, count in pr_reviewed:
        if dev_id in dev_ids:
            dev_pr_count[dev_id] += count

    # Count issues per developer (assigned or commented)
    dev_issue_count: dict[int, int] = defaultdict(int)
    issue_assigned = await db.execute(
        select(Issue.assignee_id, func.count(Issue.id))
        .where(
            Issue.assignee_id.isnot(None),
            Issue.created_at >= date_from,
            Issue.created_at <= date_to,
        )
        .group_by(Issue.assignee_id)
    )
    for dev_id, count in issue_assigned:
        if dev_id in dev_ids:
            dev_issue_count[dev_id] += count

    # Compute rates
    rates: list[tuple[int, float, float, float]] = []  # (dev_id, combined, pr_rate, issue_rate)
    for dev_id in dev_ids:
        prs = dev_pr_count.get(dev_id, 0)
        issues = dev_issue_count.get(dev_id, 0)
        pr_rate = prs / total_prs if total_prs > 0 else 0
        issue_rate = issues / total_issues if total_issues > 0 else 0
        combined = (prs + issues) / (total_prs + total_issues)
        rates.append((dev_id, combined, pr_rate, issue_rate))

    combined_values = [r[1] for r in rates]
    avg = statistics.mean(combined_values) if combined_values else 0
    stddev = statistics.stdev(combined_values) if len(combined_values) > 1 else 0

    flagged: list[OverTaggedDeveloper] = []
    for dev_id, combined, pr_rate, issue_rate in rates:
        if combined <= avg + 1.5 * stddev and combined <= 0.5:
            continue
        if stddev > 0:
            z = (combined - avg) / stddev
        else:
            z = 0
        if z >= 3 or combined >= 0.7:
            severity = "severe"
        elif z >= 2 or combined >= 0.5:
            severity = "moderate"
        else:
            severity = "mild"

        dev = devs[dev_id]
        flagged.append(
            OverTaggedDeveloper(
                developer_id=dev.id,
                display_name=dev.display_name,
                github_username=dev.github_username,
                team=dev.team,
                combined_tag_rate=round(combined, 4),
                pr_tag_rate=round(pr_rate, 4),
                issue_tag_rate=round(issue_rate, 4),
                team_average=round(avg, 4),
                severity=severity,
            )
        )

    flagged.sort(key=lambda d: d.combined_tag_rate, reverse=True)
    return OverTaggedResponse(developers=flagged)


async def get_communication_scores(
    db: AsyncSession,
    team: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> CommunicationScoresResponse:
    """Compute communication score [0-100] per developer."""
    date_from, date_to = _default_range(date_from, date_to)

    # Load active devs
    dev_query = select(Developer).where(Developer.is_active.is_(True))
    if team:
        dev_query = dev_query.where(Developer.team == team)
    dev_result = await db.execute(dev_query)
    devs = {d.id: d for d in dev_result.scalars().all()}

    if not devs:
        return CommunicationScoresResponse(developers=[])

    dev_ids = set(devs.keys())
    username_to_id = {d.github_username: d.id for d in devs.values()}
    team_size = len(dev_ids)

    # Reviews given per dev
    review_rows = await db.execute(
        select(PRReview.reviewer_id, func.count(PRReview.id))
        .where(
            PRReview.reviewer_id.isnot(None),
            PRReview.submitted_at >= date_from,
            PRReview.submitted_at <= date_to,
        )
        .group_by(PRReview.reviewer_id)
    )
    reviews_given: dict[int, int] = {}
    for dev_id, count in review_rows:
        if dev_id in dev_ids:
            reviews_given[dev_id] = count

    # Median reviews for normalization
    all_review_counts = [reviews_given.get(did, 0) for did in dev_ids]
    review_median = statistics.median(all_review_counts) if all_review_counts else 1

    # Avg comment length per dev (PR review comments)
    comment_len_rows = await db.execute(
        select(
            PRReviewComment.author_github_username,
            func.avg(func.length(PRReviewComment.body)),
        )
        .where(
            PRReviewComment.author_github_username.isnot(None),
            PRReviewComment.created_at >= date_from,
            PRReviewComment.created_at <= date_to,
        )
        .group_by(PRReviewComment.author_github_username)
    )
    avg_comment_len: dict[int, float] = {}
    for username, avg_len in comment_len_rows:
        dev_id = username_to_id.get(username)
        if dev_id:
            avg_comment_len[dev_id] = float(avg_len or 0)

    # Unique devs interacted with (via reviews)
    interact_rows = await db.execute(
        select(PRReview.reviewer_id, PullRequest.author_id)
        .join(PullRequest, PRReview.pr_id == PullRequest.id)
        .where(
            PRReview.reviewer_id.isnot(None),
            PullRequest.author_id.isnot(None),
            PRReview.reviewer_id != PullRequest.author_id,
            PRReview.submitted_at >= date_from,
            PRReview.submitted_at <= date_to,
        )
    )
    unique_interactions: dict[int, set[int]] = defaultdict(set)
    for reviewer_id, author_id in interact_rows:
        if reviewer_id in dev_ids:
            unique_interactions[reviewer_id].add(author_id)
        if author_id in dev_ids:
            unique_interactions[author_id].add(reviewer_id)

    # Avg time to first review (as reviewer)
    # Compute avg of time_to_first_review for PRs where dev was the first reviewer
    first_review_rows = await db.execute(
        select(PRReview.reviewer_id, func.avg(PullRequest.time_to_first_review_s))
        .join(PullRequest, PRReview.pr_id == PullRequest.id)
        .where(
            PRReview.reviewer_id.isnot(None),
            PullRequest.time_to_first_review_s.isnot(None),
            PRReview.submitted_at >= date_from,
            PRReview.submitted_at <= date_to,
        )
        .group_by(PRReview.reviewer_id)
    )
    avg_response_time_s: dict[int, float] = {}
    for dev_id, avg_s in first_review_rows:
        if dev_id in dev_ids:
            avg_response_time_s[dev_id] = float(avg_s or 0)

    entries: list[CommunicationScoreEntry] = []
    for dev_id, dev in devs.items():
        # Review engagement: 0-25
        rv_count = reviews_given.get(dev_id, 0)
        expected = max(review_median, 1)
        review_engagement = min(rv_count / expected, 1.0) * 25

        # Comment depth: 0-25
        avg_len = avg_comment_len.get(dev_id, 0)
        comment_depth = min(avg_len / 200.0, 1.0) * 25

        # Reach: 0-25
        unique_count = len(unique_interactions.get(dev_id, set()))
        reach = min(unique_count / max(team_size - 1, 1), 1.0) * 25

        # Responsiveness: 0-25
        avg_resp = avg_response_time_s.get(dev_id)
        if avg_resp is not None:
            hours = avg_resp / 3600
            responsiveness = (1 - min(hours / 24.0, 1.0)) * 25
        else:
            responsiveness = 0.0

        total = review_engagement + comment_depth + reach + responsiveness

        entries.append(
            CommunicationScoreEntry(
                developer_id=dev.id,
                display_name=dev.display_name,
                github_username=dev.github_username,
                avatar_url=dev.avatar_url,
                team=dev.team,
                communication_score=round(total, 1),
                review_engagement=round(review_engagement, 1),
                comment_depth=round(comment_depth, 1),
                reach=round(reach, 1),
                responsiveness=round(responsiveness, 1),
            )
        )

    entries.sort(key=lambda e: e.communication_score, reverse=True)
    return CommunicationScoresResponse(developers=entries)
