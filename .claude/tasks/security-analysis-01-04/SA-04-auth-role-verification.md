# SA-04: Fix Authorization Gaps

**Priority:** This week
**Severity:** HIGH (#6, #11), MEDIUM (#22)
**Effort:** Low
**Status:** Pending

## Findings

### Finding #6: `app_role` Trusted from JWT, Not Verified from DB
- **File:** `backend/app/api/auth.py:48-68`
- `app_role` read from JWT payload, not re-checked against DB
- Role demotions don't take effect until the 7-day token expires
- The `is_active` DB check already runs on every request — trivial to add `app_role`

### Finding #11: Any Authenticated User Can Recategorize Any PR/Issue
- **File:** `backend/app/api/stats.py:393-406`
- `PATCH /stats/work-allocation/items/{type}/{id}/category` uses `get_current_user` not `require_admin`
- Any developer can permanently reclassify any org-wide item with `source="manual"`
- Manual overrides are never auto-overwritten — permanent data corruption

### Finding #22: Goal Progress IDOR — Service Called Before Auth Check
- **File:** `backend/app/api/goals.py:68-81`
- `get_goal_progress()` executes before ownership verification
- Returns 403 (not 404) for unauthorized goals — enables goal ID enumeration

## Required Changes

### 1. Read `app_role` from DB in `get_current_user()` (`backend/app/api/auth.py`)
- Change the query at line 49 from:
  ```python
  result = await db.execute(select(Developer.is_active).where(Developer.id == developer_id))
  ```
  to:
  ```python
  result = await db.execute(select(Developer.is_active, Developer.app_role).where(Developer.id == developer_id))
  ```
- Use the DB `app_role` value in the returned `AuthUser`, ignoring the JWT payload value
- This ensures role changes take effect immediately on the next API call

### 2. Gate recategorization behind `require_admin` (`backend/app/api/stats.py`)
- Change the `PATCH /stats/work-allocation/items/{type}/{id}/category` endpoint dependency from `get_current_user` to `require_admin`
- The `GET /stats/work-allocation/items` endpoint can remain `get_current_user` (read-only)

### 3. Fix goal progress authorization ordering (`backend/app/api/goals.py`)
- Move the ownership check BEFORE the `get_goal_progress()` call:
  ```python
  if user.app_role != AppRole.admin:
      goal_obj = await db.get(DeveloperGoal, goal_id)
      if not goal_obj or goal_obj.developer_id != user.developer_id:
          raise HTTPException(status_code=404)  # 404, not 403
  result = await get_goal_progress(db, goal_id)
  ```
- Return 404 (not 403) to prevent goal ID enumeration

## Impact Analysis

### Will this break anything?

**DB query change — safe, negligible perf.** The `get_current_user()` query changes from `select(Developer.is_active)` to `select(Developer.is_active, Developer.app_role)` — same indexed PK lookup, one extra column from the same row. The result changes from scalar to tuple row, but the code already uses `result.first()`. `AuthUser` already has `app_role: AppRole` field — no schema changes. `require_admin()` depends only on `user.app_role`, unchanged signature.

**Recategorization — one test must flip.** `backend/tests/integration/test_work_allocation_items.py` has `test_recategorize_accessible_by_developer` (line 299) which explicitly asserts non-admin can recategorize — must be inverted to expect 403. The docstring says "Any authenticated user can recategorize" and must be updated.

**Frontend — UI degrades gracefully but should be updated.** `frontend/src/pages/insights/InvestmentCategory.tsx` renders the recategorize dropdown with no admin check (`useAuth` is not imported, no `isAdmin` guard). After the backend change, non-admins will get a generic error toast. The dropdown should be hidden for non-admins in a follow-up, but this is not blocking for the security fix.

**Goal 403→404 — no frontend breakage.** No frontend code inspects the specific status code from goal progress. There are no `if (error.status === 403)` branches in goal-related components — TanStack Query shows generic error state.

### Exact files to modify

| File | Change | Risk |
|------|--------|------|
| `backend/app/api/auth.py:49-68` | Add `Developer.app_role` to SELECT, use DB value in `AuthUser` | None |
| `backend/app/api/stats.py:~398` | Change dependency from `get_current_user` to `require_admin` | None |
| `backend/app/api/goals.py:68-82` | Reorder: ownership check before `get_goal_progress()`, return 404 not 403 | None |
| `backend/tests/integration/test_work_allocation_items.py:299-308` | Flip test to expect 403 for non-admin | Required |

### Follow-up (not blocking)

- `frontend/src/pages/insights/InvestmentCategory.tsx` — hide recategorize dropdown for non-admins (cosmetic, no security impact since backend now blocks)

## Testing

- Test: after changing a developer's `app_role` in DB, the next API call uses the new role
- Test: non-admin user gets 403 on `PATCH /stats/work-allocation/items/.../category`
- Test: admin can still recategorize items
- Test: non-admin accessing another user's goal gets 404 (not 403)
- Test: goal progress auth check runs before the service call
