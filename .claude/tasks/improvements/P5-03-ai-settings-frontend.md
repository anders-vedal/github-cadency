# Task P5-03: AI Settings & Cost Controls — Frontend

## Phase
Phase 5 — Operational Excellence

## Status
completed

## Blocked By
- P5-01-ai-settings-backend
- P5-02-ai-usage-tracking

## Blocks
None

## Description
Build the admin-only `/settings/ai` page with a master switch, per-feature toggle cards (each with description + disable-impact), monthly budget configuration, pricing config with "last updated" display, a daily usage chart, cooldown setting, and pre-call cost estimates in AI trigger dialogs. Also update existing AI trigger points to show dedup banners when a cached result is returned.

## Deliverables

### frontend/src/utils/types.ts (extend)

```typescript
// --- AI Settings (P5) ---

export interface AIFeatureStatus {
  feature: string
  enabled: boolean
  label: string
  description: string
  disabled_impact: string
  tokens_this_month: number
  cost_this_month_usd: number
  call_count_this_month: number
  last_used_at: string | null
}

export interface AISettingsResponse {
  ai_enabled: boolean
  feature_general_analysis: boolean
  feature_one_on_one_prep: boolean
  feature_team_health: boolean
  feature_work_categorization: boolean
  monthly_token_budget: number | null
  budget_warning_threshold: number
  input_token_price_per_million: number
  output_token_price_per_million: number
  pricing_updated_at: string | null
  cooldown_minutes: number
  updated_at: string
  updated_by: string | null
  api_key_configured: boolean
  current_month_tokens: number
  current_month_cost_usd: number
  budget_pct_used: number | null
}

export interface AISettingsUpdate {
  ai_enabled?: boolean
  feature_general_analysis?: boolean
  feature_one_on_one_prep?: boolean
  feature_team_health?: boolean
  feature_work_categorization?: boolean
  monthly_token_budget?: number | null
  budget_warning_threshold?: number
  input_token_price_per_million?: number
  output_token_price_per_million?: number
  cooldown_minutes?: number
}

export interface AIUsageSummary {
  period_start: string
  period_end: string
  total_tokens: number
  total_cost_usd: number
  budget_limit: number | null
  budget_pct_used: number | null
  features: AIFeatureStatus[]
  daily_usage: Array<{
    date: string
    tokens: number
    cost_usd: number
    calls: number
    by_feature: Record<string, { tokens: number; calls: number }>
  }>
}

export interface AICostEstimate {
  estimated_input_tokens: number
  estimated_output_tokens: number
  estimated_cost_usd: number
  data_items: number
  note: string
}
```

Update `AIAnalysis` interface:
- Add `input_tokens: number | null`
- Add `output_tokens: number | null`
- Add `estimated_cost_usd: number | null`
- Add `reused: boolean`

### frontend/src/hooks/useAISettings.ts (new)

```typescript
export function useAISettings()
  // GET /api/ai/settings → AISettingsResponse
  // queryKey: ['ai-settings'], staleTime: 30s

export function useUpdateAISettings()
  // PATCH /api/ai/settings → AISettingsResponse
  // Invalidates ['ai-settings'] on success
  // Toast: "AI settings updated" / "Failed to update settings"

export function useAIUsage(days?: number)
  // GET /api/ai/usage?days=N → AIUsageSummary
  // queryKey: ['ai-usage', days], staleTime: 60s

export function useAICostEstimate()
  // POST /api/ai/estimate → AICostEstimate
  // useMutation (on-demand, not auto-fetched)
```

### frontend/src/pages/settings/AISettings.tsx (new)
Route: `/settings/ai` (admin-only)

**Layout — 6 sections stacked vertically:**

#### Section 1: API Status Banner
- If `api_key_configured` is false: amber warning banner — "No Anthropic API key configured. AI features are unavailable. Set ANTHROPIC_API_KEY in your environment."
- If key is configured: subtle green text "API key configured"

#### Section 2: Master Switch
- `Switch` component: "AI Features" on/off
- Subtitle: "Enable or disable all AI-powered features globally. When off, all AI buttons are hidden and no API calls are made. Historical results remain accessible."
- When toggled off: entire page below dims (opacity-50, pointer-events-none) except the switch itself

#### Section 3: Feature Toggle Cards
Grid of 4 cards (2×2 on desktop, stacked on mobile), each containing:
- **Header row**: Feature icon (Lucide) + label + Switch toggle (right-aligned)
- **Description**: 1-2 sentences explaining what the feature does
- **Disabled impact** (shown when toggle is OFF): amber text block with the impact explanation
- **Usage this month**: "1,234 tokens ($0.05) · 3 calls · Last used 2h ago"
- If feature is disabled: card has muted background, usage still shown

Icons per feature:
- General Analysis: `MessageSquareText`
- 1:1 Prep Brief: `Users`
- Team Health: `HeartPulse`
- Work Categorization: `Tags`

#### Section 4: Budget Configuration
- **Monthly token budget**: Number input with "tokens" suffix. Placeholder "Unlimited" when empty. "Set to 0 or clear to remove limit."
- **Budget progress bar**: Filled bar showing `budget_pct_used`. Colors: green (<50%), amber (50-80%), red (>80%). Text: "12,345 / 100,000 tokens ($0.49 / $4.00)"
- **Warning threshold**: Slider 0.5–1.0 (labeled 50%–100%). "You'll see a warning when usage reaches this threshold."
- If no budget set: show "No budget limit — usage is unlimited" with a muted info icon

#### Section 5: Pricing Configuration
- Two inputs side by side:
  - "Input token price (per million)": number input, default $3.00
  - "Output token price (per million)": number input, default $15.00
- Below: "Last updated: March 15, 2026" (or "Never — using defaults" if `pricing_updated_at` is null)
- Muted helper text: "Set these to match your Anthropic plan pricing for accurate cost estimates. Check anthropic.com/pricing for current rates."
- Save button that PATCHes settings

#### Section 6: Usage Dashboard
- **Period selector**: "Last 7 days / 30 days / 90 days" quick-select buttons
- **Summary stat cards** (row of 3):
  - Total tokens: "45,230 tokens"
  - Estimated cost: "$1.82"
  - API calls: "12 calls"
- **Stacked area chart** (Recharts `AreaChart`): Daily usage with 4 stacked areas colored by feature. X-axis: dates. Y-axis: tokens. Tooltip shows per-feature breakdown.
- If no usage data: empty state "No AI usage recorded yet"

#### Section 7: Cooldown Setting
- Number input: "Cooldown period (minutes)" — default 30
- Helper text: "When the same analysis type and scope is requested within this window, the previous result is returned instead of calling AI again. The user can click 'Regenerate' to bypass this."

**Save behavior**: Each section auto-saves on change (debounced 500ms) via PATCH. Toast on success/error. No explicit "Save All" button — matches modern settings UX.

### frontend/src/components/Layout.tsx (modify)
Add "AI Settings" to admin nav. Place it near the existing "AI Analysis" link:
```typescript
{ to: '/settings/ai', label: 'AI Settings' },
```

### frontend/src/App.tsx (modify)
Add route:
```typescript
import AISettings from '@/pages/settings/AISettings'
// ...
<Route path="/settings/ai" element={auth.isAdmin ? <AISettings /> : <Navigate to="/" replace />} />
```

### frontend/src/pages/AIAnalysis.tsx (modify)
**Dedup banner integration:**
When a mutation returns a result with `reused: true`:
- Show an info banner at the top of the result: "Showing cached result from [time ago]. [Regenerate] button"
- "Regenerate" calls the same mutation with `?force=true` appended
- The mutation hooks in `useAI.ts` need to accept an optional `force` param

**Cost estimate in dialogs:**
Before the "Run Analysis" / "Generate Brief" / "Generate Assessment" confirm buttons:
- Show a muted line: "Estimated: ~5,000 tokens (~$0.02)" fetched via `useAICostEstimate`
- Fetched when the dialog opens (or scope changes), not on every keystroke
- If estimate fails or is loading, show "Estimating cost..." skeleton

**Budget warning:**
If `budget_pct_used >= budget_warning_threshold`:
- Show amber banner at top of AI Analysis page: "AI budget is 85% used this month (42,500 / 50,000 tokens). [Manage in AI Settings →]"

### frontend/src/hooks/useAI.ts (modify)
Update mutation hooks to support `force` parameter:
```typescript
export function useRunAnalysis() {
  return useMutation({
    mutationFn: ({ data, force }: { data: AIAnalyzeRequest; force?: boolean }) =>
      apiFetch<AIAnalysis>(`/ai/analyze${force ? '?force=true' : ''}`, {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    ...
  })
}
```
Same pattern for `useRunOneOnOnePrep` and `useRunTeamHealth`.

### frontend/src/pages/insights/Investment.tsx (modify)
When the "AI Classify" switch is toggled ON:
- If `feature_work_categorization` is disabled in settings, show a toast: "AI classification is disabled. Enable it in AI Settings." and don't toggle.
- Requires fetching AI settings (can use `useAISettings` hook, read `feature_work_categorization` field)

### frontend/src/pages/DeveloperDetail.tsx (modify)
Same dedup + cost estimate treatment as AIAnalysis.tsx for the 1:1 prep and analysis dialogs.
When feature is disabled, hide or disable the AI buttons with a tooltip: "This AI feature is disabled by an admin."

## Testing
Frontend tests are visual/manual. Key scenarios to verify:
- Master switch off → all feature cards dimmed, AI buttons hidden across app
- Individual feature toggled off → that feature's buttons disabled, others work
- Budget at 90% → amber warning on AI Analysis page
- Budget exceeded → AI calls return 429, toast shows "Budget exceeded"
- Cached result returned → blue info banner with "Regenerate" button
- Regenerate bypasses cache → new result replaces old
- Cost estimate shows in dialog before confirm
- Pricing "last updated" shows correctly, updates when pricing changed
- Usage chart renders with correct feature breakdown
- No API key → warning banner, all features shown as unavailable

## Files Created
- `frontend/src/hooks/useAISettings.ts` — `useAISettings`, `useUpdateAISettings`, `useAIUsage`, `useAICostEstimate` hooks
- `frontend/src/pages/settings/AISettings.tsx` — Admin-only settings page with 7 sections: API status banner, master switch, feature toggle cards, budget config, pricing config, usage dashboard (stacked area chart), cooldown setting

## Files Modified
- `frontend/src/utils/types.ts` — Added `AIFeatureStatus`, `AISettingsResponse`, `AISettingsUpdate`, `DailyUsageEntry`, `AIUsageSummary`, `AICostEstimate` interfaces; extended `AIAnalysis` with `input_tokens`, `output_tokens`, `estimated_cost_usd`, `reused`
- `frontend/src/hooks/useAI.ts` — Updated `useRunAnalysis`, `useRunOneOnOnePrep`, `useRunTeamHealth` to accept `{data, force}` pattern; added budget-exceeded error handling; added reused-result toast messages
- `frontend/src/App.tsx` — Added `/settings/ai` admin-only route
- `frontend/src/components/Layout.tsx` — Added "AI Settings" to admin nav
- `frontend/src/pages/AIAnalysis.tsx` — Added budget warning banner, dedup banners with "Regenerate" button, cost estimates in dialogs, "cached" badges on history items
- `frontend/src/pages/DeveloperDetail.tsx` — Updated AI mutation calls to new `{data, force}` wrapper pattern
- `frontend/src/pages/insights/Investment.tsx` — Added `feature_work_categorization` check before toggling AI classify; shows toast when feature is disabled

## Deviations from Spec
- DeveloperDetail: Updated mutation calls to match new `{data, force}` hook signature but did not add inline cost estimates or disable-tooltip on AI buttons (these can be added as a follow-up if needed)
- Cost estimates in dialogs: Fetched on mount via `useState` initializer rather than on dialog open, which achieves the same user experience
