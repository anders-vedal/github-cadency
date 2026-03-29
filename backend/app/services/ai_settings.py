"""AI settings, cost controls, and usage tracking service."""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.models.models import AIAnalysis, AISettings, AIUsageLog
from app.services.exceptions import AIFeatureDisabledError
from app.schemas.schemas import (
    AICostEstimate,
    AIFeatureStatus,
    AISettingsResponse,
    AISettingsUpdate,
    AIUsageSummary,
    DailyUsage,
)

logger = logging.getLogger(__name__)

# Feature metadata — labels, descriptions, disable-impact text
FEATURE_META: dict[str, dict[str, str]] = {
    "general_analysis": {
        "label": "General Analysis",
        "description": (
            "AI-powered communication, conflict, and sentiment analysis of PR reviews, "
            "issue comments, and team interactions."
        ),
        "disabled_impact": (
            "Admins cannot run communication, conflict, or sentiment analyses. "
            "All historical results remain accessible in the AI Analysis page."
        ),
        "analysis_types": "communication,conflict,sentiment",
    },
    "one_on_one_prep": {
        "label": "1:1 Prep Brief",
        "description": (
            "AI-generated structured meeting briefs with metric highlights, talking points, "
            "goal progress, and continuity from previous 1:1s."
        ),
        "disabled_impact": (
            "Admins must prepare 1:1 meeting notes manually. Developer stats, trends, "
            "benchmarks, and goal progress remain available without AI."
        ),
        "analysis_types": "one_on_one_prep",
    },
    "team_health": {
        "label": "Team Health Check",
        "description": (
            "AI assessment of team velocity, workload balance, collaboration patterns, "
            "communication flags, and prioritized action items."
        ),
        "disabled_impact": (
            "No automated team health scoring. The Workload, Collaboration, and Benchmarks "
            "insight pages still provide all underlying data."
        ),
        "analysis_types": "team_health",
    },
    "work_categorization": {
        "label": "Work Categorization",
        "description": (
            "AI classification of PRs and issues into feature/bugfix/tech_debt/ops categories "
            "when label-based and title-regex rules cannot determine the type."
        ),
        "disabled_impact": (
            "The Investment page uses deterministic classification only (label mapping + "
            "title regex). Items that can't be auto-classified show as 'unknown' instead "
            "of being sent to AI."
        ),
        "analysis_types": "",  # tracked in ai_usage_log, not ai_analyses
    },
}


def _month_start() -> datetime:
    """Return the first moment of the current UTC month."""
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def compute_cost(
    input_tokens: int,
    output_tokens: int,
    input_price_per_m: float,
    output_price_per_m: float,
) -> float:
    """Calculate estimated cost in USD from token counts and pricing."""
    return round(
        (input_tokens * input_price_per_m / 1_000_000)
        + (output_tokens * output_price_per_m / 1_000_000),
        6,
    )


# --- Settings CRUD ---


async def get_ai_settings(db: AsyncSession) -> AISettings:
    """Get the singleton AI settings row. Creates default if missing."""
    row = await db.get(AISettings, 1)
    if not row:
        row = AISettings(id=1)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


async def update_ai_settings(
    db: AsyncSession, updates: AISettingsUpdate, updated_by: str
) -> AISettings:
    """Partial update of AI settings. Returns updated row."""
    row = await get_ai_settings(db)

    pricing_changed = False
    for field, value in updates.model_dump(exclude_unset=True).items():
        if field == "clear_budget":
            if value:
                row.monthly_token_budget = None
            continue
        if field in ("input_token_price_per_million", "output_token_price_per_million"):
            if value is not None and getattr(row, field) != value:
                pricing_changed = True
        if value is not None:
            setattr(row, field, value)

    row.updated_at = datetime.now(timezone.utc)
    row.updated_by = updated_by
    if pricing_changed:
        row.pricing_updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(row)
    return row


# --- Guards ---


async def check_feature_enabled(db: AsyncSession, feature_name: str) -> AISettings:
    """Check if a specific AI feature is enabled. Raises 403 if not.

    Returns the settings row for downstream use (budget check, etc).
    """
    ai_settings = await get_ai_settings(db)

    if not ai_settings.ai_enabled:
        raise AIFeatureDisabledError(
            "All AI features are disabled. An admin can re-enable them in AI Settings.",
        )

    feature_attr = f"feature_{feature_name}"
    if not getattr(ai_settings, feature_attr, True):
        label = FEATURE_META.get(feature_name, {}).get("label", feature_name)
        raise AIFeatureDisabledError(
            f"AI feature '{label}' is disabled. An admin can re-enable it in AI Settings.",
        )

    return ai_settings


async def check_budget(db: AsyncSession, ai_settings: AISettings) -> dict[str, Any]:
    """Check monthly token budget. Returns usage info dict."""
    month_start = _month_start()

    # Sum tokens from ai_analyses this month (excluding reused cache hits)
    analyses_tokens = (
        await db.execute(
            select(
                func.coalesce(func.sum(AIAnalysis.tokens_used), 0),
            ).where(
                AIAnalysis.created_at >= month_start,
                AIAnalysis.reused_from_id.is_(None),
            )
        )
    ).scalar_one()

    # Sum tokens from ai_usage_log this month
    log_tokens = (
        await db.execute(
            select(
                func.coalesce(
                    func.sum(AIUsageLog.input_tokens + AIUsageLog.output_tokens), 0
                ),
            ).where(AIUsageLog.created_at >= month_start)
        )
    ).scalar_one()

    tokens_used = int(analyses_tokens) + int(log_tokens)
    budget = ai_settings.monthly_token_budget

    pct_used = None
    over_budget = False
    if budget is not None and budget > 0:
        pct_used = round(tokens_used / budget, 4)
        over_budget = tokens_used >= budget

    return {
        "tokens_used": tokens_used,
        "budget_limit": budget,
        "pct_used": pct_used,
        "over_budget": over_budget,
    }


async def find_recent_analysis(
    db: AsyncSession,
    analysis_type: str,
    scope_type: str,
    scope_id: str,
    cooldown_minutes: int,
) -> AIAnalysis | None:
    """Find a recent analysis matching type+scope within the cooldown window."""
    if cooldown_minutes <= 0:
        return None

    cutoff = datetime.now(timezone.utc).replace(microsecond=0)
    from datetime import timedelta

    cutoff = cutoff - timedelta(minutes=cooldown_minutes)

    result = await db.execute(
        select(AIAnalysis)
        .where(
            AIAnalysis.analysis_type == analysis_type,
            AIAnalysis.scope_type == scope_type,
            AIAnalysis.scope_id == scope_id,
            AIAnalysis.created_at >= cutoff,
            AIAnalysis.reused_from_id.is_(None),  # don't chain reuses
        )
        .order_by(AIAnalysis.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


# --- Usage Aggregation ---


async def get_current_month_usage(
    db: AsyncSession, ai_settings: AISettings
) -> tuple[int, float]:
    """Get total tokens and cost for the current calendar month."""
    budget_info = await check_budget(db, ai_settings)
    tokens = budget_info["tokens_used"]

    # For cost we need split tokens — approximate from ai_analyses + ai_usage_log
    month_start = _month_start()

    # ai_analyses: use input_tokens/output_tokens if available, else estimate 70/30 split
    analyses_result = await db.execute(
        select(
            func.coalesce(func.sum(AIAnalysis.input_tokens), 0),
            func.coalesce(func.sum(AIAnalysis.output_tokens), 0),
            func.coalesce(func.sum(AIAnalysis.tokens_used), 0),
        ).where(
            AIAnalysis.created_at >= month_start,
            AIAnalysis.reused_from_id.is_(None),
        )
    )
    row = analyses_result.one()
    a_input, a_output, a_total = int(row[0]), int(row[1]), int(row[2])

    # If split tokens aren't populated yet (legacy rows), estimate
    if a_input == 0 and a_output == 0 and a_total > 0:
        a_input = int(a_total * 0.7)
        a_output = a_total - a_input

    # ai_usage_log
    log_result = await db.execute(
        select(
            func.coalesce(func.sum(AIUsageLog.input_tokens), 0),
            func.coalesce(func.sum(AIUsageLog.output_tokens), 0),
        ).where(AIUsageLog.created_at >= month_start)
    )
    log_row = log_result.one()
    l_input, l_output = int(log_row[0]), int(log_row[1])

    total_input = a_input + l_input
    total_output = a_output + l_output
    cost = compute_cost(
        total_input,
        total_output,
        ai_settings.input_token_price_per_million,
        ai_settings.output_token_price_per_million,
    )

    return tokens, cost


async def build_settings_response(
    db: AsyncSession, ai_settings: AISettings
) -> dict[str, Any]:
    """Build the full AISettingsResponse with computed fields."""
    tokens, cost = await get_current_month_usage(db, ai_settings)

    budget_pct = None
    if ai_settings.monthly_token_budget and ai_settings.monthly_token_budget > 0:
        budget_pct = round(tokens / ai_settings.monthly_token_budget, 4)

    return {
        **{c.key: getattr(ai_settings, c.key) for c in AISettings.__table__.columns if c.key != "id"},
        "api_key_configured": bool(app_settings.anthropic_api_key),
        "current_month_tokens": tokens,
        "current_month_cost_usd": round(cost, 4),
        "budget_pct_used": budget_pct,
    }


async def get_feature_statuses(
    db: AsyncSession, ai_settings: AISettings
) -> list[AIFeatureStatus]:
    """Build per-feature status cards with usage data."""
    month_start = _month_start()
    features = []

    for feature_key, meta in FEATURE_META.items():
        feature_attr = f"feature_{feature_key}"
        enabled = getattr(ai_settings, feature_attr, True)

        tokens = 0
        cost = 0.0
        call_count = 0
        last_used: datetime | None = None

        if feature_key == "work_categorization":
            # Query ai_usage_log
            result = await db.execute(
                select(
                    func.coalesce(func.sum(AIUsageLog.input_tokens), 0),
                    func.coalesce(func.sum(AIUsageLog.output_tokens), 0),
                    func.count(),
                    func.max(AIUsageLog.created_at),
                ).where(
                    AIUsageLog.feature == "work_categorization",
                    AIUsageLog.created_at >= month_start,
                )
            )
            row = result.one()
            inp, out = int(row[0]), int(row[1])
            tokens = inp + out
            call_count = int(row[2])
            last_used = row[3]
            cost = compute_cost(
                inp, out,
                ai_settings.input_token_price_per_million,
                ai_settings.output_token_price_per_million,
            )
        else:
            # Query ai_analyses by analysis_type
            analysis_types = [t.strip() for t in meta["analysis_types"].split(",") if t.strip()]
            if analysis_types:
                result = await db.execute(
                    select(
                        func.coalesce(func.sum(AIAnalysis.input_tokens), 0),
                        func.coalesce(func.sum(AIAnalysis.output_tokens), 0),
                        func.coalesce(func.sum(AIAnalysis.tokens_used), 0),
                        func.count(),
                        func.max(AIAnalysis.created_at),
                    ).where(
                        AIAnalysis.analysis_type.in_(analysis_types),
                        AIAnalysis.created_at >= month_start,
                        AIAnalysis.reused_from_id.is_(None),
                    )
                )
                row = result.one()
                inp, out, total = int(row[0]), int(row[1]), int(row[2])
                # Handle legacy rows without split tokens
                if inp == 0 and out == 0 and total > 0:
                    inp = int(total * 0.7)
                    out = total - inp
                tokens = inp + out
                call_count = int(row[3])
                last_used = row[4]
                cost = compute_cost(
                    inp, out,
                    ai_settings.input_token_price_per_million,
                    ai_settings.output_token_price_per_million,
                )

        features.append(AIFeatureStatus(
            feature=feature_key,
            enabled=enabled and ai_settings.ai_enabled,
            label=meta["label"],
            description=meta["description"],
            disabled_impact=meta["disabled_impact"],
            tokens_this_month=tokens,
            cost_this_month_usd=round(cost, 4),
            call_count_this_month=call_count,
            last_used_at=last_used,
        ))

    return features


async def get_daily_usage(
    db: AsyncSession, ai_settings: AISettings, days: int = 30
) -> list[DailyUsage]:
    """Get daily usage aggregation for the usage chart."""
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # ai_analyses grouped by date and analysis_type
    analyses_result = await db.execute(
        select(
            func.date(AIAnalysis.created_at).label("day"),
            AIAnalysis.analysis_type,
            func.coalesce(func.sum(AIAnalysis.input_tokens), 0),
            func.coalesce(func.sum(AIAnalysis.output_tokens), 0),
            func.coalesce(func.sum(AIAnalysis.tokens_used), 0),
            func.count(),
        )
        .where(
            AIAnalysis.created_at >= cutoff,
            AIAnalysis.reused_from_id.is_(None),
        )
        .group_by(func.date(AIAnalysis.created_at), AIAnalysis.analysis_type)
    )

    # ai_usage_log grouped by date
    log_result = await db.execute(
        select(
            func.date(AIUsageLog.created_at).label("day"),
            func.coalesce(func.sum(AIUsageLog.input_tokens), 0),
            func.coalesce(func.sum(AIUsageLog.output_tokens), 0),
            func.count(),
        )
        .where(AIUsageLog.created_at >= cutoff)
        .group_by(func.date(AIUsageLog.created_at))
    )

    # Map analysis_type to feature key
    type_to_feature = {}
    for feature_key, meta in FEATURE_META.items():
        for t in meta["analysis_types"].split(","):
            t = t.strip()
            if t:
                type_to_feature[t] = feature_key

    # Merge into daily buckets
    daily: dict[str, dict] = {}

    for row in analyses_result.all():
        day_str = str(row[0])
        analysis_type = row[1]
        inp, out, total = int(row[2]), int(row[3]), int(row[4])
        count = int(row[5])

        if inp == 0 and out == 0 and total > 0:
            inp = int(total * 0.7)
            out = total - inp
        tokens = inp + out
        cost = compute_cost(
            inp, out,
            ai_settings.input_token_price_per_million,
            ai_settings.output_token_price_per_million,
        )

        if day_str not in daily:
            daily[day_str] = {"tokens": 0, "cost_usd": 0.0, "calls": 0, "by_feature": {}}
        daily[day_str]["tokens"] += tokens
        daily[day_str]["cost_usd"] += cost
        daily[day_str]["calls"] += count

        feature = type_to_feature.get(analysis_type, analysis_type)
        if feature not in daily[day_str]["by_feature"]:
            daily[day_str]["by_feature"][feature] = {"tokens": 0, "calls": 0}
        daily[day_str]["by_feature"][feature]["tokens"] += tokens
        daily[day_str]["by_feature"][feature]["calls"] += count

    for row in log_result.all():
        day_str = str(row[0])
        inp, out = int(row[1]), int(row[2])
        count = int(row[3])
        tokens = inp + out
        cost = compute_cost(
            inp, out,
            ai_settings.input_token_price_per_million,
            ai_settings.output_token_price_per_million,
        )

        if day_str not in daily:
            daily[day_str] = {"tokens": 0, "cost_usd": 0.0, "calls": 0, "by_feature": {}}
        daily[day_str]["tokens"] += tokens
        daily[day_str]["cost_usd"] += cost
        daily[day_str]["calls"] += count
        feat = "work_categorization"
        if feat not in daily[day_str]["by_feature"]:
            daily[day_str]["by_feature"][feat] = {"tokens": 0, "calls": 0}
        daily[day_str]["by_feature"][feat]["tokens"] += tokens
        daily[day_str]["by_feature"][feat]["calls"] += count

    return [
        DailyUsage(
            date=day,
            tokens=data["tokens"],
            cost_usd=round(data["cost_usd"], 4),
            calls=data["calls"],
            by_feature=data["by_feature"],
        )
        for day, data in sorted(daily.items())
    ]


async def get_usage_summary(
    db: AsyncSession, ai_settings: AISettings, days: int = 30
) -> AIUsageSummary:
    """Full usage summary for the admin panel."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    period_start = now - timedelta(days=days)

    features = await get_feature_statuses(db, ai_settings)
    daily = await get_daily_usage(db, ai_settings, days=days)

    total_tokens = sum(d.tokens for d in daily)
    total_cost = sum(d.cost_usd for d in daily)

    budget_pct = None
    if ai_settings.monthly_token_budget and ai_settings.monthly_token_budget > 0:
        month_tokens, _ = await get_current_month_usage(db, ai_settings)
        budget_pct = round(month_tokens / ai_settings.monthly_token_budget, 4)

    return AIUsageSummary(
        period_start=period_start,
        period_end=now,
        total_tokens=total_tokens,
        total_cost_usd=round(total_cost, 4),
        budget_limit=ai_settings.monthly_token_budget,
        budget_pct_used=budget_pct,
        features=features,
        daily_usage=daily,
    )
