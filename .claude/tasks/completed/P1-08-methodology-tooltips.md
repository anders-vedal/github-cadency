# Task P1-08: Methodology Tooltips and Metric Transparency

## Phase
Phase 1 — Make It Usable

## Status
completed

## Blocked By
- 12-frontend-remaining-pages

## Blocks
None

## Description
Add tooltip explanations next to every metric on DeveloperDetail and Dashboard pages explaining how each metric is computed. Transparency about methodology is the most effective way to convert "this feels like surveillance" into "this is a fair measurement." Currently, developers see numbers with zero context about what they mean or how they're calculated.

## Deliverables

### frontend/src/components/StatCard.tsx (extend)
- [x] Add optional `tooltip?: string` prop
- [x] When present, render an info icon (Lucide `HelpCircle`) next to the title
- [x] On hover, show a tooltip with the explanation text
- [x] Use shadcn/ui Tooltip component (new `@base-ui/react/tooltip`-based primitive)

### Tooltip content for each metric
- [x] All stat cards on DeveloperDetail have tooltip text matching spec
- [x] All stat cards on Dashboard have team-appropriate tooltip text

### frontend/src/pages/DeveloperDetail.tsx
- [x] Add tooltip prop to every StatCard instance (8 cards)
- [x] Add tooltip to Trends section header explaining linear regression and stable threshold
- [x] Add tooltip to Team Context section header explaining percentile placement and lower-is-better convention

### frontend/src/pages/Dashboard.tsx
- [x] Add tooltips to all 7 team-level stat cards with team-appropriate descriptions

## Files Created
- `frontend/src/components/ui/tooltip.tsx` — shadcn-style Tooltip using `@base-ui/react/tooltip` (Root, Trigger, Portal, Popup)

## Files Modified
- `frontend/src/components/StatCard.tsx` — Added optional `tooltip` prop with HelpCircle icon + Tooltip
- `frontend/src/pages/DeveloperDetail.tsx` — Added tooltips to 8 stat cards + Trends and Team Context section headers
- `frontend/src/pages/Dashboard.tsx` — Added tooltips to 7 team-level stat cards

## Notes
- Used `@base-ui/react/tooltip` (hover-based) instead of Popover (click-based) for better UX on short explanatory text
- DeveloperDetail stat cards differ slightly from the spec table: the page shows "PRs Open", "Code Changes", "Reviews Received", and "Avg Time to Close" which are not in the spec table — tooltips were written to match these actual metrics
- No new packages added — `@base-ui/react` already includes the tooltip primitive
