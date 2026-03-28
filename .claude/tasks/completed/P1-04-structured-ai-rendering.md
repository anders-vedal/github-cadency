# Task P1-04: Structured AI Result Rendering

## Phase
Phase 1 — Make It Usable

## Status
completed

## Blocked By
- M7-one-on-one-prep-brief
- M8-team-health-check

## Blocks
None

## Description
Replace raw `JSON.stringify(result, null, 2)` rendering of AI analysis results with structured, readable UI components. Currently, 1:1 prep briefs and team health checks — the most valuable AI features — are displayed as raw JSON in `<pre>` tags, making them unusable for non-technical managers.

## Deliverables

### frontend/src/components/ai/ (new directory)

**OneOnOnePrepView.tsx**
Renders the 1:1 prep brief result with sections:
- `period_summary` — styled paragraph with date range context
- `metrics_highlights` — table with metric name, value, concern level (color-coded: green/amber/red)
- `notable_work` — card list with PR titles (link to GitHub via `html_url` if available)
- `suggested_talking_points` — accordion/collapsible cards, each with a topic and framing text
- `goal_progress` — progress bars per active goal
- `areas_of_growth` / `areas_of_concern` — styled lists

**TeamHealthView.tsx**
Renders the team health check result with sections:
- `overall_health_score` — large gauge or colored badge
- `key_findings` — numbered list with severity indicators
- `workload_assessment` — per-developer summary cards
- `collaboration_health` — highlights from silo/bus-factor analysis
- `recommendations` — prioritized action items
- `risk_areas` — red-flagged items

**AnalysisResultRenderer.tsx**
Router component that selects the right view based on `analysis_type`:
- `one_on_one_prep` → `OneOnOnePrepView`
- `team_health` → `TeamHealthView`
- `communication` / `conflict` / `sentiment` → generic structured view with parsed JSON sections
- Fallback: formatted JSON with syntax highlighting (not raw `<pre>`)

### frontend/src/pages/AIAnalysis.tsx (rewrite)
- Add tabs or sections for: General Analysis, 1:1 Prep, Team Health
- 1:1 Prep section: developer selector dropdown + date range + "Generate Brief" button
- Team Health section: team selector + date range + "Generate Assessment" button
- History list uses `AnalysisResultRenderer` instead of `JSON.stringify`

### frontend/src/pages/DeveloperDetail.tsx (extend)
- Replace the raw JSON `<pre>` block (lines 171-173) with `AnalysisResultRenderer`
- Add a prominent "Generate 1:1 Prep Brief" button that calls `POST /api/ai/one-on-one-prep`

### backend/app/services/ai_analysis.py (minor fix)
- Add `html_url` to the PR data sent to Claude in the 1:1 brief context (currently only `number` and `title` are included)
- This allows Claude to include clickable GitHub links in `notable_work`

## Design Notes
- Use shadcn/ui Accordion for talking points, Badge for severity levels, Card for sections
- Color scheme: green (positive/on-track), amber (needs attention), red (concern/blocker)
- All sections should be collapsible for quick scanning
