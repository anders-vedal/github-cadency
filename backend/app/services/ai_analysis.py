import json
import logging
from datetime import datetime, timezone

import anthropic
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.models import (
    AIAnalysis,
    Developer,
    DeveloperGoal,
    Issue,
    IssueComment,
    PRReview,
    PullRequest,
)

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-0"
MAX_ITEM_CHARS = 500
MAX_ITEMS_PER_CATEGORY = 50


# --- Data Preparation ---


def _truncate(text: str | None) -> str:
    if not text:
        return ""
    return text[:MAX_ITEM_CHARS]


async def _gather_developer_texts(
    db: AsyncSession,
    developer_id: int,
    date_from: datetime,
    date_to: datetime,
) -> tuple[list[dict], str]:
    """Gather PR bodies, review comments, and issue comments for a developer."""
    items: list[dict] = []

    # PR descriptions
    prs = (
        await db.execute(
            select(PullRequest)
            .where(
                PullRequest.author_id == developer_id,
                PullRequest.created_at >= date_from,
                PullRequest.created_at <= date_to,
            )
            .order_by(PullRequest.created_at.desc())
            .limit(MAX_ITEMS_PER_CATEGORY)
        )
    ).scalars().all()
    for pr in prs:
        if pr.body:
            items.append({
                "type": "pr_description",
                "title": pr.title,
                "text": _truncate(pr.body),
            })

    # Reviews given
    reviews = (
        await db.execute(
            select(PRReview)
            .where(
                PRReview.reviewer_id == developer_id,
                PRReview.submitted_at >= date_from,
                PRReview.submitted_at <= date_to,
            )
            .order_by(PRReview.submitted_at.desc())
            .limit(MAX_ITEMS_PER_CATEGORY)
        )
    ).scalars().all()
    for review in reviews:
        if review.body:
            items.append({
                "type": "review_comment",
                "state": review.state,
                "text": _truncate(review.body),
            })

    # Issue comments
    comments = (
        await db.execute(
            select(IssueComment)
            .where(
                IssueComment.author_github_username
                == (
                    await db.execute(
                        select(Developer.github_username).where(
                            Developer.id == developer_id
                        )
                    )
                ).scalar_one(),
                IssueComment.created_at >= date_from,
                IssueComment.created_at <= date_to,
            )
            .order_by(IssueComment.created_at.desc())
            .limit(MAX_ITEMS_PER_CATEGORY)
        )
    ).scalars().all()
    for comment in comments:
        if comment.body:
            items.append({
                "type": "issue_comment",
                "text": _truncate(comment.body),
            })

    summary = (
        f"Developer {developer_id}: {len(prs)} PR descriptions, "
        f"{len(reviews)} review comments, {len(comments)} issue comments"
    )
    return items, summary


async def _gather_team_texts(
    db: AsyncSession,
    team_name: str,
    date_from: datetime,
    date_to: datetime,
) -> tuple[list[dict], str]:
    """Gather team-wide interactions for conflict analysis."""
    dev_rows = (
        await db.execute(
            select(Developer.id, Developer.github_username, Developer.display_name)
            .where(Developer.team == team_name, Developer.is_active.is_(True))
        )
    ).all()
    dev_ids = [r.id for r in dev_rows]
    dev_names = {r.id: r.display_name for r in dev_rows}

    items: list[dict] = []

    # Reviews between team members (especially CHANGES_REQUESTED)
    reviews = (
        await db.execute(
            select(PRReview, PullRequest.author_id, PullRequest.title)
            .join(PullRequest, PRReview.pr_id == PullRequest.id)
            .where(
                PRReview.reviewer_id.in_(dev_ids),
                PullRequest.author_id.in_(dev_ids),
                PRReview.submitted_at >= date_from,
                PRReview.submitted_at <= date_to,
            )
            .order_by(PRReview.submitted_at.desc())
            .limit(MAX_ITEMS_PER_CATEGORY)
        )
    ).all()
    for review, author_id, pr_title in reviews:
        if review.body:
            items.append({
                "type": "review",
                "reviewer": dev_names.get(review.reviewer_id, "unknown"),
                "author": dev_names.get(author_id, "unknown"),
                "state": review.state,
                "pr_title": pr_title,
                "text": _truncate(review.body),
            })

    summary = (
        f"Team '{team_name}': {len(dev_ids)} developers, "
        f"{len(reviews)} reviews analyzed"
    )
    return items, summary


async def _gather_scope_texts(
    db: AsyncSession,
    scope_type: str,
    scope_id: str,
    date_from: datetime,
    date_to: datetime,
) -> tuple[list[dict], str]:
    """Route to the right data gatherer based on scope."""
    if scope_type == "developer":
        return await _gather_developer_texts(db, int(scope_id), date_from, date_to)
    elif scope_type == "team":
        return await _gather_team_texts(db, scope_id, date_from, date_to)
    elif scope_type == "repo":
        # Sentiment for repo — gather all comments
        items: list[dict] = []
        repo_id = int(scope_id)

        reviews = (
            await db.execute(
                select(PRReview)
                .join(PullRequest, PRReview.pr_id == PullRequest.id)
                .where(
                    PullRequest.repo_id == repo_id,
                    PRReview.submitted_at >= date_from,
                    PRReview.submitted_at <= date_to,
                )
                .order_by(PRReview.submitted_at.desc())
                .limit(MAX_ITEMS_PER_CATEGORY)
            )
        ).scalars().all()
        for r in reviews:
            if r.body:
                items.append({"type": "review", "text": _truncate(r.body)})

        comments = (
            await db.execute(
                select(IssueComment)
                .join(Issue, IssueComment.issue_id == Issue.id)
                .where(
                    Issue.repo_id == repo_id,
                    IssueComment.created_at >= date_from,
                    IssueComment.created_at <= date_to,
                )
                .order_by(IssueComment.created_at.desc())
                .limit(MAX_ITEMS_PER_CATEGORY)
            )
        ).scalars().all()
        for c in comments:
            if c.body:
                items.append({"type": "issue_comment", "text": _truncate(c.body)})

        summary = f"Repo {repo_id}: {len(reviews)} reviews, {len(comments)} comments"
        return items, summary

    return [], "Unknown scope"


# --- Prompt Construction ---


SYSTEM_PROMPTS = {
    "communication": (
        "You are an engineering communication analyst. Analyze the developer's "
        "PR descriptions, review comments, and issue comments. Evaluate clarity, "
        "constructiveness, responsiveness, and tone. Respond in JSON with this schema: "
        '{"clarity_score": int (1-10), "constructiveness_score": int (1-10), '
        '"responsiveness_score": int (1-10), "tone_score": int (1-10), '
        '"observations": [str], "recommendations": [str]}'
    ),
    "conflict": (
        "You are a team dynamics analyst. Analyze team interactions in code reviews "
        "to identify friction patterns. Focus on CHANGES_REQUESTED reviews, recurring "
        "friction between specific pairs, and whether feedback is constructive. "
        "Respond in JSON with this schema: "
        '{"conflict_score": int (1-10), "friction_pairs": [{"reviewer": str, "author": str, '
        '"pattern": str}], "recurring_issues": [str], "recommendations": [str]}'
    ),
    "sentiment": (
        "You are a team morale analyst. Analyze the overall tone and sentiment "
        "across comments and PR descriptions. Respond in JSON with this schema: "
        '{"sentiment_score": int (1-10, 10=very positive), "trend": str '
        '("improving"|"stable"|"declining"), "notable_patterns": [str]}'
    ),
}


# --- Claude API Call ---


async def run_analysis(
    db: AsyncSession,
    analysis_type: str,
    scope_type: str,
    scope_id: str,
    date_from: datetime,
    date_to: datetime,
    triggered_by: str = "api",
    force: bool = False,
) -> AIAnalysis:
    """Run an AI analysis and store the result."""
    from app.services.ai_settings import (
        check_budget,
        check_feature_enabled,
        compute_cost,
        find_recent_analysis,
    )

    # --- Guards ---
    ai_settings = await check_feature_enabled(db, "general_analysis")

    budget_info = await check_budget(db, ai_settings)
    if budget_info["over_budget"]:
        from app.services.exceptions import AIBudgetExceededError

        raise AIBudgetExceededError()

    # Dedup: return cached result if recent (unless force=True)
    if not force:
        recent = await find_recent_analysis(
            db, analysis_type, scope_type, scope_id,
            ai_settings.cooldown_minutes,
        )
        if recent:
            # Create a lightweight pointer row so the caller knows it's reused
            reused = AIAnalysis(
                analysis_type=recent.analysis_type,
                scope_type=recent.scope_type,
                scope_id=recent.scope_id,
                date_from=recent.date_from,
                date_to=recent.date_to,
                input_summary=recent.input_summary,
                result=recent.result,
                raw_response=recent.raw_response,
                model_used=recent.model_used,
                tokens_used=0,
                input_tokens=0,
                output_tokens=0,
                estimated_cost_usd=0,
                reused_from_id=recent.id,
                triggered_by=triggered_by,
                created_at=datetime.now(timezone.utc),
            )
            db.add(reused)
            await db.commit()
            await db.refresh(reused)
            return reused

    # --- Data gathering ---
    items, input_summary = await _gather_scope_texts(
        db, scope_type, scope_id, date_from, date_to
    )

    if not items:
        analysis = AIAnalysis(
            analysis_type=analysis_type,
            scope_type=scope_type,
            scope_id=scope_id,
            date_from=date_from,
            date_to=date_to,
            input_summary=input_summary,
            result={"error": "No data available for the selected scope and date range"},
            model_used=MODEL,
            tokens_used=0,
            input_tokens=0,
            output_tokens=0,
            estimated_cost_usd=0,
            triggered_by=triggered_by,
            created_at=datetime.now(timezone.utc),
        )
        db.add(analysis)
        await db.commit()
        await db.refresh(analysis)
        return analysis

    system_prompt = SYSTEM_PROMPTS[analysis_type]
    user_content = json.dumps(items, indent=2)

    client = anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        max_retries=3,
        timeout=120.0,
    )
    response = await client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )

    raw_text = next(
        (b.text for b in response.content if b.type == "text"), ""
    )

    json_text = raw_text.strip()
    if json_text.startswith("```"):
        json_text = json_text.split("\n", 1)[-1]
        json_text = json_text.rsplit("```", 1)[0]

    try:
        result = json.loads(json_text)
    except json.JSONDecodeError:
        result = {"raw_text": raw_text, "parse_error": True}

    inp_tokens = response.usage.input_tokens
    out_tokens = response.usage.output_tokens
    tokens_used = inp_tokens + out_tokens
    est_cost = compute_cost(
        inp_tokens, out_tokens,
        ai_settings.input_token_price_per_million,
        ai_settings.output_token_price_per_million,
    )

    analysis = AIAnalysis(
        analysis_type=analysis_type,
        scope_type=scope_type,
        scope_id=scope_id,
        date_from=date_from,
        date_to=date_to,
        input_summary=input_summary,
        result=result,
        raw_response=raw_text,
        model_used=MODEL,
        tokens_used=tokens_used,
        input_tokens=inp_tokens,
        output_tokens=out_tokens,
        estimated_cost_usd=est_cost,
        triggered_by=triggered_by,
        created_at=datetime.now(timezone.utc),
    )
    db.add(analysis)
    await db.commit()
    await db.refresh(analysis)
    return analysis


# --- Helper: call Claude and store result ---


async def _call_claude_and_store(
    db: AsyncSession,
    system_prompt: str,
    user_content: str,
    analysis_type: str,
    scope_type: str,
    scope_id: str,
    date_from: datetime,
    date_to: datetime,
    input_summary: str,
    triggered_by: str = "api",
) -> AIAnalysis:
    """Shared helper: call Claude API, parse JSON response, store in ai_analyses."""
    from app.services.ai_settings import compute_cost, get_ai_settings

    client = anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        max_retries=3,
        timeout=120.0,
    )
    response = await client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )

    raw_text = next((b.text for b in response.content if b.type == "text"), "")

    json_text = raw_text.strip()
    if json_text.startswith("```"):
        json_text = json_text.split("\n", 1)[-1]
        json_text = json_text.rsplit("```", 1)[0]

    try:
        result = json.loads(json_text)
    except json.JSONDecodeError:
        result = {"raw_text": raw_text, "parse_error": True}

    inp_tokens = response.usage.input_tokens
    out_tokens = response.usage.output_tokens
    tokens_used = inp_tokens + out_tokens

    ai_settings = await get_ai_settings(db)
    est_cost = compute_cost(
        inp_tokens, out_tokens,
        ai_settings.input_token_price_per_million,
        ai_settings.output_token_price_per_million,
    )

    analysis = AIAnalysis(
        analysis_type=analysis_type,
        scope_type=scope_type,
        scope_id=scope_id,
        date_from=date_from,
        date_to=date_to,
        input_summary=input_summary,
        result=result,
        raw_response=raw_text,
        model_used=MODEL,
        tokens_used=tokens_used,
        input_tokens=inp_tokens,
        output_tokens=out_tokens,
        estimated_cost_usd=est_cost,
        triggered_by=triggered_by,
        created_at=datetime.now(timezone.utc),
    )
    db.add(analysis)
    await db.commit()
    await db.refresh(analysis)
    return analysis


# --- M7: 1:1 Prep Brief ---


ONE_ON_ONE_SYSTEM_PROMPT = """You are an engineering manager's assistant preparing a 1:1 meeting brief.
Analyze the developer's activity data and produce a structured JSON brief.

Respond ONLY with valid JSON matching this schema:
{
  "period_summary": "2-3 sentences on what they shipped and activity level",
  "metrics_highlights": [
    {"metric": "string", "value": "string", "context": "string", "concern_level": "none|low|moderate|high"}
  ],
  "notable_work": ["string descriptions of significant contributions"],
  "suggested_talking_points": [
    {"topic": "string", "framing": "ready-to-use constructive language for the manager", "evidence": "string"}
  ],
  "goal_progress": [
    {"title": "string", "status": "string", "current_value": "string"}
  ]
}

KEY GUIDELINES:
- The "framing" field must provide ready-to-use language that is constructive, never accusatory
- Focus on patterns, not individual incidents
- Highlight both strengths and growth areas
- If metrics are below team benchmarks, frame as opportunities, not problems
- If issue_creator_stats is present, analyze the developer's issue quality patterns:
  compare their checklist usage, reopen rate, not-planned rate, and close times against
  team averages. Surface actionable insights like "Issues without checklists take longer to close"
  or "High reopen rate may indicate unclear acceptance criteria"."""


async def run_one_on_one_prep(
    db: AsyncSession,
    developer_id: int,
    date_from: datetime,
    date_to: datetime,
    force: bool = False,
) -> AIAnalysis:
    """Generate a structured 1:1 prep brief for a developer."""
    from app.services.ai_settings import (
        check_budget,
        check_feature_enabled,
        find_recent_analysis,
    )

    # --- Guards ---
    ai_settings = await check_feature_enabled(db, "one_on_one_prep")

    budget_info = await check_budget(db, ai_settings)
    if budget_info["over_budget"]:
        from app.services.exceptions import AIBudgetExceededError

        raise AIBudgetExceededError()

    if not force:
        recent = await find_recent_analysis(
            db, "one_on_one_prep", "developer", str(developer_id),
            ai_settings.cooldown_minutes,
        )
        if recent:
            reused = AIAnalysis(
                analysis_type=recent.analysis_type,
                scope_type=recent.scope_type,
                scope_id=recent.scope_id,
                date_from=recent.date_from,
                date_to=recent.date_to,
                input_summary=recent.input_summary,
                result=recent.result,
                raw_response=recent.raw_response,
                model_used=recent.model_used,
                tokens_used=0,
                input_tokens=0,
                output_tokens=0,
                estimated_cost_usd=0,
                reused_from_id=recent.id,
                triggered_by="api",
                created_at=datetime.now(timezone.utc),
            )
            db.add(reused)
            await db.commit()
            await db.refresh(reused)
            return reused

    from app.services.goals import get_goal_progress, list_goals
    from app.services.stats import (
        get_benchmarks,
        get_developer_stats,
        get_developer_trends,
        get_issue_creator_stats,
    )

    dev = await db.get(Developer, developer_id)

    # 1. Developer stats for the period
    stats = await get_developer_stats(db, developer_id, date_from, date_to)

    # 2. Trend data — last 4 periods
    trends = await get_developer_trends(db, developer_id, periods=4, period_type="week")

    # 3. Team benchmarks for comparison
    benchmarks = await get_benchmarks(db, team=dev.team, date_from=date_from, date_to=date_to)

    # 4. PRs merged/opened with titles
    prs = (
        await db.execute(
            select(PullRequest.number, PullRequest.title, PullRequest.state, PullRequest.is_merged, PullRequest.html_url)
            .where(
                PullRequest.author_id == developer_id,
                PullRequest.created_at >= date_from,
                PullRequest.created_at <= date_to,
            )
            .order_by(PullRequest.created_at.desc())
            .limit(30)
        )
    ).all()

    # 5. Review activity summary with quality tiers (M1)
    review_quality_rows = (
        await db.execute(
            select(PRReview.quality_tier, func.count())
            .where(
                PRReview.reviewer_id == developer_id,
                PRReview.submitted_at >= date_from,
                PRReview.submitted_at <= date_to,
            )
            .group_by(PRReview.quality_tier)
        )
    ).all()

    # 6. Active goals with progress (M6)
    goals = await list_goals(db, developer_id)
    goal_data = []
    for goal in goals:
        if goal.status == "active":
            progress = await get_goal_progress(db, goal.id)
            if progress:
                goal_data.append({
                    "title": progress.title,
                    "target_value": progress.target_value,
                    "target_direction": progress.target_direction,
                    "current_value": progress.current_value,
                    "baseline_value": progress.baseline_value,
                    "status": progress.status,
                })

    # 7. Last 1:1 brief for continuity
    last_brief_result = await db.execute(
        select(AIAnalysis)
        .where(
            AIAnalysis.analysis_type == "one_on_one_prep",
            AIAnalysis.scope_type == "developer",
            AIAnalysis.scope_id == str(developer_id),
        )
        .order_by(AIAnalysis.created_at.desc())
        .limit(1)
    )
    last_brief = last_brief_result.scalar_one_or_none()

    # 8. Issue creator stats — include if this developer has created issues
    issue_creator_context = None
    has_created_issues = (
        await db.execute(
            select(func.count()).select_from(Issue).where(
                Issue.creator_github_username == dev.github_username,
                Issue.created_at >= date_from,
                Issue.created_at <= date_to,
            )
        )
    ).scalar_one()
    if has_created_issues > 0:
        creator_stats_resp = await get_issue_creator_stats(
            db, team=dev.team, date_from=date_from, date_to=date_to
        )
        # Find this developer's entry in the per-creator list
        dev_creator = next(
            (c for c in creator_stats_resp.creators if c.github_username == dev.github_username),
            None,
        )
        if dev_creator:
            issue_creator_context = {
                "developer_stats": dev_creator.model_dump(),
                "team_averages": creator_stats_resp.team_averages.model_dump(),
            }

    # Build the context document for Claude
    context = {
        "developer": {
            "name": dev.display_name,
            "team": dev.team,
            "role": dev.role,
        },
        "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "stats": stats.model_dump(),
        "trends": {
            "periods": [p.model_dump() for p in trends.periods],
            "directions": {k: v.model_dump() for k, v in trends.trends.items()},
        },
        "benchmarks": {
            "sample_size": benchmarks.sample_size,
            "metrics": {k: v.model_dump() for k, v in benchmarks.metrics.items()},
        } if benchmarks.metrics else None,
        "prs": [
            {"number": pr.number, "title": pr.title, "state": pr.state, "merged": pr.is_merged, "url": pr.html_url}
            for pr in prs
        ],
        "review_quality": {tier: count for tier, count in review_quality_rows},
        "goals": goal_data,
        "previous_brief": {
            "period_summary": last_brief.result.get("period_summary"),
            "suggested_talking_points": last_brief.result.get("suggested_talking_points"),
        } if last_brief and last_brief.result and not last_brief.result.get("parse_error") else None,
        "issue_creator_stats": issue_creator_context,
    }

    input_summary = (
        f"1:1 prep for {dev.display_name}: {stats.prs_merged} PRs merged, "
        f"{stats.reviews_given.approved + stats.reviews_given.changes_requested + stats.reviews_given.commented} reviews given, "
        f"{len(goal_data)} active goals"
    )

    return await _call_claude_and_store(
        db=db,
        system_prompt=ONE_ON_ONE_SYSTEM_PROMPT,
        user_content=json.dumps(context, indent=2, default=str),
        analysis_type="one_on_one_prep",
        scope_type="developer",
        scope_id=str(developer_id),
        date_from=date_from,
        date_to=date_to,
        input_summary=input_summary,
    )


# --- M8: Team Health Check ---


TEAM_HEALTH_SYSTEM_PROMPT = """You are an engineering team health analyst.
Analyze the team's activity data, workload balance, collaboration patterns, and communication
to produce a comprehensive health assessment.

Respond ONLY with valid JSON matching this schema:
{
  "overall_health_score": "<int 1-10>",
  "velocity_assessment": "string on sustainable shipping pace",
  "workload_concerns": [
    {"concern": "string description", "suggestion": "actionable suggestion"}
  ],
  "collaboration_patterns": "string assessment of teamwork and silos",
  "communication_flags": [
    {"severity": "low|medium|high", "observation": "string"}
  ],
  "process_recommendations": ["actionable process improvement strings"],
  "strengths": ["positive observations to reinforce"],
  "action_items": [
    {"priority": "high|medium|low", "action": "string", "owner": "manager|lead|team"}
  ]
}

KEY GUIDELINES:
- overall_health_score: 1-10, be honest but fair
- Focus on systemic patterns, not individual blame
- Communication flags should cite specific patterns from the review/comment data
- Action items must be concrete and assignable
- Strengths are important — always include at least 2-3 positive observations"""


async def run_team_health(
    db: AsyncSession,
    team: str | None,
    date_from: datetime,
    date_to: datetime,
    force: bool = False,
) -> AIAnalysis:
    """Generate a comprehensive team health assessment."""
    from app.services.ai_settings import (
        check_budget,
        check_feature_enabled,
        find_recent_analysis,
    )

    # --- Guards ---
    ai_settings = await check_feature_enabled(db, "team_health")

    budget_info = await check_budget(db, ai_settings)
    if budget_info["over_budget"]:
        from app.services.exceptions import AIBudgetExceededError

        raise AIBudgetExceededError()

    scope_id = team or "all"
    if not force:
        recent = await find_recent_analysis(
            db, "team_health", "team", scope_id,
            ai_settings.cooldown_minutes,
        )
        if recent:
            reused = AIAnalysis(
                analysis_type=recent.analysis_type,
                scope_type=recent.scope_type,
                scope_id=recent.scope_id,
                date_from=recent.date_from,
                date_to=recent.date_to,
                input_summary=recent.input_summary,
                result=recent.result,
                raw_response=recent.raw_response,
                model_used=recent.model_used,
                tokens_used=0,
                input_tokens=0,
                output_tokens=0,
                estimated_cost_usd=0,
                reused_from_id=recent.id,
                triggered_by="api",
                created_at=datetime.now(timezone.utc),
            )
            db.add(reused)
            await db.commit()
            await db.refresh(reused)
            return reused

    from app.services.collaboration import get_collaboration
    from app.services.stats import get_benchmarks, get_team_stats, get_workload

    # 1. Team stats + benchmarks
    team_stats = await get_team_stats(db, team=team, date_from=date_from, date_to=date_to)
    benchmarks = await get_benchmarks(db, team=team, date_from=date_from, date_to=date_to)

    # 2. Workload balance (M4)
    workload = await get_workload(db, team=team, date_from=date_from, date_to=date_to)

    # 3. Collaboration matrix with insights (M5)
    collaboration = await get_collaboration(db, team=team, date_from=date_from, date_to=date_to)

    # 4. CHANGES_REQUESTED reviews with body text + metadata (up to 60)
    dev_query = select(Developer.id, Developer.display_name).where(Developer.is_active.is_(True))
    if team:
        dev_query = dev_query.where(Developer.team == team)
    dev_result = await db.execute(dev_query)
    dev_rows = dev_result.all()
    dev_ids = [r.id for r in dev_rows]
    dev_names = {r.id: r.display_name for r in dev_rows}

    cr_reviews = []
    if dev_ids:
        cr_result = (
            await db.execute(
                select(PRReview, PullRequest.author_id, PullRequest.title, PullRequest.number)
                .join(PullRequest, PRReview.pr_id == PullRequest.id)
                .where(
                    PRReview.state == "CHANGES_REQUESTED",
                    PRReview.reviewer_id.in_(dev_ids),
                    PRReview.submitted_at >= date_from,
                    PRReview.submitted_at <= date_to,
                )
                .order_by(PRReview.submitted_at.desc())
                .limit(60)
            )
        ).all()
        for review, author_id, pr_title, pr_number in cr_result:
            cr_reviews.append({
                "reviewer": dev_names.get(review.reviewer_id, "external"),
                "author": dev_names.get(author_id, "external"),
                "pr": f"#{pr_number} {pr_title}",
                "body": _truncate(review.body),
                "submitted_at": review.submitted_at.isoformat() if review.submitted_at else None,
            })

    # 5. High back-and-forth issue threads (3+ comments between 2 people)
    heated_threads = []
    if dev_ids:
        # Find issues with 3+ comments from tracked devs
        dev_usernames_result = await db.execute(
            select(Developer.id, Developer.github_username).where(Developer.id.in_(dev_ids))
        )
        dev_username_map = {r.github_username: r.id for r in dev_usernames_result.all()}
        dev_name_by_username = {}
        for uname, did in dev_username_map.items():
            dev_name_by_username[uname] = dev_names.get(did, uname)

        # Get issues with many comments in the period
        busy_issues_result = await db.execute(
            select(IssueComment.issue_id, func.count().label("cnt"))
            .where(
                IssueComment.created_at >= date_from,
                IssueComment.created_at <= date_to,
            )
            .group_by(IssueComment.issue_id)
            .having(func.count() >= 3)
            .order_by(func.count().desc())
            .limit(20)
        )
        busy_issue_ids = [r.issue_id for r in busy_issues_result.all()]

        for issue_id in busy_issue_ids:
            # Fetch full comment thread in chronological order
            issue = await db.get(Issue, issue_id)
            if not issue:
                continue

            comments_result = await db.execute(
                select(IssueComment)
                .where(IssueComment.issue_id == issue_id)
                .order_by(IssueComment.created_at.asc())
            )
            comments = list(comments_result.scalars().all())

            # Check if there's back-and-forth between 2 people
            authors_in_thread = set()
            for c in comments:
                if c.author_github_username:
                    authors_in_thread.add(c.author_github_username)

            # Only include threads involving tracked devs with back-and-forth
            tracked_in_thread = authors_in_thread & set(dev_username_map.keys())
            if len(tracked_in_thread) < 2:
                continue

            # Build chronological dialogue
            dialogue = []
            prev_time = None
            for c in comments:
                gap_hours = None
                if prev_time and c.created_at:
                    gap_hours = round((c.created_at - prev_time).total_seconds() / 3600, 1)
                if c.created_at:
                    prev_time = c.created_at

                dialogue.append({
                    "author": dev_name_by_username.get(
                        c.author_github_username, c.author_github_username or "unknown"
                    ),
                    "body": _truncate(c.body),
                    "timestamp": c.created_at.isoformat() if c.created_at else None,
                    "hours_since_previous": gap_hours,
                })

            heated_threads.append({
                "issue": f"#{issue.number} {issue.title}",
                "comment_count": len(comments),
                "participants": [
                    dev_name_by_username.get(u, u) for u in tracked_in_thread
                ],
                "dialogue": dialogue,
            })

    # 6. Goal progress across team (M6) — batch query instead of per-dev
    team_goals = []
    if dev_ids:
        all_goals_result = await db.execute(
            select(DeveloperGoal).where(
                DeveloperGoal.developer_id.in_(dev_ids),
                DeveloperGoal.status == "active",
            )
        )
        all_goals = list(all_goals_result.scalars().all())
        for goal in all_goals:
            # Compute current value for each goal
            from app.services.goals import _get_metric_value
            current_value = await _get_metric_value(
                db, goal.developer_id, goal.metric_key, date_from, date_to
            )
            team_goals.append({
                "developer": dev_names.get(goal.developer_id, "unknown"),
                "title": goal.title,
                "metric_key": goal.metric_key,
                "target_value": goal.target_value,
                "current_value": round(current_value, 2),
                "target_direction": goal.target_direction,
                "status": goal.status,
            })

    # Build context document
    context = {
        "team": team or "all",
        "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "team_stats": team_stats.model_dump(),
        "benchmarks": {
            "sample_size": benchmarks.sample_size,
            "metrics": {k: v.model_dump() for k, v in benchmarks.metrics.items()},
        } if benchmarks.metrics else None,
        "workload": {
            "developers": [d.model_dump() for d in workload.developers],
            "alerts": [a.model_dump() for a in workload.alerts],
        },
        "collaboration": {
            "insights": collaboration.insights.model_dump(),
            "pair_count": len(collaboration.matrix),
        },
        "changes_requested_reviews": cr_reviews,
        "heated_threads": heated_threads,
        "team_goals": team_goals,
    }

    scope_id = team or "all"
    input_summary = (
        f"Team health for '{scope_id}': {team_stats.developer_count} devs, "
        f"{team_stats.total_prs} PRs, {len(cr_reviews)} CR reviews, "
        f"{len(heated_threads)} heated threads, {len(workload.alerts)} workload alerts"
    )

    return await _call_claude_and_store(
        db=db,
        system_prompt=TEAM_HEALTH_SYSTEM_PROMPT,
        user_content=json.dumps(context, indent=2, default=str),
        analysis_type="team_health",
        scope_type="team",
        scope_id=scope_id,
        date_from=date_from,
        date_to=date_to,
        input_summary=input_summary,
    )
