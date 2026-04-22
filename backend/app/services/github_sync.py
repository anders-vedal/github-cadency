import asyncio
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import jwt
import sqlalchemy as sa
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logging import get_logger
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

logger = get_logger(__name__)

GITHUB_API = "https://api.github.com"


# --- GitHub App Authentication ---


class GitHubAuthError(Exception):
    """Raised when GitHub App authentication fails with an actionable hint."""

    def __init__(self, message: str, hint: str):
        self.hint = hint
        super().__init__(message)


class GitHubAuth:
    def __init__(self):
        self._token: str | None = None
        self._token_expires_at: float = 0

    def _generate_jwt(self) -> str:
        now = int(time.time())
        key_path = Path(settings.github_app_private_key_path)

        if settings.github_app_id == 0:
            raise GitHubAuthError(
                "GITHUB_APP_ID is not set (defaults to 0)",
                "Set GITHUB_APP_ID in your .env file to your GitHub App's numeric ID.",
            )

        try:
            private_key = key_path.read_bytes()
        except FileNotFoundError:
            raise GitHubAuthError(
                f"Private key file not found: {key_path.resolve()}",
                f"Download the .pem file from your GitHub App settings and place it at "
                f"'{settings.github_app_private_key_path}', or set GITHUB_APP_PRIVATE_KEY_PATH "
                f"in your .env file.",
            )
        except PermissionError:
            raise GitHubAuthError(
                f"Cannot read private key file: {key_path.resolve()} (permission denied)",
                "Check file permissions on the .pem file.",
            )

        if not private_key.strip():
            raise GitHubAuthError(
                f"Private key file is empty: {key_path.resolve()}",
                "The .pem file exists but has no content. Re-download it from your GitHub App settings.",
            )

        payload = {
            "iat": now - 60,
            "exp": now + (9 * 60),
            "iss": str(settings.github_app_id),
        }
        try:
            return jwt.encode(payload, private_key, algorithm="RS256")
        except (jwt.InvalidKeyError, ValueError, TypeError) as e:
            raise GitHubAuthError(
                f"Invalid private key: {e}",
                "The .pem file does not contain a valid RSA private key. "
                "Re-download it from your GitHub App settings > Private keys.",
            )

    async def get_installation_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        if settings.github_app_installation_id == 0:
            raise GitHubAuthError(
                "GITHUB_APP_INSTALLATION_ID is not set (defaults to 0)",
                "Find it at https://github.com/settings/installations — click your app, "
                "the ID is the number in the URL.",
            )

        app_jwt = self._generate_jwt()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GITHUB_API}/app/installations/{settings.github_app_installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {app_jwt}",
                    "Accept": "application/vnd.github+json",
                },
            )
            if resp.status_code >= 400:
                github_msg = ""
                try:
                    github_msg = resp.json().get("message", "")
                except Exception:
                    pass
                raise GitHubAuthError(
                    f"GitHub API returned HTTP {resp.status_code} when requesting installation token"
                    + (f": {github_msg}" if github_msg else ""),
                    _installation_token_hint(resp.status_code, github_msg),
                )
            data = resp.json()

        self._token = data["token"]
        expires_at = data["expires_at"]  # ISO format
        self._token_expires_at = datetime.fromisoformat(
            expires_at.replace("Z", "+00:00")
        ).timestamp()
        return self._token


def _installation_token_hint(status_code: int, github_msg: str) -> str:
    """Return an actionable hint based on the GitHub API error."""
    msg_lower = github_msg.lower()
    if status_code == 401:
        if "bad credentials" in msg_lower or "could not be decoded" in msg_lower:
            return (
                "The JWT was rejected — your .pem key may not match the GitHub App. "
                "Re-download the private key from your App settings."
            )
        return (
            "Authentication failed. Check that GITHUB_APP_ID and the .pem file "
            "match your GitHub App."
        )
    if status_code == 404:
        return (
            "Installation not found. Check that GITHUB_APP_INSTALLATION_ID is correct "
            "and the app is installed on your organization."
        )
    if status_code == 403:
        return (
            "The GitHub App lacks required permissions. Check your App's permission "
            "settings on GitHub."
        )
    return f"Unexpected error from GitHub (HTTP {status_code}). Check your GitHub App configuration."


github_auth = GitHubAuth()


# --- SyncContext ---


@dataclass
class SyncContext:
    """Holds state for a sync run, passed through the call chain."""

    db: AsyncSession
    client: httpx.AsyncClient
    sync_event: SyncEvent
    sync_logger: object = field(default_factory=lambda: logger)
    rate_limit_wait_total: int = 0


# --- JSONB Mutation Helper ---


def _append_jsonb(obj: object, attr: str, value: dict | str) -> None:
    """Safely append to a JSONB list column, triggering SQLAlchemy change detection."""
    current = list(getattr(obj, attr) or [])
    current.append(value)
    setattr(obj, attr, current)


# --- Structured Error Helpers ---


MAX_LOG_ENTRIES = 500

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


def _extract_github_message(exception: httpx.HTTPStatusError) -> str:
    """Try to extract the human-readable message from a GitHub API error response."""
    try:
        body = exception.response.json()
        msg = body.get("message", "")
        doc_url = body.get("documentation_url", "")
        if msg and doc_url:
            return f"{msg} (see {doc_url})"
        return msg
    except Exception:
        return ""


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
    hint = None

    if isinstance(exception, GitHubAuthError):
        error_type = "config"
        retryable = False
        hint = exception.hint
    elif isinstance(exception, httpx.HTTPStatusError):
        status_code = exception.response.status_code
        error_type, retryable = STATUS_CODE_CLASSIFICATION.get(
            status_code, ("github_api", False)
        )
    elif isinstance(exception, httpx.TimeoutException):
        error_type, retryable = "timeout", True
    elif isinstance(exception, httpx.ConnectError):
        error_type, retryable = "timeout", True
    elif isinstance(exception, (FileNotFoundError, PermissionError)):
        error_type = "config"
        retryable = False

    # Build message — include GitHub API error body for HTTP errors
    message = str(exception)[:500]
    if isinstance(exception, httpx.HTTPStatusError):
        github_msg = _extract_github_message(exception)
        if github_msg:
            message = f"{message} — GitHub: {github_msg}"[:500]

    result = {
        "repo": repo,
        "repo_id": repo_id,
        "step": step,
        "error_type": error_type,
        "status_code": status_code,
        "message": message,
        "retryable": retryable,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "attempt": attempt,
    }
    if hint:
        result["hint"] = hint[:500]
    return result


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


class SyncCancelled(Exception):
    """Raised when a sync is cancelled by user request."""
    pass


async def _check_cancel(ctx: SyncContext) -> None:
    """Check if cancellation was requested and raise if so."""
    db = ctx.db
    result = await db.execute(
        select(SyncEvent.cancel_requested).where(
            SyncEvent.id == ctx.sync_event.id
        )
    )
    if result.scalar_one_or_none():
        _add_log(ctx, "warn", "Sync cancelled by user")
        raise SyncCancelled("Sync cancelled by user request")


def _clear_repo_progress(sync_event: "SyncEvent") -> None:
    """Clear per-repo progress fields between repos."""
    sync_event.current_step = None
    sync_event.current_repo_prs_total = None
    sync_event.current_repo_prs_done = None
    sync_event.current_repo_issues_total = None
    sync_event.current_repo_issues_done = None


PROGRESS_COMMIT_INTERVAL = 10


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
            "Rate limit low, waiting",
            remaining=remaining, wait_seconds=wait_seconds, event_type="system.github_api",
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
        ctx.sync_logger.info("Rate limit check", remaining=remaining, event_type="system.github_api")

        if remaining < 200:
            reset_at = data.get("resources", {}).get("core", {}).get("reset", 0)
            wait_seconds = max(reset_at - int(time.time()), 1)
            if wait_seconds > 300:
                await ctx.db.commit()
            _add_log(ctx, "warn", f"Proactive rate limit wait: {wait_seconds}s")
            ctx.rate_limit_wait_total += wait_seconds
            await asyncio.sleep(wait_seconds)
    except Exception as e:
        ctx.sync_logger.warning("Proactive rate check failed", error=str(e), event_type="system.github_api")


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
                    "Retryable error, retrying",
                    path=path, attempt=attempt + 1, max_attempts=MAX_RETRIES + 1,
                    backoff_seconds=backoff, error=str(last_exc), event_type="system.github_api",
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


async def fetch_installation_repositories(
    client: httpx.AsyncClient, ctx: SyncContext | None = None
) -> list[dict]:
    """Fetch all repos accessible to the GitHub App installation.

    Uses ``/installation/repositories`` so this works for both User and Org
    installations. Response shape is ``{"total_count": N, "repositories": [...]}``
    so we unwrap ``.repositories`` and paginate manually.
    """
    all_repos: list[dict] = []
    page = 1
    per_page = 100
    while True:
        resp = await github_get(
            client,
            "/installation/repositories",
            {"per_page": str(per_page), "page": str(page)},
            ctx=ctx,
        )
        data = resp.json()
        repos = data.get("repositories") or []
        if not repos:
            break
        all_repos.extend(repos)
        if len(repos) < per_page:
            break
        page += 1
    return all_repos


# --- Author Resolution ---


async def _fetch_user_profile(
    client: httpx.AsyncClient, login: str, ctx: SyncContext | None = None,
) -> dict | None:
    """Fetch a full user profile from ``GET /users/{login}``.

    Returns the JSON dict on success, or ``None`` if the request fails.
    The full profile includes ``name``, ``email``, ``location``, ``bio``,
    ``company`` — fields absent from the "simple user" objects embedded in
    PR / review / org-members responses.
    """
    try:
        resp = await github_get(client, f"/users/{login}", ctx=ctx)
        return resp.json()
    except Exception:
        logger.warning("Failed to fetch profile", login=login, event_type="system.github_api")
        return None


def _apply_profile_to_developer(dev: Developer, profile: dict) -> None:
    """Set Developer fields from a full GitHub user profile dict."""
    name = profile.get("name")
    if name:
        dev.display_name = name
    if not dev.email:
        dev.email = profile.get("email")
    if not dev.location:
        dev.location = profile.get("location")
    if not dev.avatar_url:
        dev.avatar_url = profile.get("avatar_url")


async def resolve_author(
    db: AsyncSession,
    github_username: str | None,
    *,
    user_data: dict | None = None,
    client: httpx.AsyncClient | None = None,
    ctx: SyncContext | None = None,
) -> int | None:
    """Resolve a GitHub username to a developer ID, optionally auto-creating.

    If ``user_data`` is provided and the username is not found, a new Developer
    row is created.  When ``client`` is also provided the full user profile is
    fetched from ``GET /users/{login}`` so that ``display_name``, ``email``,
    and ``location`` are populated correctly.
    """
    if not github_username:
        return None
    result = await db.execute(
        select(Developer).where(Developer.github_username == github_username)
    )
    dev = result.scalar_one_or_none()
    if dev is not None:
        if not dev.is_active:
            dev.is_active = True
            await db.flush()
            logger.warning("Auto-reactivated inactive developer", github_username=github_username, developer_id=dev.id, event_type="system.sync")
            if ctx:
                _add_log(ctx, "warn", f"Auto-reactivated inactive developer '{github_username}' — appeared in GitHub activity")
        return dev.id

    if user_data is None:
        return None

    # Fetch the full profile so we get name/email/location
    profile = None
    if client is not None:
        profile = await _fetch_user_profile(client, github_username, ctx=ctx)

    display_name = (
        (profile or {}).get("name")
        or user_data.get("name")
        or user_data.get("login")
        or github_username
    )
    dev = Developer(
        github_username=github_username,
        display_name=display_name,
        avatar_url=user_data.get("avatar_url"),
        app_role="developer",
        is_active=True,
    )
    if profile:
        _apply_profile_to_developer(dev, profile)
    db.add(dev)
    await db.flush()
    logger.info("Auto-created developer", github_username=github_username, developer_id=dev.id, event_type="system.sync")
    return dev.id


async def backfill_author_links(db: AsyncSession) -> dict[str, int]:
    """Bulk-update NULL author/reviewer/assignee FKs using stored github usernames.

    Only updates rows where a matching developer actually exists (using an EXISTS
    guard) so that rowcount accurately reflects real changes.

    Returns counts of rows updated per table.
    """
    from sqlalchemy import update

    # Backfill pull_requests.author_id
    pr_subq = (
        select(Developer.id)
        .where(Developer.github_username == PullRequest.author_github_username)
        .correlate(PullRequest)
        .scalar_subquery()
    )
    pr_result = await db.execute(
        update(PullRequest)
        .where(
            PullRequest.author_id.is_(None),
            PullRequest.author_github_username.isnot(None),
            select(Developer.id)
            .where(Developer.github_username == PullRequest.author_github_username)
            .correlate(PullRequest)
            .exists(),
        )
        .values(author_id=pr_subq)
    )
    pr_count = pr_result.rowcount

    # Backfill pr_reviews.reviewer_id
    review_subq = (
        select(Developer.id)
        .where(Developer.github_username == PRReview.reviewer_github_username)
        .correlate(PRReview)
        .scalar_subquery()
    )
    review_result = await db.execute(
        update(PRReview)
        .where(
            PRReview.reviewer_id.is_(None),
            PRReview.reviewer_github_username.isnot(None),
            select(Developer.id)
            .where(Developer.github_username == PRReview.reviewer_github_username)
            .correlate(PRReview)
            .exists(),
        )
        .values(reviewer_id=review_subq)
    )
    review_count = review_result.rowcount

    # Backfill issues.assignee_id
    issue_subq = (
        select(Developer.id)
        .where(Developer.github_username == Issue.assignee_github_username)
        .correlate(Issue)
        .scalar_subquery()
    )
    issue_result = await db.execute(
        update(Issue)
        .where(
            Issue.assignee_id.is_(None),
            Issue.assignee_github_username.isnot(None),
            select(Developer.id)
            .where(Developer.github_username == Issue.assignee_github_username)
            .correlate(Issue)
            .exists(),
        )
        .values(assignee_id=issue_subq)
    )
    issue_count = issue_result.rowcount

    # Backfill issues.creator_id
    creator_subq = (
        select(Developer.id)
        .where(Developer.github_username == Issue.creator_github_username)
        .correlate(Issue)
        .scalar_subquery()
    )
    creator_result = await db.execute(
        update(Issue)
        .where(
            Issue.creator_id.is_(None),
            Issue.creator_github_username.isnot(None),
            select(Developer.id)
            .where(Developer.github_username == Issue.creator_github_username)
            .correlate(Issue)
            .exists(),
        )
        .values(creator_id=creator_subq)
    )
    creator_count = creator_result.rowcount

    await db.flush()
    counts = {
        "pull_requests": pr_count,
        "pr_reviews": review_count,
        "issues_assignee": issue_count,
        "issues_creator": creator_count,
    }
    logger.info("backfill_author_links complete", event_type="system.sync", **counts)
    return counts


async def run_contributor_sync() -> SyncEvent:
    """Standalone contributor backfill with SyncEvent tracking.

    Creates a SyncEvent(sync_type="contributors") and re-runs
    ``backfill_author_links`` to repair any NULL author/reviewer/assignee FKs
    on existing rows. Contributors themselves are materialised on-demand by
    ``resolve_author`` during the main sync — no separate fetch needed.
    """
    async with AsyncSessionLocal() as db:
        # Concurrency guard (safety net for TOCTOU race with the API check)
        active_result = await db.execute(
            select(SyncEvent).where(SyncEvent.status == "started").limit(1)
        )
        if active_result.scalar_one_or_none():
            logger.warning("Skipping contributor sync — another sync is in progress", event_type="system.sync")
            raise RuntimeError("A sync is already in progress")

        sync_event = SyncEvent(
            sync_type="contributors",
            status="started",
            started_at=datetime.now(timezone.utc),
            repos_synced=0,
            prs_upserted=0,
            issues_upserted=0,
            errors=[],
            repos_completed=[],
            repos_failed=[],
            log_summary=[],
            is_resumable=False,
            rate_limit_wait_s=0,
        )
        db.add(sync_event)
        await db.commit()

        sync_log = logger.bind(sync_id=sync_event.id)
        ctx = SyncContext(
            db=db, client=None, sync_event=sync_event, sync_logger=sync_log,  # type: ignore[arg-type]
        )
        _add_log(ctx, "info", "Contributor sync started")

        cancelled = False
        try:
            await _check_cancel(ctx)

            _add_log(ctx, "info", "Backfilling author links...")
            backfill = await backfill_author_links(db)
            await db.commit()

            total_backfilled = sum(backfill.values())
            if total_backfilled:
                _add_log(ctx, "info", f"Backfilled {total_backfilled} author links")

            sync_event.status = "completed"
            sync_event.repos_synced = 0
            _add_log(ctx, "info", f"Contributor sync complete: {total_backfilled} author links backfilled")

        except SyncCancelled:
            cancelled = True
            sync_event.status = "cancelled"
            sync_event.is_resumable = False

        except Exception as e:
            sync_log.error("Contributor sync failed", error=str(e)[:200], exc_type=type(e).__name__, event_type="system.sync")
            saved_logs = list(sync_event.log_summary or [])
            saved_errors = list(sync_event.errors or [])
            await db.rollback()
            await db.refresh(sync_event)
            sync_event.log_summary = saved_logs
            sync_event.errors = saved_errors
            sync_event.status = "failed"
            _append_jsonb(
                sync_event, "errors",
                make_sync_error(step="contributor_sync", exception=e),
            )
            _add_log(ctx, "error", f"Contributor sync failed: {e}")

        finally:
            now = datetime.now(timezone.utc)
            sync_event.completed_at = now
            sync_event.cancel_requested = False
            if sync_event.started_at:
                sync_event.duration_s = int(
                    (now - sync_event.started_at).total_seconds()
                )
            await db.commit()

    return sync_event


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
    pr.author_github_username = author_login
    pr.author_id = await resolve_author(db, author_login, user_data=user, client=client)

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
            logger.warning("Failed to fetch detail for PR", pr_number=pr.number, event_type="system.github_api")

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


_MENTION_RE = re.compile(
    r"(?<!\w)@([a-zA-Z0-9](?:[a-zA-Z0-9]|-(?=[a-zA-Z0-9])){0,38})"
)


def extract_mentions(body: str | None) -> list[str] | None:
    """Extract @mentions from a comment body. Returns unique usernames or None."""
    if not body:
        return None
    mentions = list(set(_MENTION_RE.findall(body)))
    return mentions if mentions else None


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
    db: AsyncSession,
    review_data: dict,
    pr: PullRequest,
    client: httpx.AsyncClient | None = None,
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
    reviewer_login = user.get("login")
    review.reviewer_github_username = reviewer_login
    review.reviewer_id = await resolve_author(db, reviewer_login, user_data=user, client=client)

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
    comment.mentions = extract_mentions(comment.body)
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
    db: AsyncSession,
    issue_data: dict,
    repo: Repository,
    client: httpx.AsyncClient | None = None,
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

    # GitHub issue type (available when repo has issue types enabled)
    type_obj = issue_data.get("type")
    issue.issue_type = type_obj.get("name") if isinstance(type_obj, dict) else None

    assignee = issue_data.get("assignee") or {}
    assignee_login = assignee.get("login")
    issue.assignee_github_username = assignee_login
    issue.assignee_id = await resolve_author(db, assignee_login, user_data=assignee if assignee_login else None, client=client)

    # Quality scoring fields
    body = issue_data.get("body") or ""
    issue.comment_count = issue_data.get("comments", 0)
    issue.body_length = len(body)
    issue.has_checklist = bool(re.search(r'- \[[ xX]\]', body))
    issue.state_reason = issue_data.get("state_reason")
    creator_user = issue_data.get("user") or {}
    creator_login = creator_user.get("login")
    issue.creator_github_username = creator_login
    issue.creator_id = await resolve_author(
        db, creator_login, user_data=creator_user if creator_login else None, client=client
    )

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
    comment.mentions = extract_mentions(comment.body)
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
    check_run.html_url = check_data.get("html_url") or check_data.get("details_url")

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
        .where(
            Deployment.repo_id == repo.id,
            Deployment.deployed_at.isnot(None),
            Deployment.status == "success",
        )
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
                "status": "completed",
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
        await detect_deployment_failures(db, repo)

    return count


async def detect_deployment_failures(
    db: AsyncSession, repo: Repository
) -> None:
    """Detect deployment failures and link recoveries for CFR/MTTR.

    Three failure signals:
    1. Failed workflow runs (conclusion != "success")
    2. Revert PRs merged within 48h after a successful deployment
    3. Hotfix PRs (configurable labels/branch prefixes) merged after a deployment
    """
    result = await db.execute(
        select(Deployment)
        .where(Deployment.repo_id == repo.id, Deployment.deployed_at.isnot(None))
        .order_by(Deployment.deployed_at.asc())
    )
    all_deps = list(result.scalars().all())
    if not all_deps:
        return

    # Reset failure flags for re-detection
    for dep in all_deps:
        dep.is_failure = False
        dep.failure_detected_via = None
        dep.recovered_at = None
        dep.recovery_deployment_id = None
        dep.recovery_time_s = None

    # Parse hotfix config
    hotfix_labels = {
        lbl.strip().lower()
        for lbl in settings.hotfix_labels.split(",")
        if lbl.strip()
    }
    hotfix_prefixes = [
        p.strip() for p in settings.hotfix_branch_prefixes.split(",") if p.strip()
    ]

    # Signal 1: Failed workflow runs
    for dep in all_deps:
        if dep.status and dep.status != "success":
            dep.is_failure = True
            dep.failure_detected_via = "failed_deploy"

    # Build index of successful deployments for recovery lookups
    successful = [d for d in all_deps if d.status == "success"]

    # Signal 2: Revert PRs merged within 48h after a successful deployment
    for dep in successful:
        window_end = dep.deployed_at + timedelta(hours=48)
        revert_exists = await db.scalar(
            select(PullRequest.id).where(
                PullRequest.repo_id == repo.id,
                PullRequest.is_revert.is_(True),
                PullRequest.is_merged.is_(True),
                PullRequest.merged_at.isnot(None),
                PullRequest.merged_at > dep.deployed_at,
                PullRequest.merged_at <= window_end,
            ).limit(1)
        )
        if revert_exists is not None:
            dep.is_failure = True
            dep.failure_detected_via = "revert_pr"

    # Signal 3: Hotfix PRs merged after a successful deployment
    if hotfix_labels or hotfix_prefixes:
        for dep in successful:
            if dep.is_failure:
                continue  # already flagged
            window_end = dep.deployed_at + timedelta(hours=48)
            pr_rows = (
                await db.execute(
                    select(PullRequest.labels, PullRequest.head_branch).where(
                        PullRequest.repo_id == repo.id,
                        PullRequest.is_merged.is_(True),
                        PullRequest.merged_at.isnot(None),
                        PullRequest.merged_at > dep.deployed_at,
                        PullRequest.merged_at <= window_end,
                        PullRequest.is_revert.isnot(True),
                    )
                )
            ).all()
            if not pr_rows:
                continue
            for labels, head_branch in pr_rows:
                matched = False
                if labels and hotfix_labels:
                    pr_label_names = {
                        (lbl.get("name", "") if isinstance(lbl, dict) else str(lbl)).lower()
                        for lbl in labels
                    }
                    if pr_label_names & hotfix_labels:
                        matched = True
                if not matched and head_branch and hotfix_prefixes:
                    for prefix in hotfix_prefixes:
                        if head_branch.startswith(prefix):
                            matched = True
                            break
                if matched:
                    dep.is_failure = True
                    dep.failure_detected_via = "hotfix_pr"
                    break

    # Link failures to recovery deployments (exclude flagged failures from candidates)
    recovery_candidates = [
        d for d in all_deps if d.status == "success" and not d.is_failure
    ]
    for dep in all_deps:
        if not dep.is_failure:
            continue
        # Find the next non-failure successful deployment after this failure
        recovery = None
        for candidate in recovery_candidates:
            if candidate.deployed_at and dep.deployed_at and candidate.deployed_at > dep.deployed_at:
                recovery = candidate
                break
        if recovery:
            dep.recovered_at = recovery.deployed_at
            dep.recovery_deployment_id = recovery.id
            dep.recovery_time_s = _safe_delta_seconds(recovery.deployed_at, dep.deployed_at)

    await db.flush()


# --- Sync Orchestration ---


BATCH_SIZE = 50

# Phase 09 timeline batching: GitHub's aliased-PR query tops out around 50 PRs
# per request before hitting node-limit errors. Matches the ceiling in
# `github_timeline.fetch_pr_timeline_batch`.
TIMELINE_BATCH_SIZE = 50


async def _fetch_codeowners_text(
    client: httpx.AsyncClient,
    repo_full_name: str,
    ctx: SyncContext,
) -> str | None:
    """Fetch CODEOWNERS content from the canonical locations.

    Returns the first file found (as decoded text) or ``None`` if none exist.
    GitHub hosts CODEOWNERS in one of three places; we probe in priority order
    and stop at the first hit. A 404 is the healthy "no file" case — any other
    error bubbles up as a warning in the caller.
    """
    from base64 import b64decode

    for path in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"):
        try:
            resp = await github_get(
                client, f"/repos/{repo_full_name}/contents/{path}", ctx=ctx
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                continue
            raise
        body = resp.json()
        content = body.get("content") or ""
        encoding = body.get("encoding") or "base64"
        if encoding == "base64":
            try:
                return b64decode(content).decode("utf-8", errors="replace")
            except Exception:
                return None
        return content
    return None


async def _enrich_pr_timelines(
    ctx: SyncContext,
    repo: Repository,
    pr_items: list[dict],
) -> None:
    """Fetch timeline events for PRs synced in this repo, persist, derive aggregates.

    Also detects CODEOWNERS bypass on merged PRs with an owners file present.
    Smart-skip already excluded unchanged PRs from ``pr_items`` upstream; we
    still re-scope here to PRs that exist in the DB with their current numbers.
    """
    from app.services.codeowners import check_bypass, parse_codeowners
    from app.services.github_timeline import (
        derive_pr_aggregates,
        fetch_pr_timeline_batch,
        persist_timeline_events,
    )

    db = ctx.db
    client = ctx.client
    owner, _, name = repo.full_name.partition("/")
    if not (owner and name):
        return

    pr_numbers = [int(p["number"]) for p in pr_items if p.get("number")]
    if not pr_numbers:
        return

    # Load the DB rows once so we can match GraphQL results to PRs without
    # N round trips. This covers both newly-synced and smart-skipped PRs —
    # timeline is idempotent and re-deriving aggregates is cheap.
    pr_rows = (
        await db.execute(
            select(PullRequest).where(
                PullRequest.repo_id == repo.id,
                PullRequest.number.in_(pr_numbers),
            )
        )
    ).scalars().all()
    pr_by_number: dict[int, PullRequest] = {pr.number: pr for pr in pr_rows}

    token = await github_auth.get_installation_token()

    # CODEOWNERS (best-effort: missing file is normal)
    codeowners_rules: list[tuple[str, list[str]]] = []
    try:
        text = await _fetch_codeowners_text(client, repo.full_name, ctx)
        if text:
            codeowners_rules = parse_codeowners(text)
    except Exception as exc:
        ctx.sync_logger.warning(
            "CODEOWNERS fetch failed",
            repo=repo.full_name,
            error=str(exc),
            event_type="system.github_api",
        )

    ctx.sync_event.current_step = "enriching_pr_timelines"
    await db.commit()
    _add_log(
        ctx, "info",
        f"Fetching PR timeline for {len(pr_numbers)} PRs",
        repo=repo.full_name,
    )

    total_events = 0
    for i in range(0, len(pr_numbers), TIMELINE_BATCH_SIZE):
        chunk = pr_numbers[i : i + TIMELINE_BATCH_SIZE]
        nodes_by_pr = await fetch_pr_timeline_batch(
            client, token, owner, name, chunk, batch_size=TIMELINE_BATCH_SIZE
        )
        for num, nodes in nodes_by_pr.items():
            pr = pr_by_number.get(num)
            if pr is None:
                continue
            counts = await persist_timeline_events(db, pr, nodes, client=client)
            total_events += counts.get("inserted", 0) + counts.get("updated", 0)
            await derive_pr_aggregates(db, pr)

            # CODEOWNERS bypass — only meaningful for merged PRs with rules + changed files
            if codeowners_rules and pr.merged_at is not None:
                await _set_codeowners_bypass(db, pr, codeowners_rules)

        await db.commit()
        await _check_cancel(ctx)

    _add_log(
        ctx, "info",
        f"PR timeline: {total_events} events synced",
        repo=repo.full_name,
    )


async def _set_codeowners_bypass(
    db: AsyncSession,
    pr: PullRequest,
    rules: list[tuple[str, list[str]]],
) -> None:
    """Run CODEOWNERS bypass detection for a single merged PR."""
    from app.services.codeowners import check_bypass

    # Changed files for this PR
    files_result = await db.execute(
        select(PRFile.filename).where(PRFile.pr_id == pr.id)
    )
    changed_paths = [row[0] for row in files_result.all() if row[0]]
    if not changed_paths:
        return

    # Approver tokens: reviewers who submitted an APPROVED review.
    approvers_result = await db.execute(
        select(PRReview.reviewer_github_username).where(
            PRReview.pr_id == pr.id,
            PRReview.state == "APPROVED",
            PRReview.reviewer_github_username.isnot(None),
        )
    )
    approver_tokens = [row[0] for row in approvers_result.all() if row[0]]

    pr.codeowners_bypass = check_bypass(
        changed_paths=changed_paths,
        rules=rules,
        approver_tokens=approver_tokens,
        merged=True,
    )


async def sync_repo(
    ctx: SyncContext,
    repo: Repository,
    since: datetime | None = None,
) -> tuple[int, int, list[str], int, int]:
    """Sync a single repo. Returns (prs_upserted, issues_upserted, warnings, prs_skipped, issues_skipped).

    Commits every BATCH_SIZE PRs for crash resilience within large repos.
    Updates granular progress fields for frontend visibility.
    Uses smart-skip: PRs/issues whose updated_at hasn't changed are skipped
    to avoid redundant API calls (detail, reviews, files, check runs).
    """
    db = ctx.db
    client = ctx.client
    sync_event = ctx.sync_event
    prs_upserted = 0
    prs_skipped = 0
    issues_upserted = 0
    issues_skipped = 0

    # Load classification rules once for this repo sync
    from app.services.work_categories import classify_work_item_with_rules, get_all_rules
    classification_rules = await get_all_rules(db)
    warnings: list[str] = []

    # Pre-load existing PR updated_at timestamps for smart-skip
    existing_prs_result = await db.execute(
        select(PullRequest.number, PullRequest.updated_at).where(
            PullRequest.repo_id == repo.id
        )
    )
    existing_pr_timestamps: dict[int, datetime | None] = {
        row[0]: row[1] for row in existing_prs_result.all()
    }

    # Pre-load existing issue updated_at timestamps for smart-skip
    existing_issues_result = await db.execute(
        select(Issue.number, Issue.updated_at).where(
            Issue.repo_id == repo.id
        )
    )
    existing_issue_timestamps: dict[int, datetime | None] = {
        row[0]: row[1] for row in existing_issues_result.all()
    }

    # --- PRs ---
    sync_event.current_step = "fetching_prs"
    await db.commit()
    _add_log(ctx, "info", "Fetching pull requests...", repo=repo.full_name)

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

    sync_event.current_step = "processing_prs"
    sync_event.current_repo_prs_total = len(pr_items)
    sync_event.current_repo_prs_done = 0
    await db.commit()
    _add_log(
        ctx, "info",
        f"Found {len(pr_items)} PRs to process",
        repo=repo.full_name,
    )

    for pr_data in pr_items:
        pr_number = pr_data["number"]
        processed_count = prs_upserted + prs_skipped

        # Smart-skip: if PR exists in DB with matching updated_at, skip
        # expensive per-PR API calls (detail, reviews, comments, files, checks)
        gh_updated = pr_data.get("updated_at")
        if gh_updated and pr_number in existing_pr_timestamps:
            gh_dt = datetime.fromisoformat(gh_updated.replace("Z", "+00:00"))
            db_dt = existing_pr_timestamps[pr_number]
            if db_dt and db_dt == gh_dt:
                prs_skipped += 1
                sync_event.current_repo_prs_done = processed_count
                if processed_count % PROGRESS_COMMIT_INTERVAL == 0:
                    await db.commit()
                continue

        pr = await upsert_pull_request(db, client, pr_data, repo)
        prs_upserted += 1
        processed_count = prs_upserted + prs_skipped

        # Classify work category (skip manual overrides)
        if pr.work_category_source != "manual":
            cat, src = classify_work_item_with_rules(pr.labels, pr.title, classification_rules)
            pr.work_category = cat
            pr.work_category_source = src if src else None

        # Fetch reviews for this PR
        reviews_data = await github_get_paginated(
            client, f"/repos/{repo.full_name}/pulls/{pr.number}/reviews", ctx=ctx
        )
        for review_data in reviews_data:
            await upsert_review(db, review_data, pr, client=client)

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
                    "Failed to fetch check runs for PR",
                    pr_number=pr.number, head_sha=pr.head_sha, error=str(e),
                    event_type="system.github_api",
                )

        # Update progress counter
        sync_event.current_repo_prs_done = processed_count

        # Batch commit every BATCH_SIZE PRs (data durability)
        if prs_upserted % BATCH_SIZE == 0:
            await db.commit()
            _add_log(
                ctx, "info",
                f"Batch committed {prs_upserted}/{len(pr_items)} PRs"
                + (f" ({prs_skipped} skipped)" if prs_skipped else ""),
                repo=repo.full_name,
            )
            # Check for cancellation at batch boundaries
            await _check_cancel(ctx)
        # Lighter progress commit every PROGRESS_COMMIT_INTERVAL PRs
        elif prs_upserted % PROGRESS_COMMIT_INTERVAL == 0:
            await db.commit()
            _add_log(
                ctx, "info",
                f"Processed {prs_upserted}/{len(pr_items)} PRs",
                repo=repo.full_name,
            )

    # --- PR timeline enrichment (Phase 09) ---
    # After PRs are upserted, fetch timeline events + derive aggregates + detect
    # CODEOWNERS bypass. Done at this step boundary (not per-batch) so one GraphQL
    # fault doesn't corrupt mid-sync state.
    if prs_upserted > 0:
        try:
            await _enrich_pr_timelines(ctx, repo, pr_items)
        except Exception as exc:  # best-effort: never break the rest of sync
            warn_msg = f"pr_timeline: {exc}"
            warnings.append(warn_msg)
            ctx.sync_logger.warning(
                "PR timeline enrichment failed",
                repo=repo.full_name,
                error=str(exc),
                event_type="system.sync",
            )

    # --- Issues ---
    if prs_skipped:
        _add_log(
            ctx, "info",
            f"PRs: {prs_upserted} synced, {prs_skipped} unchanged (skipped)",
            repo=repo.full_name,
        )

    sync_event.current_step = "fetching_issues"
    sync_event.current_repo_prs_done = prs_upserted + prs_skipped
    await db.commit()
    _add_log(ctx, "info", "Fetching issues...", repo=repo.full_name)

    issue_params: dict = {"state": "all", "sort": "updated", "direction": "desc"}
    if since:
        issue_params["since"] = since.isoformat()

    issue_items = await github_get_paginated(
        client, f"/repos/{repo.full_name}/issues", issue_params, ctx=ctx
    )

    # Filter out PRs from issue list
    pure_issues = [i for i in issue_items if "pull_request" not in i]
    sync_event.current_step = "processing_issues"
    sync_event.current_repo_issues_total = len(pure_issues)
    sync_event.current_repo_issues_done = 0
    await db.commit()
    _add_log(
        ctx, "info",
        f"Found {len(pure_issues)} issues to process",
        repo=repo.full_name,
    )

    for issue_data in pure_issues:
        issue_number = issue_data["number"]
        issue_processed = issues_upserted + issues_skipped

        # Smart-skip: if issue exists in DB with matching updated_at, skip
        gh_issue_updated = issue_data.get("updated_at")
        if gh_issue_updated and issue_number in existing_issue_timestamps:
            gh_dt = datetime.fromisoformat(gh_issue_updated.replace("Z", "+00:00"))
            db_dt = existing_issue_timestamps[issue_number]
            if db_dt and db_dt == gh_dt:
                issues_skipped += 1
                sync_event.current_repo_issues_done = issues_upserted + issues_skipped
                continue

        issue = await upsert_issue(db, issue_data, repo, client=client)
        issues_upserted += 1

        # Classify work category (skip manual overrides)
        if issue.work_category_source != "manual":
            cat, src = classify_work_item_with_rules(
                issue.labels, issue.title, classification_rules, issue_type=issue.issue_type,
            )
            issue.work_category = cat
            issue.work_category_source = src if src else None

        sync_event.current_repo_issues_done = issues_upserted + issues_skipped
        if issues_upserted % PROGRESS_COMMIT_INTERVAL == 0:
            await db.commit()

    if issues_skipped:
        _add_log(
            ctx, "info",
            f"Issues: {issues_upserted} synced, {issues_skipped} unchanged (skipped)",
            repo=repo.full_name,
        )

    # --- Issue Comments ---
    sync_event.current_step = "processing_issue_comments"
    await db.commit()
    _add_log(ctx, "info", "Fetching issue comments...", repo=repo.full_name)

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

    # --- File Tree ---
    sync_event.current_step = "syncing_file_tree"
    await db.commit()
    _add_log(ctx, "info", "Syncing file tree...", repo=repo.full_name)

    try:
        _tree_count, tree_truncated = await sync_repo_tree(client, db, repo, ctx=ctx)
        repo.tree_truncated = tree_truncated
    except Exception as e:
        warn_msg = f"repo_tree: {e}"
        warnings.append(warn_msg)
        ctx.sync_logger.warning("sync_repo_tree failed", repo=repo.full_name, error=str(e), event_type="system.sync")

    # --- Deployments ---
    sync_event.current_step = "fetching_deployments"
    await db.commit()
    _add_log(ctx, "info", "Fetching deployments...", repo=repo.full_name)

    try:
        await sync_deployments(client, db, repo, ctx=ctx)
    except Exception as e:
        warn_msg = f"deployments: {e}"
        warnings.append(warn_msg)
        ctx.sync_logger.warning("sync_deployments failed", repo=repo.full_name, error=str(e), event_type="system.sync")

    repo.last_synced_at = datetime.now(timezone.utc)
    return prs_upserted, issues_upserted, warnings, prs_skipped, issues_skipped


async def discover_org_repos(db: AsyncSession) -> list[Repository]:
    """Fetch all repos accessible to the GitHub App installation and upsert them.

    Uses the installation-scoped ``/installation/repositories`` endpoint, which
    works uniformly for both User and Org installations. Does NOT sync PRs /
    issues — only discovers repos so the UI can display them for selection.

    Name kept as ``discover_org_repos`` for API stability; in practice the scope
    is "whatever the installation can see".
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        repos_data = await fetch_installation_repositories(client)
        for repo_data in repos_data:
            await upsert_repo(db, repo_data)
            await db.flush()
        await db.commit()

    result = await db.execute(select(Repository).order_by(Repository.full_name))
    return list(result.scalars().all())


async def run_sync(
    sync_type: str = "full",
    repo_ids: list[int] | None = None,
    since_override: datetime | None = None,
    resumed_from_id: int | None = None,
    triggered_by: str | None = None,
    sync_scope: str | None = None,
    sync_event_id: int | None = None,
) -> SyncEvent:
    """Run a full or incremental sync across repos.

    Args:
        sync_type: "full" or "incremental"
        repo_ids: specific repo IDs to sync (None = all tracked)
        since_override: override per-repo last_synced_at with this date
        resumed_from_id: ID of the SyncEvent this resumes from
        triggered_by: "manual", "scheduled", or "auto_resume"
        sync_scope: descriptive label for what was synced
        sync_event_id: ID of a pre-created SyncEvent (skips creation if provided)
    """
    async with AsyncSessionLocal() as db:
        if sync_event_id:
            # Use pre-created SyncEvent (created by the API endpoint for instant UI feedback)
            sync_event = await db.get(SyncEvent, sync_event_id)
            if not sync_event or sync_event.status != "started":
                raise RuntimeError(f"SyncEvent {sync_event_id} not found or not in started state")
        else:
            # Concurrency guard: advisory lock prevents TOCTOU race between
            # the "is another sync running?" check and the INSERT.
            # Lock key 73796e63 = crc32('devpulse_sync') — arbitrary constant.
            SYNC_ADVISORY_LOCK_KEY = 1937337955  # noqa: N806
            try:
                await db.execute(sa.text("SELECT pg_advisory_lock(:key)"), {"key": SYNC_ADVISORY_LOCK_KEY})
            except Exception:
                # SQLite (tests) doesn't support advisory locks — fall through to app-level check
                pass

            active_result = await db.execute(
                select(SyncEvent).where(SyncEvent.status == "started").limit(1)
            )
            if active_result.scalar_one_or_none():
                # Release advisory lock before raising
                try:
                    await db.execute(sa.text("SELECT pg_advisory_unlock(:key)"), {"key": SYNC_ADVISORY_LOCK_KEY})
                except Exception:
                    pass
                logger.warning("Skipping sync — another sync is already in progress", event_type="system.sync")
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
                triggered_by=triggered_by,
                sync_scope=sync_scope,
            )
            db.add(sync_event)
            await db.commit()

            # Release advisory lock — the committed SyncEvent row now guards concurrency
            try:
                await db.execute(sa.text("SELECT pg_advisory_unlock(:key)"), {"key": SYNC_ADVISORY_LOCK_KEY})
            except Exception:
                pass

        sync_log = logger.bind(sync_id=sync_event.id)
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
                    # Fetch installation repos from GitHub and upsert all
                    repos_data = await fetch_installation_repositories(client, ctx=ctx)
                    for repo_data in repos_data:
                        repo = await upsert_repo(db, repo_data)
                        await db.flush()

                    # Commit repo upserts
                    await db.commit()

                    result = await db.execute(
                        select(Repository).where(Repository.is_tracked.is_(True))
                    )
                    tracked_repos = list(result.scalars().all())

                # Contributors are materialised on-demand by resolve_author
                # as we walk PRs / reviews / comments, so there's no separate
                # org-wide contributor fetch here.

                sync_event.total_repos = len(tracked_repos)
                await db.commit()
                _add_log(ctx, "info", f"{len(tracked_repos)} repos to sync")

                cancelled = False
                for repo in tracked_repos:
                    # Check for cancellation before each repo
                    await _check_cancel(ctx)

                    # Clear per-repo progress and set current repo
                    _clear_repo_progress(sync_event)
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
                        prs, issues, warnings, pr_skip, issue_skip = await sync_repo(ctx, repo, since=since)

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
                            "prs_skipped": pr_skip,
                            "issues_skipped": issue_skip,
                            "warnings": warnings,
                        })
                        await db.commit()

                        status_label = "partial" if warnings else "ok"
                        skip_info = ""
                        if pr_skip or issue_skip:
                            skip_info = f", {pr_skip + issue_skip} skipped"
                        _add_log(
                            ctx, "info",
                            f"Complete ({status_label}): {prs} PRs, {issues} issues{skip_info}",
                            repo=repo.full_name,
                        )
                        sync_log.info(
                            "Repo complete (%s): %d PRs, %d issues",
                            status_label, prs, issues,
                        )

                    except SyncCancelled:
                        sync_log.info("Sync cancelled by user")
                        cancelled = True
                        break

                    except Exception as e:
                        sync_log.error("Error syncing repo", repo=repo.full_name, error=str(e)[:200], exc_type=type(e).__name__, event_type="system.sync")

                        # Preserve in-memory state before rollback expires attributes
                        saved_logs = list(sync_event.log_summary or [])
                        saved_errors = list(sync_event.errors or [])
                        saved_repos_failed = list(sync_event.repos_failed or [])

                        await db.rollback()

                        # Refresh after rollback to reload all attributes
                        await db.refresh(sync_event)
                        sync_event.log_summary = saved_logs
                        sync_event.errors = saved_errors
                        sync_event.repos_failed = saved_repos_failed

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

                # Backfill author links for any newly created developers
                try:
                    backfill = await backfill_author_links(db)
                    total_backfilled = sum(backfill.values())
                    if total_backfilled:
                        _add_log(ctx, "info", f"Backfilled {total_backfilled} author links")
                    await db.commit()
                except Exception as e:
                    ctx.sync_logger.warning("backfill_author_links failed", error=str(e), event_type="system.sync")

                # Recompute collaboration scores
                try:
                    from app.services.enhanced_collaboration import (
                        recompute_collaboration_scores,
                    )

                    _add_log(ctx, "info", "Recomputing collaboration scores")
                    collab_since = sync_event.since_override or (
                        datetime.now(timezone.utc) - timedelta(days=90)
                    )
                    pair_count = await recompute_collaboration_scores(
                        db,
                        collab_since,
                        datetime.now(timezone.utc),
                    )
                    _add_log(
                        ctx, "info",
                        f"Collaboration scores recomputed: {pair_count} pairs",
                    )
                except Exception as e:
                    ctx.sync_logger.warning("Collaboration score recomputation failed", error=str(e), event_type="system.sync")

                # Evaluate notification alerts post-sync
                try:
                    from app.services.notifications import evaluate_all_alerts
                    await evaluate_all_alerts(db)
                except Exception as e:
                    ctx.sync_logger.warning("Post-sync notification evaluation failed", error=str(e), event_type="system.sync")

                # Determine final status
                if cancelled:
                    sync_event.status = "cancelled"
                    sync_event.is_resumable = True
                else:
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

                # Send Slack notification (non-blocking)
                try:
                    from app.services.slack import send_sync_notification
                    await send_sync_notification(db, sync_event)
                except Exception as e:
                    ctx.sync_logger.warning("Slack sync notification failed", error=str(e), event_type="system.slack")

        except SyncCancelled:
            sync_log.info("Sync cancelled at top level")
            sync_event.status = "cancelled"
            sync_event.is_resumable = True
            _add_log(ctx, "warn", "Sync cancelled by user")

        except Exception as e:
            sync_log.error("Sync failed", error=str(e)[:200], exc_type=type(e).__name__, event_type="system.sync")
            saved_logs = list(sync_event.log_summary or [])
            saved_errors = list(sync_event.errors or [])
            await db.rollback()
            await db.refresh(sync_event)
            sync_event.log_summary = saved_logs
            sync_event.errors = saved_errors
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
            _clear_repo_progress(sync_event)
            sync_event.cancel_requested = False
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
