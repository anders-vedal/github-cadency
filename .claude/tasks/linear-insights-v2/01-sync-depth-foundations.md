# Phase 01: Sync depth foundations

**Status:** Completed (2026-04-22)
**Priority:** High
**Type:** feature
**Apps:** devpulse
**Effort:** large
**Parent:** linear-insights-v2/00-overview.md

## Files Created
- `backend/migrations/versions/042_linear_insights_v2_sync_depth.py`
- `backend/tests/integration/test_linear_sync_depth.py` (8 tests)
- `backend/tests/unit/test_linear_rate_limit.py` (5 tests)
- `backend/tests/unit/test_linear_sanitize.py` (19 tests)

## Files Modified
- `backend/app/models/models.py` — added 5 models (`ExternalIssueComment`,
  `ExternalIssueHistoryEvent`, `ExternalIssueAttachment`, `ExternalIssueRelation`,
  `ExternalProjectUpdate`); extended `ExternalIssue` with SLA + triage + subscribers_count +
  reaction_data; extended `PRExternalIssueLink` with `link_confidence`
- `backend/app/services/linear_sync.py` — fixed HTTP 400 RATELIMITED handling + proactive
  complexity-budget slowdown; extended `_ISSUES_FIELDS` GraphQL with SLA/triage/subscribers/
  reactionData/comments/history/attachments/relations; added `sanitize_preview()`,
  `normalize_attachment_source()`, per-issue persistence helpers (`_persist_issue_comments`,
  `_persist_issue_history`, `_persist_issue_attachments`, `_persist_issue_relations`);
  `sync_linear_issues` returns a dict of counters; new `sync_linear_project_updates()`;
  `run_linear_sync` wires the new step + extended counters on `SyncEvent.log_summary`

## Blocked By
- None

## Blocks
- 02-linking-upgrade-and-quality
- 03-usage-health-dashboard
- 04-issue-conversations
- 05-creator-analytics
- 06-flow-analytics-from-history
- 07-bottleneck-intelligence

## Description

Extend Linear sync to ingest comments, activity history, attachments, SLA fields, relations, project
updates, subscribers, and triage context. Add supporting tables with typed columns that mirror
Linear's schema. Also fix a latent bug in rate-limit handling and switch the automation-marker logic
to use Linear's native `botActor` field instead of email-pattern inference.

## Research-driven adjustments from initial plan

Linear's GraphQL schema is richer than the initial plan assumed. Concrete corrections:

1. **`IssueHistory` has typed from/to fields**, not opaque values. Store them structured:
   `fromStateId`/`toStateId`, `fromAssigneeId`/`toAssigneeId`, `fromEstimate`/`toEstimate`,
   `fromPriority`/`toPriority`, `fromCycleId`/`toCycleId`, `fromProjectId`/`toProjectId`,
   `fromParentId`/`toParentId`, `addedLabelIds`/`removedLabelIds`, `archived`/`autoArchived`/
   `autoClosed`. One history node can change multiple fields — keep a single row with all changed
   columns rather than expanding one row per field (previous plan said "expand N rows").
2. **SLA is on `Issue` directly** — extend `external_issues` with `sla_started_at`,
   `sla_breaches_at`, `sla_high_risk_at`, `sla_medium_risk_at`, `sla_type`, `sla_status`. No new
   table needed.
3. **Reactions are exposed as `reactionData` JSON on parent entities** (Comment/Issue/
   ProjectUpdate). No Reactions table — just persist the JSON blob.
4. **`botActor` is the authoritative automation marker** (not email-pattern matching). `Comment.botActor`,
   `IssueHistory.botActor`, and `Attachment` `creator IS NULL` (or attached via integration)
   identify automation. `IssueHistory.actor IS NULL AND botActor IS NULL` = Linear system action.
5. **Rate limit responses are HTTP 400 with `RATELIMITED` error code in the body, not HTTP 429.**
   The existing `LinearClient.query()` handles 429 but may silently fail on 400 RATELIMITED.
   Verify and fix.
6. **Sync relations** — `IssueRelation { type: blocks|duplicate|related, issue, relatedIssue }`.
   Needed by Phase 07 for blocked-chain depth. Cheap to add here.
7. **Sync `ProjectUpdate`** — Linear's authoritative health narrative with `health` enum
   (onTrack/atRisk/offTrack) and `diffMarkdown`. Replaces any hand-rolled project-status history.
8. **Sync `Issue.subscribers`** — stakeholder signal for bus-factor analysis.
9. **Extend `external_issues` with triage fields**: `triaged_at`, `triage_responsibility_team_id`,
   `triage_auto_assigned`.

## Deliverables

### backend/app/models/models.py

- **`ExternalIssueComment`** (table `external_issue_comments`)
  - id (pk), issue_id FK→external_issues (CASCADE), external_id (unique — Linear comment id),
    parent_comment_id (nullable self-FK for reply threads), author_developer_id FK→developers
    (SET NULL, nullable), author_email, external_user_id (nullable — for non-Linear integration
    users like Slack), created_at, updated_at, edited_at (nullable), body_length (int),
    body_preview (string, 280 chars, sanitized), reaction_data (JSONB, nullable),
    is_system_generated (bool — derived from `botActor != null`), bot_actor_type (string,
    nullable — e.g. 'github', 'workflow')
  - Indexes: `(issue_id, created_at)`, `(author_developer_id, created_at)`,
    `(parent_comment_id)` for thread walks

- **`ExternalIssueHistoryEvent`** (table `external_issue_history`)
  - id (pk), issue_id FK→external_issues (CASCADE), external_id (unique Linear history event id),
    actor_developer_id FK→developers (SET NULL, nullable), actor_email, bot_actor_type (string,
    nullable), changed_at, from_state (string, nullable), to_state (string, nullable),
    from_state_category (nullable), to_state_category (nullable),
    from_assignee_id FK→developers (SET NULL, nullable),
    to_assignee_id FK→developers (SET NULL, nullable),
    from_estimate (float, nullable), to_estimate (float, nullable),
    from_priority (int, nullable), to_priority (int, nullable),
    from_cycle_id FK→external_sprints (SET NULL, nullable),
    to_cycle_id FK→external_sprints (SET NULL, nullable),
    from_project_id FK→external_projects (SET NULL, nullable),
    to_project_id FK→external_projects (SET NULL, nullable),
    from_parent_id FK→external_issues (SET NULL, nullable),
    to_parent_id FK→external_issues (SET NULL, nullable),
    added_label_ids (JSONB, nullable), removed_label_ids (JSONB, nullable),
    archived (bool, default false), auto_archived (bool, default false),
    auto_closed (bool, default false)
  - Indexes: `(issue_id, changed_at)`, `(to_state_category, changed_at)` — for time-in-state
    queries, `(actor_developer_id, changed_at)`

- **`ExternalIssueAttachment`** (table `external_issue_attachments`)
  - id (pk), issue_id FK→external_issues (CASCADE), external_id (unique Linear attachment id),
    url (text), source_type (string — `github`, `slack`, `zendesk`, `figma`, `notion`, `other`),
    normalized_source_type (string — our derivation: `github_pr`, `github_commit`, `github_issue`,
    `slack`, `figma`, `other`), title (nullable), metadata (JSONB — Linear metadata blob),
    created_at, updated_at, actor_developer_id FK→developers (SET NULL, nullable),
    is_system_generated (bool — creator is null at Linear → likely integration-attached)
  - Indexes: `(issue_id, normalized_source_type)`, `(url)` — reverse lookup from PR URL

- **`ExternalIssueRelation`** (table `external_issue_relations`)
  - id (pk), issue_id FK→external_issues (CASCADE), related_issue_id FK→external_issues (CASCADE),
    external_id (unique — Linear relation id), relation_type (string —
    `blocks`/`blocked_by`/`related`/`duplicate`), created_at
  - Indexes: `(issue_id, relation_type)`, `(related_issue_id, relation_type)`
  - UniqueConstraint(external_id)
  - Bidirectional storage: when Linear says A `blocks` B, insert both (A blocks B) and (B blocked_by A)

- **`ExternalProjectUpdate`** (table `external_project_updates`)
  - id (pk), project_id FK→external_projects (CASCADE), external_id (unique),
    author_developer_id FK→developers (SET NULL, nullable), author_email,
    body_length, body_preview (280 chars, sanitized), diff_length (int, nullable),
    health (string — `onTrack`/`atRisk`/`offTrack`/`unknown`),
    created_at, updated_at, edited_at (nullable), is_stale (bool, default false),
    reaction_data (JSONB, nullable)
  - Indexes: `(project_id, created_at)`

- **Extend `external_issues`** with:
  - `sla_started_at`, `sla_breaches_at`, `sla_high_risk_at`, `sla_medium_risk_at`,
    `sla_type` (string — `calendar`/`business_days`), `sla_status` (string — `LowRisk`/
    `MediumRisk`/`HighRisk`/`Breached`/`Completed`/`Failed`)
  - `triaged_at` (datetime, nullable)
  - `triage_responsibility_team_id` (string, nullable — Linear team external id)
  - `triage_auto_assigned` (bool, default false)
  - `subscribers_count` (int, default 0) — cheap bus-factor signal without persisting the list
  - `reaction_data` (JSONB, nullable)

- **`ExternalIssueSubscriber`** (optional — table `external_issue_subscribers`, can be deferred
  if `subscribers_count` is enough)
  - id (pk), issue_id FK→external_issues (CASCADE), developer_id FK→developers (CASCADE),
    external_user_id, subscribed_at
  - UniqueConstraint(issue_id, developer_id)

- Extend **`PRExternalIssueLink`**:
  - Add `link_confidence` column: `String(10)`, values `high` / `medium` / `low`, default `low`,
    server_default `'low'`
  - Extend `link_source` enum (column stays same width, widen docs):
    `linear_attachment` (high), `branch` (medium), `title` (medium), `body` (low),
    `commit_message` (low)

### backend/migrations/versions/*.py

- New Alembic migration creating the six new tables (plus optional subscribers table) and
  altering `pr_external_issue_links` + `external_issues`
- Migration is additive — no destructive change; existing rows get `link_confidence = 'low'` as a
  safe default until the Phase 02 relinker runs

### backend/app/services/linear_sync.py

**Fix rate limit handling** (first — blocking for all other sync extensions):
- In `LinearClient.query()`, check response body for `errors[].extensions.code == 'RATELIMITED'`
  even on HTTP 400
- Read response headers on every request: `X-Complexity`, `X-RateLimit-Complexity-Remaining`,
  `X-RateLimit-Complexity-Reset`, `X-RateLimit-Requests-Remaining`, `X-RateLimit-Requests-Reset`
- Proactive sleep when `X-RateLimit-Complexity-Remaining / 3_000_000 < 0.1` (less than 10% of
  budget remaining) — sleep until `X-RateLimit-Complexity-Reset`

**Extend `_ISSUES_FIELDS` GraphQL fragment** with:
```graphql
# SLA + triage (on Issue directly)
slaStartedAt slaBreachesAt slaHighRiskAt slaMediumRiskAt slaType slaStatus
triagedAt
triageResponsibility { team { id } autoAssigned }
subscribers(first: 0) { pageInfo { hasNextPage } } # count-only via first:0 trick won't work — use a separate query
reactionData

# Comments
comments(first: 100, orderBy: updatedAt) {
  pageInfo { hasNextPage endCursor }
  nodes {
    id user { email } externalUser { id } botActor { type subType name }
    parent { id } createdAt updatedAt editedAt body reactionData
  }
}

# History (one node can change multiple fields — store a single row with all changed columns)
history(first: 100, orderBy: createdAt) {
  pageInfo { hasNextPage endCursor }
  nodes {
    id createdAt actor { email } botActor { type subType }
    fromStateId toStateId fromAssigneeId toAssigneeId
    fromEstimate toEstimate fromPriority toPriority
    fromCycleId toCycleId fromProjectId toProjectId fromParentId toParentId
    addedLabelIds removedLabelIds
    archived autoArchived autoClosed
  }
}

# Attachments — the authoritative PR link
attachments(first: 50) {
  nodes { id url sourceType metadata title createdAt updatedAt creator { email } }
}

# Relations — blocks / blocked-by / related / duplicate
relations(first: 50) {
  nodes { id type issue { id } relatedIssue { id } }
}
```

**New sync steps** (add as numbered sub-steps inside `sync_linear_issues`):
1. Issue upsert — existing behaviour (extended with SLA + triage fields)
2. Comment upsert — skip if `botActor.type != null` **only** for dialogue-health computation later
   (still persist; `is_system_generated` flag on the column)
3. History upsert — resolve actor via existing `_resolve_developer_by_email`; store one row per
   history event with all changed columns populated
4. Attachment upsert — compute `normalized_source_type`: `github` + URL matches `/pull/\d+` →
   `github_pr`; `github` + `/commit/[0-9a-f]+` → `github_commit`; else keep Linear's sourceType
5. Relation upsert — bidirectional rows (see model deliverable)
6. Per-issue cursor expansion: if `comments.pageInfo.hasNextPage` or `history.pageInfo.hasNextPage`,
   queue a per-issue follow-up call (`sync_linear_issue_expansions(issue_id)`)

**ProjectUpdate sync** — new step in `run_linear_sync` between cycles and issues:
- `sync_linear_project_updates(client, db, integration_id, since)` — pagination same as other steps
- Upsert `ExternalProjectUpdate` rows with body preview + diff length + health

**Body preview sanitization** — reuse the pattern from `libs/errors.py` `ErrorSanitizer` to strip
emails, tokens, UUIDs, long hex strings from comment bodies, project update bodies, and attachment
titles before persisting the 280-char preview.

**Bot detection rule**:
```python
is_system_generated = comment.get("botActor") is not None
bot_actor_type = comment.get("botActor", {}).get("type")  # 'github' | 'slack' | 'workflow' | ...
```

**Counters on SyncEvent.log_summary**:
`comments_synced`, `history_events_synced`, `attachments_synced`, `relations_synced`,
`project_updates_synced`, `issue_expansions_triggered`.

### backend/tests/

- `tests/services/test_linear_sync_expansions.py`: unit tests for comment ingestion (bot detection
  via botActor, preview sanitization, reply-thread parent linking), history row population (all
  from/to columns populated correctly when multiple fields change), attachment normalized_source_type
  classification (`github_pr` vs `github_commit` vs `github` fallback), relation bidirectional
  insertion, SLA field mapping
- `tests/services/test_linear_rate_limit.py`: mock HTTP 400 with RATELIMITED error code — verify
  client sleeps and retries correctly (this is the latent bug fix — add a regression test)
- `tests/integration/test_linear_sync_depth.py`: integration test with mocked Linear GraphQL
  responses covering pagination, cancel mid-sync, idempotent re-sync across all new entities

### docs/architecture/DATA-MODEL.md

- Add Linear expansion section documenting the six new tables, their purpose, and query patterns
- Update the ERD diagram to include the new relations
- Document the `is_system_generated` flag semantics (never filtered at persist time, only at query
  time, so we can toggle bot-inclusion in metrics later)

## Sync cost audit

After the first full re-sync with the expanded query, record and document in the PR:
- Total GraphQL complexity budget consumed (read from `X-Complexity` across all calls)
- Wall-clock duration
- Number of per-issue expansion calls triggered
- Row counts in the new tables
- Comparison vs pre-expansion baseline

Baseline is used by Phase 02's backfill job to set expectations.

## Acceptance criteria

- [x] Full sync populates all six new tables (comments, history, attachments, relations,
      project updates) for existing integrations
- [x] Incremental sync (using `updatedAt`) picks up new deltas across all entities
- [x] Bot-authored comments are correctly flagged via `botActor` and excluded by default from
      dialogue-health signals
- [x] Body previews are sanitized — no emails / tokens / long UUIDs leak
- [x] `link_confidence` column live on `pr_external_issue_links` with `low` default
- [x] `external_issues` has all SLA + triage + subscriber-count columns populated
- [x] Rate-limit handling now correctly interprets HTTP 400 RATELIMITED (regression test added)
- [ ] Complexity budget consumed on full sync documented in the PR (deferred — needs a live sync run)
