# AC-02: Notification Frontend Concerns

**Priority:** This week
**Severity:** Medium
**Effort:** Low
**Status:** Pending

## Finding #1: No Polling on Notification Bell

- **File:** `frontend/src/hooks/useNotifications.ts`, `frontend/src/components/NotificationCenter/NotificationBell.tsx`
- `useNotifications()` uses the default 30s `staleTime` but no `refetchInterval`
- The badge count only updates when: (a) a mutation invalidates the cache, (b) the user navigates causing a re-mount, or (c) the component re-mounts after 30s staleness
- New critical alerts won't appear in the bell until the user interacts with the app
- For a "live alert" indicator, this gap is noticeable

### Required Changes
1. Add `refetchInterval: 30_000` (or 60_000) to the `useNotifications()` query options
2. This matches the pattern used by `useSyncStatus()` which polls at 3s/10s intervals
3. Consider stopping the interval when the notification panel is open (already fetching on interaction)

## Finding #2: ALERT_TYPE_LABELS Duplicated in NotificationPanel

- **File:** `frontend/src/components/NotificationCenter/NotificationPanel.tsx` (local `ALERT_TYPE_LABELS` constant)
- The 16 alert type display labels are hardcoded as a local map in the panel component
- The backend already sends `alert_types[].label` via `GET /notifications/config` (used correctly by `NotificationSettings.tsx`)
- If alert types are added or renamed on the backend, the panel will fall back to the raw key string
- Drift risk between frontend constant and backend `ALERT_TYPE_META`

### Required Changes
1. Option A: Fetch labels from `useNotificationConfig()` and pass them to the panel — shares the server-driven data
2. Option B: Accept the duplication but add a comment noting the backend source of truth
3. Recommendation: Option A is cleaner; `useNotificationConfig` already has 60s staleTime and is loaded by the settings page

## Finding #3: AlertSummaryBar "View in notification center" Not Clickable

- **File:** `frontend/src/components/NotificationCenter/AlertSummaryBar.tsx:40`
- The text "View in notification center" renders as a `<span>`, not a `<Link>` or clickable element
- Users cannot navigate to `/admin/notifications` from the Dashboard summary bar
- The `NotificationPanel` footer correctly links to the settings page

### Required Changes
1. Replace `<span>` with `<Link to="/admin/notifications">` (from react-router-dom)
2. Or make it open the `NotificationPanel` dropdown (mirrors the bell click behavior)

## Finding #4: ErrorCard Prop Mismatch in NotificationSettings

- **File:** `frontend/src/pages/settings/NotificationSettings.tsx:58`
- Code passes `<ErrorCard title="..." error={error} />` but `ErrorCardProps` only accepts `title`, `message`, `onRetry`
- The `error` prop is silently ignored; the TanStack Query error detail is never shown to the user
- TypeScript should catch this but may not if strict mode is not enforced

### Required Changes
1. Replace `error={error}` with `message={error instanceof Error ? error.message : 'Failed to load notification config'}`
2. Optionally add `onRetry={() => refetch()}` for retry capability
