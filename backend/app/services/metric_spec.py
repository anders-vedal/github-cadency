"""Phase 11 — Metrics governance. `MetricSpec` registry + catalog.

Every metric exposed via the API should register a MetricSpec so the UI can:
- Show appropriate tooltips and paired-outcome companions
- Enforce per-metric visibility defaults
- Flag activity-only metrics (must be paired with outcome)
- Render distribution-style cards for metrics that need p50/p90

Also contains the BANNED_METRICS list — metrics we explicitly don't expose.
"""

from dataclasses import dataclass, field
from typing import Literal


VisibilityDefault = Literal["self", "team", "admin"]
GoodhartRisk = Literal["low", "medium", "high"]


@dataclass
class MetricSpec:
    key: str
    label: str
    category: str  # throughput | stability | flow | dialogue | bottleneck | quality
    is_activity: bool
    paired_outcome_key: str | None = None
    visibility_default: VisibilityDefault = "team"
    is_distribution: bool = False
    goodhart_risk: GoodhartRisk = "low"
    goodhart_notes: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        if self.is_activity and not self.paired_outcome_key:
            raise ValueError(
                f"Activity metric {self.key!r} must declare a paired_outcome_key "
                f"(per Phase 11 governance). "
                f"Either pair it with an outcome metric or set is_activity=False."
            )


# Banned metrics — never exposed, documented for clarity
BANNED_METRICS = [
    {
        "key": "lines_of_code_per_dev",
        "reason": "LOC is not a productivity metric. Correlates negatively with quality.",
    },
    {
        "key": "commits_per_dev",
        "reason": "Incentivizes commit-padding and discourages meaningful commit hygiene.",
    },
    {
        "key": "story_points_per_sprint_per_dev",
        "reason": "Per-individual velocity is weaponizable and blind to scope, complexity, blockers.",
    },
    {
        "key": "time_to_first_review_as_kpi",
        "reason": "Creates incentives for rubber-stamp reviews. Ship distribution, not target.",
    },
    {
        "key": "loc_weighted_impact_score",
        "reason": "Amplifies LOC bias. Reviewer-count or bus-factor is a better impact proxy.",
    },
    {
        "key": "raw_sentiment_per_developer",
        "reason": "Cross-cultural noise ~30% per research. Team-aggregate only, opt-in.",
    },
]


# Core metric registry. Each phase may extend this list.
REGISTRY: list[MetricSpec] = [
    # --- Throughput ---
    MetricSpec(
        key="deployment_frequency",
        label="Deployment frequency",
        category="throughput",
        is_activity=True,
        paired_outcome_key="change_failure_rate",
        visibility_default="team",
        goodhart_risk="medium",
        goodhart_notes="Inflated by micro-deploys; pair with CFR so optimizing ignores quality",
        description="Deploys per day over the selected window",
    ),
    MetricSpec(
        key="lead_time_p50_s",
        label="Lead time (p50)",
        category="throughput",
        is_activity=False,
        is_distribution=True,
        visibility_default="team",
        description="Commit → deploy median",
    ),
    MetricSpec(
        key="mttr_p50_s",
        label="MTTR (p50)",
        category="throughput",
        is_activity=False,
        is_distribution=True,
        visibility_default="team",
    ),
    # --- Stability ---
    MetricSpec(
        key="change_failure_rate",
        label="Change failure rate",
        category="stability",
        is_activity=False,
        visibility_default="team",
    ),
    MetricSpec(
        key="rework_rate",
        label="Rework rate",
        category="stability",
        is_activity=False,
        visibility_default="team",
        goodhart_notes="Watch for batch-merging to suppress",
    ),
    # --- Flow ---
    MetricSpec(
        key="wip_per_developer",
        label="WIP per developer",
        category="flow",
        is_activity=True,
        paired_outcome_key="cycle_time_p50_s",
        visibility_default="team",
    ),
    MetricSpec(
        key="cycle_time_p50_s",
        label="Cycle time (p50)",
        category="flow",
        is_activity=False,
        is_distribution=True,
        visibility_default="team",
    ),
    # --- Dialogue / conversations ---
    MetricSpec(
        key="median_comments_per_issue",
        label="Comments per issue (median)",
        category="dialogue",
        is_activity=False,
        is_distribution=True,
        visibility_default="team",
        goodhart_notes="High numbers can be good (healthy dialogue) or bad (muddled spec)",
    ),
    MetricSpec(
        key="first_response_time",
        label="First-response time",
        category="dialogue",
        is_activity=False,
        is_distribution=True,
        visibility_default="team",
    ),
    # --- Bottleneck ---
    MetricSpec(
        key="review_load_gini",
        label="Review load Gini",
        category="bottleneck",
        is_activity=False,
        visibility_default="team",
    ),
    MetricSpec(
        key="review_round_count",
        label="Review round count",
        category="bottleneck",
        is_activity=False,
        is_distribution=True,
        visibility_default="team",
        goodhart_risk="medium",
        goodhart_notes=">3 rounds = ping-pong signal. Don't frame as author performance.",
    ),
    MetricSpec(
        key="bus_factor_by_file",
        label="Single-owner files",
        category="bottleneck",
        is_activity=False,
        visibility_default="team",
    ),
    # --- Quality ---
    MetricSpec(
        key="avg_downstream_pr_review_rounds",
        label="Avg downstream PR review rounds (by ticket creator)",
        category="quality",
        is_activity=False,
        visibility_default="self",  # Phase 11: creator-outcome is self+admin only
        goodhart_risk="high",
        goodhart_notes=(
            "Creator-outcome correlation. Default self+admin visibility to prevent weaponization. "
            "Frame as 'ticket clarity signal for self-reflection', not a performance ranking."
        ),
    ),
    MetricSpec(
        key="issue_linkage_rate",
        label="Issue linkage rate",
        category="quality",
        is_activity=False,
        visibility_default="team",
    ),
]


REGISTRY_BY_KEY: dict[str, MetricSpec] = {m.key: m for m in REGISTRY}


def get_catalog() -> dict:
    """Public metrics catalog for the frontend to consume (tooltips, pair linking, etc)."""
    return {
        "metrics": [
            {
                "key": m.key,
                "label": m.label,
                "category": m.category,
                "is_activity": m.is_activity,
                "paired_outcome_key": m.paired_outcome_key,
                "visibility_default": m.visibility_default,
                "is_distribution": m.is_distribution,
                "goodhart_risk": m.goodhart_risk,
                "goodhart_notes": m.goodhart_notes,
                "description": m.description,
            }
            for m in REGISTRY
        ],
        "banned": BANNED_METRICS,
    }


def validate_registry() -> None:
    """Validate the registry at import/startup. Raises ValueError if invariants broken."""
    for m in REGISTRY:
        if m.is_activity and not m.paired_outcome_key:
            raise ValueError(
                f"Activity metric {m.key!r} missing paired_outcome_key (Phase 11 violation)"
            )
        if m.paired_outcome_key and m.paired_outcome_key not in REGISTRY_BY_KEY:
            raise ValueError(
                f"Metric {m.key!r} pairs with unknown outcome key {m.paired_outcome_key!r}"
            )


# Validate at import time so startup fails loudly on broken registry
validate_registry()
