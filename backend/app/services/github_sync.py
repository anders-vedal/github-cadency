import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import jwt
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.database import AsyncSessionLocal
from app.models.models import (
    Deployment,
    Developer,
    Issue,
    IssueComment,
    PRCheckRun,
    PRFile,
    PRReview,
    PRReviewComment,
    PullRequest,
    RepoTreeFile,
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


# --- SyncContext ---


@dataclass
class SyncContext:
    """Holds state for a sync run, passed through the call chain."""

    db: AsyncSession
    client: httpx.AsyncClient
    sync_event: SyncEvent
    sync_logger: logging.Logger = field(default_factory=lambda: logger)
    rate_limit_wait_total: int = 0


# --- JSONB Mutation Helper ---


def _append_jsonb(obj: object, attr: str, value: dict | str) -> None:
    """Safely append to a JSONB list column, triggering SQLAlchemy change detection."""
    current = list(getattr(obj, attr) or [])
    current.append(value)
    setattr(obj, attr, current)


# --- Structured Error Helpers ---


MAX_LOG_ENTRIES = 100

RETRYABLE_STATUS_CODES = {502, 503, 504}

STATUS_CODE_CLASSIFICATION: dict[int, tuple[str, bool]] = {
    401: ("auth", False),
    403: ("auth", False),
    404: ("github_api", False),
    422: ("github_api", False),
    502: ("github_api", True),
    503: ("github_api", True),
    504: ("github_api", True),
}


def make_sync_error(
    *,
    repo: str | None = None,
    repo_id: int | None = None,
    step: str,
    exception: Exception,
    attempt: int = 1,
) -> dict:
    """Create a structured error object from an exception."""
    error_type = "unknown"
    retryable = False
    status_code = None

    if isinstance(exception, httpx.HTTPStatusError):
        status_code = exception.response.status_code
        error_type, retryable = STATUS_CODE_CLASSIFICATION.get(
            status_code, ("github_api", False)
        )
    elif isinstance(exception, httpx.TimeoutException):
        error_type, retryable = "timeout", True
    elif isinstance(exception, httpx.ConnectError):
        error_type, retryable = "timeout", True

    return {
        "repo": repo,
        "repo_id": repo_id,
        "step": step,
        "error_type": error_type,
        "status_code": status_code,
        "message": str(exception)[:500],
        "retryable": retryable,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "attempt": attempt,
    }


def _add_log(
    ctx: SyncContext, level: str, msg: str, repo: str | None = None
) -> None:
    """Append a structured log entry to sync_event.log_summary."""
    entry: dict = {
        "ts": datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "level": level.lower(),
        "msg": msg[:200],
    }
    if repo:
        entry["repo"] = repo

    logs = list(ctx.sync_event.log_summary or [])
    if len(logs) >= MAX_LOG_ENTRIES:
        # Drop oldest INFO, keep warnings/errors
        for i, e in enumerate(logs):
            if e.get("level") == "info":
                logs.pop(i)
                break
        else:
            logs.pop(0)
    logs.append(entry)
    ctx.sync_event.log_summary = logs


# --- Rate Limit Handling ---


async def check_rate_limit(
    response: httpx.Response, ctx: SyncContext | None = None
) -> int:
    """Check rate limit headers and sleep if needed. Returns seconds waited."""
    remaining = int(response.headers.get("X-RateLimit-Remaining", "5000"))
    if remaining < 200:
        reset_at = int(response.headers.get("X-RateLimit-Reset", "0"))
        wait_seconds = max(reset_at - int(time.time()), 1)

        if wait_seconds > 300 and ctx:
            _add_log(ctx, "warn", f"Committing before {wait_seconds}s rate limit wait")
            await ctx.db.commit()

        logger.warning(
            "Rate limit low (%d remaining). Waiting %ds.", remaining, wait_seconds
        )
        if ctx:
            _add_log(ctx, "warn", f"Rate limit: {remaining} remaining, waiting {wait_seconds}s")

        await asyncio.sleep(wait_seconds)
        return wait_seconds
    return 0


async def proactive_rate_check(
    client: httpx.AsyncClient, ctx: SyncContext
) -> None:
    """Check rate limit proactively before starting a repo."""
    try:
        token = await github_auth.get_installation_token()
        resp = await client.get(
            f"{GITHUB_API}/rate_limit",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        data = resp.json()
        remaining = data.get("resources", {}).get("core", {}).get("remaining", 5000)
        ctx.sync_logger.info("Rate limit: %d remaining", remaining)

        if remaining < 200:
            reset_at = data.get("resources", {}).get("core", {}).get("reset", 0)
            wait_seconds = max(reset_at - int(time.time()), 1)
            if wait_seconds > 300:
                await ctx.db.commit()
            _add_log(ctx, "warn", f"Proactive rate limit wait: {wait_seconds}s")
            ctx.rate_limit_wait_total += wait_seconds
            await asyncio.sleep(wait_seconds)
    except Exception as e:
        ctx.sync_logger.warning("Proactive rate check failed: %s", e)


# --- GitHub API Client ---


MAX_RETRIES = 3
RETRY_BACKOFF = [2, 8, 30]
RETRYABLE_EXCEPTIONS = (httpx.TimeoutException, httpx.ConnectError)


async def github_get(
    client: httpx.AsyncClient,
    path: str,
    params: dict | None = None,
    ctx: SyncContext | None = None,
) -> httpx.Response:
    last_exc: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            token = await github_auth.get_installation_token()
            resp = await client.get(
                f"{GITHUB_API}{path}",
                params=params,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            wait_s = await check_rate_limit(resp, ctx)
            if ctx:
                ctx.rate_limit_wait_total += wait_s
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as e:
            if e.response.status_code not in RETRYABLE_STATUS_CODES:
                raise
            last_exc = e
        except RETRYABLE_EXCEPTIONS as e:
            last_exc = e

        if attempt < MAX_RETRIES:
            backoff = RETRY_BACKOFF[attempt]
            if ctx:
                ctx.sync_logger.warning(
                    "Retryable error on %s (attempt %d/%d), retrying in %ds: %s",
                    path, attempt + 1, MAX_RETRIES + 1, backoff, last_exc,
                )
            await asyncio.sleep(backoff)

    raise last_exc  # type: ignore[misc]


async def github_get_paginated(
    client: httpx.AsyncClient,
    path: str,
    params: dict | None = None,
    stop_before: datetime | None = None,
    ctx: SyncContext | None = None,
) -> list[dict]:
    params = dict(params or {})
    params.setdefault("per_page", "100")
    all_items: list[dict] = []
    page = 1

    while True:
        params["page"] = str(page)
        resp = await github_get(client, path, params, ctx=ctx)
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
    repo.default_branch = repo_data.get("default_branch")
    return repo


_CLOSING_PATTERN = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE
)


def extract_closing_issue_numbers(body: str | None) -> list[int]:
    """Parse closing keywords from PR body and return deduplicated issue numbers."""
    if not body:
        return []
    return sorted(set(int(m) for m in _CLOSING_PATTERN.findall(body)))


# Revert detection patterns
_REVERT_TITLE_PATTERN = re.compile(r'^Revert "(.+)"', re.IGNORECASE)
_REVERT_BODY_PR_PATTERN = re.compile(
    r"Reverts\s+(?:[\w.-]+/[\w.-]+)?#(\d+)", re.IGNORECASE
)


def detect_revert(title: str | None, body: str | None) -> tuple[bool, int | None]:
    """Detect if a PR is a revert and extract the reverted PR number.

    Checks title for GitHub's standard ``Revert "..."`` pattern and body for
    ``Reverts #NNN`` or ``Reverts owner/repo#NNN`` references.

    Returns ``(is_revert, reverted_pr_number)``.
    """
    if not title:
        return False, None

    title_match = _REVERT_TITLE_PATTERN.match(title)
    body_has_revert = bool(body and "revert" in body.lower())

    if not title_match and not body_has_revert:
        return False, None

    # Try to extract PR number from body first (most reliable)
    if body:
        pr_match = _REVERT_BODY_PR_PATTERN.search(body)
        if pr_match:
            return True, int(pr_match.group(1))

    # Title matched but no PR number found yet — still a revert
    if title_match:
        return True, None

    # Body mentions "revert" but no standard title pattern — not a revert
    return False, None


async def _resolve_revert_pr_number(
    db: AsyncSession, repo_id: int, original_title: str
) -> int | None:
    """Fallback: look up the reverted PR by matching its title in the same repo."""
    result = await db.execute(
        select(PullRequest.number).where(
            PullRequest.repo_id == repo_id,
            PullRequest.title == original_title,
        ).limit(1)
    )
    row = result.scalar_one_or_none()
    return row


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
    pr.closes_issue_numbers = extract_closing_issue_numbers(pr.body)
    pr.state = pr_data.get("state")
    pr.is_merged = pr_data.get("merged", False)
    pr.is_draft = pr_data.get("draft", False)
    pr.comments_count = pr_data.get("comments", 0)
    pr.review_comments_count = pr_data.get("review_comments", 0)
    pr.html_url = pr_data.get("html_url")
    pr.labels = [l["name"] for l in pr_data.get("labels", [])]
    pr.head_branch = (pr_data.get("head") or {}).get("ref")
    pr.base_branch = (pr_data.get("base") or {}).get("ref")
    pr.head_sha = (pr_data.get("head") or {}).get("sha")

    user = pr_data.get("user") or {}
    author_login = user.get("login")
    pr.author_id = await resolve_author(db, author_login)

    for field in ("created_at", "updated_at", "merged_at", "closed_at"):
        val = pr_data.get(field)
        if val:
            setattr(pr, field, datetime.fromisoformat(val.replace("Z", "+00:00")))

    # Fetch detail stats (additions/deletions/changed_files/merged_by)
    needs_detail = (
        pr.additions is None
        or pr.state == "open"
        or (pr.merged_by_username is None and pr.merged_at is not None)
    )
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
            pr.merged_by_username = (detail.get("merged_by") or {}).get("login")
            if detail.get("merged_at"):
                pr.merged_at = datetime.fromisoformat(
                    detail["merged_at"].replace("Z", "+00:00")
                )
        except httpx.HTTPStatusError:
            logger.warning("Failed to fetch detail for PR #%d", pr.number)

    # Compute time_to_merge_s
    if pr.merged_at and pr.created_at:
        pr.time_to_merge_s = int((pr.merged_at - pr.created_at).total_seconds())

    # Compute is_self_merged
    pr.is_self_merged = (
        pr.is_merged is True
        and pr.merged_by_username is not None
        and pr.merged_by_username == author_login
    )

    # Detect revert PRs
    is_revert, reverted_pr_number = detect_revert(pr.title, pr.body)
    if is_revert and reverted_pr_number is None:
        # Fallback: look up by original title extracted from revert title
        title_match = _REVERT_TITLE_PATTERN.match(pr.title or "")
        if title_match:
            reverted_pr_number = await _resolve_revert_pr_number(
                db, repo.id, title_match.group(1)
            )
    pr.is_revert = is_revert
    pr.reverted_pr_number = reverted_pr_number

    return pr


def classify_comment_type(body: str) -> str:
    """Classify a review comment into a type based on keywords/patterns.

    Types (checked in priority order — first match wins):
      nit, blocker, suggestion, architectural, praise, question, general
    """
    if not body:
        return "general"
    lower = body.lower().strip()

    # --- Explicit prefix checks (reviewer intent is clear) ---
    if lower.startswith(("nit:", "nit ", "nitpick:", "optional:", "minor:", "style:", "cosmetic:", "tiny:")):
        return "nit"
    if lower.startswith(("blocker:", "blocking:", "must fix:", "must-fix:", "critical:", "bug:")):
        return "blocker"
    if lower.startswith(("suggestion:", "consider:")):
        return "suggestion"
    if lower.startswith("question:"):
        return "question"

    # --- Content pattern checks ---
    if "```suggestion" in lower:
        return "suggestion"
    if any(kw in lower for kw in (
        "security issue", "race condition", "data loss", "will break", "memory leak",
    )):
        return "blocker"
    if any(kw in lower for kw in (
        "architecture", "design concern", "separation of concern", "coupling",
        "abstraction", "single responsibility", "encapsulation", "dependency injection",
    )):
        return "architectural"
    if any(kw in lower for kw in (
        "lgtm", "well done", "love this", ":+1:", "good job", "nice catch",
        "good call", "looks good", "awesome", "excellent", "clean code", "\U0001f44d",
    )):
        return "praise"
    if any(kw in lower for kw in ("have you considered", "what about", "alternatively", "you could also", "perhaps")):
        return "suggestion"

    # --- Loose / fallback checks ---
    if lower.startswith(("nice", "great")):
        return "praise"
    if lower.endswith("?") or lower.startswith(("why ", "what ", "how ", "wondering", "curious")):
        return "question"

    return "general"


def classify_review_quality(
    state: str | None,
    body_length: int,
    reviewer_comment_count: int,
    body: str = "",
    has_blocker_comment: bool = False,
    architectural_comment_count: int = 0,
) -> str:
    """Classify a PR review into a quality tier.

    Tiers (checked highest-first):
      thorough:     body > 500 chars, or 3+ inline comments,
                    or CHANGES_REQUESTED with body > 100 chars,
                    or 3+ architectural comments
      standard:     body 100-500 chars, or CHANGES_REQUESTED (any length),
                    or body contains code blocks, or has blocker comment
      rubber_stamp: state=APPROVED with body < 20 chars and 0 inline comments
      minimal:      everything else
    """
    has_code_blocks = "```" in body if body else False

    if body_length > 500 or reviewer_comment_count >= 3:
        return "thorough"
    if state == "CHANGES_REQUESTED" and body_length > 100:
        return "thorough"
    if architectural_comment_count >= 3:
        return "thorough"
    if state == "CHANGES_REQUESTED":
        return "standard"
    if body_length >= 100 or has_code_blocks:
        return "standard"
    if has_blocker_comment:
        return "standard"
    if state == "APPROVED" and body_length < 20 and reviewer_comment_count == 0:
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
        review.state, review.body_length, 0, body=body_text
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
    comment.comment_type = classify_comment_type(comment.body or "")
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
            # Count comment types for quality tier promotion
            has_blocker = (await db.scalar(
                select(func.count()).where(
                    PRReviewComment.pr_id == pr.id,
                    PRReviewComment.review_id == review.id,
                    PRReviewComment.author_github_username == reviewer_username,
                    PRReviewComment.comment_type == "blocker",
                )
            ) or 0) > 0
            arch_count = await db.scalar(
                select(func.count()).where(
                    PRReviewComment.pr_id == pr.id,
                    PRReviewComment.review_id == review.id,
                    PRReviewComment.author_github_username == reviewer_username,
                    PRReviewComment.comment_type == "architectural",
                )
            ) or 0
        else:
            comment_count = 0
            has_blocker = False
            arch_count = 0

        review.quality_tier = classify_review_quality(
            review.state, review.body_length, comment_count, body=review.body or "",
            has_blocker_comment=has_blocker, architectural_comment_count=arch_count,
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

    # Detect reopen before overwriting state
    incoming_state = issue_data.get("state")
    if issue.state == "closed" and incoming_state == "open":
        issue.reopen_count = (issue.reopen_count or 0) + 1

    issue.github_id = issue_data["id"]
    issue.title = issue_data.get("title")
    issue.body = issue_data.get("body")
    issue.state = incoming_state
    issue.labels = [l["name"] for l in issue_data.get("labels", [])]
    issue.html_url = issue_data.get("html_url")

    assignee = issue_data.get("assignee") or {}
    issue.assignee_id = await resolve_author(db, assignee.get("login"))

    # Quality scoring fields
    body = issue_data.get("body") or ""
    issue.comment_count = issue_data.get("comments", 0)
    issue.body_length = len(body)
    issue.has_checklist = bool(re.search(r'- \[[ xX]\]', body))
    issue.state_reason = issue_data.get("state_reason")
    issue.creator_github_username = issue_data.get("user", {}).get("login")

    milestone = issue_data.get("milestone") or {}
    issue.milestone_title = milestone.get("title")
    due_on = milestone.get("due_on")
    if due_on:
        issue.milestone_due_on = datetime.fromisoformat(
            due_on.replace("Z", "+00:00")
        ).date()
    else:
        issue.milestone_due_on = None

    for field in ("created_at", "updated_at", "closed_at"):
        val = issue_data.get(field)
        if val:
            setattr(issue, field, datetime.fromisoformat(val.replace("Z", "+00:00")))
        else:
            setattr(issue, field, None)

    if issue.closed_at and issue.created_at:
        issue.time_to_close_s = int(
            (issue.closed_at - issue.created_at).total_seconds()
        )
    else:
        issue.time_to_close_s = None

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


def _safe_delta_seconds(a: datetime | None, b: datetime | None) -> int | None:
    """Compute (a - b) in seconds, normalizing timezone-aware/naive mismatch (SQLite strips tz)."""
    if a is None or b is None:
        return None
    # Strip tzinfo if only one side has it (SQLite returns naive datetimes)
    if a.tzinfo is not None and b.tzinfo is None:
        a = a.replace(tzinfo=None)
    elif b.tzinfo is not None and a.tzinfo is None:
        b = b.replace(tzinfo=None)
    return int((a - b).total_seconds())


async def compute_approval_metrics(
    db: AsyncSession, pr: PullRequest
) -> None:
    """Compute approved_at, approval_count, time_to_approve_s, time_after_approve_s,
    and merged_without_approval from synced reviews."""
    approved_reviews = await db.execute(
        select(PRReview.submitted_at).where(
            PRReview.pr_id == pr.id,
            PRReview.state == "APPROVED",
            PRReview.submitted_at.isnot(None),
        )
    )
    approved_timestamps = [row[0] for row in approved_reviews.all()]

    pr.approval_count = len(approved_timestamps)

    if approved_timestamps:
        pr.approved_at = max(approved_timestamps)
        pr.time_to_approve_s = _safe_delta_seconds(pr.approved_at, pr.created_at)
        pr.time_after_approve_s = _safe_delta_seconds(pr.merged_at, pr.approved_at)
    else:
        pr.approved_at = None
        pr.time_to_approve_s = None
        pr.time_after_approve_s = None

    pr.merged_without_approval = (
        pr.is_merged is True and pr.approval_count == 0
    )


# --- PR Files & Repo Tree ---


async def upsert_pr_file(
    db: AsyncSession, file_data: dict, pr: PullRequest
) -> PRFile:
    filename = file_data["filename"]
    result = await db.execute(
        select(PRFile).where(PRFile.pr_id == pr.id, PRFile.filename == filename)
    )
    pr_file = result.scalar_one_or_none()
    if not pr_file:
        pr_file = PRFile(pr_id=pr.id, filename=filename)
        db.add(pr_file)

    pr_file.additions = file_data.get("additions", 0)
    pr_file.deletions = file_data.get("deletions", 0)
    pr_file.status = file_data.get("status")
    pr_file.previous_filename = file_data.get("previous_filename")
    return pr_file


async def upsert_check_run(
    db: AsyncSession, check_data: dict, pr: PullRequest
) -> PRCheckRun:
    check_name = check_data.get("name", "unknown")
    run_attempt = check_data.get("run_attempt", 1) or 1

    result = await db.execute(
        select(PRCheckRun).where(
            PRCheckRun.pr_id == pr.id,
            PRCheckRun.check_name == check_name,
            PRCheckRun.run_attempt == run_attempt,
        )
    )
    check_run = result.scalar_one_or_none()
    if not check_run:
        check_run = PRCheckRun(
            pr_id=pr.id, check_name=check_name, run_attempt=run_attempt
        )
        db.add(check_run)

    check_run.conclusion = check_data.get("conclusion")

    for field in ("started_at", "completed_at"):
        val = check_data.get(field)
        if val:
            setattr(
                check_run, field,
                datetime.fromisoformat(val.replace("Z", "+00:00")),
            )

    if check_run.started_at and check_run.completed_at:
        check_run.duration_s = int(
            (check_run.completed_at - check_run.started_at).total_seconds()
        )

    return check_run


async def sync_repo_tree(
    client: httpx.AsyncClient,
    db: AsyncSession,
    repo: Repository,
    ctx: SyncContext | None = None,
) -> tuple[int, bool]:
    """Fetch the full file tree for a repo's default branch.

    Returns (count_of_entries, truncated).
    """
    if not repo.default_branch:
        return 0, False

    resp = await github_get(
        client,
        f"/repos/{repo.full_name}/git/trees/{repo.default_branch}",
        params={"recursive": "1"},
        ctx=ctx,
    )
    data = resp.json()
    truncated = data.get("truncated", False)

    # Full snapshot replacement — delete old entries, insert fresh
    await db.execute(
        delete(RepoTreeFile).where(RepoTreeFile.repo_id == repo.id)
    )

    now = datetime.now(timezone.utc)
    count = 0
    for item in data.get("tree", []):
        if item["type"] in ("blob", "tree"):
            db.add(
                RepoTreeFile(
                    repo_id=repo.id,
                    path=item["path"],
                    type=item["type"],
                    last_synced_at=now,
                )
            )
            count += 1

    return count, truncated


# --- Deployments (DORA) ---


async def upsert_deployment(
    db: AsyncSession, run_data: dict, repo: Repository
) -> Deployment:
    """Upsert a deployment record from a GitHub Actions workflow run."""
    run_id = run_data["id"]
    result = await db.execute(
        select(Deployment).where(
            Deployment.repo_id == repo.id,
            Deployment.workflow_run_id == run_id,
        )
    )
    dep = result.scalar_one_or_none()
    if not dep:
        dep = Deployment(repo_id=repo.id, workflow_run_id=run_id)
        db.add(dep)

    dep.environment = settings.deploy_environment
    dep.sha = run_data.get("head_sha")
    dep.workflow_name = run_data.get("name")
    dep.status = run_data.get("conclusion") or run_data.get("status")

    updated = run_data.get("updated_at")
    if updated:
        dep.deployed_at = datetime.fromisoformat(updated.replace("Z", "+00:00"))

    return dep


async def compute_deployment_lead_times(
    db: AsyncSession, repo: Repository
) -> None:
    """Compute lead_time_s for all deployments in a repo.

    For each deployment, find the oldest PR merged between the previous
    deployment and this one. lead_time = deployed_at - oldest_pr.merged_at.
    """
    result = await db.execute(
        select(Deployment)
        .where(Deployment.repo_id == repo.id, Deployment.deployed_at.isnot(None))
        .order_by(Deployment.deployed_at.asc())
    )
    deployments = list(result.scalars().all())

    for i, dep in enumerate(deployments):
        if i == 0:
            # First deployment has no prior reference point — skip lead time
            dep.lead_time_s = None
            continue

        prev_deployed_at = deployments[i - 1].deployed_at

        # Find PRs merged between the previous deploy and this one
        oldest_merge = await db.scalar(
            select(func.min(PullRequest.merged_at)).where(
                PullRequest.repo_id == repo.id,
                PullRequest.is_merged.is_(True),
                PullRequest.merged_at.isnot(None),
                PullRequest.merged_at <= dep.deployed_at,
                PullRequest.merged_at > prev_deployed_at,
            )
        )

        if oldest_merge:
            dep.lead_time_s = _safe_delta_seconds(dep.deployed_at, oldest_merge)
        else:
            dep.lead_time_s = None


async def sync_deployments(
    client: httpx.AsyncClient,
    db: AsyncSession,
    repo: Repository,
    ctx: SyncContext | None = None,
) -> int:
    """Sync deployment data from GitHub Actions workflow runs.

    Only runs if DEPLOY_WORKFLOW_NAME is configured. Returns count of
    deployments upserted.

    Note: The Actions /runs endpoint returns { workflow_runs: [...] }, not a
    flat array, so we paginate manually instead of using github_get_paginated.
    """
    if not settings.deploy_workflow_name:
        return 0

    branch = repo.default_branch or "main"

    all_runs: list[dict] = []
    page = 1
    while True:
        resp = await github_get(
            client,
            f"/repos/{repo.full_name}/actions/runs",
            {
                "event": "push",
                "branch": branch,
                "status": "success",
                "per_page": "100",
                "page": str(page),
            },
            ctx=ctx,
        )
        data = resp.json()
        runs = data.get("workflow_runs", [])
        if not runs:
            break
        all_runs.extend(runs)
        if len(runs) < 100:
            break
        page += 1

    count = 0
    for run in all_runs:
        # Filter by workflow name
        if run.get("name") != settings.deploy_workflow_name:
            continue
        await upsert_deployment(db, run, repo)
        count += 1

    if count > 0:
        await db.flush()
        await compute_deployment_lead_times(db, repo)

    return count


# --- Sync Orchestration ---


BATCH_SIZE = 50


async def sync_repo(
    ctx: SyncContext,
    repo: Repository,
    since: datetime | None = None,
) -> tuple[int, int, list[str]]:
    """Sync a single repo. Returns (prs_upserted, issues_upserted, warnings).

    Commits every BATCH_SIZE PRs for crash resilience within large repos.
    """
    db = ctx.db
    client = ctx.client
    prs_upserted = 0
    issues_upserted = 0
    warnings: list[str] = []

    # Fetch PRs
    pr_params: dict = {"state": "all", "sort": "updated", "direction": "desc"}
    if since:
        pr_items = await github_get_paginated(
            client,
            f"/repos/{repo.full_name}/pulls",
            pr_params,
            stop_before=since,
            ctx=ctx,
        )
    else:
        pr_items = await github_get_paginated(
            client, f"/repos/{repo.full_name}/pulls", pr_params, ctx=ctx
        )

    for pr_data in pr_items:
        pr = await upsert_pull_request(db, client, pr_data, repo)
        prs_upserted += 1

        # Fetch reviews for this PR
        reviews_data = await github_get_paginated(
            client, f"/repos/{repo.full_name}/pulls/{pr.number}/reviews", ctx=ctx
        )
        for review_data in reviews_data:
            await upsert_review(db, review_data, pr)

        # Fetch review comments (inline code comments) for this PR
        review_comments_data = await github_get_paginated(
            client, f"/repos/{repo.full_name}/pulls/{pr.number}/comments", ctx=ctx
        )
        for comment_data in review_comments_data:
            await upsert_review_comment(db, comment_data, pr)

        # Flush so comment counts are visible, then recompute quality tiers
        await db.flush()
        await recompute_review_quality_tiers(db, pr)

        # Compute approval metrics from synced reviews
        await compute_approval_metrics(db, pr)

        # Compute review round count (number of CHANGES_REQUESTED reviews)
        round_count = await db.scalar(
            select(func.count()).where(
                PRReview.pr_id == pr.id,
                PRReview.state == "CHANGES_REQUESTED",
            )
        ) or 0
        pr.review_round_count = round_count

        # Fetch file-level changes for this PR
        files_data = await github_get_paginated(
            client, f"/repos/{repo.full_name}/pulls/{pr.number}/files", ctx=ctx
        )
        for file_data in files_data:
            await upsert_pr_file(db, file_data, pr)

        # Fetch check runs for this PR's HEAD commit
        if pr.head_sha:
            try:
                check_resp = await github_get(
                    client,
                    f"/repos/{repo.full_name}/commits/{pr.head_sha}/check-runs",
                    ctx=ctx,
                )
                check_runs_data = check_resp.json().get("check_runs", [])
                for check_data in check_runs_data:
                    await upsert_check_run(db, check_data, pr)
            except httpx.HTTPStatusError as e:
                warn_msg = f"check_runs PR#{pr.number}: {e}"
                warnings.append(warn_msg)
                ctx.sync_logger.warning(
                    "Failed to fetch check runs for PR #%d (sha=%s): %s",
                    pr.number, pr.head_sha, e,
                )

        # Batch commit every BATCH_SIZE PRs
        if prs_upserted % BATCH_SIZE == 0:
            await db.commit()
            _add_log(
                ctx, "info",
                f"Batch committed {prs_upserted}/{len(pr_items)} PRs",
                repo=repo.full_name,
            )

    # Fetch issues (skip PRs — they have a pull_request key)
    issue_params: dict = {"state": "all", "sort": "updated", "direction": "desc"}
    if since:
        issue_params["since"] = since.isoformat()

    issue_items = await github_get_paginated(
        client, f"/repos/{repo.full_name}/issues", issue_params, ctx=ctx
    )
    for issue_data in issue_items:
        if "pull_request" in issue_data:
            continue
        await upsert_issue(db, issue_data, repo)
        issues_upserted += 1

    # Fetch issue comments
    comment_params: dict = {"sort": "updated", "direction": "desc"}
    if since:
        comment_params["since"] = since.isoformat()

    comments_data = await github_get_paginated(
        client, f"/repos/{repo.full_name}/issues/comments", comment_params, ctx=ctx
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

    # Sync the repo file tree for stale directory detection
    try:
        _tree_count, tree_truncated = await sync_repo_tree(client, db, repo, ctx=ctx)
        repo.tree_truncated = tree_truncated
    except Exception as e:
        warn_msg = f"repo_tree: {e}"
        warnings.append(warn_msg)
        ctx.sync_logger.warning("sync_repo_tree failed for %s: %s", repo.full_name, e)

    # Sync deployments for DORA metrics (skipped if DEPLOY_WORKFLOW_NAME not set)
    try:
        await sync_deployments(client, db, repo, ctx=ctx)
    except Exception as e:
        warn_msg = f"deployments: {e}"
        warnings.append(warn_msg)
        ctx.sync_logger.warning("sync_deployments failed for %s: %s", repo.full_name, e)

    repo.last_synced_at = datetime.now(timezone.utc)
    return prs_upserted, issues_upserted, warnings


async def run_sync(
    sync_type: str = "full",
    repo_ids: list[int] | None = None,
    since_override: datetime | None = None,
    resumed_from_id: int | None = None,
) -> SyncEvent:
    """Run a full or incremental sync across repos.

    Args:
        sync_type: "full" or "incremental"
        repo_ids: specific repo IDs to sync (None = all tracked)
        since_override: override per-repo last_synced_at with this date
        resumed_from_id: ID of the SyncEvent this resumes from
    """
    async with AsyncSessionLocal() as db:
        # Concurrency guard
        active_result = await db.execute(
            select(SyncEvent).where(SyncEvent.status == "started")
        )
        if active_result.scalar_one_or_none():
            logger.warning("Skipping sync — another sync is already in progress")
            raise RuntimeError("A sync is already in progress")

        sync_event = SyncEvent(
            sync_type=sync_type,
            status="started",
            started_at=datetime.now(timezone.utc),
            repos_synced=0,
            prs_upserted=0,
            issues_upserted=0,
            errors=[],
            repo_ids=repo_ids,
            since_override=since_override,
            resumed_from_id=resumed_from_id,
            repos_completed=[],
            repos_failed=[],
            log_summary=[],
            is_resumable=False,
            rate_limit_wait_s=0,
        )
        db.add(sync_event)
        await db.commit()

        sync_log = logger.getChild(f"sync.{sync_event.id}")
        ctx = SyncContext(
            db=db, client=None, sync_event=sync_event, sync_logger=sync_log  # type: ignore[arg-type]
        )
        _add_log(ctx, "info", f"Sync started: type={sync_type}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                ctx.client = client

                # Determine which repos to sync
                if repo_ids:
                    # Specific repos requested (resume or custom sync)
                    result = await db.execute(
                        select(Repository).where(Repository.id.in_(repo_ids))
                    )
                    tracked_repos = list(result.scalars().all())
                else:
                    # Fetch org repos from GitHub and upsert all
                    repos_data = await github_get_paginated(
                        client,
                        f"/orgs/{settings.github_org}/repos",
                        {"type": "all", "sort": "updated"},
                        ctx=ctx,
                    )
                    for repo_data in repos_data:
                        repo = await upsert_repo(db, repo_data)
                        await db.flush()

                    # Commit repo upserts
                    await db.commit()

                    result = await db.execute(
                        select(Repository).where(Repository.is_tracked.is_(True))
                    )
                    tracked_repos = list(result.scalars().all())

                sync_event.total_repos = len(tracked_repos)
                await db.commit()
                _add_log(ctx, "info", f"{len(tracked_repos)} repos to sync")

                for repo in tracked_repos:
                    # Update current repo for progress visibility
                    sync_event.current_repo_name = repo.full_name
                    await db.commit()

                    sync_log.info("Starting repo: %s", repo.full_name)
                    _add_log(ctx, "info", "Starting sync", repo=repo.full_name)

                    # Proactive rate limit check
                    await proactive_rate_check(client, ctx)

                    try:
                        since = since_override or (
                            repo.last_synced_at if sync_type == "incremental" else None
                        )
                        prs, issues, warnings = await sync_repo(ctx, repo, since=since)

                        # Per-repo commit — data is now durable
                        sync_event.repos_synced = (sync_event.repos_synced or 0) + 1
                        sync_event.prs_upserted = (sync_event.prs_upserted or 0) + prs
                        sync_event.issues_upserted = (
                            sync_event.issues_upserted or 0
                        ) + issues
                        _append_jsonb(sync_event, "repos_completed", {
                            "repo_id": repo.id,
                            "repo_name": repo.full_name,
                            "status": "partial" if warnings else "ok",
                            "prs": prs,
                            "issues": issues,
                            "warnings": warnings,
                        })
                        await db.commit()

                        status_label = "partial" if warnings else "ok"
                        _add_log(
                            ctx, "info",
                            f"Complete ({status_label}): {prs} PRs, {issues} issues",
                            repo=repo.full_name,
                        )
                        sync_log.info(
                            "Repo complete (%s): %d PRs, %d issues",
                            status_label, prs, issues,
                        )

                    except Exception as e:
                        sync_log.error("Error syncing %s: %s", repo.full_name, e)

                        # Preserve in-memory log before rollback discards it
                        saved_logs = list(sync_event.log_summary or [])

                        await db.rollback()

                        # Re-merge sync_event after rollback, restore logs
                        sync_event = await db.merge(sync_event)
                        ctx.sync_event = sync_event
                        sync_event.log_summary = saved_logs

                        _append_jsonb(sync_event, "repos_failed", {
                            "repo_id": repo.id,
                            "repo_name": repo.full_name,
                            "error": str(e)[:500],
                        })
                        _append_jsonb(
                            sync_event, "errors",
                            make_sync_error(
                                repo=repo.full_name, repo_id=repo.id,
                                step="sync_repo", exception=e,
                            ),
                        )
                        _add_log(ctx, "error", str(e)[:200], repo=repo.full_name)
                        await db.commit()

                # Determine final status
                failed_count = len(sync_event.repos_failed or [])
                completed_count = len(sync_event.repos_completed or [])
                if failed_count == 0:
                    sync_event.status = "completed"
                elif completed_count > 0:
                    sync_event.status = "completed_with_errors"
                    sync_event.is_resumable = True
                else:
                    sync_event.status = "failed"
                    sync_event.is_resumable = True

        except Exception as e:
            sync_log.error("Sync failed: %s", e)
            saved_logs = list(sync_event.log_summary or [])
            await db.rollback()
            sync_event = await db.merge(sync_event)
            ctx.sync_event = sync_event
            sync_event.log_summary = saved_logs
            sync_event.status = "failed"
            sync_event.is_resumable = True
            _append_jsonb(
                sync_event, "errors",
                make_sync_error(step="run_sync", exception=e),
            )
            _add_log(ctx, "error", f"Sync failed: {e}")

        finally:
            now = datetime.now(timezone.utc)
            sync_event.current_repo_name = None
            sync_event.completed_at = now
            sync_event.rate_limit_wait_s = ctx.rate_limit_wait_total
            if sync_event.started_at:
                sync_event.duration_s = int(
                    (now - sync_event.started_at).total_seconds()
                )

            total = len(sync_event.repos_completed or [])
            failed = len(sync_event.repos_failed or [])
            _add_log(
                ctx, "info",
                f"Sync done: {total} ok, {failed} failed, {sync_event.duration_s}s",
            )
            await db.commit()

    return sync_event
