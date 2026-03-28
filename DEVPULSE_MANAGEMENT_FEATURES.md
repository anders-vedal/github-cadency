# DevPulse — Management Features

This document specifies features that turn DevPulse from a raw stats dashboard into an actionable management tool. These build on top of the base spec in DEVPULSE_SPEC.md and should be implemented after Phase 3 (frontend).

---

## M1. Team-Relative Context

### Problem
Raw stats are meaningless without context. "Avg time-to-merge: 48h" tells the manager nothing unless they know what normal looks like for this team.

### Implementation

Add a `team_benchmarks` endpoint that computes percentile bands across all active developers for a given period.

**Endpoint:** `GET /api/stats/benchmarks?date_from=...&date_to=...&team=...`

**Response:**
```json
{
  "period": { "from": "...", "to": "..." },
  "sample_size": 18,
  "metrics": {
    "time_to_merge_h": { "p25": 12.3, "p50": 28.7, "p75": 52.1 },
    "time_to_first_review_h": { "p25": 1.2, "p50": 3.8, "p75": 8.4 },
    "prs_merged": { "p25": 3, "p50": 6, "p75": 11 },
    "review_turnaround_h": { "p25": 2.1, "p50": 5.5, "p75": 14.2 },
    "reviews_given": { "p25": 4, "p50": 9, "p75": 16 },
    "additions_per_pr": { "p25": 42, "p50": 128, "p75": 340 }
  }
}
```

**Developer stats extension:** Every `DeveloperStats` response gains a `percentiles` field showing where this developer falls on each metric:
```json
{
  "avg_time_to_merge_h": 52.3,
  "percentile_band": "above_p75",
  "team_median": 28.7
}
```

**Percentile bands:** `below_p25`, `p25_to_p50`, `p50_to_p75`, `above_p75`. The frontend renders these as colored indicators (not rankings) — green for "typical", amber for "notable", no red. The point is context, not punishment.

### Data layer
No new tables needed. Compute at query time from existing stats. If performance is an issue with 20+ devs, cache the benchmarks in a `team_benchmark_cache` table refreshed nightly.

---

## M2. Trend Lines

### Problem
A single period's stats are near-useless for performance conversations. Managers need to see direction: improving, declining, or flat.

### Implementation

**Endpoint:** `GET /api/stats/developer/{id}/trends?periods=8&period_type=week`

Computes the same stats as the regular developer stats endpoint, but returns an array of period buckets.

**Parameters:**
- `periods`: number of buckets (default: 8)
- `period_type`: `week` | `sprint` | `month` (default: week)
- `sprint_length_days`: only used when period_type=sprint (default: 14)

**Response:**
```json
{
  "developer_id": 5,
  "period_type": "week",
  "periods": [
    {
      "start": "2026-03-16",
      "end": "2026-03-22",
      "prs_merged": 4,
      "avg_time_to_merge_h": 22.1,
      "reviews_given": 7,
      "additions": 842,
      "deletions": 310,
      "issues_closed": 3
    },
    // ... 7 more periods
  ],
  "trends": {
    "prs_merged": { "direction": "stable", "change_pct": 5.2 },
    "avg_time_to_merge_h": { "direction": "worsening", "change_pct": 38.7 },
    "reviews_given": { "direction": "improving", "change_pct": -22.0 }
  }
}
```

**Trend calculation:** Linear regression over the period buckets. Direction is `improving` / `stable` / `worsening` based on slope magnitude. Note that "improving" means different things for different metrics — lower is better for time_to_merge, higher is better for reviews_given. The service must know the polarity of each metric.

**Metric polarity map (hardcoded in service):**
- Lower is better: time_to_merge_h, time_to_first_review_h, time_to_close_issue_h
- Higher is better: prs_merged, reviews_given, issues_closed
- Neutral (no direction judgment): additions, deletions, changed_files

### Frontend
Render trends as sparklines on the developer detail page. Color-code the trend direction subtly (don't make it look like a report card).

---

## M3. Workload Balance

### Problem
Before attributing slow output to poor performance, the manager needs to see if the developer is simply overloaded — or if work is unevenly distributed across the team.

### Implementation

**Endpoint:** `GET /api/stats/workload?date_from=...&date_to=...&team=...`

**Response:**
```json
{
  "developers": [
    {
      "developer_id": 5,
      "display_name": "Kari Nordmann",
      "open_prs_authored": 3,
      "open_prs_reviewing": 7,
      "open_issues_assigned": 12,
      "reviews_given_this_period": 24,
      "reviews_received_this_period": 6,
      "prs_waiting_for_review": 2,
      "avg_review_wait_h": 18.3,
      "workload_score": "high"
    }
  ],
  "alerts": [
    {
      "type": "review_bottleneck",
      "developer_id": 5,
      "message": "Kari has reviewed 24 PRs this period (team median: 9). She may be a review bottleneck."
    },
    {
      "type": "stale_prs",
      "developer_id": 12,
      "message": "Ola has 2 PRs waiting >48h for review."
    },
    {
      "type": "uneven_assignment",
      "message": "Issue assignment is concentrated: top 3 developers hold 64% of open issues."
    }
  ]
}
```

**Workload score heuristic:** Combine open PRs authored + open PRs reviewing + open issues assigned, weighted by team median. Score as `low` / `balanced` / `high` / `overloaded`. This is a rough heuristic, not a precise measurement — label it as such in the UI.

**Alerts:** Computed server-side with simple threshold rules:
- `review_bottleneck`: reviews_given > 2x team median
- `stale_prs`: any PR waiting for first review > 48h
- `uneven_assignment`: top 20% of devs hold > 50% of open issues
- `underutilized`: developer has 0 PRs and 0 reviews in the period

---

## M4. Review Quality Signals

### Problem
Review count is a vanity metric. A single "LGTM" approval and a detailed 15-comment code review both count as 1 review. Managers need to distinguish meaningful reviews from rubber stamps.

### Implementation

**Classify reviews into quality tiers at sync time.** Add two columns to `pr_reviews`:

```sql
ALTER TABLE pr_reviews ADD COLUMN body_length integer DEFAULT 0;
ALTER TABLE pr_reviews ADD COLUMN quality_tier varchar(20) DEFAULT 'minimal';
```

**Quality tier rules (computed on upsert, no AI needed):**
- `thorough`: body > 500 chars, or 3+ inline review comments, or CHANGES_REQUESTED with body > 100 chars, or 3+ architectural comments
- `standard`: body 100-500 chars, or CHANGES_REQUESTED (any length), or body contains code blocks, or has blocker comment
- `rubber_stamp`: state=APPROVED with body < 20 chars and 0 inline comments
- `minimal`: everything else

**Stats extension:** `DeveloperStats` gains:
```json
{
  "reviews_given": 14,
  "review_quality_breakdown": {
    "rubber_stamp": 3,
    "minimal": 4,
    "standard": 5,
    "thorough": 2
  },
  "review_quality_score": 6.2
}
```

**Review quality score formula:** `(rubber_stamp * 0 + minimal * 1 + standard * 3 + thorough * 5) / total_reviews`. Normalized to 0-10 scale.

**Comment type categorization (P4-03):** Each inline review comment is classified at sync time into one of 7 types: `nit`, `blocker`, `architectural`, `question`, `praise`, `suggestion`, `general`. Classification uses keyword/prefix detection (e.g., "nit:" prefix → nit, "security issue" content → blocker, GitHub ` ```suggestion` blocks → suggestion). Priority ordering ensures explicit prefixes win over loose patterns (e.g., "nit: why?" → nit, not question).

Comment types feed back into quality tier classification:
- Reviews with a `blocker` comment → minimum `standard` tier
- Reviews with 3+ `architectural` comments → `thorough` tier regardless of body length

**Comment type stats** added to `DeveloperStats`:
```json
{
  "comment_type_distribution": {"nit": 8, "blocker": 2, "suggestion": 5, ...},
  "nit_ratio": 0.23,
  "blocker_catch_rate": 0.125
}
```

- `nit_ratio` — fraction of all comments that are nits (high ratio may indicate over-focus on style)
- `blocker_catch_rate` — fraction of reviews containing ≥1 blocker comment

**AI enhancement (on-demand):** When a manager triggers AI analysis for a developer, the AI module can additionally assess the *content* of their reviews — are they catching real issues, suggesting improvements, or just nitpicking style? This requires reading the actual review text and is expensive, so it only runs when explicitly requested.

---

## M5. 1:1 Prep Brief

### Problem
The manager has 19 direct reports. Preparing for each 1:1 takes 15-20 minutes of digging through GitHub. That's 5+ hours per sprint just on prep.

### Implementation

**New AI analysis type:** `one_on_one_prep`

**Endpoint:** `POST /api/ai/analyze`
```json
{
  "analysis_type": "one_on_one_prep",
  "scope_type": "developer",
  "scope_id": "5",
  "date_from": "2026-03-14T00:00:00Z",
  "date_to": "2026-03-28T00:00:00Z"
}
```

**Data gathered before sending to Claude:**
1. Developer's stats for the period (from stats service)
2. Developer's trend data (last 4 periods)
3. Team benchmarks for comparison
4. List of PRs merged/opened with titles
5. Review activity summary (given + received, quality tiers)
6. Any open goals for this developer (see M6)
7. Last 1:1 brief if one exists (for continuity)

**Prompt instructs Claude to produce:**
```json
{
  "period_summary": "String — 2-3 sentences on what they shipped and how active they were.",
  "metrics_highlights": [
    {
      "metric": "time_to_merge_h",
      "value": 52.3,
      "context": "Above team p75 (28.7h). Has been climbing for 3 weeks.",
      "concern_level": "moderate"
    }
  ],
  "notable_work": [
    "Led the auth refactor (#342) — large PR, well-reviewed, merged cleanly.",
    "Reviewed 12 PRs this sprint, mostly in the payments repo."
  ],
  "suggested_talking_points": [
    {
      "topic": "PR cycle time trending up",
      "framing": "Your PRs are taking longer to merge recently. Is something blocking you, or are these larger changes? Let's see if we can break them down.",
      "evidence": "PRs #351, #358 both took >4 days. Previous sprint avg was 1.5 days."
    },
    {
      "topic": "Strong review contribution",
      "framing": "You've been carrying a lot of the review load — I appreciate that. Are you comfortable with the volume or should we redistribute?",
      "evidence": "12 reviews given (team median: 9), quality score 7.8."
    }
  ],
  "goal_progress": [
    {
      "goal": "Reduce avg PR size to < 200 lines",
      "status": "on_track",
      "current": "Avg 178 lines (was 340 last month)"
    }
  ]
}
```

**Key design choice:** The `framing` field in suggested talking points gives the manager ready-to-use language that is constructive, not accusatory. This is the most valuable part. The manager can use it verbatim or adapt it.

**Frontend:** Add a "Prepare 1:1" button on the Developer Detail page. Opens a panel with the structured brief. Include a "Copy as markdown" button for pasting into the manager's notes.

---

## M6. Developer Goals

### Problem
After a 1:1 where you've identified an area for improvement, there's no way to track whether the developer actually improves. You forget by next sprint, or you re-discover the same issue and have the same conversation.

### Implementation

**New table: `developer_goals`**

| Column | Type | Notes |
|--------|------|-------|
| id | serial PK | |
| developer_id | FK → developers | NOT NULL |
| title | varchar(255) | "Reduce avg PR size" |
| description | text | Longer context |
| metric_key | varchar(100) | Which metric to track: avg_pr_additions, time_to_merge_h, reviews_given, review_quality_score, etc. |
| target_value | float | The target number |
| target_direction | varchar(10) | "below" or "above" — is the goal to get the metric below or above the target? |
| baseline_value | float | Value when goal was set |
| status | varchar(20) | active, achieved, abandoned |
| created_at | timestamptz | |
| target_date | date | Optional deadline |
| achieved_at | timestamptz | |
| notes | text | Manager notes on progress |

**Endpoints:**
```
POST   /api/goals                       Create a goal for a developer
GET    /api/goals?developer_id=5        List goals for a developer
PATCH  /api/goals/{id}                  Update goal (status, notes)
GET    /api/goals/{id}/progress         Get current metric value vs target over time
```

**Progress tracking:** The `/progress` endpoint computes the metric's current value and returns a time series showing the trajectory toward the goal. No AI needed — pure stats.

```json
{
  "goal_id": 3,
  "title": "Reduce avg PR size to < 200 lines",
  "target_value": 200,
  "target_direction": "below",
  "baseline_value": 340,
  "current_value": 178,
  "status": "on_track",
  "history": [
    { "period": "2026-W10", "value": 340 },
    { "period": "2026-W11", "value": 285 },
    { "period": "2026-W12", "value": 210 },
    { "period": "2026-W13", "value": 178 }
  ]
}
```

**Auto-achievement:** When the metric crosses the target for 2 consecutive periods, the system marks the goal as `achieved` (but doesn't notify — the manager confirms in the next 1:1).

**1:1 integration:** The 1:1 prep brief (M5) automatically includes goal progress for all active goals.

---

## M7. Collaboration Matrix

### Problem
Managers need to identify silos (teams that don't review each other's code), bus factors (one person reviews all PRs for a critical repo), and underconnected developers (new hires who aren't yet integrated into the review culture).

### Implementation

**Endpoint:** `GET /api/stats/collaboration?date_from=...&date_to=...&team=...`

**Response:**
```json
{
  "matrix": [
    {
      "reviewer": { "id": 5, "name": "Kari", "team": "Platform" },
      "author": { "id": 8, "name": "Ola", "team": "Product" },
      "reviews_count": 12,
      "approvals": 9,
      "changes_requested": 3
    }
  ],
  "insights": {
    "silos": [
      "Platform team members reviewed 0 PRs from Product team this period."
    ],
    "bus_factors": [
      { "repo": "payment-service", "sole_reviewer": "Kari", "review_share_pct": 87 }
    ],
    "isolated_developers": [
      { "developer": "New Dev", "reviews_given": 0, "reviews_received_from_unique": 1 }
    ],
    "strongest_pairs": [
      { "pair": ["Kari", "Ola"], "mutual_reviews": 18 }
    ]
  }
}
```

**Bus factor calculation:** For each repo, compute what percentage of reviews came from each reviewer. If any single reviewer accounts for > 70% of reviews, flag as bus factor risk.

**Frontend:** Render the matrix as a heatmap grid (reviewers on Y axis, authors on X axis, color intensity = review count). Highlight silos and bus factors visually.

---

## M8. Team Health Check (AI)

### Problem
The manager wants a monthly or quarterly summary of team dynamics that goes beyond what numbers can show.

### Implementation

**New AI analysis type:** `team_health`

**Data gathered:**
1. Full team stats + benchmarks for the period
2. Workload balance data (M3)
3. Collaboration matrix (M7)
4. All `CHANGES_REQUESTED` reviews with body text (up to 60)
5. Any issue comments with high back-and-forth (3+ comments on same issue between 2 people)
6. Goal progress for all active goals across the team

**Output structure:**
```json
{
  "overall_health_score": 7.2,
  "velocity_assessment": "String — is the team shipping at a sustainable pace?",
  "workload_concerns": [
    "Kari is carrying a disproportionate review load. Consider designating a second reviewer for payment-service."
  ],
  "collaboration_patterns": "String — are people working together well? Any silos?",
  "communication_flags": [
    {
      "severity": "low",
      "observation": "Review comments in infrastructure repo tend to be terse. May reflect time pressure rather than friction."
    }
  ],
  "process_recommendations": [
    "3 of 5 slow-to-merge PRs this period had no description. Consider enforcing PR templates.",
    "Issue assignment is manual and uneven. Consider a round-robin or sprint planning allocation."
  ],
  "strengths": [
    "Cross-team code review has increased 40% since last period.",
    "Average review quality score improved from 5.1 to 6.8."
  ],
  "action_items": [
    { "priority": "high", "action": "Redistribute review load for payment-service", "owner": "manager" },
    { "priority": "medium", "action": "Enforce PR description template", "owner": "manager" },
    { "priority": "low", "action": "Pair new dev with senior for first month of reviews", "owner": "lead" }
  ]
}
```

---

## Implementation Order

These features build on each other. Recommended sequence:

1. **M4 — Review Quality Signals** (add during Phase 2, extends sync + stats, no AI)
2. **M1 — Team-Relative Context** (add during Phase 2, extends stats, no AI)
3. **M2 — Trend Lines** (add during Phase 2, extends stats, no AI)
4. **M3 — Workload Balance** (add during Phase 2-3, new endpoint, no AI)
5. **M7 — Collaboration Matrix** (add during Phase 3, new endpoint + frontend viz, no AI)
6. **M6 — Developer Goals** (add during Phase 3, new table + CRUD + frontend)
7. **M5 — 1:1 Prep Brief** (Phase 4, AI — depends on M1-M4 and M6 existing)
8. **M8 — Team Health Check** (Phase 4, AI — depends on M3 and M7 existing)

Features M1-M4 are pure computation with no AI cost. They provide the most management value per implementation effort and should ship before any AI features.

---

## Privacy and Trust Considerations

This tool surfaces individual developer metrics to their manager. Handle with care:

- **Developers should know this tool exists.** Don't deploy it secretly. Present it as a team improvement tool, not a surveillance tool.
- **Consider giving developers read access to their own data.** Let them see their own stats, trends, and how they compare to team medians. Self-awareness often fixes problems before the 1:1.
- **AI analysis results should not be shared with the developer verbatim.** The manager uses the brief to prepare, then has a human conversation. The developer sees metrics, not AI judgments about their communication.
- **Never use these metrics for compensation or termination decisions in isolation.** This tool provides signals, not verdicts. Always combine with qualitative judgment.
- **Log who views what.** Add an audit trail for who accessed which developer's stats and AI analyses. This builds trust and accountability.
