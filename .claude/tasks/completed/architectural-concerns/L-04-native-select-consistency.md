# Task L-04: Replace Native `<select>` with shadcn Select

## Severity
Low

## Status
done

## Blocked By
None

## Blocks
None

## Description
Most forms use the shadcn/ui `Select` component, but `Dashboard.tsx`, `WorkloadOverview.tsx`, `DeveloperDetail.tsx`, and `AIAnalysis.tsx` use raw `<select>` HTML elements with inline className styling. This produces visual inconsistency — shadcn Select has different styling, dropdown behavior, and accessibility attributes.

### Fix
Replace native `<select>` elements with shadcn `Select` / `SelectTrigger` / `SelectContent` / `SelectItem` in the 4 affected pages.

### Files
- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/pages/insights/WorkloadOverview.tsx`
- `frontend/src/pages/DeveloperDetail.tsx`
- `frontend/src/pages/AIAnalysis.tsx`
