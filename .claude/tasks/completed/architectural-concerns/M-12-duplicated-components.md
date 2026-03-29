# Task M-12: Extract Shared AlertStrip/SortableHead Components

## Severity
Medium

## Status
done

## Blocked By
None

## Blocks
None

## Description
`AlertStrip` and `SortableHead` sub-components are copy-pasted between `Dashboard.tsx` and `WorkloadOverview.tsx`. Both files also define identical `alertSeverityMap`, `severityStyles`, `severityLabels`, and `workloadStyles` constants. This duplication means bug fixes or style changes must be applied in two places.

Additionally, `CATEGORY_CONFIG` / `CATEGORY_ORDER` are defined identically in `ExecutiveDashboard.tsx` and `Investment.tsx`.

### Fix
1. Extract `AlertStrip` and `SortableHead` to `frontend/src/components/`
2. Move shared constants (`alertSeverityMap`, `severityStyles`, etc.) alongside the components
3. Move `CATEGORY_CONFIG` / `CATEGORY_ORDER` to a shared constants file or `utils/types.ts`
4. Update imports in `Dashboard.tsx`, `WorkloadOverview.tsx`, `ExecutiveDashboard.tsx`, `Investment.tsx`

### Files
- `frontend/src/components/AlertStrip.tsx` — new shared component
- `frontend/src/components/SortableHead.tsx` — new shared component
- `frontend/src/pages/Dashboard.tsx` — remove local definitions, import
- `frontend/src/pages/insights/WorkloadOverview.tsx` — remove local definitions, import
- `frontend/src/pages/ExecutiveDashboard.tsx` — extract CATEGORY_CONFIG
- `frontend/src/pages/insights/Investment.tsx` — import shared CATEGORY_CONFIG
