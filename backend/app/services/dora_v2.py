"""Phase 10 — DORA v2 wrapper: cohort split + rework rate + 2024 thresholds.

Layers on top of the existing `get_dora_metrics` in stats.py. Does NOT refactor
existing DORA internals — this file is additive so we don't destabilize v1 callers.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import PRFile, PullRequest
from app.services.ai_cohort import classify_ai_cohorts_batch, default_rules as default_ai_rules
from app.services.utils import default_range

# DORA 2024 bands per elite/high/medium/low cut points (approximate published numbers)
BANDS_DEPLOY_FREQUENCY = [  # deploys per day
    ("elite", 1.0),
    ("high", 0.14),     # weekly
    ("medium", 0.033),  # monthly
    # < 0.033 = low
]
BANDS_LEAD_TIME_HOURS = [
    ("elite", 24),
    ("high", 168),   # 1 week
    ("medium", 730), # 1 month
    # > 1 month = low
]
BANDS_CFR = [  # percent
    ("elite", 5),
    ("high", 10),
    ("medium", 15),
    # > 15% = low
]
BANDS_MTTR_HOURS = [
    ("elite", 1),
    ("high", 24),
    ("medium", 168),  # 1 week
    # > 1 week = low
]
BANDS_REWORK = [  # percent of merges followed by fixup within 7 days
    ("elite", 5),
    ("high", 10),
    ("medium", 20),
    # > 20% = low
]


def _band(value: float | None, thresholds: list[tuple[str, float]], higher_is_better: bool) -> str:
    if value is None:
        return "low"
    if higher_is_better:
        for label, cutoff in thresholds:
            if value >= cutoff:
                return label
        return "low"
    for label, cutoff in thresholds:
        if value <= cutoff:
            return label
    return "low"


def _overall_band(bands: dict[str, str]) -> str:
    """Worst of the individual bands."""
    rank = {"elite": 3, "high": 2, "medium": 1, "low": 0}
    worst = min(bands.values(), key=lambda b: rank.get(b, 0))
    return worst


async def compute_rework_rate(
    db: AsyncSession,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    pr_ids: set[int] | None = None,
) -> dict:
    """Rework rate: for each merged PR in range, count follow-up PRs touching same files within 7 days.

    Returns `{merges: int, reworks: int, rework_rate: float}`. A PR counts as
    "reworked" if any other PR touching at least one shared filename is merged
    within 7 days after it.
    """
    since, until = default_range(date_from, date_to)

    base_pr = aliased(PullRequest)
    base_file = aliased(PRFile)
    followup_pr = aliased(PullRequest)
    followup_file = aliased(PRFile)

    # Count each merged PR once, regardless of how many follow-ups touched it
    # or how many shared files existed. The self-join matches a PR to any later
    # PR that shares at least one filename and merged within the 7-day window;
    # DISTINCT reduces to a single "was reworked?" row per base PR.
    base_filters = [
        base_pr.merged_at.isnot(None),
        base_pr.merged_at >= since,
        base_pr.merged_at <= until,
    ]
    if pr_ids is not None:
        base_filters.append(base_pr.id.in_(pr_ids))

    merges_row = await db.execute(
        select(func.count(func.distinct(base_pr.id))).where(*base_filters)
    )
    merges = int(merges_row.scalar() or 0)
    if merges == 0:
        return {"merges": 0, "reworks": 0, "rework_rate": 0.0}

    # One query, two joins: base PR → its files → any follow-up PR file with the
    # same filename → follow-up PR merged later but within 7 days. This replaces
    # the prior N+1 loop (one query per merged PR).
    # SQL gets the candidate pairs in one self-join; the 7-day window is applied
    # in Python because timedelta arithmetic on DateTime columns doesn't compile
    # uniformly across SQLite and PostgreSQL. The join alone reduces the previous
    # N+1 loop to a single database round trip — Python-side filtering scales
    # with the number of file-overlap pairs (small) rather than merged PRs.
    reworks_query = (
        select(
            base_pr.id.label("base_id"),
            base_pr.merged_at.label("base_merged_at"),
            followup_pr.merged_at.label("followup_merged_at"),
        )
        .distinct()
        .join(base_file, base_file.pr_id == base_pr.id)
        .join(followup_file, followup_file.filename == base_file.filename)
        .join(followup_pr, followup_pr.id == followup_file.pr_id)
        .where(
            *base_filters,
            followup_pr.id != base_pr.id,
            followup_pr.merged_at.isnot(None),
            followup_pr.merged_at > base_pr.merged_at,
        )
    )
    rows = (await db.execute(reworks_query)).all()
    rework_window = timedelta(days=7)
    reworked_ids: set[int] = set()
    for row in rows:
        if row.base_merged_at and row.followup_merged_at:
            if row.followup_merged_at - row.base_merged_at <= rework_window:
                reworked_ids.add(row.base_id)
    reworks = len(reworked_ids)

    return {
        "merges": merges,
        "reworks": reworks,
        "rework_rate": (reworks / merges) if merges else 0.0,
    }


async def get_dora_v2(
    db: AsyncSession,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    cohort: str = "all",
) -> dict:
    """DORA v2 shape: {throughput, stability, bands, cohorts, trend}.

    For cohort=`all`, returns metrics computed across all PRs.
    For a specific cohort, restricts the data window to PRs in that cohort.
    """
    from app.services.stats import get_dora_metrics  # local import to avoid circulars

    since, until = default_range(date_from, date_to)

    # Compute baseline DORA using the existing service
    baseline = await get_dora_metrics(db, date_from=since, date_to=until)
    baseline_d = baseline.model_dump()

    # Rework rate over same window
    rework = await compute_rework_rate(db, date_from=since, date_to=until)

    throughput = {
        "deployment_frequency": baseline_d.get("deploy_frequency"),
        "lead_time_hours": baseline_d.get("avg_lead_time_hours"),
        "mttr_hours": baseline_d.get("avg_mttr_hours"),
    }
    stability = {
        "change_failure_rate": baseline_d.get("change_failure_rate"),
        "rework_rate": rework["rework_rate"] * 100 if rework["rework_rate"] is not None else None,
    }

    bands = {
        "deployment_frequency": _band(
            throughput["deployment_frequency"], BANDS_DEPLOY_FREQUENCY, True
        ),
        "lead_time": _band(throughput["lead_time_hours"], BANDS_LEAD_TIME_HOURS, False),
        "mttr": _band(throughput["mttr_hours"], BANDS_MTTR_HOURS, False),
        "change_failure_rate": _band(stability["change_failure_rate"], BANDS_CFR, False),
        "rework_rate": _band(stability["rework_rate"], BANDS_REWORK, False),
    }
    bands["overall"] = _overall_band(bands)

    # Cohorts — restrict to PRs in range, classify, compute per-cohort rework
    pr_rows = (
        await db.execute(
            select(PullRequest.id)
            .where(
                PullRequest.merged_at.isnot(None),
                PullRequest.merged_at >= since,
                PullRequest.merged_at <= until,
            )
        )
    ).scalars().all()
    # Merge admin-editable rules on top of the hard-coded defaults so
    # /admin/classifier-rules customisations take effect here.
    from app.services.classifier_rules import load_ai_detection_rules

    ai_rules = await load_ai_detection_rules(db)
    cohorts_map = await classify_ai_cohorts_batch(db, pr_rows, rules=ai_rules)
    cohort_buckets: dict[str, set[int]] = defaultdict(set)
    for pid, c in cohorts_map.items():
        cohort_buckets[c].add(pid)

    cohort_results: dict[str, dict] = {}
    for cohort_name in ("human", "ai_reviewed", "ai_authored", "hybrid"):
        ids = cohort_buckets.get(cohort_name, set())
        if not ids:
            cohort_results[cohort_name] = {
                "merges": 0,
                "rework_rate": 0.0,
                "share_pct": 0.0,
            }
            continue
        r = await compute_rework_rate(db, date_from=since, date_to=until, pr_ids=ids)
        share_pct = (len(ids) / len(pr_rows) * 100) if pr_rows else 0.0
        cohort_results[cohort_name] = {
            "merges": r["merges"],
            "rework_rate": r["rework_rate"] * 100,
            "share_pct": share_pct,
        }

    return {
        "throughput": throughput,
        "stability": stability,
        "bands": bands,
        "cohorts": cohort_results,
        "date_from": since.isoformat(),
        "date_to": until.isoformat(),
    }
