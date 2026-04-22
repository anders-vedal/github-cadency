"""Linear integration service — GraphQL client, sync orchestration, PR linking, developer mapping."""

import asyncio
import re
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger
from app.models.models import (
    Developer,
    DeveloperIdentityMap,
    ExternalIssue,
    ExternalIssueAttachment,
    ExternalIssueComment,
    ExternalIssueHistoryEvent,
    ExternalIssueRelation,
    ExternalProject,
    ExternalProjectUpdate,
    ExternalSprint,
    IntegrationConfig,
    PRExternalIssueLink,
    PullRequest,
    SyncEvent,
)
from app.services.encryption import decrypt_token, encrypt_token

logger = get_logger(__name__)

LINEAR_API_URL = "https://api.linear.app/graphql"
LINEAR_ISSUE_KEY_PATTERN = re.compile(r"\b([A-Z]{2,10}-\d+)\b")

# PR URL patterns used by attachment linker (Phase 02)
GITHUB_PR_URL_RE = re.compile(r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)")
GITHUB_COMMIT_URL_RE = re.compile(r"https?://github\.com/([^/]+)/([^/]+)/commit/([0-9a-fA-F]+)")
GITHUB_ISSUE_URL_RE = re.compile(r"https?://github\.com/([^/]+)/([^/]+)/issues/(\d+)")


# --- Body preview sanitization (for comments, project updates, attachment titles) ---

_SANITIZE_PATTERNS = [
    (re.compile(r"[\w.-]+@[\w.-]+\.\w+"), "[EMAIL]"),
    (re.compile(r"(?i)(Bearer\s+|token[=:\s]+|api[_-]?key[=:\s]+)\S+"), r"\1[CREDENTIAL]"),
    (re.compile(r"(?i)password[\s:=]+\S+"), "password=[REDACTED]"),
    (re.compile(r"(?i)secret[\s:=]+\S+"), "secret=[REDACTED]"),
    (re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE), "[UUID]"),
    (re.compile(r"\b[0-9a-f]{40}\b", re.IGNORECASE), "[SHA]"),
]


def sanitize_preview(text: str | None, max_len: int = 280) -> str | None:
    """Strip emails/tokens/secrets/UUIDs/SHAs from text and truncate to max_len."""
    if not text:
        return None
    out = text
    for pattern, replacement in _SANITIZE_PATTERNS:
        out = pattern.sub(replacement, out)
    # Collapse whitespace for a clean preview
    out = re.sub(r"\s+", " ", out).strip()
    if len(out) > max_len:
        out = out[: max_len - 1] + "…"
    return out


def _derive_sla_status(
    started_at: datetime | None,
    breaches_at: datetime | None,
    high_risk_at: datetime | None,
    medium_risk_at: datetime | None,
    *,
    completed_at: datetime | None = None,
    cancelled_at: datetime | None = None,
) -> str | None:
    """Derive SLA status from Linear's SLA timestamps.

    Linear exposes SLA timestamps on Issue but not the status enum directly.
    Map: completed before breach → Completed; cancelled → Failed; past breach → Breached;
    past high-risk threshold → HighRisk; past medium-risk threshold → MediumRisk;
    SLA active but well within bounds → LowRisk; no SLA → None.
    """
    if started_at is None:
        return None
    if cancelled_at is not None:
        return "Failed"
    if completed_at is not None:
        if breaches_at is not None and completed_at > breaches_at:
            return "Breached"
        return "Completed"
    now = datetime.now(timezone.utc)
    if breaches_at is not None and now >= breaches_at:
        return "Breached"
    if high_risk_at is not None and now >= high_risk_at:
        return "HighRisk"
    if medium_risk_at is not None and now >= medium_risk_at:
        return "MediumRisk"
    return "LowRisk"


def normalize_attachment_source(source_type: str | None, url: str) -> str:
    """Classify a Linear attachment into our canonical normalized_source_type values."""
    url_lower = (url or "").lower()
    if source_type == "github" or "github.com" in url_lower:
        if GITHUB_PR_URL_RE.search(url):
            return "github_pr"
        if GITHUB_COMMIT_URL_RE.search(url):
            return "github_commit"
        if GITHUB_ISSUE_URL_RE.search(url):
            return "github_issue"
        return "github"
    if source_type in ("slack", "figma", "zendesk", "notion"):
        return source_type
    return source_type or "other"


# --- Linear GraphQL Client ---


class LinearClient:
    """Read-only GraphQL client for the Linear API."""

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=LINEAR_API_URL,
            headers={
                "Authorization": api_key,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def query(self, query: str, variables: dict | None = None) -> dict:
        """Execute a GraphQL query against Linear. Returns the 'data' payload.

        Handles HTTP 429 and HTTP 400 RATELIMITED rate-limit responses with a single retry.
        Proactively sleeps when nearing Linear's 3M complexity budget (<10% remaining).
        """
        payload: dict = {"query": query}
        if variables:
            payload["variables"] = variables
        resp = await self._client.post("", json=payload)

        # Rate limit detection: handle HTTP 429 OR HTTP 400 with RATELIMITED error code
        rate_limited = False
        if resp.status_code == 429:
            rate_limited = True
        elif resp.status_code == 400:
            try:
                err_body = resp.json()
                errs = (err_body or {}).get("errors") or []
                if any((e.get("extensions") or {}).get("code") == "RATELIMITED" for e in errs):
                    rate_limited = True
            except Exception:
                pass

        if rate_limited:
            retry_after = int(resp.headers.get("Retry-After", "60"))
            reset_at = int(resp.headers.get("X-RateLimit-Requests-Reset",
                                            resp.headers.get("X-RateLimit-Reset", "0")))
            now = int(time.time())
            wait_from_reset = max(0, reset_at - now) if reset_at else 0
            wait_seconds = max(retry_after, wait_from_reset, 1)
            logger.warning(
                "Linear rate limited — retrying",
                status=resp.status_code,
                retry_after=retry_after,
                wait_seconds=wait_seconds,
                event_type="system.linear_api",
            )
            await asyncio.sleep(min(wait_seconds, 120))
            resp = await self._client.post("", json=payload)

        if resp.is_error:
            try:
                err_body = resp.json()
            except Exception:
                err_body = None
            errors = (err_body or {}).get("errors") or []
            if errors:
                msg = errors[0].get("message", str(errors))
                raise LinearAPIError(
                    f"Linear API {resp.status_code}: {msg}", errors=errors
                )
            resp.raise_for_status()

        # Proactive slowdown based on complexity budget (primary) or legacy remaining (fallback)
        complexity_remaining_s = resp.headers.get("X-RateLimit-Complexity-Remaining")
        complexity_limit_s = resp.headers.get("X-RateLimit-Complexity-Limit", "3000000")
        if complexity_remaining_s is not None:
            try:
                complexity_remaining = int(complexity_remaining_s)
                complexity_limit = max(1, int(complexity_limit_s))
                if complexity_remaining / complexity_limit < 0.10:
                    reset_at = int(resp.headers.get("X-RateLimit-Complexity-Reset", "0"))
                    wait_seconds = max(0, reset_at - int(time.time())) + 1
                    logger.warning(
                        "Linear complexity budget approaching",
                        complexity_remaining=complexity_remaining,
                        complexity_limit=complexity_limit,
                        wait_seconds=wait_seconds,
                        event_type="system.linear_api",
                    )
                    await asyncio.sleep(min(wait_seconds, 60))
            except (ValueError, TypeError):
                pass
        else:
            remaining = int(resp.headers.get("X-RateLimit-Remaining", "100"))
            if remaining < 10:
                reset_at = int(resp.headers.get("X-RateLimit-Reset", "0"))
                wait_seconds = max(0, reset_at - int(time.time())) + 1
                logger.warning(
                    "Linear rate limit approaching",
                    remaining=remaining,
                    wait_seconds=wait_seconds,
                    event_type="system.linear_api",
                )
                await asyncio.sleep(min(wait_seconds, 60))

        body = resp.json()
        if "errors" in body:
            errors = body["errors"]
            msg = errors[0].get("message", str(errors)) if errors else "Unknown GraphQL error"
            raise LinearAPIError(msg, errors=errors)
        return body.get("data", {})

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


class LinearAPIError(Exception):
    def __init__(self, message: str, errors: list | None = None):
        super().__init__(message)
        self.errors = errors or []


# --- Key extraction ---


def extract_linear_keys(text: str) -> list[str]:
    """Extract Linear issue identifiers (e.g., ENG-123) from text. Returns unique keys."""
    if not text:
        return []
    return list(dict.fromkeys(LINEAR_ISSUE_KEY_PATTERN.findall(text)))


# --- Integration config helpers ---


async def get_integration(db: AsyncSession, integration_id: int) -> IntegrationConfig | None:
    return await db.get(IntegrationConfig, integration_id)


async def get_active_linear_integration(db: AsyncSession) -> IntegrationConfig | None:
    result = await db.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.type == "linear",
            IntegrationConfig.status == "active",
        )
    )
    return result.scalar_one_or_none()


async def create_integration(
    db: AsyncSession, type: str, display_name: str | None, api_key: str | None
) -> IntegrationConfig:
    config = IntegrationConfig(type=type, display_name=display_name or type.capitalize())
    if api_key:
        config.api_key = encrypt_token(api_key)
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


async def update_integration(
    db: AsyncSession, config: IntegrationConfig, updates: dict
) -> IntegrationConfig:
    for field, value in updates.items():
        if field == "api_key":
            if value:
                value = encrypt_token(value)
            else:
                value = None  # Clear the key rather than storing empty string
        setattr(config, field, value)
    config.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(config)
    return config


async def delete_integration(db: AsyncSession, config: IntegrationConfig) -> None:
    await db.delete(config)
    await db.commit()


async def test_linear_connection(db: AsyncSession, config: IntegrationConfig) -> dict:
    """Test Linear API connection. Returns {success, message, workspace_name}."""
    if not config.api_key:
        return {"success": False, "message": "No API key configured", "workspace_name": None}
    try:
        api_key = decrypt_token(config.api_key)
    except ValueError:
        return {"success": False, "message": "Failed to decrypt API key — encryption key may have changed", "workspace_name": None}

    try:
        async with LinearClient(api_key) as client:
            data = await client.query("{ viewer { id name email } organization { id name urlKey } }")
            org = data.get("organization", {})
            workspace_name = org.get("name")
            workspace_id = org.get("id")

            if workspace_id and workspace_id != config.workspace_id:
                config.workspace_id = workspace_id
                config.workspace_name = workspace_name
                await db.commit()

            return {
                "success": True,
                "message": f"Connected to workspace: {workspace_name}",
                "workspace_name": workspace_name,
            }
    except LinearAPIError as e:
        return {"success": False, "message": f"Linear API error: {e}", "workspace_name": None}
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return {"success": False, "message": "Invalid API key — authentication failed", "workspace_name": None}
        return {"success": False, "message": f"HTTP error: {e.response.status_code}", "workspace_name": None}
    except Exception as e:
        return {"success": False, "message": f"Connection failed: {e}", "workspace_name": None}


async def get_primary_issue_source(db: AsyncSession) -> str:
    """Returns 'github' or 'linear'. Checks integration_config for is_primary_issue_source=True."""
    result = await db.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.is_primary_issue_source.is_(True),
            IntegrationConfig.status == "active",
        )
    )
    config = result.scalar_one_or_none()
    return config.type if config else "github"


async def set_primary_issue_source(db: AsyncSession, integration_id: int) -> IntegrationConfig:
    """Set the given integration as primary issue source, clearing any others."""
    await db.execute(
        IntegrationConfig.__table__.update().values(is_primary_issue_source=False)
    )
    config = await db.get(IntegrationConfig, integration_id)
    if not config:
        raise ValueError(f"Integration {integration_id} not found")
    config.is_primary_issue_source = True
    await db.commit()
    await db.refresh(config)
    return config


# --- Linear users (for mapping UI) ---


async def list_linear_users(db: AsyncSession, config: IntegrationConfig) -> dict:
    """Fetch Linear workspace users and annotate with existing developer mappings."""
    if not config.api_key:
        return {"users": [], "total": 0, "mapped_count": 0, "unmapped_count": 0}

    try:
        api_key = decrypt_token(config.api_key)
    except ValueError:
        logger.warning("Failed to decrypt Linear API key", error_category="user_config", event_type="system.sync")
        return {"users": [], "total": 0, "mapped_count": 0, "unmapped_count": 0}

    async with LinearClient(api_key) as client:
        data = await client.query("""
            {
                users {
                    nodes {
                        id
                        name
                        displayName
                        email
                        active
                    }
                }
            }
        """)

    users_data = data.get("users", {}).get("nodes", [])

    # Load existing mappings
    result = await db.execute(
        select(DeveloperIdentityMap).where(DeveloperIdentityMap.integration_type == "linear")
    )
    mappings = {m.external_user_id: m for m in result.scalars().all()}

    # Load developers for mapped names
    dev_ids = [m.developer_id for m in mappings.values()]
    devs_by_id = {}
    if dev_ids:
        result = await db.execute(select(Developer).where(Developer.id.in_(dev_ids)))
        devs_by_id = {d.id: d for d in result.scalars().all()}

    users = []
    mapped_count = 0
    for u in users_data:
        mapping = mappings.get(u["id"])
        dev = devs_by_id.get(mapping.developer_id) if mapping else None
        if mapping:
            mapped_count += 1
        users.append({
            "id": u["id"],
            "name": u.get("name", ""),
            "display_name": u.get("displayName"),
            "email": u.get("email"),
            "active": u.get("active", True),
            "mapped_developer_id": mapping.developer_id if mapping else None,
            "mapped_developer_name": dev.display_name if dev else None,
        })

    return {
        "users": users,
        "total": len(users),
        "mapped_count": mapped_count,
        "unmapped_count": len(users) - mapped_count,
    }


async def map_user(
    db: AsyncSession, config: IntegrationConfig, external_user_id: str, developer_id: int
) -> DeveloperIdentityMap:
    """Manually map a Linear user to a DevPulse developer."""
    result = await db.execute(
        select(DeveloperIdentityMap).where(
            DeveloperIdentityMap.developer_id == developer_id,
            DeveloperIdentityMap.integration_type == "linear",
        )
    )
    mapping = result.scalar_one_or_none()
    if mapping:
        mapping.external_user_id = external_user_id
        mapping.mapped_by = "admin"
    else:
        mapping = DeveloperIdentityMap(
            developer_id=developer_id,
            integration_type="linear",
            external_user_id=external_user_id,
            mapped_by="admin",
        )
        db.add(mapping)
    await db.commit()
    await db.refresh(mapping)
    return mapping


# --- Sync orchestration ---


MAX_LOG_ENTRIES = 500


class LinearSyncCancelled(Exception):
    """Raised when a Linear sync is cancelled by user request."""
    pass


def _add_log(sync_event: SyncEvent, level: str, msg: str) -> None:
    """Append a structured log entry to sync_event.log_summary."""
    entry = {
        "ts": datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "level": level.lower(),
        "msg": msg[:200],
    }
    logs = list(sync_event.log_summary or [])
    if len(logs) >= MAX_LOG_ENTRIES:
        # Drop oldest info entries first
        for i, e in enumerate(logs):
            if e.get("level") == "info":
                logs.pop(i)
                break
        else:
            logs.pop(0)
    logs.append(entry)
    sync_event.log_summary = logs


async def _check_linear_cancel(db: AsyncSession, sync_event: SyncEvent) -> None:
    """Check if cancellation was requested. Raises LinearSyncCancelled if so."""
    result = await db.execute(
        select(SyncEvent.cancel_requested).where(SyncEvent.id == sync_event.id)
    )
    if result.scalar_one_or_none():
        _add_log(sync_event, "warn", "Sync cancelled by user")
        sync_event.status = "cancelled"
        sync_event.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise LinearSyncCancelled("Linear sync cancelled by user")


async def run_linear_sync(
    db: AsyncSession,
    integration_id: int,
    sync_event_id: int | None = None,
    triggered_by: str = "manual",
) -> SyncEvent:
    """Full Linear sync orchestration. Creates a SyncEvent if sync_event_id not provided."""
    config = await db.get(IntegrationConfig, integration_id)
    if not config or config.status != "active" or not config.api_key:
        raise ValueError("Linear integration not active or missing API key")

    # Concurrency guard: skip if another Linear sync is already running
    active = (await db.execute(
        select(SyncEvent.id).where(
            SyncEvent.sync_type == "linear",
            SyncEvent.status == "started",
        ).limit(1)
    )).scalar_one_or_none()
    if active:
        logger.info(
            "Skipping Linear sync — another sync already in progress",
            active_sync_id=active,
            event_type="system.sync",
        )
        raise ValueError("Linear sync already in progress")

    api_key = decrypt_token(config.api_key)

    # Create or load sync event
    if sync_event_id:
        sync_event = await db.get(SyncEvent, sync_event_id)
    else:
        sync_event = SyncEvent(
            sync_type="linear",
            status="started",
            started_at=datetime.now(timezone.utc),
            triggered_by=triggered_by,
            sync_scope="Linear workspace sync",
        )
        db.add(sync_event)
        await db.commit()
        await db.refresh(sync_event)

    logger.info(
        "Starting Linear sync",
        sync_id=sync_event.id,
        integration_id=integration_id,
        event_type="system.sync",
    )
    _add_log(sync_event, "info", "Starting Linear workspace sync")

    counts = {
        "projects": 0,
        "sprints": 0,
        "issues": 0,
        "comments_synced": 0,
        "history_events_synced": 0,
        "attachments_synced": 0,
        "relations_synced": 0,
        "project_updates_synced": 0,
        "issue_expansions_triggered": 0,
        "pr_links": 0,
        "mapped": 0,
    }

    try:
        async with LinearClient(api_key) as client:
            # 1. Sync projects
            await _check_linear_cancel(db, sync_event)
            sync_event.current_step = "syncing_projects"
            _add_log(sync_event, "info", "Syncing Linear projects...")
            await db.commit()
            counts["projects"] = await sync_linear_projects(client, db, integration_id)
            _add_log(sync_event, "info", f"Synced {counts['projects']} projects")

            # 1b. Sync project updates (health narrative)
            await _check_linear_cancel(db, sync_event)
            sync_event.current_step = "syncing_project_updates"
            _add_log(sync_event, "info", "Syncing Linear project updates...")
            await db.commit()
            counts["project_updates_synced"] = await sync_linear_project_updates(
                client, db, integration_id
            )
            _add_log(sync_event, "info", f"Synced {counts['project_updates_synced']} project updates")

            # 2. Sync cycles (sprints)
            await _check_linear_cancel(db, sync_event)
            sync_event.current_step = "syncing_cycles"
            _add_log(sync_event, "info", "Syncing Linear cycles (sprints)...")
            await db.commit()
            counts["sprints"] = await sync_linear_cycles(client, db, integration_id)
            _add_log(sync_event, "info", f"Synced {counts['sprints']} sprints")

            # 3. Sync issues (since last sync or all) — now includes comments, history,
            #    attachments, and relations per issue
            await _check_linear_cancel(db, sync_event)
            since = config.last_synced_at
            sync_event.current_step = "syncing_issues"
            mode = f"incremental since {since.strftime('%Y-%m-%d %H:%M')}" if since else "full scan"
            _add_log(sync_event, "info", f"Syncing issues with depth ({mode})...")
            await db.commit()
            issue_counts = await sync_linear_issues(
                client, db, integration_id, since=since, sync_event=sync_event
            )
            counts["issues"] = issue_counts.get("issues", 0)
            counts["comments_synced"] = issue_counts.get("comments", 0)
            counts["history_events_synced"] = issue_counts.get("history", 0)
            counts["attachments_synced"] = issue_counts.get("attachments", 0)
            counts["relations_synced"] = issue_counts.get("relations", 0)
            counts["issue_expansions_triggered"] = issue_counts.get("expansions_triggered", 0)
            _add_log(
                sync_event,
                "info",
                (
                    f"Synced {counts['issues']} issues "
                    f"({counts['comments_synced']} comments, "
                    f"{counts['history_events_synced']} history events, "
                    f"{counts['attachments_synced']} attachments, "
                    f"{counts['relations_synced']} relations)"
                ),
            )

            # 4. Link PRs to external issues (attachment-first via Phase 02 linker)
            await _check_linear_cancel(db, sync_event)
            sync_event.current_step = "linking_prs"
            _add_log(sync_event, "info", "Linking PRs to external issues...")
            await db.commit()
            counts["pr_links"] = await link_prs_to_external_issues(db, integration_id, since=since)
            _add_log(sync_event, "info", f"Created {counts['pr_links']} new PR-issue links")

            # 5. Fetch Linear users for accurate identity mapping, then auto-map
            await _check_linear_cancel(db, sync_event)
            sync_event.current_step = "mapping_developers"
            _add_log(sync_event, "info", "Auto-mapping developers...")
            await db.commit()
            linear_users = await _fetch_linear_users(client)
            mapped, unmapped = await auto_map_developers(db, integration_id, linear_users=linear_users)
            counts["mapped"] = mapped
            _add_log(sync_event, "info", f"Mapped {mapped} developers ({unmapped} unmapped)")

        # Update integration
        config.last_synced_at = datetime.now(timezone.utc)
        config.error_message = None

        # Update sync event
        sync_event.status = "completed"
        sync_event.completed_at = datetime.now(timezone.utc)
        sync_event.repos_synced = counts["issues"]  # reuse field for issue count
        sync_event.current_step = None
        started = sync_event.started_at
        if started:
            sync_event.duration_s = int((sync_event.completed_at - started).total_seconds())
        _add_log(sync_event, "info", f"Sync completed: {counts}")

        await db.commit()

        logger.info(
            "Linear sync completed",
            sync_id=sync_event.id,
            counts=counts,
            event_type="system.sync",
        )

        # Trigger planning notification evaluation after successful sync
        try:
            from app.services.notifications import evaluate_all_alerts
            await evaluate_all_alerts(db)
        except Exception as eval_err:
            logger.warning(
                "Post-sync notification evaluation failed",
                error=str(eval_err),
                event_type="system.notifications",
            )

    except LinearSyncCancelled:
        logger.info("Linear sync cancelled", sync_id=sync_event.id, event_type="system.sync")
        # Status already set by _check_linear_cancel

    except Exception as e:
        sync_event.status = "failed"
        sync_event.completed_at = datetime.now(timezone.utc)
        sync_event.current_step = None
        config.error_message = str(e)[:500]
        _add_log(sync_event, "error", f"Sync failed: {str(e)[:180]}")
        await db.commit()

        from app.main import _classifier

        classified = _classifier.classify(e)
        log_level = logger.error if classified.category.value == "app_bug" else logger.warning
        log_level(
            "Linear sync failed",
            sync_id=sync_event.id,
            error=str(e)[:200],
            exc_type=type(e).__name__,
            error_category=classified.category.value,
            event_type="system.sync",
        )
        raise

    return sync_event


# --- Individual sync functions ---


PROJECTS_QUERY = """
query($cursor: String) {
    projects(first: 50, after: $cursor, filter: { state: { nin: ["canceled"] } }) {
        pageInfo { hasNextPage endCursor }
        nodes {
            id
            name
            slugId
            state
            health
            startDate
            targetDate
            progress
            url
            lead { id email }
        }
    }
}
"""


async def sync_linear_projects(client: LinearClient, db: AsyncSession, integration_id: int) -> int:
    """Sync all non-cancelled projects from Linear. Returns count synced."""
    count = 0
    cursor = None

    while True:
        data = await client.query(PROJECTS_QUERY, {"cursor": cursor})
        projects = data.get("projects", {})
        nodes = projects.get("nodes", [])

        for p in nodes:
            result = await db.execute(
                select(ExternalProject).where(ExternalProject.external_id == p["id"])
            )
            project = result.scalar_one_or_none()
            if not project:
                project = ExternalProject(
                    integration_id=integration_id,
                    external_id=p["id"],
                    name=p.get("name", ""),
                )
                db.add(project)
            else:
                project.name = p.get("name", "")
            project.key = p.get("slugId")
            project.status = _map_project_state(p.get("state"))
            project.health = _map_project_health(p.get("health"))
            project.start_date = _parse_date(p.get("startDate"))
            project.target_date = _parse_date(p.get("targetDate"))
            project.progress_pct = p.get("progress")
            project.url = p.get("url")

            # Map lead if possible
            lead = p.get("lead")
            if lead and lead.get("email"):
                project.lead_id = await _resolve_developer_by_email(db, lead["email"])

            count += 1

        await db.commit()

        page_info = projects.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")

    logger.info("Synced Linear projects", count=count, event_type="system.sync")
    return count


PROJECT_UPDATES_QUERY = """
query($cursor: String) {
    projectUpdates(first: 50, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
            id
            project { id }
            user { id email }
            body
            diffMarkdown
            health
            createdAt
            updatedAt
            editedAt
            isStale
            reactionData
        }
    }
}
"""


async def sync_linear_project_updates(
    client: LinearClient, db: AsyncSession, integration_id: int
) -> int:
    """Sync Linear ProjectUpdate entries (authoritative project-health narrative).

    Body is not persisted in full — we keep length + 280-char sanitized preview + health enum.
    """
    count = 0
    cursor = None

    while True:
        data = await client.query(PROJECT_UPDATES_QUERY, {"cursor": cursor})
        updates = data.get("projectUpdates", {}) or {}
        nodes = updates.get("nodes") or []

        for u in nodes:
            ext_id = u.get("id")
            if not ext_id:
                continue
            project_ref = u.get("project") or {}
            project_ext_id = project_ref.get("id")
            if not project_ext_id:
                continue
            project_internal_id = await _resolve_external_project(db, project_ext_id)
            if not project_internal_id:
                # Project not synced yet; skip until the next cycle
                continue

            result = await db.execute(
                select(ExternalProjectUpdate).where(ExternalProjectUpdate.external_id == ext_id)
            )
            row = result.scalar_one_or_none()
            created_at = _parse_datetime(u.get("createdAt")) or datetime.now(timezone.utc)
            if not row:
                row = ExternalProjectUpdate(
                    project_id=project_internal_id,
                    external_id=ext_id,
                    created_at=created_at,
                )
                db.add(row)

            user = u.get("user") or {}
            author_email = user.get("email")
            row.author_email = author_email
            if author_email:
                row.author_developer_id = await _resolve_developer_by_email(db, author_email)
            body = u.get("body") or ""
            diff = u.get("diffMarkdown") or ""
            row.body_length = len(body)
            row.body_preview = sanitize_preview(body, 280)
            row.diff_length = len(diff) if diff else None
            row.health = u.get("health")
            row.updated_at = _parse_datetime(u.get("updatedAt"))
            row.edited_at = _parse_datetime(u.get("editedAt"))
            row.is_stale = bool(u.get("isStale"))
            row.reaction_data = u.get("reactionData")

            count += 1

        await db.commit()

        page_info = updates.get("pageInfo", {}) or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")

    logger.info("Synced Linear project updates", count=count, event_type="system.sync")
    return count


CYCLES_QUERY = """
query($cursor: String) {
    cycles(first: 50, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
            id
            name
            number
            startsAt
            endsAt
            completedAt
            progress
            scopeHistory
            completedScopeHistory
            team { id key name }
            issues { nodes { id } }
            uncompletedIssuesUponClose { nodes { id } }
        }
    }
}
"""


async def sync_linear_cycles(client: LinearClient, db: AsyncSession, integration_id: int) -> int:
    """Sync all cycles from Linear. Returns count synced."""
    count = 0
    cursor = None

    while True:
        data = await client.query(CYCLES_QUERY, {"cursor": cursor})
        cycles = data.get("cycles", {})
        nodes = cycles.get("nodes", [])

        for c in nodes:
            result = await db.execute(
                select(ExternalSprint).where(ExternalSprint.external_id == c["id"])
            )
            sprint = result.scalar_one_or_none()
            if not sprint:
                sprint = ExternalSprint(
                    integration_id=integration_id,
                    external_id=c["id"],
                    state="active",
                )
                db.add(sprint)

            sprint.name = c.get("name")
            sprint.number = c.get("number")

            team = c.get("team") or {}
            sprint.team_key = team.get("key")
            sprint.team_name = team.get("name")

            sprint.start_date = _parse_date(c.get("startsAt"))
            sprint.end_date = _parse_date(c.get("endsAt"))

            # Determine state
            if c.get("completedAt"):
                sprint.state = "closed"
            elif sprint.start_date and sprint.end_date:
                now = datetime.now(timezone.utc).date()
                if now < sprint.start_date:
                    sprint.state = "future"
                else:
                    sprint.state = "active"
            else:
                sprint.state = "active"

            # Scope metrics from history arrays
            scope_history = c.get("scopeHistory") or []
            completed_history = c.get("completedScopeHistory") or []

            total_issues = len((c.get("issues") or {}).get("nodes", []))
            uncompleted = len((c.get("uncompletedIssuesUponClose") or {}).get("nodes", []))

            if scope_history:
                # Points-based scope from Linear history arrays
                sprint.planned_scope = scope_history[0]
                initial_scope = scope_history[0]
                final_scope = scope_history[-1]
                sprint.added_scope = max(0, final_scope - initial_scope) if initial_scope is not None else None
                sprint.completed_scope = completed_history[-1] if completed_history else None
                sprint.scope_unit = "points"
            elif c.get("completedAt"):
                # Fallback to issue counts for closed cycles without scope history
                sprint.planned_scope = total_issues
                sprint.completed_scope = total_issues - uncompleted
                sprint.added_scope = None
                sprint.scope_unit = "issues"
            else:
                sprint.planned_scope = None
                sprint.completed_scope = None
                sprint.added_scope = None
                sprint.scope_unit = None
            sprint.cancelled_scope = uncompleted if c.get("completedAt") else None

            count += 1

        await db.commit()

        page_info = cycles.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")

    logger.info("Synced Linear cycles", count=count, event_type="system.sync")
    return count


_ISSUES_FIELDS = """
        pageInfo { hasNextPage endCursor }
        nodes {
            id
            identifier
            title
            description
            state { name type }
            priority
            priorityLabel
            estimate
            labels { nodes { id name } }
            assignee { id email displayName }
            creator { id email displayName }
            project { id }
            cycle { id }
            parent { id }
            createdAt
            startedAt
            completedAt
            canceledAt
            updatedAt
            url
            slaStartedAt
            slaBreachesAt
            slaHighRiskAt
            slaMediumRiskAt
            slaType
            triagedAt
            subscribers { nodes { id } }
            reactionData
            comments(first: 50) {
                pageInfo { hasNextPage endCursor }
                nodes {
                    id
                    parent { id }
                    user { id email }
                    externalUser { id }
                    botActor { type subType name }
                    createdAt
                    updatedAt
                    editedAt
                    body
                    reactionData
                }
            }
            history(first: 50) {
                pageInfo { hasNextPage endCursor }
                nodes {
                    id
                    createdAt
                    actor { id email }
                    botActor { type subType name }
                    fromState { id name type }
                    toState { id name type }
                    fromAssignee { id email }
                    toAssignee { id email }
                    fromEstimate
                    toEstimate
                    fromPriority
                    toPriority
                    fromCycle { id }
                    toCycle { id }
                    fromProject { id }
                    toProject { id }
                    fromParent { id }
                    toParent { id }
                    addedLabelIds
                    removedLabelIds
                    archived
                    autoArchived
                    autoClosed
                }
            }
            attachments(first: 50) {
                nodes {
                    id
                    url
                    sourceType
                    title
                    metadata
                    createdAt
                    updatedAt
                    creator { id email }
                }
            }
            relations(first: 50) {
                nodes {
                    id
                    type
                    relatedIssue { id }
                }
            }
        }
"""

ISSUES_QUERY = """
query($cursor: String, $updatedAfter: DateTime) {
    issues(
        first: 50,
        after: $cursor,
        filter: { updatedAt: { gte: $updatedAfter } }
    ) {""" + _ISSUES_FIELDS + """    }
}
"""

ISSUES_QUERY_ALL = """
query($cursor: String) {
    issues(first: 50, after: $cursor) {""" + _ISSUES_FIELDS + """    }
}
"""


# Per-issue inner-page pagination for comments/history when the initial batched
# fetch returned hasNextPage=true. Selections must stay in sync with the comments
# and history fragments inside `_ISSUES_FIELDS`.
ISSUE_COMMENTS_PAGE_QUERY = """
query($issueId: String!, $cursor: String) {
    issue(id: $issueId) {
        comments(first: 100, after: $cursor) {
            pageInfo { hasNextPage endCursor }
            nodes {
                id
                parent { id }
                user { id email }
                externalUser { id }
                botActor { type subType name }
                createdAt
                updatedAt
                editedAt
                body
                reactionData
            }
        }
    }
}
"""

ISSUE_HISTORY_PAGE_QUERY = """
query($issueId: String!, $cursor: String) {
    issue(id: $issueId) {
        history(first: 100, after: $cursor) {
            pageInfo { hasNextPage endCursor }
            nodes {
                id
                createdAt
                actor { id email }
                botActor { type subType name }
                fromState { id name type }
                toState { id name type }
                fromAssignee { id email }
                toAssignee { id email }
                fromEstimate
                toEstimate
                fromPriority
                toPriority
                fromCycle { id }
                toCycle { id }
                fromProject { id }
                toProject { id }
                fromParent { id }
                toParent { id }
                addedLabelIds
                removedLabelIds
                archived
                autoArchived
                autoClosed
            }
        }
    }
}
"""

# Hard cap so a pathological issue can't spin forever; 50 pages * 100 items = 5000
# comments or history events per issue. Real-world issues are orders of magnitude below.
_MAX_INNER_PAGES = 50


async def _fetch_all_comment_pages(
    client: LinearClient,
    issue_external_id: str,
    initial_end_cursor: str | None,
) -> list[dict]:
    """Walk the comments connection for one issue from ``initial_end_cursor`` to exhaustion."""
    collected: list[dict] = []
    cursor = initial_end_cursor
    for _ in range(_MAX_INNER_PAGES):
        if not cursor:
            break
        data = await client.query(
            ISSUE_COMMENTS_PAGE_QUERY,
            {"issueId": issue_external_id, "cursor": cursor},
        )
        issue_data = data.get("issue") or {}
        conn = issue_data.get("comments") or {}
        nodes = conn.get("nodes") or []
        collected.extend(nodes)
        page_info = conn.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
    return collected


async def _fetch_all_history_pages(
    client: LinearClient,
    issue_external_id: str,
    initial_end_cursor: str | None,
) -> list[dict]:
    """Walk the history connection for one issue from ``initial_end_cursor`` to exhaustion."""
    collected: list[dict] = []
    cursor = initial_end_cursor
    for _ in range(_MAX_INNER_PAGES):
        if not cursor:
            break
        data = await client.query(
            ISSUE_HISTORY_PAGE_QUERY,
            {"issueId": issue_external_id, "cursor": cursor},
        )
        issue_data = data.get("issue") or {}
        conn = issue_data.get("history") or {}
        nodes = conn.get("nodes") or []
        collected.extend(nodes)
        page_info = conn.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
    return collected


def _classify_external_issue(issue: ExternalIssue, rules: list) -> tuple[str, str]:
    """Classify an external issue using the same work category rules as GitHub issues."""
    from app.services.work_categories import classify_work_item_with_rules

    labels = issue.labels if isinstance(issue.labels, list) else []
    return classify_work_item_with_rules(labels, issue.title, rules, issue_type=issue.issue_type)


# --- Sync helpers for per-issue expansions (comments / history / attachments / relations) ---


async def _persist_issue_comments(
    db: AsyncSession,
    issue: ExternalIssue,
    comment_nodes: list[dict],
    *,
    email_cache: dict[str, int | None] | None = None,
) -> tuple[int, list[str]]:
    """Upsert comment rows for an issue. Returns (count, external_ids_processed).

    Replies are resolved after all comments are inserted so parent IDs can resolve.
    """
    if not comment_nodes:
        return 0, []

    # Preload existing comments keyed by external_id to map parent refs
    ext_ids = [c["id"] for c in comment_nodes if c.get("id")]
    existing_rows = await db.execute(
        select(ExternalIssueComment).where(ExternalIssueComment.external_id.in_(ext_ids))
    )
    existing_by_ext_id: dict[str, ExternalIssueComment] = {
        row.external_id: row for row in existing_rows.scalars().all()
    }

    count = 0
    # First pass: upsert without parent (we'll link parents in pass 2)
    pending_parents: list[tuple[str, str]] = []  # [(child_ext_id, parent_ext_id)]
    for c in comment_nodes:
        ext_id = c.get("id")
        if not ext_id:
            continue
        row = existing_by_ext_id.get(ext_id)
        bot_actor_raw = c.get("botActor")  # dict if bot, None if human
        user = c.get("user") or {}
        ext_user = c.get("externalUser") or {}
        author_email = user.get("email")
        body = c.get("body") or ""
        created_at = _parse_datetime(c.get("createdAt")) or datetime.now(timezone.utc)

        author_dev_id = None
        if author_email:
            author_dev_id = await _resolve_developer_by_email(db, author_email, email_cache)

        if not row:
            row = ExternalIssueComment(
                issue_id=issue.id,
                external_id=ext_id,
                created_at=created_at,
            )
            db.add(row)
            existing_by_ext_id[ext_id] = row

        row.author_developer_id = author_dev_id
        row.author_email = author_email
        row.external_user_id = ext_user.get("id") if ext_user else user.get("id")
        row.updated_at = _parse_datetime(c.get("updatedAt"))
        row.edited_at = _parse_datetime(c.get("editedAt"))
        row.body_length = len(body)
        row.body_preview = sanitize_preview(body, 280)
        row.reaction_data = c.get("reactionData")
        # Linear sets botActor to a populated object for bot/integration comments,
        # null for human comments. Treat any non-null botActor as system-generated.
        row.is_system_generated = bot_actor_raw is not None
        row.bot_actor_type = (bot_actor_raw or {}).get("type")

        parent = c.get("parent") or {}
        if parent and parent.get("id"):
            pending_parents.append((ext_id, parent["id"]))

        count += 1

    # Flush so new rows have IDs for parent linking
    if count:
        await db.flush()

    # Second pass: resolve parent refs
    for child_ext_id, parent_ext_id in pending_parents:
        child = existing_by_ext_id.get(child_ext_id)
        parent = existing_by_ext_id.get(parent_ext_id)
        if child and parent and child.id != parent.id:
            child.parent_comment_id = parent.id

    return count, ext_ids


async def _persist_issue_history(
    db: AsyncSession,
    issue: ExternalIssue,
    history_nodes: list[dict],
    *,
    email_cache: dict[str, int | None] | None = None,
) -> int:
    """Upsert IssueHistory events for an issue. Returns count persisted."""
    if not history_nodes:
        return 0

    ext_ids = [h["id"] for h in history_nodes if h.get("id")]
    existing_rows = await db.execute(
        select(ExternalIssueHistoryEvent).where(ExternalIssueHistoryEvent.external_id.in_(ext_ids))
    )
    existing_by_ext_id: dict[str, ExternalIssueHistoryEvent] = {
        row.external_id: row for row in existing_rows.scalars().all()
    }

    count = 0
    for h in history_nodes:
        ext_id = h.get("id")
        if not ext_id:
            continue
        row = existing_by_ext_id.get(ext_id)
        changed_at = _parse_datetime(h.get("createdAt")) or datetime.now(timezone.utc)
        actor = h.get("actor") or {}
        actor_email = actor.get("email")
        bot_actor_raw = h.get("botActor")  # dict if bot, None if human / system
        bot_type = (bot_actor_raw or {}).get("type")

        actor_dev_id = None
        if actor_email:
            actor_dev_id = await _resolve_developer_by_email(db, actor_email, email_cache)

        if not row:
            row = ExternalIssueHistoryEvent(
                issue_id=issue.id,
                external_id=ext_id,
                changed_at=changed_at,
            )
            db.add(row)
            existing_by_ext_id[ext_id] = row

        row.actor_developer_id = actor_dev_id
        row.actor_email = actor_email
        row.bot_actor_type = bot_type

        from_state = h.get("fromState") or {}
        to_state = h.get("toState") or {}
        row.from_state = from_state.get("name")
        row.to_state = to_state.get("name")
        row.from_state_category = _map_status_type(from_state.get("type"))
        row.to_state_category = _map_status_type(to_state.get("type"))

        from_assignee = h.get("fromAssignee") or {}
        to_assignee = h.get("toAssignee") or {}
        if from_assignee.get("email"):
            row.from_assignee_id = await _resolve_developer_by_email(
                db, from_assignee["email"], email_cache
            )
        if to_assignee.get("email"):
            row.to_assignee_id = await _resolve_developer_by_email(
                db, to_assignee["email"], email_cache
            )

        row.from_estimate = h.get("fromEstimate")
        row.to_estimate = h.get("toEstimate")
        # Linear schema types priority as Float; cast to int for our column.
        from_pri = h.get("fromPriority")
        to_pri = h.get("toPriority")
        row.from_priority = int(from_pri) if from_pri is not None else None
        row.to_priority = int(to_pri) if to_pri is not None else None

        from_cycle = h.get("fromCycle") or {}
        to_cycle = h.get("toCycle") or {}
        if from_cycle.get("id"):
            row.from_cycle_id = await _resolve_external_sprint(db, from_cycle["id"])
        if to_cycle.get("id"):
            row.to_cycle_id = await _resolve_external_sprint(db, to_cycle["id"])

        from_project = h.get("fromProject") or {}
        to_project = h.get("toProject") or {}
        if from_project.get("id"):
            row.from_project_id = await _resolve_external_project(db, from_project["id"])
        if to_project.get("id"):
            row.to_project_id = await _resolve_external_project(db, to_project["id"])

        from_parent = h.get("fromParent") or {}
        to_parent = h.get("toParent") or {}
        if from_parent.get("id"):
            row.from_parent_id = await _resolve_external_issue(db, from_parent["id"])
        if to_parent.get("id"):
            row.to_parent_id = await _resolve_external_issue(db, to_parent["id"])

        row.added_label_ids = h.get("addedLabelIds")
        row.removed_label_ids = h.get("removedLabelIds")
        row.archived = bool(h.get("archived"))
        row.auto_archived = bool(h.get("autoArchived"))
        row.auto_closed = bool(h.get("autoClosed"))

        count += 1

    return count


async def _persist_issue_attachments(
    db: AsyncSession,
    issue: ExternalIssue,
    attachment_nodes: list[dict],
    *,
    email_cache: dict[str, int | None] | None = None,
) -> int:
    """Upsert attachment rows for an issue. Returns count persisted."""
    if not attachment_nodes:
        return 0

    ext_ids = [a["id"] for a in attachment_nodes if a.get("id")]
    existing_rows = await db.execute(
        select(ExternalIssueAttachment).where(ExternalIssueAttachment.external_id.in_(ext_ids))
    )
    existing_by_ext_id: dict[str, ExternalIssueAttachment] = {
        row.external_id: row for row in existing_rows.scalars().all()
    }

    count = 0
    for a in attachment_nodes:
        ext_id = a.get("id")
        if not ext_id:
            continue
        url = a.get("url") or ""
        row = existing_by_ext_id.get(ext_id)
        created_at = _parse_datetime(a.get("createdAt")) or datetime.now(timezone.utc)
        creator = a.get("creator") or {}
        creator_email = creator.get("email")
        actor_dev_id = None
        if creator_email:
            actor_dev_id = await _resolve_developer_by_email(db, creator_email, email_cache)

        if not row:
            row = ExternalIssueAttachment(
                issue_id=issue.id,
                external_id=ext_id,
                url=url,
                created_at=created_at,
            )
            db.add(row)
            existing_by_ext_id[ext_id] = row

        row.url = url
        row.source_type = a.get("sourceType")
        row.normalized_source_type = normalize_attachment_source(a.get("sourceType"), url)
        title = a.get("title")
        row.title = sanitize_preview(title, 500) if title else None
        row.attachment_metadata = a.get("metadata")
        row.updated_at = _parse_datetime(a.get("updatedAt"))
        row.actor_developer_id = actor_dev_id
        row.is_system_generated = creator_email is None  # integration-attached = no creator

        count += 1

    return count


async def _persist_issue_relations(
    db: AsyncSession,
    issue: ExternalIssue,
    relation_nodes: list[dict],
) -> int:
    """Upsert IssueRelation rows bidirectionally. Returns count of rows persisted.

    Linear emits a single relation node but we store both directions so queries on
    either side don't require a UNION.
    """
    if not relation_nodes:
        return 0

    count = 0
    for r in relation_nodes:
        ext_id = r.get("id")
        rel_type = r.get("type")
        related = r.get("relatedIssue") or {}
        related_ext_id = related.get("id")
        if not (ext_id and rel_type and related_ext_id):
            continue

        related_internal_id = await _resolve_external_issue(db, related_ext_id)
        if not related_internal_id:
            continue  # the related issue isn't in our DB yet; skip until next sync

        created_at = datetime.now(timezone.utc)
        # Forward relation: issue -> related with rel_type
        await _upsert_relation_row(db, ext_id, rel_type, issue.id, related_internal_id, created_at)
        count += 1
        # Inverse: if blocks, store blocked_by reverse. If related/duplicate, mirror type.
        inverse_type = _inverse_relation_type(rel_type)
        if inverse_type:
            await _upsert_relation_row(
                db, ext_id, inverse_type, related_internal_id, issue.id, created_at
            )
            count += 1

    return count


def _inverse_relation_type(rel_type: str) -> str | None:
    if rel_type == "blocks":
        return "blocked_by"
    if rel_type == "blocked_by":
        return "blocks"
    if rel_type in ("related", "duplicate"):
        return rel_type
    return None


async def _upsert_relation_row(
    db: AsyncSession,
    external_id: str,
    relation_type: str,
    issue_id: int,
    related_issue_id: int,
    created_at: datetime,
) -> None:
    result = await db.execute(
        select(ExternalIssueRelation).where(
            ExternalIssueRelation.external_id == external_id,
            ExternalIssueRelation.relation_type == relation_type,
            ExternalIssueRelation.issue_id == issue_id,
        )
    )
    row = result.scalar_one_or_none()
    if row:
        row.related_issue_id = related_issue_id
    else:
        db.add(
            ExternalIssueRelation(
                issue_id=issue_id,
                related_issue_id=related_issue_id,
                external_id=external_id,
                relation_type=relation_type,
                created_at=created_at,
            )
        )


async def sync_linear_issues(
    client: LinearClient,
    db: AsyncSession,
    integration_id: int,
    since: datetime | None = None,
    sync_event: SyncEvent | None = None,
) -> dict:
    """Sync issues from Linear updated since the given timestamp.

    Returns a dict of counters: ``{"issues": N, "comments": N, "history": N,
    "attachments": N, "relations": N, "expansions_triggered": N}``.
    """
    # Load classification rules once for the entire sync
    from app.services.work_categories import get_all_rules
    classification_rules = await get_all_rules(db)

    # Preload email→developer_id to avoid thousands of per-row SELECTs during
    # comment/history persistence. One SELECT up front beats 6000+ lookups on a
    # full 588-issue sync.
    email_cache = await _build_email_cache(db)

    counts = {
        "issues": 0,
        "comments": 0,
        "history": 0,
        "attachments": 0,
        "relations": 0,
        "expansions_triggered": 0,
    }
    count = 0
    cursor = None
    updated_after = since.isoformat() if since else None

    while True:
        variables: dict = {"cursor": cursor}
        if updated_after:
            variables["updatedAfter"] = updated_after
            query = ISSUES_QUERY
        else:
            query = ISSUES_QUERY_ALL

        data = await client.query(query, variables)
        issues = data.get("issues", {})
        nodes = issues.get("nodes", [])

        for i in nodes:
            result = await db.execute(
                select(ExternalIssue).where(ExternalIssue.external_id == i["id"])
            )
            issue = result.scalar_one_or_none()
            if not issue:
                issue = ExternalIssue(
                    integration_id=integration_id,
                    external_id=i["id"],
                    identifier=i.get("identifier", ""),
                    title=i.get("title", "")[:500],
                )
                db.add(issue)
            else:
                issue.identifier = i.get("identifier", "")
                issue.title = i.get("title", "")[:500]
            desc = i.get("description") or ""
            issue.description_length = len(desc)

            # State mapping
            state = i.get("state") or {}
            issue.status = state.get("name")
            issue.status_category = _map_status_type(state.get("type"))

            # Issue type from labels
            issue.issue_type = _detect_issue_type(i)

            issue.priority = i.get("priority", 0)
            issue.priority_label = i.get("priorityLabel")
            issue.estimate = i.get("estimate")
            issue.labels = [l["name"] for l in (i.get("labels") or {}).get("nodes", [])]

            # Assignee
            assignee = i.get("assignee")
            if assignee:
                issue.assignee_email = assignee.get("email")
                issue.assignee_developer_id = await _resolve_developer_by_email(
                    db, assignee.get("email"), email_cache
                )

            # Creator
            creator = i.get("creator")
            if creator:
                issue.creator_email = creator.get("email")
                issue.creator_developer_id = await _resolve_developer_by_email(
                    db, creator.get("email"), email_cache
                )

            # Foreign keys to other synced entities
            project_data = i.get("project")
            if project_data:
                issue.project_id = await _resolve_external_project(db, project_data["id"])
            else:
                issue.project_id = None

            cycle_data = i.get("cycle")
            if cycle_data:
                issue.sprint_id = await _resolve_external_sprint(db, cycle_data["id"])
            else:
                issue.sprint_id = None

            parent_data = i.get("parent")
            if parent_data:
                issue.parent_issue_id = await _resolve_external_issue(db, parent_data["id"])

            # Timestamps
            issue.created_at = _parse_datetime(i.get("createdAt")) or datetime.now(timezone.utc)
            issue.started_at = _parse_datetime(i.get("startedAt"))
            issue.completed_at = _parse_datetime(i.get("completedAt"))
            issue.cancelled_at = _parse_datetime(i.get("canceledAt"))
            issue.updated_at = _parse_datetime(i.get("updatedAt")) or datetime.now(timezone.utc)
            issue.url = i.get("url")

            # SLA fields (Phase 01) — slaStatus is not a field on Issue, derive from timestamps
            issue.sla_started_at = _parse_datetime(i.get("slaStartedAt"))
            issue.sla_breaches_at = _parse_datetime(i.get("slaBreachesAt"))
            issue.sla_high_risk_at = _parse_datetime(i.get("slaHighRiskAt"))
            issue.sla_medium_risk_at = _parse_datetime(i.get("slaMediumRiskAt"))
            issue.sla_type = i.get("slaType")
            issue.sla_status = _derive_sla_status(
                issue.sla_started_at,
                issue.sla_breaches_at,
                issue.sla_high_risk_at,
                issue.sla_medium_risk_at,
                completed_at=issue.completed_at,
                cancelled_at=issue.cancelled_at,
            )

            # Triage (Phase 01)
            issue.triaged_at = _parse_datetime(i.get("triagedAt"))

            # Subscriber count (cheap bus-factor signal)
            subs = (i.get("subscribers") or {}).get("nodes") or []
            issue.subscribers_count = len(subs)

            # Reactions
            issue.reaction_data = i.get("reactionData")

            # Compute durations
            if issue.status_category != "triage" and issue.created_at and issue.started_at:
                issue.triage_duration_s = int(
                    (issue.started_at - issue.created_at).total_seconds()
                )
            if issue.started_at and issue.completed_at:
                issue.cycle_time_s = int(
                    (issue.completed_at - issue.started_at).total_seconds()
                )

            # Work categorization (same pipeline as GitHub issues)
            if issue.work_category_source != "manual":
                cat, source = _classify_external_issue(issue, classification_rules)
                issue.work_category = cat
                issue.work_category_source = source

            # Flush to ensure issue.id is available for child rows
            if not issue.id:
                await db.flush()

            # Persist per-issue expansions (comments, history, attachments, relations).
            # When the batched issues query hit the inner page limit (50 items), walk
            # the remaining pages so issues with long histories aren't silently truncated.
            comments_conn = i.get("comments") or {}
            comment_nodes = list(comments_conn.get("nodes") or [])
            comments_page_info = comments_conn.get("pageInfo") or {}
            if comments_page_info.get("hasNextPage"):
                counts["expansions_triggered"] += 1
                try:
                    extra = await _fetch_all_comment_pages(
                        client, i["id"], comments_page_info.get("endCursor")
                    )
                    comment_nodes.extend(extra)
                except LinearAPIError as exc:
                    logger.warning(
                        "Failed to paginate Linear comments for issue",
                        issue_external_id=i.get("id"),
                        error=str(exc),
                        event_type="system.sync",
                    )
            if comment_nodes:
                c_count, _ = await _persist_issue_comments(
                    db, issue, comment_nodes, email_cache=email_cache
                )
                counts["comments"] += c_count

            history_conn = i.get("history") or {}
            history_nodes = list(history_conn.get("nodes") or [])
            history_page_info = history_conn.get("pageInfo") or {}
            if history_page_info.get("hasNextPage"):
                counts["expansions_triggered"] += 1
                try:
                    extra = await _fetch_all_history_pages(
                        client, i["id"], history_page_info.get("endCursor")
                    )
                    history_nodes.extend(extra)
                except LinearAPIError as exc:
                    logger.warning(
                        "Failed to paginate Linear history for issue",
                        issue_external_id=i.get("id"),
                        error=str(exc),
                        event_type="system.sync",
                    )
            if history_nodes:
                counts["history"] += await _persist_issue_history(
                    db, issue, history_nodes, email_cache=email_cache
                )

            attachment_nodes = (i.get("attachments") or {}).get("nodes") or []
            if attachment_nodes:
                counts["attachments"] += await _persist_issue_attachments(
                    db, issue, attachment_nodes, email_cache=email_cache
                )

            relation_nodes = (i.get("relations") or {}).get("nodes") or []
            if relation_nodes:
                counts["relations"] += await _persist_issue_relations(db, issue, relation_nodes)

            count += 1
            counts["issues"] = count

            if count % 50 == 0:
                if sync_event:
                    sync_event.current_repo_issues_done = count
                    await _check_linear_cancel(db, sync_event)
                await db.commit()

        if sync_event:
            sync_event.current_repo_issues_done = count
        await db.commit()

        page_info = issues.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")

    logger.info(
        "Synced Linear issues",
        count=count,
        comments=counts["comments"],
        history=counts["history"],
        attachments=counts["attachments"],
        relations=counts["relations"],
        event_type="system.sync",
    )
    return counts


# --- PR ↔ External Issue linking ---


# Link confidence tier per source (Phase 02)
LINK_SOURCE_CONFIDENCE = {
    "linear_attachment": "high",
    "branch": "medium",
    "title": "medium",
    "body": "low",
    "commit_message": "low",
}

# Confidence ranking for upgrade logic (higher tier wins)
_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


from app.models.models import Repository  # noqa: E402 — imported here to avoid circular at top


async def _load_pr_id_by_github_pr_url(
    db: AsyncSession, url: str
) -> int | None:
    """Parse a GitHub PR URL and resolve to an internal PullRequest.id."""
    m = GITHUB_PR_URL_RE.search(url)
    if not m:
        return None
    owner, name, number = m.group(1), m.group(2), int(m.group(3))
    full_name = f"{owner}/{name}"
    result = await db.execute(
        select(PullRequest.id)
        .join(Repository, PullRequest.repo_id == Repository.id)
        .where(
            func.lower(Repository.full_name) == full_name.lower(),
            PullRequest.number == number,
        )
    )
    return result.scalar_one_or_none()


async def _upsert_pr_issue_link(
    db: AsyncSession,
    pr_id: int,
    issue_id: int,
    link_source: str,
    existing_by_pair: dict[tuple[int, int], PRExternalIssueLink],
) -> bool:
    """Upsert a PR-issue link. Returns True if newly created, False if existing.

    Existing links are upgraded if the new source has a higher confidence tier.
    """
    confidence = LINK_SOURCE_CONFIDENCE.get(link_source, "low")
    key = (pr_id, issue_id)
    existing = existing_by_pair.get(key)
    if existing:
        # Upgrade confidence if new source is stronger
        # Default to -1 (below "low") so unknown / null stored confidence still upgrades cleanly.
        if _CONFIDENCE_RANK[confidence] > _CONFIDENCE_RANK.get(existing.link_confidence or "", -1):
            existing.link_source = link_source
            existing.link_confidence = confidence
        return False
    link = PRExternalIssueLink(
        pull_request_id=pr_id,
        external_issue_id=issue_id,
        link_source=link_source,
        link_confidence=confidence,
    )
    db.add(link)
    existing_by_pair[key] = link
    return True


async def link_prs_to_external_issues(
    db: AsyncSession, integration_id: int, since: datetime | None = None
) -> int:
    """Run the 4-pass PR↔issue linker.

    Pass 1 (high): Linear GitHub attachments (`external_issue_attachments` with
    ``normalized_source_type == 'github_pr'``) → resolve URL → PR.id.
    Pass 2 (medium): regex on PR head_branch.
    Pass 3 (medium): regex on PR title.
    Pass 4 (low): regex on PR body.

    Existing links are upgraded to higher confidence when a stronger signal is found.
    A PR may link to multiple issues (each signal creates a row independently).

    Returns count of *newly created* links (upgrades don't count).

    When ``since`` is provided, regex passes 2-4 only scan PRs updated since then
    (incremental). The attachment pass always scans all attachments because Linear
    attachments update independently of PR updated_at.
    """
    count = 0

    # Load known issue identifier → internal id (for regex passes)
    result = await db.execute(
        select(ExternalIssue.id, ExternalIssue.identifier).where(
            ExternalIssue.integration_id == integration_id
        )
    )
    issue_id_by_identifier = {row.identifier: row.id for row in result.all()}

    # Load existing links into a map for upserts
    result = await db.execute(select(PRExternalIssueLink))
    existing_by_pair: dict[tuple[int, int], PRExternalIssueLink] = {
        (r.pull_request_id, r.external_issue_id): r for r in result.scalars().all()
    }

    # --- Pass 1: attachment-first (high confidence) ---
    # Scan ExternalIssueAttachment rows with normalized_source_type == 'github_pr'
    # that belong to issues of this integration.
    att_result = await db.execute(
        select(
            ExternalIssueAttachment.id,
            ExternalIssueAttachment.url,
            ExternalIssueAttachment.issue_id,
        )
        .join(ExternalIssue, ExternalIssueAttachment.issue_id == ExternalIssue.id)
        .where(
            ExternalIssue.integration_id == integration_id,
            ExternalIssueAttachment.normalized_source_type == "github_pr",
        )
    )
    for _att_id, url, issue_id in att_result.all():
        pr_id = await _load_pr_id_by_github_pr_url(db, url)
        if not pr_id:
            continue
        if await _upsert_pr_issue_link(
            db, pr_id, issue_id, "linear_attachment", existing_by_pair
        ):
            count += 1

    # --- Passes 2-4: regex-based on PR text fields ---
    if issue_id_by_identifier:
        batch_size = 500
        offset = 0
        while True:
            pr_query = (
                select(
                    PullRequest.id,
                    PullRequest.title,
                    PullRequest.head_branch,
                    PullRequest.body,
                )
                .order_by(PullRequest.id)
                .limit(batch_size)
                .offset(offset)
            )
            if since is not None:
                pr_query = pr_query.where(PullRequest.updated_at >= since)
            rows = (await db.execute(pr_query)).all()
            if not rows:
                break

            for pr_id, title, branch, body in rows:
                # Passes in priority order: branch > title > body
                for source_name, text in (
                    ("branch", branch or ""),
                    ("title", title or ""),
                    ("body", body or ""),
                ):
                    keys = extract_linear_keys(text)
                    for key in keys:
                        issue_id = issue_id_by_identifier.get(key)
                        if not issue_id:
                            continue
                        if await _upsert_pr_issue_link(
                            db, pr_id, issue_id, source_name, existing_by_pair
                        ):
                            count += 1

            offset += batch_size

    if count or existing_by_pair:
        await db.commit()

    logger.info("Linked PRs to external issues", count=count, event_type="system.sync")
    return count


async def run_linear_relink(
    db: AsyncSession, integration_id: int
) -> SyncEvent:
    """Convenience wrapper — rerun the full 4-pass linker as a tracked SyncEvent.

    Used by the admin "Rerun linker" button. Idempotent; upgrades existing links
    to the best available confidence tier.
    """
    config = await db.get(IntegrationConfig, integration_id)
    if not config or config.type != "linear":
        raise ValueError(f"Linear integration {integration_id} not found")

    sync_event = SyncEvent(
        sync_type="linear",
        status="started",
        started_at=datetime.now(timezone.utc),
        triggered_by="manual",
        sync_scope="Linear PR relink",
        current_step="relinking",
    )
    db.add(sync_event)
    await db.commit()
    await db.refresh(sync_event)

    try:
        new_links = await link_prs_to_external_issues(db, integration_id)
        sync_event.status = "completed"
        sync_event.completed_at = datetime.now(timezone.utc)
        started = sync_event.started_at
        if started:
            # Normalize to tz-aware for SQLite (tests) and Postgres parity
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            sync_event.duration_s = int(
                (sync_event.completed_at - started).total_seconds()
            )
        _add_log(sync_event, "info", f"Relinked PRs — {new_links} new link rows")
        await db.commit()
    except Exception as e:
        sync_event.status = "failed"
        sync_event.completed_at = datetime.now(timezone.utc)
        _add_log(sync_event, "error", f"Relink failed: {str(e)[:180]}")
        await db.commit()
        raise

    return sync_event


# --- Developer auto-mapping ---


async def _fetch_linear_users(client: LinearClient) -> list[dict]:
    """Fetch all workspace users from Linear. Returns list of {id, email, displayName}."""
    data = await client.query("""
        {
            users {
                nodes {
                    id
                    name
                    displayName
                    email
                    active
                }
            }
        }
    """)
    return data.get("users", {}).get("nodes", [])


async def auto_map_developers(
    db: AsyncSession,
    integration_id: int,
    linear_users: list[dict] | None = None,
) -> tuple[int, int]:
    """Auto-map Linear users to DevPulse developers by email match.

    When ``linear_users`` is provided, uses the list to resolve the correct
    ``external_user_id`` for each mapping (fixing the empty-string bug).

    Returns (mapped_count, unmapped_count).
    """
    # Build email → Linear user ID lookup from the users list
    email_to_linear_id: dict[str, str] = {}
    if linear_users:
        for u in linear_users:
            u_email = u.get("email")
            if u_email:
                email_to_linear_id[u_email.lower()] = u["id"]

    # Forward-fix: backfill existing mappings with empty external_user_id
    if email_to_linear_id:
        result = await db.execute(
            select(DeveloperIdentityMap).where(
                DeveloperIdentityMap.integration_type == "linear",
                DeveloperIdentityMap.external_user_id == "",
                DeveloperIdentityMap.external_email.isnot(None),
            )
        )
        for stale_mapping in result.scalars().all():
            linear_id = email_to_linear_id.get((stale_mapping.external_email or "").lower())
            if linear_id:
                stale_mapping.external_user_id = linear_id

    # Get unique assignee emails from external issues
    result = await db.execute(
        select(ExternalIssue.assignee_email)
        .where(
            ExternalIssue.integration_id == integration_id,
            ExternalIssue.assignee_email.isnot(None),
        )
        .distinct()
    )
    external_emails = {row[0] for row in result.all()}

    # Get already mapped developer IDs for linear
    result = await db.execute(
        select(DeveloperIdentityMap.external_email).where(
            DeveloperIdentityMap.integration_type == "linear",
            DeveloperIdentityMap.external_email.isnot(None),
        )
    )
    already_mapped_emails = {row[0] for row in result.all()}

    unmapped_emails = external_emails - already_mapped_emails
    mapped = 0
    unmapped = 0

    for email in unmapped_emails:
        result = await db.execute(
            select(Developer).where(
                func.lower(Developer.email) == email.lower(),
                Developer.is_active.is_(True),
            )
        )
        dev = result.scalar_one_or_none()
        if dev:
            # Check if this developer already has a linear mapping
            result2 = await db.execute(
                select(DeveloperIdentityMap).where(
                    DeveloperIdentityMap.developer_id == dev.id,
                    DeveloperIdentityMap.integration_type == "linear",
                )
            )
            if not result2.scalar_one_or_none():
                linear_id = email_to_linear_id.get(email.lower(), "")
                mapping = DeveloperIdentityMap(
                    developer_id=dev.id,
                    integration_type="linear",
                    external_user_id=linear_id,
                    external_email=email,
                    mapped_by="auto",
                )
                db.add(mapping)
                mapped += 1
        else:
            unmapped += 1

    if mapped:
        await db.commit()

    logger.info(
        "Auto-mapped developers",
        mapped=mapped,
        unmapped=unmapped,
        event_type="system.sync",
    )
    return mapped, unmapped


# --- Helper functions ---


def _map_project_state(state: str | None) -> str | None:
    """Map Linear project state to normalized status."""
    mapping = {
        "planned": "planned",
        "started": "started",
        "paused": "paused",
        "completed": "completed",
        "canceled": "cancelled",
        "cancelled": "cancelled",
    }
    return mapping.get(state, state)


def _map_project_health(health: str | None) -> str | None:
    """Map Linear project health to normalized health."""
    mapping = {
        "onTrack": "on_track",
        "atRisk": "at_risk",
        "offTrack": "off_track",
    }
    return mapping.get(health, health)


def _map_status_type(status_type: str | None) -> str | None:
    """Map Linear workflow state type to normalized status category."""
    mapping = {
        "triage": "triage",
        "backlog": "backlog",
        "unstarted": "todo",
        "started": "in_progress",
        "completed": "done",
        "canceled": "cancelled",
        "cancelled": "cancelled",
    }
    return mapping.get(status_type, status_type)


def _detect_issue_type(issue_data: dict) -> str | None:
    """Detect issue type from Linear issue data (labels or other signals)."""
    labels = [l["name"].lower() for l in (issue_data.get("labels") or {}).get("nodes", [])]
    if "bug" in labels:
        return "bug"
    if "feature" in labels:
        return "feature"
    if "improvement" in labels:
        return "improvement"
    parent = issue_data.get("parent")
    if parent:
        return "sub_issue"
    return "issue"


def _parse_date(value: str | None):
    """Parse ISO date string to date object."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        return None


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse ISO datetime string to datetime object."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


async def _resolve_developer_by_email(
    db: AsyncSession,
    email: str | None,
    cache: dict[str, int | None] | None = None,
) -> int | None:
    """Look up a developer by email, return their ID or None.

    Accepts an optional ``cache`` dict (keyed by lowercased email) to amortize
    the per-call SELECT over a full sync run. On cache miss we populate the
    dict so subsequent lookups for the same email stay in-memory. Nothing is
    ever evicted — the cache's lifetime is one sync run, not a singleton.
    """
    if not email:
        return None
    key = email.lower()
    if cache is not None and key in cache:
        return cache[key]
    result = await db.execute(
        select(Developer.id).where(
            func.lower(Developer.email) == key,
            Developer.is_active.is_(True),
        )
    )
    row = result.first()
    dev_id = row[0] if row else None
    if cache is not None:
        cache[key] = dev_id
    return dev_id


async def _build_email_cache(db: AsyncSession) -> dict[str, int | None]:
    """Preload active developers into an email→id dict for a sync run.

    Caller passes the returned dict to persist helpers to skip per-row
    SELECTs (Phase 01 observed ~6000 SELECTs for a 588-issue full sync).
    """
    result = await db.execute(
        select(Developer.email, Developer.id).where(Developer.is_active.is_(True))
    )
    cache: dict[str, int | None] = {}
    for email, dev_id in result.all():
        if email:
            cache[email.lower()] = dev_id
    return cache


async def _resolve_external_project(db: AsyncSession, external_id: str) -> int | None:
    """Look up an external project by its Linear ID, return internal ID or None."""
    result = await db.execute(
        select(ExternalProject.id).where(ExternalProject.external_id == external_id)
    )
    row = result.first()
    return row[0] if row else None


async def _resolve_external_sprint(db: AsyncSession, external_id: str) -> int | None:
    """Look up an external sprint by its Linear ID, return internal ID or None."""
    result = await db.execute(
        select(ExternalSprint.id).where(ExternalSprint.external_id == external_id)
    )
    row = result.first()
    return row[0] if row else None


async def _resolve_external_issue(db: AsyncSession, external_id: str) -> int | None:
    """Look up an external issue by its Linear ID, return internal ID or None."""
    result = await db.execute(
        select(ExternalIssue.id).where(ExternalIssue.external_id == external_id)
    )
    row = result.first()
    return row[0] if row else None
