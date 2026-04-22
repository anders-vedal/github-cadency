"""PR cycle-time stage decomposition.

Breaks the end-to-end PR cycle into four measurable stages using data from
``pull_requests`` + Phase 09's ``pr_timeline_events`` enrichment:

    open (created_at)
        → ready_for_review_at (fall back to first_review_at when a PR skipped
          the ``ready_for_review`` timeline event, e.g. non-draft PRs)
        → first_review_at
        → approved_at
        → merged_at

Stage outputs are seconds. Per-stage distributions are returned as p50/p75/p90
plus a ``count`` of contributing PRs. A PR contributes to a stage only when
both endpoints are known; stages whose start > end are discarded (clock skew).

The optional ``group_by`` argument supports ``"repo"`` or ``"all"``. A
``"team"`` breakdown is planned in a follow-up — the author's team is stored
on ``developers`` so the grouping is straightforward, but this phase keeps
the surface minimal.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import PullRequest, Repository

STAGE_KEYS = (
    "open_to_ready_s",
    "ready_to_first_review_s",
    "first_review_to_approval_s",
    "approval_to_merge_s",
)


def _ensure_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def compute_pr_stage_durations(pr: PullRequest) -> dict[str, int | None]:
    """Compute each stage's duration for a single PR.

    Returns a dict with the four stage keys mapped to seconds (int) or
    ``None`` when either endpoint is missing or the duration would be
    negative (clock skew — we treat that as "unknown" rather than zero so
    callers can filter cleanly).

    For ``open_to_ready_s``, when ``ready_for_review_at`` is null we fall
    back to ``first_review_at`` (so non-draft PRs still contribute a
    meaningful "open → reviewed" figure in that bucket).
    """
    created = _ensure_aware(pr.created_at)
    ready = _ensure_aware(pr.ready_for_review_at)
    first_review = _ensure_aware(pr.first_review_at)
    approved = _ensure_aware(pr.approved_at)
    merged = _ensure_aware(pr.merged_at)

    # Fall back if ready_for_review_at is null
    ready_or_fallback = ready or first_review

    def delta(start: datetime | None, end: datetime | None) -> int | None:
        if not start or not end:
            return None
        diff = (end - start).total_seconds()
        if diff < 0:
            return None
        return int(diff)

    out: dict[str, int | None] = {
        "open_to_ready_s": delta(created, ready_or_fallback),
        # Use raw `ready` (not fallback) — for non-draft PRs, ready == first_review, which
        # would collapse this stage to zero and bias percentile distributions to zero.
        "ready_to_first_review_s": delta(ready, first_review),
        "first_review_to_approval_s": delta(first_review, approved),
        "approval_to_merge_s": delta(approved, merged),
    }
    return out


def _percentile(sorted_values: list[int], pct: float) -> int | None:
    """Linear-interpolated percentile on a pre-sorted list."""
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * pct
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return int(sorted_values[int(k)])
    d0 = sorted_values[f] * (c - k)
    d1 = sorted_values[c] * (k - f)
    return int(round(d0 + d1))


def summarize_stage_samples(
    samples: dict[str, list[int]],
) -> dict[str, dict[str, int | None]]:
    """Given per-stage sample lists, return p50/p75/p90/count per stage."""
    out: dict[str, dict[str, int | None]] = {}
    for stage in STAGE_KEYS:
        values = sorted(samples.get(stage, []))
        out[stage] = {
            "count": len(values),
            "p50": _percentile(values, 0.50),
            "p75": _percentile(values, 0.75),
            "p90": _percentile(values, 0.90),
        }
    return out


async def get_pr_cycle_stage_distribution(
    db: AsyncSession,
    since: datetime,
    until: datetime,
    *,
    group_by: str = "all",
) -> dict[str, Any]:
    """Return p50/p75/p90 per stage for PRs merged in ``[since, until]``.

    Only merged PRs are included — unmerged PRs lack a cycle-complete endpoint
    for the ``approval_to_merge_s`` stage and would bias earlier stages.

    ``group_by``:
      - ``"all"`` — single group covering every qualifying PR.
      - ``"repo"`` — grouped by ``repositories.full_name``.

    Return shape:
      ```
      {
        "all": {"open_to_ready_s": {"count": N, "p50": s, "p75": s, "p90": s}, ...},
        ...  # or per-repo dicts if group_by="repo"
      }
      ```
    """
    if group_by not in ("all", "repo"):
        raise ValueError(f"unsupported group_by: {group_by}")

    since_aware = _ensure_aware(since)
    until_aware = _ensure_aware(until)

    stmt = (
        select(PullRequest, Repository.full_name)
        .join(Repository, PullRequest.repo_id == Repository.id)
        .where(
            PullRequest.is_merged.is_(True),
            PullRequest.merged_at.isnot(None),
            PullRequest.merged_at >= since_aware,
            PullRequest.merged_at <= until_aware,
        )
    )
    result = await db.execute(stmt)

    groups: dict[str, dict[str, list[int]]] = {}
    for pr, repo_full_name in result.all():
        key = repo_full_name if group_by == "repo" else "all"
        bucket = groups.setdefault(
            key, {stage: [] for stage in STAGE_KEYS}
        )
        durations = compute_pr_stage_durations(pr)
        for stage, value in durations.items():
            if value is not None:
                bucket[stage].append(value)

    out: dict[str, Any] = {}
    for key, samples in groups.items():
        out[key] = summarize_stage_samples(samples)
    return out
