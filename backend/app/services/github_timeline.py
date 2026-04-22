"""GitHub PR timeline enrichment.

Fetches the union of timeline events for a batch of PRs via a single GraphQL
call and persists them into ``pr_timeline_events``. Derives the aggregate
columns on ``pull_requests`` (force-push bounce count, draft flips, merge
queue wait, etc.) from the stored events.

This module is intentionally *standalone* for Phase 09 — it is not yet wired
into ``sync_repo``. A follow-up phase will integrate batching into the main
sync loop; for now callers can drive it via the public entry points below.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger
from app.models.models import PRTimelineEvent, PullRequest
from app.services.github_sync import resolve_author

logger = get_logger(__name__)

GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"

# Each typename maps to the short `event_type` we store on `pr_timeline_events`.
# Keep this list in lockstep with the timelineItems itemTypes argument in
# TIMELINE_QUERY below — adding a type requires updating both.
TYPENAME_TO_EVENT_TYPE: dict[str, str] = {
    "ReviewRequestedEvent": "review_requested",
    "ReviewRequestRemovedEvent": "review_request_removed",
    "ReviewDismissedEvent": "review_dismissed",
    "AssignedEvent": "assigned",
    "UnassignedEvent": "unassigned",
    "LabeledEvent": "labeled",
    "UnlabeledEvent": "unlabeled",
    "HeadRefForcePushedEvent": "head_ref_force_pushed",
    "ReadyForReviewEvent": "ready_for_review",
    "ConvertToDraftEvent": "converted_to_draft",
    "RenamedTitleEvent": "renamed_title",
    "CrossReferencedEvent": "cross_referenced",
    "AddedToMergeQueueEvent": "added_to_merge_queue",
    "RemovedFromMergeQueueEvent": "removed_from_merge_queue",
    "AutoMergeEnabledEvent": "auto_merge_enabled",
    "AutoMergeDisabledEvent": "auto_merge_disabled",
    "MarkedAsDuplicateEvent": "marked_as_duplicate",
}


# GraphQL query for a single PR's timeline. ``fetch_pr_timeline_batch`` composes
# aliased copies of this block, one per PR, into a single request.
TIMELINE_QUERY = """
query TimelineQuery($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      timelineItems(first: 100, itemTypes: [
        REVIEW_REQUESTED_EVENT,
        REVIEW_REQUEST_REMOVED_EVENT,
        REVIEW_DISMISSED_EVENT,
        ASSIGNED_EVENT,
        UNASSIGNED_EVENT,
        LABELED_EVENT,
        UNLABELED_EVENT,
        HEAD_REF_FORCE_PUSHED_EVENT,
        READY_FOR_REVIEW_EVENT,
        CONVERT_TO_DRAFT_EVENT,
        RENAMED_TITLE_EVENT,
        CROSS_REFERENCED_EVENT,
        ADDED_TO_MERGE_QUEUE_EVENT,
        REMOVED_FROM_MERGE_QUEUE_EVENT,
        AUTO_MERGE_ENABLED_EVENT,
        AUTO_MERGE_DISABLED_EVENT,
        MARKED_AS_DUPLICATE_EVENT
      ]) {
        nodes {
          __typename
          ... on ReviewRequestedEvent {
            id
            createdAt
            actor { login }
            requestedReviewer {
              ... on User { login }
              ... on Team { name slug }
            }
          }
          ... on ReviewRequestRemovedEvent {
            id
            createdAt
            actor { login }
            requestedReviewer {
              ... on User { login }
              ... on Team { name slug }
            }
          }
          ... on ReviewDismissedEvent {
            id
            createdAt
            actor { login }
            dismissalMessage
            review { author { login } }
          }
          ... on AssignedEvent {
            id
            createdAt
            actor { login }
            assignee { ... on User { login } }
          }
          ... on UnassignedEvent {
            id
            createdAt
            actor { login }
            assignee { ... on User { login } }
          }
          ... on LabeledEvent {
            id
            createdAt
            actor { login }
            label { name color }
          }
          ... on UnlabeledEvent {
            id
            createdAt
            actor { login }
            label { name color }
          }
          ... on HeadRefForcePushedEvent {
            id
            createdAt
            actor { login }
            beforeCommit { oid }
            afterCommit { oid }
          }
          ... on ReadyForReviewEvent {
            id
            createdAt
            actor { login }
          }
          ... on ConvertToDraftEvent {
            id
            createdAt
            actor { login }
          }
          ... on RenamedTitleEvent {
            id
            createdAt
            actor { login }
            previousTitle
            currentTitle
          }
          ... on CrossReferencedEvent {
            id
            createdAt
            actor { login }
            source {
              __typename
              ... on PullRequest { number title repository { nameWithOwner } }
              ... on Issue { number title repository { nameWithOwner } }
            }
          }
          ... on AddedToMergeQueueEvent {
            id
            createdAt
            actor { login }
          }
          ... on RemovedFromMergeQueueEvent {
            id
            createdAt
            actor { login }
            reason
          }
          ... on AutoMergeEnabledEvent {
            id
            createdAt
            actor { login }
          }
          ... on AutoMergeDisabledEvent {
            id
            createdAt
            actor { login }
            reason
          }
          ... on MarkedAsDuplicateEvent {
            id
            createdAt
            actor { login }
          }
        }
      }
    }
  }
  rateLimit { cost remaining resetAt }
}
""".strip()


class GitHubGraphQLError(Exception):
    """Raised when the GraphQL endpoint returns errors we can't recover from."""


async def fetch_pr_timeline_batch(
    client: httpx.AsyncClient,
    token: str,
    repo_owner: str,
    repo_name: str,
    pr_numbers: list[int],
    *,
    batch_size: int = 50,
) -> dict[int, list[dict[str, Any]]]:
    """Fetch timeline items for up to ``batch_size`` PRs in a single GraphQL call.

    Returns a dict keyed by PR number; value is the list of timeline node
    dicts (as returned by GitHub, annotated with ``__typename``). PRs that
    the API returned as ``null`` (e.g. repo renamed, permissions revoked)
    are omitted from the returned dict.

    Callers with more PRs should chunk the input themselves and call this
    repeatedly — this function strictly respects ``batch_size`` to bound
    GraphQL query size.
    """
    if not pr_numbers:
        return {}

    # De-duplicate while preserving order, then chunk.
    seen: set[int] = set()
    ordered: list[int] = []
    for num in pr_numbers:
        if num not in seen:
            ordered.append(num)
            seen.add(num)

    chunks: list[list[int]] = [
        ordered[i : i + batch_size] for i in range(0, len(ordered), batch_size)
    ]
    result: dict[int, list[dict[str, Any]]] = {}
    for chunk in chunks:
        result.update(
            await _fetch_single_batch(
                client, token, repo_owner, repo_name, chunk
            )
        )
    return result


async def _fetch_single_batch(
    client: httpx.AsyncClient,
    token: str,
    repo_owner: str,
    repo_name: str,
    pr_numbers: list[int],
) -> dict[int, list[dict[str, Any]]]:
    """Execute one aliased GraphQL request for the given (bounded) PR list."""
    # Build one aliased repository->pullRequest block per PR number. Sharing
    # the repository() field via alias is the cheap pattern — we pay per
    # pullRequest() selection but only one rateLimit accounting.
    alias_blocks: list[str] = []
    for num in pr_numbers:
        alias = f"pr{num}"
        alias_blocks.append(
            f"""
            {alias}: repository(owner: $owner, name: $name) {{
              pullRequest(number: {num}) {{
                timelineItems(first: 100, itemTypes: [
                  REVIEW_REQUESTED_EVENT,
                  REVIEW_REQUEST_REMOVED_EVENT,
                  REVIEW_DISMISSED_EVENT,
                  ASSIGNED_EVENT,
                  UNASSIGNED_EVENT,
                  LABELED_EVENT,
                  UNLABELED_EVENT,
                  HEAD_REF_FORCE_PUSHED_EVENT,
                  READY_FOR_REVIEW_EVENT,
                  CONVERT_TO_DRAFT_EVENT,
                  RENAMED_TITLE_EVENT,
                  CROSS_REFERENCED_EVENT,
                  ADDED_TO_MERGE_QUEUE_EVENT,
                  REMOVED_FROM_MERGE_QUEUE_EVENT,
                  AUTO_MERGE_ENABLED_EVENT,
                  AUTO_MERGE_DISABLED_EVENT,
                  MARKED_AS_DUPLICATE_EVENT
                ]) {{
                  nodes {{
                    ...TimelineNode
                  }}
                }}
              }}
            }}
            """.strip()
        )

    query = (
        "query($owner: String!, $name: String!) {\n"
        + "\n".join(alias_blocks)
        + "\n  rateLimit { cost remaining resetAt }\n}\n"
        + _TIMELINE_FRAGMENT
    )
    variables = {"owner": repo_owner, "name": repo_name}

    resp = await client.post(
        GITHUB_GRAPHQL_URL,
        json={"query": query, "variables": variables},
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
    )
    resp.raise_for_status()
    payload = resp.json()
    if "errors" in payload and payload["errors"]:
        # GraphQL can return partial data alongside errors; log and keep going
        # if we at least got something back.
        logger.warning(
            "GraphQL timeline query returned errors",
            repo=f"{repo_owner}/{repo_name}",
            errors=payload["errors"][:3],
            event_type="system.github_api",
        )
        if not payload.get("data"):
            raise GitHubGraphQLError(str(payload["errors"])[:500])

    data = payload.get("data") or {}
    rate_limit = data.get("rateLimit") or {}
    if rate_limit:
        logger.debug(
            "GraphQL timeline rate limit",
            cost=rate_limit.get("cost"),
            remaining=rate_limit.get("remaining"),
            reset_at=rate_limit.get("resetAt"),
            pr_count=len(pr_numbers),
            event_type="system.github_api",
        )

    out: dict[int, list[dict[str, Any]]] = {}
    for num in pr_numbers:
        alias_block = data.get(f"pr{num}")
        if not alias_block:
            continue
        pr_node = alias_block.get("pullRequest")
        if not pr_node:
            continue
        timeline = pr_node.get("timelineItems") or {}
        nodes = timeline.get("nodes") or []
        out[num] = [n for n in nodes if n]
    return out


# A shared GraphQL fragment — keeps the alias blocks above compact. Mirrors the
# per-type selections from ``TIMELINE_QUERY`` (they must stay in sync).
_TIMELINE_FRAGMENT = """
fragment TimelineNode on PullRequestTimelineItems {
  __typename
  ... on ReviewRequestedEvent {
    id
    createdAt
    actor { login }
    requestedReviewer {
      ... on User { login }
      ... on Team { name slug }
    }
  }
  ... on ReviewRequestRemovedEvent {
    id
    createdAt
    actor { login }
    requestedReviewer {
      ... on User { login }
      ... on Team { name slug }
    }
  }
  ... on ReviewDismissedEvent {
    id
    createdAt
    actor { login }
    dismissalMessage
    review { author { login } }
  }
  ... on AssignedEvent {
    id
    createdAt
    actor { login }
    assignee { ... on User { login } }
  }
  ... on UnassignedEvent {
    id
    createdAt
    actor { login }
    assignee { ... on User { login } }
  }
  ... on LabeledEvent {
    id
    createdAt
    actor { login }
    label { name color }
  }
  ... on UnlabeledEvent {
    id
    createdAt
    actor { login }
    label { name color }
  }
  ... on HeadRefForcePushedEvent {
    id
    createdAt
    actor { login }
    beforeCommit { oid }
    afterCommit { oid }
  }
  ... on ReadyForReviewEvent {
    id
    createdAt
    actor { login }
  }
  ... on ConvertToDraftEvent {
    id
    createdAt
    actor { login }
  }
  ... on RenamedTitleEvent {
    id
    createdAt
    actor { login }
    previousTitle
    currentTitle
  }
  ... on CrossReferencedEvent {
    id
    createdAt
    actor { login }
    source {
      __typename
      ... on PullRequest { number title repository { nameWithOwner } }
      ... on Issue { number title repository { nameWithOwner } }
    }
  }
  ... on AddedToMergeQueueEvent {
    id
    createdAt
    actor { login }
  }
  ... on RemovedFromMergeQueueEvent {
    id
    createdAt
    actor { login }
    reason
  }
  ... on AutoMergeEnabledEvent {
    id
    createdAt
    actor { login }
  }
  ... on AutoMergeDisabledEvent {
    id
    createdAt
    actor { login }
    reason
  }
  ... on MarkedAsDuplicateEvent {
    id
    createdAt
    actor { login }
  }
}
""".strip()


# ── Persistence ──────────────────────────────────────────────────────────


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _actor_login(node: dict[str, Any]) -> str | None:
    actor = node.get("actor") or {}
    return actor.get("login")


def _extract_subject(node: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    """Return (subject_login, extra_data) for a timeline node.

    ``extra_data`` is stored in the ``data`` JSONB column and captures the
    event's type-specific fields (label name, rename from/to, dismissal
    message, cross-ref target, queue removal reason, etc).
    """
    typename = node.get("__typename") or ""
    subject: str | None = None
    data: dict[str, Any] = {}

    if typename in ("ReviewRequestedEvent", "ReviewRequestRemovedEvent"):
        requested = node.get("requestedReviewer") or {}
        subject = requested.get("login")
        if not subject and requested.get("slug"):
            # Team request — store team identifier in data, leave subject null
            data["team_slug"] = requested.get("slug")
            data["team_name"] = requested.get("name")
    elif typename == "ReviewDismissedEvent":
        review = node.get("review") or {}
        author = review.get("author") or {}
        subject = author.get("login")
        if node.get("dismissalMessage"):
            data["dismissal_message"] = node["dismissalMessage"]
    elif typename in ("AssignedEvent", "UnassignedEvent"):
        assignee = node.get("assignee") or {}
        subject = assignee.get("login")
    elif typename in ("LabeledEvent", "UnlabeledEvent"):
        label = node.get("label") or {}
        if label:
            data["label_name"] = label.get("name")
            data["label_color"] = label.get("color")
    elif typename == "RenamedTitleEvent":
        data["previous_title"] = node.get("previousTitle")
        data["current_title"] = node.get("currentTitle")
    elif typename == "CrossReferencedEvent":
        source = node.get("source") or {}
        if source:
            data["source_type"] = source.get("__typename")
            data["source_number"] = source.get("number")
            data["source_title"] = source.get("title")
            repo = source.get("repository") or {}
            if repo.get("nameWithOwner"):
                data["source_repo"] = repo["nameWithOwner"]
    elif typename in ("RemovedFromMergeQueueEvent", "AutoMergeDisabledEvent"):
        if node.get("reason"):
            data["reason"] = node["reason"]

    return subject, data


async def persist_timeline_events(
    db: AsyncSession,
    pr: PullRequest,
    timeline_nodes: list[dict[str, Any]],
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[str, int]:
    """Upsert timeline events for a single PR.

    Returns a counts dict with ``inserted``, ``updated``, ``skipped``. Events
    are keyed by their GitHub ``id`` (stored in ``external_id``); repeat runs
    on the same payload are idempotent.
    """
    counts = {"inserted": 0, "updated": 0, "skipped": 0}
    if not timeline_nodes:
        return counts

    # Load existing events for this PR once so we can upsert without issuing
    # a round trip per node. External_ids are unique across the whole table,
    # but scoping the query to this PR is cheaper.
    existing_result = await db.execute(
        select(PRTimelineEvent).where(PRTimelineEvent.pr_id == pr.id)
    )
    existing_by_ext: dict[str, PRTimelineEvent] = {
        e.external_id: e for e in existing_result.scalars().all()
    }

    for node in timeline_nodes:
        typename = node.get("__typename") or ""
        event_type = TYPENAME_TO_EVENT_TYPE.get(typename)
        if not event_type:
            counts["skipped"] += 1
            continue

        external_id = node.get("id")
        if not external_id:
            counts["skipped"] += 1
            continue

        created_at = _parse_dt(node.get("createdAt"))
        if not created_at:
            counts["skipped"] += 1
            continue

        actor_login = _actor_login(node)
        actor_dev_id: int | None = None
        if actor_login:
            actor_dev_id = await resolve_author(
                db,
                actor_login,
                user_data={"login": actor_login},
                client=client,
            )

        subject_login, extra_data = _extract_subject(node)
        subject_dev_id: int | None = None
        if subject_login:
            subject_dev_id = await resolve_author(
                db,
                subject_login,
                user_data={"login": subject_login},
                client=client,
            )

        before_sha: str | None = None
        after_sha: str | None = None
        if typename == "HeadRefForcePushedEvent":
            before = node.get("beforeCommit") or {}
            after = node.get("afterCommit") or {}
            before_sha = before.get("oid")
            after_sha = after.get("oid")

        row = existing_by_ext.get(external_id)
        if row is None:
            row = PRTimelineEvent(
                pr_id=pr.id,
                external_id=external_id,
                event_type=event_type,
                created_at=created_at,
                actor_developer_id=actor_dev_id,
                actor_github_username=actor_login,
                subject_developer_id=subject_dev_id,
                subject_github_username=subject_login,
                before_sha=before_sha,
                after_sha=after_sha,
                data=extra_data or None,
            )
            db.add(row)
            counts["inserted"] += 1
        else:
            row.event_type = event_type
            row.created_at = created_at
            row.actor_developer_id = actor_dev_id
            row.actor_github_username = actor_login
            row.subject_developer_id = subject_dev_id
            row.subject_github_username = subject_login
            row.before_sha = before_sha
            row.after_sha = after_sha
            row.data = extra_data or None
            counts["updated"] += 1

    await db.flush()
    return counts


# ── Aggregate derivation ─────────────────────────────────────────────────


def _ensure_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def derive_pr_aggregates(db: AsyncSession, pr: PullRequest) -> None:
    """Recompute the Phase 09 aggregate columns on ``pull_requests`` from events.

    Fields computed here:
      - ``force_push_count_after_first_review``: count of ``head_ref_force_pushed``
        events strictly after ``first_review_at`` (or 0 if no first review yet).
      - ``review_requested_count``: distinct reviewer requests
        (``review_requested`` events — counts each request, matching research).
      - ``ready_for_review_at``: earliest ``ready_for_review`` event. If none,
        stays null (and callers fall back to ``first_review_at``).
      - ``draft_flip_count``: total ``ready_for_review`` + ``converted_to_draft``
        events (either direction).
      - ``renamed_title_count``: count of ``renamed_title`` events.
      - ``dismissed_review_count``: count of ``review_dismissed`` events.
      - ``merge_queue_waited_s``: if PR merged, the interval from the earliest
        ``added_to_merge_queue`` to the latest ``removed_from_merge_queue`` (or
        merged_at if no removal logged).
      - ``auto_merge_waited_s``: if PR merged, the interval from the earliest
        ``auto_merge_enabled`` (without a subsequent disable before merge) to
        ``merged_at``.

    ``codeowners_bypass`` is NOT set here — it requires CODEOWNERS parsing +
    changed-file knowledge that only ``pr_cycle_stages`` has context for.
    """
    events_result = await db.execute(
        select(PRTimelineEvent)
        .where(PRTimelineEvent.pr_id == pr.id)
        .order_by(PRTimelineEvent.created_at.asc())
    )
    events = list(events_result.scalars().all())

    first_review_at = _ensure_aware(pr.first_review_at)
    merged_at = _ensure_aware(pr.merged_at)

    force_push_after_review = 0
    review_requested = 0
    draft_flips = 0
    renamed_title = 0
    dismissed = 0
    ready_for_review_at: datetime | None = None

    merge_queue_added: datetime | None = None
    merge_queue_removed: datetime | None = None
    auto_merge_enabled_at: datetime | None = None
    auto_merge_disabled_at: datetime | None = None

    for ev in events:
        ev_created = _ensure_aware(ev.created_at)
        if ev.event_type == "head_ref_force_pushed":
            if first_review_at and ev_created and ev_created > first_review_at:
                force_push_after_review += 1
        elif ev.event_type == "review_requested":
            review_requested += 1
        elif ev.event_type == "ready_for_review":
            draft_flips += 1
            if ready_for_review_at is None or (
                ev_created and ev_created < ready_for_review_at
            ):
                ready_for_review_at = ev_created
        elif ev.event_type == "converted_to_draft":
            draft_flips += 1
        elif ev.event_type == "renamed_title":
            renamed_title += 1
        elif ev.event_type == "review_dismissed":
            dismissed += 1
        elif ev.event_type == "added_to_merge_queue":
            if merge_queue_added is None or (
                ev_created and ev_created < merge_queue_added
            ):
                merge_queue_added = ev_created
        elif ev.event_type == "removed_from_merge_queue":
            if merge_queue_removed is None or (
                ev_created and ev_created > merge_queue_removed
            ):
                merge_queue_removed = ev_created
        elif ev.event_type == "auto_merge_enabled":
            if auto_merge_enabled_at is None or (
                ev_created and ev_created < auto_merge_enabled_at
            ):
                auto_merge_enabled_at = ev_created
        elif ev.event_type == "auto_merge_disabled":
            auto_merge_disabled_at = ev_created

    pr.force_push_count_after_first_review = force_push_after_review
    pr.review_requested_count = review_requested
    pr.draft_flip_count = draft_flips
    pr.renamed_title_count = renamed_title
    pr.dismissed_review_count = dismissed
    if ready_for_review_at is not None:
        pr.ready_for_review_at = ready_for_review_at

    # Merge queue: only meaningful if PR merged.
    if merged_at and merge_queue_added:
        end = merge_queue_removed or merged_at
        if end and end >= merge_queue_added:
            pr.merge_queue_waited_s = int(
                (end - merge_queue_added).total_seconds()
            )

    # Auto-merge: from enablement to merge, unless it was disabled before merge.
    if merged_at and auto_merge_enabled_at:
        # If auto_merge_disabled came after enable but before merge and there's
        # no subsequent enable, treat it as "disabled before merge" — no wait.
        disabled_before_merge = (
            auto_merge_disabled_at is not None
            and auto_merge_disabled_at > auto_merge_enabled_at
            and auto_merge_disabled_at < merged_at
        )
        if not disabled_before_merge:
            pr.auto_merge_waited_s = int(
                (merged_at - auto_merge_enabled_at).total_seconds()
            )

    await db.flush()


async def count_force_push_after_first_review(
    db: AsyncSession, pr_id: int
) -> int:
    """Helper: re-count force-push events for a PR (used by tests + back-fills)."""
    result = await db.execute(
        select(func.count())
        .select_from(PRTimelineEvent)
        .where(
            PRTimelineEvent.pr_id == pr_id,
            PRTimelineEvent.event_type == "head_ref_force_pushed",
        )
    )
    return int(result.scalar() or 0)
