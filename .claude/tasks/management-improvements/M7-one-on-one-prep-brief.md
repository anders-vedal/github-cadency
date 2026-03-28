# Task M7: 1:1 Prep Brief (AI)

## Phase
Management Phase 3 — Phase 4 (AI-powered)

## Status
completed

## Blocked By
- 09-ai-analysis-service
- M1-review-quality-signals
- M2-team-benchmarks
- M3-trend-lines
- M6-developer-goals

## Blocks
None

## Description
Add a new AI analysis type `one_on_one_prep` that generates structured 1:1 meeting briefs with period summary, metric highlights, notable work, suggested talking points with ready-to-use framing, and goal progress. Corresponds to DEVPULSE_MANAGEMENT_FEATURES.md section M5.

## Deliverables

### backend/app/services/ai_analysis.py (extend)
**New analysis type: `one_on_one_prep`**

Data gathering before Claude API call:
1. Developer's stats for the period (from stats service)
2. Developer's trend data — last 4 periods (from M3 trends)
3. Team benchmarks for comparison (from M2 benchmarks)
4. List of PRs merged/opened with titles
5. Review activity summary: given + received, quality tiers (from M1)
6. Active goals for this developer with progress (from M6)
7. Last 1:1 brief if one exists (for continuity — query ai_analyses)

**Prompt design:**
Instruct Claude to produce structured JSON output:
- `period_summary`: 2-3 sentences on what they shipped and activity level
- `metrics_highlights`: array of notable metrics with value, context, and concern_level (none/low/moderate/high)
- `notable_work`: array of strings highlighting significant contributions
- `suggested_talking_points`: array with topic, framing (ready-to-use constructive language), and evidence
- `goal_progress`: array with goal title, status, and current value

**Key design:** The `framing` field provides ready-to-use language that is constructive, not accusatory. This is the highest-value part.

### backend/app/schemas/ (extend)
- `OneOnOnePrepResult` schema matching the output structure
- Add `one_on_one_prep` to the analysis_type enum

### Frontend: Developer Detail page (extend)
- "Prepare 1:1" button on Developer Detail page
- Opens panel/modal displaying the structured brief
- "Copy as markdown" button for pasting into manager's notes app
- Display previous 1:1 briefs in a collapsible history section
