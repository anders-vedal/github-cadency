# Task NC-04: Notification Center — Frontend UI

## Phase
Notification Center v2

## Status
completed

## Blocked By
- NC-03-api-endpoints

## Blocks
None

## Description
Build the frontend notification center: a bell icon in the header with unread count badge, a dropdown panel showing active alerts grouped by severity, read/dismiss interactions, and an admin settings page for configuring alert thresholds and toggles. Replace the current AlertStrip + StalePRsSection vertical stacking on Dashboard and Workload pages with a compact summary bar that links to the notification center.

## Deliverables

### frontend/src/hooks/useNotifications.ts (new)

```typescript
// TanStack Query hooks for the notification center

// Fetch active notifications — 30s staleTime, auto-refetch
useNotifications(options?: { severity?: string; alertType?: string; includeDismissed?: boolean })
  → GET /api/notifications
  → returns NotificationsListResponse

// Mutations
useMarkRead()         → POST /api/notifications/{id}/read
useMarkAllRead()      → POST /api/notifications/read-all
useDismissNotification() → POST /api/notifications/{id}/dismiss
useDismissAlertType() → POST /api/notifications/dismiss-type
useUndismiss()        → DELETE /api/notifications/dismissals/{id}

// Config (admin)
useNotificationConfig()       → GET /api/notifications/config
useUpdateNotificationConfig() → PATCH /api/notifications/config
useEvaluateNotifications()    → POST /api/notifications/evaluate
```

All mutations invalidate `["notifications"]` query key on success.

### frontend/src/utils/types.ts (extend)

```typescript
interface Notification {
  id: number
  alert_type: string
  severity: 'critical' | 'warning' | 'info'
  title: string
  body: string | null
  entity_type: string | null
  entity_id: number | null
  link_path: string | null
  developer_id: number | null
  metadata: Record<string, unknown> | null
  is_read: boolean
  is_dismissed: boolean
  created_at: string
  updated_at: string
}

interface NotificationsListResponse {
  notifications: Notification[]
  unread_count: number
  counts_by_severity: Record<string, number>
  total: number
}

interface NotificationConfigResponse {
  alert_stale_pr_enabled: boolean
  stale_pr_threshold_hours: number
  // ... all config fields
  alert_types: AlertTypeMeta[]
  updated_at: string
  updated_by: string | null
}

interface AlertTypeMeta {
  key: string
  label: string
  description: string
  enabled: boolean
  thresholds: ThresholdConfig[]
}

interface ThresholdConfig {
  field: string
  label: string
  value: number
  unit: string
  min?: number
  max?: number
}
```

### frontend/src/components/NotificationCenter/NotificationBell.tsx (new)

The bell icon that lives in the Layout header, next to the date range picker.

- Renders a `Bell` icon from Lucide
- Shows a red badge with `unread_count` when > 0 (same styling as the unassigned role badge)
- Badge pulses briefly on count increase (CSS animation)
- Click opens `NotificationPanel` as a Popover (using shadcn/ui Popover)
- When panel opens, does NOT auto-mark-all-read — user must click items or "Mark all read"
- Only rendered for admin users (checked via `useAuth().isAdmin`)

### frontend/src/components/NotificationCenter/NotificationPanel.tsx (new)

The dropdown panel that opens from the bell. Max height 500px, scrollable.

**Header:**
- Title: "Notifications" with total count
- "Mark all read" button (muted text, right-aligned)
- Severity filter tabs: All | Critical (count) | Warning (count) | Info (count)

**Body — notification list:**
- Grouped by severity when "All" tab is selected (Critical section, Warning section, Info section)
- Each group has a collapsible header: "Critical (2)" with chevron
- Critical group expanded by default, others collapsed
- Within each group, sorted by `created_at` DESC (newest first)

**Individual notification item (`NotificationItem.tsx`):**
- Left: severity dot (red/amber/blue, 8px circle)
- Center: 
  - Title (font-medium, truncated to 2 lines)
  - Body preview (text-muted-foreground, truncated to 1 line, only if body exists)
  - Relative time ("2h ago", "3d ago") using existing `timeAgo()` from `format.ts`
- Right: action buttons
  - If `link_path`: arrow-right icon button → navigates to link_path (marks read on click)
    - External links (starting with "http") open in new tab
    - Internal links use React Router navigation
  - Dismiss button (X icon) → opens DismissPopover
- Unread items have a subtle left border accent (2px blue)
- Read items have slightly muted text
- Clicking anywhere on the item (except dismiss) marks as read and navigates to link_path

**Footer:**
- "Notification Settings" link → `/admin/notifications` (gear icon)

**Empty state:**
- Green checkmark icon + "All clear — no active alerts"

### frontend/src/components/NotificationCenter/DismissPopover.tsx (new)

Popover with dismiss options, triggered from the X button on a notification item.

Options:
- "Dismiss this alert" → permanent dismiss of this instance
- "Dismiss for 7 days" → temporary dismiss, duration_days=7
- "Dismiss for 30 days" → temporary dismiss, duration_days=30
- Divider
- "Mute all {alert_type_label} alerts" → type-level permanent dismiss
- "Mute {alert_type_label} for 7 days" → type-level temporary dismiss

Each option is a button row with descriptive text. Click fires the appropriate mutation and closes the popover.

Success toast: "Alert dismissed" / "Alert type muted for 7 days"

### frontend/src/components/NotificationCenter/AlertSummaryBar.tsx (new)

Compact replacement for the current AlertStrip on Dashboard and Workload pages.

- Single-line bar showing severity counts: "2 critical, 3 warnings, 1 info"
- Each count uses its severity color (red/amber/blue text)
- If all counts are 0: green "All clear" message (same as current AlertStrip empty state)
- Right side: "View all" link that opens the notification panel (or a "bell" icon button)
- Clicking a severity count scrolls/filters to that severity in the notification panel
- Height: ~44px (same as one old AlertStrip row, but replaces potentially 20+ rows)

### frontend/src/components/Layout.tsx (modify)

- Import `NotificationBell` component
- Add to header, between the nav and the date range picker area:
  ```tsx
  <div className="ml-auto flex items-center gap-2 text-sm">
    {isAdmin && <NotificationBell />}
    <DateRangePicker ... />
    {user && (
      <>
        <span className="text-muted-foreground">{user.display_name}</span>
        <Button variant="ghost" size="sm" onClick={logout}>Logout</Button>
      </>
    )}
  </div>
  ```

### frontend/src/pages/Dashboard.tsx (modify)

Replace the three alert zones with the compact summary bar:

**Before (current):**
```tsx
{workload && <AlertStrip alerts={workload.alerts} />}
{stalePRs && stalePRs.stale_prs.length > 0 && <StalePRsSection ... />}
{openHighRiskPRs.length > 0 && <HighRiskPRsSection ... />}
```

**After:**
```tsx
<AlertSummaryBar />
{/* Keep StalePRsSection but capped at top 5 */}
{stalePRs && stalePRs.stale_prs.length > 0 && (
  <StalePRsSection prs={stalePRs.stale_prs.slice(0, 5)} riskScores={riskScoresMap} />
)}
{stalePRs && stalePRs.stale_prs.length > 5 && (
  <button className="text-sm text-muted-foreground hover:text-foreground">
    Show all {stalePRs.stale_prs.length} stale PRs
  </button>
)}
{/* Keep HighRiskPRsSection but capped at top 3 */}
{openHighRiskPRs.length > 0 && (
  <HighRiskPRsSection prs={openHighRiskPRs.slice(0, 3)} />
)}
```

- Remove the `AlertStrip` import
- Add `AlertSummaryBar` import
- Keep `useWorkload` call for the Team Status grid (workload data is still used for the table)
- The workload alerts are no longer rendered inline — they live in the notification center

### frontend/src/pages/insights/WorkloadOverview.tsx (modify)

Same pattern as Dashboard:
- Replace `AlertStrip` with `AlertSummaryBar`
- Cap `StalePRsSection` at top 5 with "Show all" expansion

### frontend/src/pages/settings/NotificationSettings.tsx (new)

Admin-only page at `/admin/notifications`. Added to admin sidebar and admin dropdown.

**Layout:** Single-column settings page (same pattern as AISettings and SlackSettings).

**Section 1: Alert Type Cards**
- One card per alert type from `config.alert_types`
- Each card shows:
  - Alert type label + description
  - Enable/disable toggle (auto-saves with 500ms debounce)
  - Threshold inputs (if the type has configurable thresholds):
    - Numeric inputs with labels and units (e.g., "48 hours", "2.0x median", "5%")
    - Auto-save with 800ms debounce on change
- Cards grouped visually:
  - "Code Review Alerts" — stale_pr, review_bottleneck, merged_without_approval
  - "Workload Alerts" — underutilized, uneven_assignment, revert_spike
  - "Risk Alerts" — high_risk_pr
  - "Collaboration Alerts" — bus_factor, team_silo, isolated_developer
  - "Trend Alerts" — declining_trend, issue_linkage
  - "System Alerts" — ai_budget, sync_failure, unassigned_roles, missing_config

**Section 2: Contribution Category Exclusion**
- Multi-select for which contribution categories to exclude from alerts
- Options: system, non_contributor, issue_contributor, code_contributor
- Default: system, non_contributor selected
- Description: "Developers with these role categories will not trigger activity-based alerts"

**Section 3: Evaluation**
- "Evaluation interval" — number input for minutes (min 5, max 60)
- "Evaluate now" button — triggers POST /notifications/evaluate, shows toast with counts
- Last evaluation time (computed from most recent notification's updated_at)

### frontend/src/App.tsx (modify)

- Add lazy import for NotificationSettings:
  ```typescript
  const NotificationSettings = lazy(() => import('@/pages/settings/NotificationSettings'))
  ```
- Add route under admin section:
  ```tsx
  <Route path="/notifications" element={<NotificationSettings />} />
  ```
- Add to `adminSidebarItems`:
  ```typescript
  { to: '/admin/notifications', label: 'Notifications' }
  ```

### frontend/src/components/Layout.tsx (modify — nav)
- Add `{ to: '/admin/notifications', label: 'Notifications' }` to `adminNavItems` Admin children

### Design Notes

**Interaction flow:**
1. User sees red badge on bell → clicks bell → panel opens
2. Scans notifications grouped by severity (critical expanded)
3. Clicks a notification → navigates to the relevant page, notification marked read
4. Alternatively, clicks dismiss → popover with duration options
5. Bell badge decrements as items are read/dismissed

**Performance:**
- `useNotifications` uses 30s staleTime (same as other hooks)
- Panel only fetches when opened (not on every page load) — use `enabled: panelOpen` on the query
- The bell badge count uses a separate lightweight query or the same query with refetchInterval
- Actually: fetch always (for the badge count), but the full list query can be the same — it's a small payload

**Responsive:**
- Panel is a fixed-width popover (380px) on desktop
- On mobile (< 640px), panel becomes a full-screen overlay (same pattern as NavDropdown but larger)

**Dark mode:**
- All severity colors use the existing `dark:` variants from AlertStrip's `severityStyles`
- Notification items use `bg-muted/50` on hover

**Accessibility:**
- Bell button has `aria-label="Notifications"` and `aria-haspopup="true"`
- Panel has `role="dialog"` with focus trap
- Notification items are focusable with Enter to navigate and Escape to close panel
- Severity filter tabs use `role="tablist"` pattern

**Supersedes:**
- This task supersedes `.claude/tasks/improvements/P3-09-configurable-alert-thresholds.md` — all of that task's functionality (configurable thresholds per alert type) is included in the NotificationConfig singleton and the admin settings page
