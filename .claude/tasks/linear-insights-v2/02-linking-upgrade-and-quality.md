# Phase 02: Linking upgrade + data quality panel

**Status:** Completed (2026-04-22)
**Priority:** High
**Type:** feature
**Apps:** devpulse
**Effort:** medium
**Parent:** linear-insights-v2/00-overview.md

## Files Created
- `backend/app/services/linkage_quality.py`
- `backend/tests/integration/test_linking_upgrade.py` (8 tests)
- `frontend/src/pages/admin/LinkageQuality.tsx`
- `frontend/src/hooks/useLinkageQuality.ts`

## Files Modified
- `backend/app/services/linear_sync.py` — rewrote `link_prs_to_external_issues` as 4-pass
  pipeline (linear_attachment high → branch medium → title medium → body low) with
  confidence upgrade logic; added `run_linear_relink()` wrapper
- `backend/app/api/integrations.py` — `GET /api/integrations/{id}/linkage-quality`,
  `POST /api/integrations/{id}/relink`
- `backend/app/schemas/schemas.py` — `LinkQualitySummary`, `LinkQualityUnlinkedPR`,
  `LinkQualityDisagreementPR`, `LinkQualityDisagreementLink`, `RelinkResponse`
- `frontend/src/App.tsx` — `/admin/linkage-quality` route + admin sidebar entry
- `frontend/src/utils/types.ts` — added Phase 02 types

## Deviations from spec
- Trend card "linkage rate over last 12 weeks" deferred — no history endpoint exists yet

## Blocked By
- 01-sync-depth-foundations

## Blocks
- 03-usage-health-dashboard
- 04-issue-conversations
- 05-creator-analytics
- 07-bottleneck-intelligence

## Description

Rewrite PR↔issue linking to prefer Linear's native GitHub attachments as the authoritative signal,
falling back to regex only when no attachment exists. Expose link quality to admins so they can see
the effect of the upgrade and identify gaps in team process.

## Research-driven notes

- Linear exposes attachments via GraphQL `attachments` connection on `Issue`, with a dedicated
  root `attachments(filter: { sourceType: { eq: "github" } })` query. `Attachment.sourceType`
  returns `'github'` (among others) and `metadata` is a JSON blob containing PR status / review
  counts / commit info per Linear's own docs. The `normalized_source_type` column added in Phase
  01 distinguishes `github_pr` (URL matches `/pull/\d+`) from `github_commit` (matches
  `/commit/[0-9a-f]+`) — the linker should only resolve `github_pr` rows to PullRequest
- Most attachments are integration-created when the Linear GitHub integration is installed on
  the repo. If a workspace has never installed that integration, `external_issue_attachments`
  will be empty and the linker degrades gracefully to regex-only (passes 2-4)
- Phase 01 already populates `external_issue_attachments` from Linear — this phase is about
  consuming that data

## Deliverables

### backend/app/services/linear_sync.py

- Rewrite `link_prs_to_external_issues(db, integration_id)`:
  1. **Pass 1 — attachments (high confidence)**: query `external_issue_attachments` where
     `normalized_source_type = 'github_pr'`, parse each `url` to extract
     `owner/repo/pull/<number>` (regex `https://github\.com/([^/]+)/([^/]+)/pull/(\d+)`),
     resolve to `PullRequest.id` via `Repository.owner + Repository.name + PR.number`, upsert
     `PRExternalIssueLink` with `link_source='linear_attachment'`, `link_confidence='high'`
  2. **Pass 2 — branch matching (medium confidence)**: for PRs not yet linked in Pass 1, apply
     existing regex to `head_branch`; upsert with `link_source='branch'`, `link_confidence='medium'`
  3. **Pass 3 — title matching (medium confidence)**: for still-unlinked PRs, apply regex to
     `title`; `link_source='title'`, `link_confidence='medium'`
  4. **Pass 4 — body matching (low confidence)**: apply regex to `body`; `link_source='body'`,
     `link_confidence='low'`
- Important: the passes are cumulative — a PR already linked at `high` doesn't get downgraded by a
  later pass finding a weaker match. But if Pass 1 links PR→IssueA and Pass 2 finds PR→IssueB in
  the branch name, we create a second link row with lower confidence (a PR can touch multiple
  issues). Track all matches; don't hide disagreements
- Existing behaviour of skipping duplicate `(pull_request_id, external_issue_id)` pairs stays

### backend/app/services/stats.py or new backend/app/services/linkage_quality.py

- `get_link_quality_summary(db, org_id=None)` → returns:
  ```python
  {
      "total_prs": int,
      "linked_prs": int,
      "linkage_rate": float,  # linked / total
      "by_confidence": {"high": int, "medium": int, "low": int},
      "by_source": {"linear_attachment": int, "branch": int, "title": int, "body": int},
      "unlinked_recent": [PR summaries, last 30 days, up to 50],
      "disagreement_prs": [PR ids where multiple issue IDs linked with equal confidence],
  }
  ```

### backend/app/api/integrations.py

- New endpoint `GET /api/integrations/{id}/linkage-quality` → `LinkQualitySummary` response
  (admin-only via `require_admin`)
- New endpoint `POST /api/integrations/{id}/relink` → triggers async relink job
  (admin-only, protected by the existing advisory-lock pattern used for sync)

### backend/app/services/linear_sync.py — background relink job

- `run_linear_relink(integration_id)` — convenience wrapper that runs the 4-pass linker on all
  existing PRs for that integration. Writes progress to a `SyncEvent` with `kind='relink'` so the
  UI can show progress
- Idempotent — can be re-run safely; upserts rather than recreates links
- The Phase 01 sync path also calls the new linker after each sync completes, replacing the old
  regex-only path

### frontend/src/pages/admin/LinkageQuality.tsx (new)

- Route: `/admin/linkage-quality` (add to Admin sidebar under Integrations)
- Summary card: linkage rate donut chart (high / medium / low / unlinked)
- Trend card: linkage rate over last 12 weeks (once history exists)
- Source breakdown bar chart: `linear_attachment` vs `branch` vs `title` vs `body`
- Table: unlinked PRs (last 30 days) with PR title, author, repo, created date, link to GitHub —
  gives the team a to-do list to tighten their process
- Disagreement PRs table: PRs with multiple issue links at the same confidence — may indicate
  either legitimate multi-issue PRs or confused linking
- "Rerun linker" button (admin-only) calls `POST /api/integrations/{id}/relink` and streams progress

### frontend/src/hooks/

- New `useLinkageQuality(integrationId)` hook following the existing TanStack Query pattern

### frontend/src/App.tsx

- Add Admin sidebar entry: "Linkage Quality" → `/admin/linkage-quality`, gated on admin role

### backend/tests/

- `tests/services/test_linking_upgrade.py`: regression tests for the 4-pass pipeline, confidence
  tier assignment, disagreement tracking
- `tests/integration/test_relink_idempotency.py`: running the linker twice must not create duplicates

## Acceptance criteria

- [x] A PR with a Linear-attached GitHub PR link is always linked at `high` confidence, regardless
      of whether its title mentions the issue ID
- [x] A PR that only has the issue ID in its body gets `low` confidence
- [x] Relinking an integration with N PRs is O(N), and rerunning produces zero diff
- [x] The admin panel shows linkage rate broken down by confidence tier
- [x] Disagreement PRs surface correctly when test data is seeded with conflicting signals
- [x] Phase 01's post-sync call to the new linker works end-to-end in a clean local sync
