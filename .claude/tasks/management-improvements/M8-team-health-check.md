# Task M8: Team Health Check (AI)

## Phase
Management Phase 3 — Phase 4 (AI-powered)

## Status
completed

## Blocked By
- 09-ai-analysis-service
- M4-workload-balance
- M5-collaboration-matrix
- M1-review-quality-signals
- M2-team-benchmarks

## Blocks
None

## Description
Add a new AI analysis type `team_health` that produces a comprehensive team health assessment combining stats, workload, collaboration, and communication analysis. Corresponds to DEVPULSE_MANAGEMENT_FEATURES.md section M8.

## Deliverables

### backend/app/services/ai_analysis.py (extend)
**New analysis type: `team_health`**

Data gathering before Claude API call:
1. Full team stats + benchmarks for the period (M2)
2. Workload balance data (M4)
3. Collaboration matrix with insights (M5)
4. All CHANGES_REQUESTED reviews with body text (up to 60)
5. Issue comments with high back-and-forth (3+ comments on same issue between 2 people)
6. Goal progress for all active goals across the team (M6, if available)

**Prompt design:**
Instruct Claude to produce structured JSON output:
- `overall_health_score`: 1-10 numeric score
- `velocity_assessment`: string on sustainable shipping pace
- `workload_concerns`: array of specific concerns with actionable suggestions
- `collaboration_patterns`: string assessment of teamwork and silos
- `communication_flags`: array with severity (low/medium/high) and observation
- `process_recommendations`: array of actionable process improvements
- `strengths`: array of positive observations to reinforce
- `action_items`: array with priority (high/medium/low), action description, and suggested owner (manager/lead/team)

### backend/app/schemas/ (extend)
- `TeamHealthResult` schema matching the output structure
- `CommunicationFlag` schema: severity, observation
- `ActionItem` schema: priority, action, owner
- Add `team_health` to the analysis_type enum

### Frontend: Team Dashboard (extend) or new page
- "Run Team Health Check" button (monthly/quarterly cadence suggested in UI)
- Display structured results with sections for each category
- Action items as a checklist-style display
- History of past health checks for trend comparison
- Warning that this is an AI assessment and should be combined with qualitative judgment
