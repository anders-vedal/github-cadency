import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.database import AsyncSessionLocal
from app.models.models import (
    Developer,
    Issue,
    IssueComment,
    PRReview,
    PRReviewComment,
    PullRequest,
    Repository,
    SyncEvent,
)

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


# --- GitHub App Authentication ---


class GitHubAuth:
    def __init__(self):
        self._token: str | None = None
        self._token_expires_at: float = 0

    def _generate_jwt(self) -> str:
        now = int(time.time())
        key_path = Path(settings.github_app_private_key_path)
        private_key = key_path.read_bytes()
        payload = {
            "iat": now - 60,
            "exp": now + (10 * 60),
            "iss": settings.github_app_id,
        }
        return jwt.encode(payload, private_key, algorithm="RS256")

    async def get_installation_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        app_jwt = self._generate_jwt()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GITHUB_API}/app/installations/{settings.github_app_installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {app_jwt}",
                    "Accept": "application/vnd.github+json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        self._token = data["token"]
        expires_at = data["expires_at"]  # ISO format
        self._token_expires_at = datetime.fromisoformat(
            expires_at.replace("Z", "+00:00")
        ).timestamp()
        return self._token


github_auth = GitHubAuth()


# --- Rate Limit Handling ---


async def check_rate_limit(response: httpx.Response) -> None:
    remaining = int(response.headers.get("X-RateLimit-Remaining", "5000"))
    if remaining < 100:
        reset_at = int(response.headers.get("X-RateLimit-Reset", "0"))
        wait_seconds = max(reset_at - int(time.time()), 1)
        logger.warning(
            "Rate limit low (%d remaining). Waiting %ds.", remaining, wait_seconds
        )
        import asyncio

        await asyncio.sleep(wait_seconds)


# --- GitHub API Client ---


async def github_get(
    client: httpx.AsyncClient, path: str, params: dict | None = None
) -> httpx.Response:
    token = await github_auth.get_installation_token()
    resp = await client.get(
        f"{GITHUB_API}{path}",
        params=params,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
    )
    await check_rate_limit(resp)
    resp.raise_for_status()
    return resp


async def github_get_paginated(
    client: httpx.AsyncClient,
    path: str,
    params: dict | None = None,
    stop_before: datetime | None = None,
) -> list[dict]:
    params = dict(params or {})
    params.setdefault("per_page", "100")
    all_items: list[dict] = []
    page = 1

    while True:
        params["page"] = str(page)
        resp = await github_get(client, path, params)
        items = resp.json()
        if not items:
            break

        for item in items:
            if stop_before:
                updated = item.get("updated_at")
                if updated:
                    updated_dt = datetime.fromisoformat(
                        updated.replace("Z", "+00:00")
                    )
                    if updated_dt < stop_before:
                        return all_items
            all_items.append(item)

        if len(items) < int(params["per_page"]):
            break
        page += 1

    return all_items


# --- Author Resolution ---


async def resolve_author(
    db: AsyncSession, github_username: str | None
) -> int | None:
    if not github_username:
        return None
    result = await db.execute(
        select(Developer.id).where(Developer.github_username == github_username)
    )
    return result.scalar_one_or_none()


# --- Upsert Helpers ---


async def upsert_repo(db: AsyncSession, repo_data: dict) -> Repository:
    result = await db.execute(
        select(Repository).where(Repository.github_id == repo_data["id"])
    )
    repo = result.scalar_one_or_none()
    if not repo:
        repo = Repository(github_id=repo_data["id"])
        db.add(repo)

    repo.name = repo_data.get("name")
    repo.full_name = repo_data.get("full_name")
    repo.description = repo_data.get("description")
    repo.language = repo_data.get("language")
    return repo


async def upsert_pull_request(
    db: AsyncSession,
    client: httpx.AsyncClient,
    pr_data: dict,
    repo: Repository,
) -> PullRequest:
    result = await db.execute(
        select(PullRequest).where(
            PullRequest.repo_id == repo.id,
            PullRequest.number == pr_data["number"],
        )
    )
    pr = result.scalar_one_or_none()
    if not pr:
        pr = PullRequest(repo_id=repo.id, number=pr_data["number"])
        db.add(pr)

    pr.github_id = pr_data["id"]
    pr.title = pr_data.get("title")
    pr.body = pr_data.get("body")
    pr.state = pr_data.get("state")
    pr.is_merged = pr_data.get("merged", False)
    pr.is_draft = pr_data.get("draft", False)
    pr.comments_count = pr_data.get("comments", 0)
    pr.review_comments_count = pr_data.get("review_comments", 0)
    pr.html_url = pr_data.get("html_url")

    user = pr_data.get("user") or {}
    pr.author_id = await resolve_author(db, user.get("login"))

    for field in ("created_at", "updated_at", "merged_at", "closed_at"):
        val = pr_data.get(field)
        if val:
            setattr(pr, field, datetime.fromisoformat(val.replace("Z", "+00:00")))

    # Fetch detail stats (additions/deletions/changed_files)
    needs_detail = pr.additions is None or pr.state == "open"
    if needs_detail:
        try:
            detail_resp = await github_get(
                client,
                f"/repos/{repo.full_name}/pulls/{pr.number}",
            )
            detail = detail_resp.json()
            pr.additions = detail.get("additions")
            pr.deletions = detail.get("deletions")
            pr.changed_files = detail.get("changed_files")
            pr.is_merged = detail.get("merged", pr.is_merged)
            if detail.get("merged_at"):
                pr.merged_at = datetime.fromisoformat(
                    detail["merged_at"].replace("Z", "+00:00")
                )
        except httpx.HTTPStatusError:
            logger.warning("Failed to fetch detail for PR #%d", pr.number)

    # Compute time_to_merge_s
    if pr.merged_at and pr.created_at:
        pr.time_to_merge_s = int((pr.merged_at - pr.created_at).total_seconds())

    return pr


def classify_review_quality(
    state: str | None,
    body_length: int,
    reviewer_comment_count: int,
) -> str:
    """Classify a PR review into a quality tier.

    Tiers (checked highest-first):
      thorough:     body > 500 chars, or 3+ inline review comments by this reviewer
      standard:     body 100-500 chars
      rubber_stamp: state=APPROVED with body < 20 chars
      minimal:      everything else
    """
    if body_length > 500 or reviewer_comment_count >= 3:
        return "thorough"
    if 100 <= body_length <= 500:
        return "standard"
    if state == "APPROVED" and body_length < 20:
        return "rubber_stamp"
    return "minimal"


async def upsert_review(
    db: AsyncSession, review_data: dict, pr: PullRequest
) -> PRReview:
    result = await db.execute(
        select(PRReview).where(PRReview.github_id == review_data["id"])
    )
    review = result.scalar_one_or_none()
    if not review:
        review = PRReview(github_id=review_data["id"], pr_id=pr.id)
        db.add(review)

    review.state = review_data.get("state")
    review.body = review_data.get("body")

    body_text = review.body or ""
    review.body_length = len(body_text)

    user = review_data.get("user") or {}
    review.reviewer_id = await resolve_author(db, user.get("login"))

    submitted = review_data.get("submitted_at")
    if submitted:
        review.submitted_at = datetime.fromisoformat(
            submitted.replace("Z", "+00:00")
        )

    # Update first_review_at on the PR
    if review.submitted_at:
        if not pr.first_review_at or review.submitted_at < pr.first_review_at:
            pr.first_review_at = review.submitted_at
            if pr.created_at:
                pr.time_to_first_review_s = int(
                    (pr.first_review_at - pr.created_at).total_seconds()
                )

    # Quality tier — reviewer comment count is updated after review comments sync
    # For now, classify without comments; recompute_review_quality_tiers fixes it
    review.quality_tier = classify_review_quality(
        review.state, review.body_length, 0
    )

    return review


async def upsert_review_comment(
    db: AsyncSession, comment_data: dict, pr: PullRequest
) -> PRReviewComment:
    result = await db.execute(
        select(PRReviewComment).where(
            PRReviewComment.github_id == comment_data["id"]
        )
    )
    comment = result.scalar_one_or_none()
    if not comment:
        comment = PRReviewComment(github_id=comment_data["id"], pr_id=pr.id)
        db.add(comment)

    comment.body = comment_data.get("body")
    comment.path = comment_data.get("path")
    comment.line = comment_data.get("line")

    user = comment_data.get("user") or {}
    comment.author_github_username = user.get("login")

    # Link to review if available
    review_github_id = comment_data.get("pull_request_review_id")
    if review_github_id:
        review_result = await db.execute(
            select(PRReview.id).where(PRReview.github_id == review_github_id)
        )
        comment.review_id = review_result.scalar_one_or_none()

    for field in ("created_at", "updated_at"):
        val = comment_data.get(field)
        if val:
            setattr(comment, field, datetime.fromisoformat(val.replace("Z", "+00:00")))

    return comment


async def recompute_review_quality_tiers(
    db: AsyncSession, pr: PullRequest
) -> None:
    """Recompute quality tiers for all reviews on a PR using actual comment counts."""
    reviews_result = await db.execute(
        select(PRReview).where(PRReview.pr_id == pr.id)
    )
    reviews = list(reviews_result.scalars().all())

    for review in reviews:
        # Count inline comments by this reviewer on this PR
        if review.reviewer_id:
            # Resolve reviewer's github username
            dev_result = await db.execute(
                select(Developer.github_username).where(Developer.id == review.reviewer_id)
            )
            reviewer_username = dev_result.scalar_one_or_none()
        else:
            reviewer_username = None

        if reviewer_username:
            comment_count = await db.scalar(
                select(func.count()).where(
                    PRReviewComment.pr_id == pr.id,
                    PRReviewComment.review_id == review.id,
                    PRReviewComment.author_github_username == reviewer_username,
                )
            ) or 0
        else:
            comment_count = 0

        review.quality_tier = classify_review_quality(
            review.state, review.body_length, comment_count
        )


async def upsert_issue(
    db: AsyncSession, issue_data: dict, repo: Repository
) -> Issue:
    result = await db.execute(
        select(Issue).where(
            Issue.repo_id == repo.id, Issue.number == issue_data["number"]
        )
    )
    issue = result.scalar_one_or_none()
    if not issue:
        issue = Issue(repo_id=repo.id, number=issue_data["number"])
        db.add(issue)

    issue.github_id = issue_data["id"]
    issue.title = issue_data.get("title")
    issue.body = issue_data.get("body")
    issue.state = issue_data.get("state")
    issue.labels = [l["name"] for l in issue_data.get("labels", [])]
    issue.html_url = issue_data.get("html_url")

    assignee = issue_data.get("assignee") or {}
    issue.assignee_id = await resolve_author(db, assignee.get("login"))

    for field in ("created_at", "updated_at", "closed_at"):
        val = issue_data.get(field)
        if val:
            setattr(issue, field, datetime.fromisoformat(val.replace("Z", "+00:00")))

    if issue.closed_at and issue.created_at:
        issue.time_to_close_s = int(
            (issue.closed_at - issue.created_at).total_seconds()
        )

    return issue


async def upsert_issue_comment(
    db: AsyncSession, comment_data: dict, issue: Issue
) -> IssueComment:
    result = await db.execute(
        select(IssueComment).where(IssueComment.github_id == comment_data["id"])
    )
    comment = result.scalar_one_or_none()
    if not comment:
        comment = IssueComment(github_id=comment_data["id"], issue_id=issue.id)
        db.add(comment)

    comment.body = comment_data.get("body")
    user = comment_data.get("user") or {}
    comment.author_github_username = user.get("login")

    created = comment_data.get("created_at")
    if created:
        comment.created_at = datetime.fromisoformat(created.replace("Z", "+00:00"))

    return comment


# --- Sync Orchestration ---


async def sync_repo(
    client: httpx.AsyncClient,
    db: AsyncSession,
    repo: Repository,
    since: datetime | None = None,
) -> tuple[int, int]:
    """Sync a single repo. Returns (prs_upserted, issues_upserted)."""
    prs_upserted = 0
    issues_upserted = 0

    # Fetch PRs
    pr_params: dict = {"state": "all", "sort": "updated", "direction": "desc"}
    if since:
        pr_items = await github_get_paginated(
            client,
            f"/repos/{repo.full_name}/pulls",
            pr_params,
            stop_before=since,
        )
    else:
        pr_items = await github_get_paginated(
            client, f"/repos/{repo.full_name}/pulls", pr_params
        )

    for pr_data in pr_items:
        pr = await upsert_pull_request(db, client, pr_data, repo)
        prs_upserted += 1

        # Fetch reviews for this PR
        reviews_data = await github_get_paginated(
            client, f"/repos/{repo.full_name}/pulls/{pr.number}/reviews"
        )
        for review_data in reviews_data:
            await upsert_review(db, review_data, pr)

        # Fetch review comments (inline code comments) for this PR
        review_comments_data = await github_get_paginated(
            client, f"/repos/{repo.full_name}/pulls/{pr.number}/comments"
        )
        for comment_data in review_comments_data:
            await upsert_review_comment(db, comment_data, pr)

        # Flush so comment counts are visible, then recompute quality tiers
        await db.flush()
        await recompute_review_quality_tiers(db, pr)

    # Fetch issues (skip PRs — they have a pull_request key)
    issue_params: dict = {"state": "all", "sort": "updated", "direction": "desc"}
    if since:
        issue_params["since"] = since.isoformat()

    issue_items = await github_get_paginated(
        client, f"/repos/{repo.full_name}/issues", issue_params
    )
    for issue_data in issue_items:
        if "pull_request" in issue_data:
            continue
        issue = await upsert_issue(db, issue_data, repo)
        issues_upserted += 1

    # Fetch issue comments
    comment_params: dict = {"sort": "updated", "direction": "desc"}
    if since:
        comment_params["since"] = since.isoformat()

    comments_data = await github_get_paginated(
        client, f"/repos/{repo.full_name}/issues/comments", comment_params
    )
    for comment_data in comments_data:
        # Find the parent issue by issue URL
        issue_url = comment_data.get("issue_url", "")
        issue_number = int(issue_url.rstrip("/").split("/")[-1]) if issue_url else None
        if issue_number:
            result = await db.execute(
                select(Issue).where(
                    Issue.repo_id == repo.id, Issue.number == issue_number
                )
            )
            parent_issue = result.scalar_one_or_none()
            if parent_issue:
                await upsert_issue_comment(db, comment_data, parent_issue)

    repo.last_synced_at = datetime.now(timezone.utc)
    return prs_upserted, issues_upserted


async def run_sync(sync_type: str = "full") -> SyncEvent:
    """Run a full or incremental sync across all tracked repos."""
    sync_event = SyncEvent(
        sync_type=sync_type,
        status="started",
        started_at=datetime.now(timezone.utc),
        repos_synced=0,
        prs_upserted=0,
        issues_upserted=0,
        errors=[],
    )

    async with AsyncSessionLocal() as db:
        db.add(sync_event)
        await db.commit()

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Fetch org repos
                repos_data = await github_get_paginated(
                    client,
                    f"/orgs/{settings.github_org}/repos",
                    {"type": "all", "sort": "updated"},
                )

                for repo_data in repos_data:
                    repo = await upsert_repo(db, repo_data)
                    await db.flush()

                    if not repo.is_tracked:
                        continue

                    since = repo.last_synced_at if sync_type == "incremental" else None

                    try:
                        prs, issues = await sync_repo(client, db, repo, since=since)
                        sync_event.repos_synced = (sync_event.repos_synced or 0) + 1
                        sync_event.prs_upserted = (sync_event.prs_upserted or 0) + prs
                        sync_event.issues_upserted = (
                            sync_event.issues_upserted or 0
                        ) + issues
                    except Exception as e:
                        logger.error("Error syncing repo %s: %s", repo.full_name, e)
                        errors = sync_event.errors or []
                        errors.append(f"{repo.full_name}: {str(e)}")
                        sync_event.errors = errors

                sync_event.status = "completed"
        except Exception as e:
            logger.error("Sync failed: %s", e)
            sync_event.status = "failed"
            errors = sync_event.errors or []
            errors.append(str(e))
            sync_event.errors = errors
        finally:
            now = datetime.now(timezone.utc)
            sync_event.completed_at = now
            if sync_event.started_at:
                sync_event.duration_s = int(
                    (now - sync_event.started_at).total_seconds()
                )
            await db.commit()

    return sync_event
