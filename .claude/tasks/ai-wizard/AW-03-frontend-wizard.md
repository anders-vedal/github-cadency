# Task AW-03: Frontend — AI Analysis Wizard

## Phase
AI Analysis Wizard

## Status
completed

## Blocked By
- AW-01-backend-dry-run-estimation

## Blocks
- AW-04-frontend-landing-schedules

## Description
Build a multi-step AI analysis wizard at `/admin/ai/new` following the Sync wizard pattern (useReducer, step indicator, adaptive steps). Replaces the current dialog-based trigger. Includes info cards explaining each analysis type, adaptive scope configuration, time range + repo filter, and a confirm step with accurate cost estimation. Supports pre-filling from URL params (DeveloperDetail quick-launch) and a "Save as Schedule" option on the confirm step.

## Deliverables

### frontend/src/utils/types.ts

**New/updated types:**

1. Update `AICostEstimate`:
   ```ts
   export interface AICostEstimate {
     estimated_input_tokens: number
     estimated_output_tokens: number
     estimated_cost_usd: number
     data_items: number
     character_count: number
     system_prompt_tokens: number
     remaining_budget_tokens: number
     would_exceed_budget: boolean
     note: string
   }
   ```

2. Update request types to include `repo_ids`:
   ```ts
   export interface AIAnalyzeRequest {
     analysis_type: 'communication' | 'conflict' | 'sentiment'
     scope_type: 'developer' | 'team' | 'repo'
     scope_id: string
     date_from: string
     date_to: string
     repo_ids?: number[]
   }

   export interface OneOnOnePrepRequest {
     developer_id: number
     date_from: string
     date_to: string
     repo_ids?: number[]
   }

   export interface TeamHealthRequest {
     team?: string
     date_from: string
     date_to: string
     repo_ids?: number[]
   }
   ```

3. New schedule types:
   ```ts
   export interface AISchedule {
     id: number
     name: string
     analysis_type: string
     general_type: string | null
     scope_type: string
     scope_id: string
     repo_ids: number[] | null
     time_range_days: number
     frequency: string
     day_of_week: number | null
     hour: number
     minute: number
     is_enabled: boolean
     last_run_at: string | null
     last_run_analysis_id: number | null
     last_run_status: string | null
     created_by: string | null
     created_at: string
     updated_at: string
     next_run_description: string | null
   }

   export interface AIScheduleCreate {
     name: string
     analysis_type: string
     general_type?: string
     scope_type: string
     scope_id: string
     repo_ids?: number[]
     time_range_days?: number
     frequency: string
     day_of_week?: number
     hour?: number
     minute?: number
   }

   export interface AIScheduleUpdate {
     name?: string
     is_enabled?: boolean
     repo_ids?: number[]
     time_range_days?: number
     frequency?: string
     day_of_week?: number
     hour?: number
     minute?: number
   }

   export type AnalysisWizardType = 'communication' | 'conflict' | 'sentiment' | 'one_on_one_prep' | 'team_health'
   ```

### frontend/src/hooks/useAI.ts

**Update existing mutation hooks to pass `repo_ids`:**

4. `useRunAnalysis` — already works (body includes all AIAnalyzeRequest fields, repo_ids added to type)
5. `useRunOneOnOnePrep` — same, already serializes full body
6. `useRunTeamHealth` — same

### frontend/src/hooks/useAISettings.ts

**Update cost estimate hook:**

7. `useAICostEstimate()` — update mutation params to include `repo_ids`:
   ```ts
   mutationFn: (params: {
     feature: string
     scope_type?: string
     scope_id?: string
     date_from?: string
     date_to?: string
     repo_ids?: number[]
   }) => {
     const qs = new URLSearchParams({ feature: params.feature })
     // ... existing params ...
     if (params.repo_ids?.length) qs.set('repo_ids', params.repo_ids.join(','))
     return apiFetch<AICostEstimate>(`/ai/estimate?${qs}`, { method: 'POST' })
   }
   ```

### frontend/src/hooks/useAISchedules.ts (new file)

8. Schedule hooks:
   ```ts
   export function useAISchedules()
   // useQuery<AISchedule[]>({ queryKey: ['ai-schedules'], queryFn: () => apiFetch('/ai/schedules') })

   export function useCreateAISchedule()
   // useMutation POST /ai/schedules, onSuccess invalidate ['ai-schedules'], toast

   export function useUpdateAISchedule()
   // useMutation PATCH /ai/schedules/{id}, onSuccess invalidate, toast

   export function useDeleteAISchedule()
   // useMutation DELETE /ai/schedules/{id}, onSuccess invalidate, toast

   export function useRunAISchedule()
   // useMutation POST /ai/schedules/{id}/run, onSuccess invalidate ['ai-history', 'ai-schedules'], toast
   ```

### frontend/src/pages/ai/ (new directory)

**Directory structure:**
```
frontend/src/pages/ai/
├── AIWizard.tsx          # Wizard orchestrator (useReducer + step routing)
├── steps/
│   ├── StepChooseType.tsx    # Step 1: analysis type info cards
│   ├── StepConfigureScope.tsx # Step 2: adaptive scope selection
│   ├── StepTimeRange.tsx     # Step 3: time range + repo filter
│   └── StepConfirm.tsx       # Step 4: summary + cost + run/schedule
```

### frontend/src/pages/ai/AIWizard.tsx

**Wizard orchestrator (mirrors SyncWizard.tsx pattern):**

9. State definition:
   ```ts
   type WizardStep = 'type' | 'scope' | 'time-range' | 'confirm'

   interface WizardState {
     step: WizardStep
     analysisType: AnalysisWizardType | null
     // Scope
     scopeType: 'developer' | 'team' | 'repo' | null
     scopeId: string
     scopeName: string  // display name for confirm step
     // Time range (reuse TimeRangeOption from sync)
     timeRange: TimeRangeOption
     customDate: string
     // Optional repo filter
     repoIds: number[]
   }

   type WizardAction =
     | { type: 'SET_ANALYSIS_TYPE'; analysisType: AnalysisWizardType }
     | { type: 'SET_SCOPE'; scopeType: WizardState['scopeType']; scopeId: string; scopeName: string }
     | { type: 'SET_TIME_RANGE'; range: TimeRangeOption }
     | { type: 'SET_CUSTOM_DATE'; date: string }
     | { type: 'SET_REPO_IDS'; repoIds: number[] }
     | { type: 'NEXT_STEP' }
     | { type: 'PREV_STEP' }
     | { type: 'RESET' }
   ```

10. URL param pre-filling on mount:
    - Read `?type=`, `?developer_id=`, `?team=`, `?schedule=` from `useSearchParams()`
    - If `type` is set: pre-fill `analysisType` and skip to step 2 (`scope`)
    - If `developer_id` is set: pre-fill `scopeType='developer'`, `scopeId`, look up `scopeName` from developers query
    - If `schedule` is set: fetch schedule by ID, pre-fill all state, change confirm step CTAs to "Update Schedule" + "Run Now"
    - Use `useEffect` on mount only (empty dep array after reading params)

11. Step indicator: horizontal stepper at top (hidden on step 1), same styling as SyncWizard:
    - Numbered circles, filled for current/completed, checkmark for completed
    - Labels: 'Analysis Type', 'Scope', 'Time Range', 'Confirm'

12. Step routing via `state.step` switch, Back/Next buttons outside step components (in wizard body)

13. Next button disabled logic:
    - `type` step: disabled when `analysisType === null`
    - `scope` step: disabled when `scopeId === ''`
    - `time-range` step: disabled when `timeRange === 'custom' && !customDate`
    - `confirm` step: no Next (has its own Run/Schedule buttons)

14. `computeSinceDate(timeRange, customDate)` — reuse the exact same function from SyncWizard (extract to shared util or copy)

### frontend/src/pages/ai/steps/StepChooseType.tsx

**Step 1: Analysis type selection with info cards**

15. Three cards in a `grid md:grid-cols-3 gap-4` layout, plus two more below in `grid md:grid-cols-2 gap-4`:

    **Card 1: Communication Analysis**
    - Icon: `MessageSquare` (lucide)
    - Title: "Communication Analysis"
    - Scope badge: "Per Developer"
    - Description: "Evaluates clarity, constructiveness, responsiveness, and tone across a developer's PR descriptions, review comments, and issue comments."
    - What it reads: "PR descriptions (up to 50), review comments (up to 50), issue comments (up to 50) — each truncated to 500 characters"
    - What it generates: "Scores (1-10) for clarity, constructiveness, responsiveness, and tone, plus qualitative observations and actionable recommendations"

    **Card 2: Conflict Detection**
    - Icon: `Swords` (lucide)
    - Title: "Conflict Detection"
    - Scope badge: "Per Team"
    - Description: "Analyzes team code review interactions to identify friction patterns, especially around CHANGES_REQUESTED reviews and recurring disagreements between pairs."
    - What it reads: "Up to 50 review comments between team members, with reviewer/author attribution and review state"
    - What it generates: "Conflict score (1-10), specific friction pairs with patterns, recurring issues, and de-escalation recommendations"

    **Card 3: Sentiment Analysis**
    - Icon: `Smile` (lucide)
    - Title: "Sentiment Analysis"
    - Scope badge: "Developer / Team / Repo"
    - Description: "Lightweight analysis of overall tone and morale across comments and PR descriptions in the selected scope."
    - What it reads: "Review comments and issue comments (up to 50 each) from the selected scope"
    - What it generates: "Sentiment score (1-10), trend direction (improving/stable/declining), and notable patterns"

    **Card 4: 1:1 Prep Brief**
    - Icon: `Users` (lucide)
    - Title: "1:1 Prep Brief"
    - Scope badge: "Per Developer"
    - Description: "Generates a structured meeting brief for engineering managers. Combines activity metrics, trends, peer benchmarks, goal progress, and review quality into actionable talking points."
    - What it reads: "Developer stats, 4-week trends, team benchmarks, recent PRs (up to 30), review quality tiers, active goals with progress, previous brief (for continuity), issue creator stats vs team averages"
    - What it generates: "Period summary, metrics highlights with concern levels, notable work, suggested talking points with constructive framing, and goal progress"

    **Card 5: Team Health Check**
    - Icon: `HeartPulse` (lucide)
    - Title: "Team Health Check"
    - Scope badge: "Per Team / All"
    - Description: "Comprehensive team health assessment combining velocity, workload balance, collaboration patterns, communication flags, and goal progress into a prioritized action plan."
    - What it reads: "Team stats + benchmarks, per-developer workload scores, collaboration matrix + insights, CHANGES_REQUESTED reviews with body text (up to 60), heated issue threads (3+ back-and-forth comments), team goal progress"
    - What it generates: "Health score (1-10), velocity assessment, workload concerns with suggestions, collaboration patterns, communication flags with severity, process recommendations, strengths, and prioritized action items"

16. Each card has a selectable ring style: `ring-2 ring-primary` when selected, `hover:ring-2 hover:ring-primary/50` otherwise (same as Sync time range cards)

17. Clicking a card sets `analysisType` AND auto-sets `scopeType` for types with a single valid scope:
    - `communication` → `scopeType: 'developer'`
    - `conflict` → `scopeType: 'team'`
    - `one_on_one_prep` → `scopeType: 'developer'`
    - `team_health` → `scopeType: 'team'`
    - `sentiment` → `scopeType: null` (user chooses in step 2)

### frontend/src/pages/ai/steps/StepConfigureScope.tsx

**Step 2: Adaptive scope selection**

18. Render depends on `state.analysisType`:

    **For `communication` / `one_on_one_prep` (developer scope):**
    - Label: "Select Developer"
    - Searchable `Select` dropdown of active developers from `useDevelopers()`
    - Each option: `{display_name} (@{github_username})`
    - Below select: brief context card showing developer's team and role (from the developers list)

    **For `conflict` / `team_health` (team scope):**
    - Label: "Select Team"
    - `Select` dropdown of teams (derived from developers) + "All teams" option for team_health
    - For `conflict`: "All teams" is NOT available (conflict requires a specific team)
    - Below select: show team member count

    **For `sentiment` (flexible scope):**
    - First: scope type radio group (Developer / Team / Repository) using Cards-as-radios pattern
    - Then: conditional Select based on chosen scope type (same as above + repo select from `useRepos()`)

19. On scope selection: dispatch `SET_SCOPE` with scopeType, scopeId, and scopeName (for display in confirm step)

### frontend/src/pages/ai/steps/StepTimeRange.tsx

**Step 3: Time range + optional repo filter**

20. Time range section — radio card grid (reuse Sync pattern):
    - Options: Last 7 days, Last 14 days, Last 30 days, Last 60 days, Last 90 days, Custom date
    - NO "Since last sync" or "All history" options (not applicable to AI analysis)
    - `grid sm:grid-cols-2 gap-3` layout
    - Custom date: conditional `Input[type=date]` below grid when selected
    - Default selection: "Last 30 days"

21. Repo filter section — collapsible "Advanced: Filter by repositories" below time range:
    - `Collapsible` (shadcn/ui) with trigger text "Filter by specific repositories (optional)"
    - When expanded: checkbox list of tracked repos from `useRepos()` (same pattern as SyncWizard StepSelectRepos)
    - Search input, Select All / Deselect All buttons
    - When collapsed and repos are selected: show `Badge` count "3 repos selected"
    - When no repos selected: text "All repositories (default)"
    - Dispatch `SET_REPO_IDS` on change

### frontend/src/pages/ai/steps/StepConfirm.tsx

**Step 4: Summary + cost estimate + run/schedule**

22. Summary card (same layout as Sync StepConfirm):
    - Analysis Type: badge with type name
    - Scope: `{scopeType}: {scopeName}`
    - Time Range: human-readable label
    - Repos: "All" or badge list (up to 5 + overflow)

23. Cost estimation section — fires `useAICostEstimate()` on mount with all wizard params:
    - Loading state: `Skeleton` lines
    - Success state:
      - "Estimated cost: ~$0.0042" (prominent)
      - "~12,450 input tokens + ~3,000 output tokens"
      - "Based on 847 data items (34,200 characters)"
      - Budget bar: visual progress bar showing `(used + estimated) / total` with color coding:
        - Green: within budget
        - Amber: would use >80% of remaining budget
        - Red: `would_exceed_budget === true` — show warning "This analysis would exceed your monthly budget"
    - Error state: "Could not estimate cost" with retry button

24. **"Run Analysis" button** (primary):
    - Disabled when `would_exceed_budget` and no override
    - When `would_exceed_budget`: show checkbox "Run anyway (exceeds budget)" to enable
    - On click: dispatch appropriate mutation based on `analysisType`:
      - `communication/conflict/sentiment` → `useRunAnalysis`
      - `one_on_one_prep` → `useRunOneOnOnePrep`
      - `team_health` → `useRunTeamHealth`
    - Include `repo_ids` in request (only if non-empty)
    - On success: navigate to `/admin/ai` (landing page with history)
    - Loading state: "Running analysis..." with spinner

25. **"Save as Schedule" button** (outline/secondary):
    - On click: expand inline schedule configuration section below the buttons (animated with CSS transition)
    - Schedule config fields:
      - Name input (required, pre-filled with sensible default: e.g., "Weekly 1:1 Prep — {developerName}")
      - Frequency: `Select` with options: Daily, Weekly, Every 2 weeks, Monthly
      - Day of week: `Select` (Mon-Sun), shown only for Weekly/Biweekly
      - Time: hour `Select` (0-23, formatted as "8:00 AM") + minute `Select` (0, 15, 30, 45)
      - Preview text: "Runs weekly on Monday at 8:00 AM, analyzing the last 30 days"
    - "Save Schedule" button → calls `useCreateAISchedule` with all wizard state + schedule config
    - On success: navigate to `/admin/ai` with toast "Schedule created"

26. **Edit schedule mode** (when `?schedule=` param present):
    - "Run Analysis" button still present (test-run the schedule)
    - Instead of "Save as Schedule": "Update Schedule" button → calls `useUpdateAISchedule`
    - "Delete Schedule" button (destructive outline) → calls `useDeleteAISchedule` with confirmation dialog

### frontend/src/App.tsx

**Route registration:**

27. Add lazy import:
    ```ts
    const AIWizard = lazy(() => import('@/pages/ai/AIWizard'))
    ```

28. Add route inside admin group:
    ```tsx
    <Route path="/ai/new" element={<AIWizard />} />
    ```
    Place BEFORE `/ai` route so `/ai/new` doesn't match `/ai` first.

### frontend/src/pages/DeveloperDetail.tsx

**Replace AI section with quick-launch buttons:**

29. Replace the existing AI Analysis section (current ~lines 774-870 with two Dialog components) with:
    ```tsx
    {/* AI Analysis */}
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">AI Analysis</h2>
        <div className="flex gap-2">
          <Button asChild>
            <Link to={`/admin/ai/new?type=one_on_one_prep&developer_id=${dev.id}`}>
              Generate 1:1 Prep Brief
            </Link>
          </Button>
          <Button variant="outline" asChild>
            <Link to={`/admin/ai/new?type=communication&developer_id=${dev.id}`}>
              Run AI Analysis
            </Link>
          </Button>
        </div>
      </div>
      {/* Keep existing history list below, but use the shared HistoryList component */}
    </div>
    ```

30. Remove the `prepOpen`, `analyzeOpen` dialog state, the `analyzeForm` state, and both `Dialog` components. Import `Link` from react-router-dom (likely already imported).

### frontend/src/pages/AIAnalysis.tsx

**Refactor to landing page:**

31. Remove the `Dialog` for "New Analysis", the inline 1:1 prep card, and the inline team health card.

32. Replace with:
    - "New Analysis" button at the top that navigates to `/admin/ai/new`
    - Budget warning banner (keep existing)
    - Tabs: History (all types combined, keep `HistoryList`) | Schedules (from AW-04)
    - History tab: unified list of all analysis types (merge generalHistory + prepHistory + healthHistory), each item shows analysis_type badge. Filter dropdown for type.

### Tests

33. No frontend unit tests required (project uses pytest for backend only). Manual test plan:
    - Navigate to `/admin/ai/new` — see 5 info cards on step 1
    - Select "1:1 Prep Brief" → auto-advances scope to developer
    - Select a developer → proceed to time range
    - Select "Last 30 days" → proceed to confirm
    - Verify cost estimate loads with character_count, budget bar
    - Click "Run Analysis" → redirects to `/admin/ai` with result in history
    - Test pre-fill: navigate from DeveloperDetail → wizard opens at step 2 with developer pre-selected
    - Test "Save as Schedule" → expands schedule config, saves, appears in schedules tab
    - Test repo filter: expand advanced, select 2 repos, verify cost estimate updates
    - Test budget warning: when `would_exceed_budget=true`, verify warning + override checkbox
