# Multi-tenant SaaS foundation (open signups)

**Status:** Planned
**Priority:** High
**Type:** feature
**Apps:** devpulse
**Effort:** large

## Overview

Convert DevPulse from a single-tenant deployment into a multi-tenant SaaS where any organization can sign up, install the GitHub App / connect Linear, and get isolated access — all on the same Hetzner VPS + Postgres instance. The goal is to open self-serve signups to external orgs (initial target: a handful of trial customers, capacity planning for 20–50 small orgs on a modest VPS) without customer data ever being cross-visible.

This is a foundational refactor: no table in DevPulse currently carries an `org_id`, no JWT carries tenant identity, and the sync scheduler assumes one global workspace. The work spans data model, auth, background work, quotas, query performance, signup UX, and ops tooling.

## Tenant model decisions (confirmed)

1. **Tenant identity**: users create an **Org first**, then install the GitHub App *into* that org. A single org can later add more GitHub installs or Linear workspaces. Org identity is decoupled from any single external integration.
2. **Membership**: **invite-only**. The person who creates the org is the first admin. Subsequent users from the same GitHub org do NOT auto-join — they must be invited by an existing admin. Prevents one bad actor in a large public GitHub org from seeing everyone's data.
3. **Pricing at MVP**: one **free tier** with conservative quotas (max 10 repos, hourly sync minimum, $10/month AI budget cap). No Stripe integration in Phase 04 — internal quota enforcement only. A future epic can add paid tiers.
4. **Data residency**: single-region (Hetzner EU) for now. Tenants are informed at signup. No per-tenant DB / per-tenant region routing.

## Why this matters

The alternative — spinning up a separate VPS + DB per customer — doesn't scale past a handful of design partners and burns ops time on every trial signup. True multi-tenancy is the only path to self-serve onboarding. The architectural shift is significant but one-time; the resulting codebase becomes the template for how Nordlabs apps accept external orgs.

## Load and capacity targets

- **Target capacity**: 20–50 small orgs (each <20 repos, hourly sync) on a Hetzner CPX21 (3 vCPU / 4 GB)
- **Bottleneck ordering** (by my analysis): sync worker RAM > Postgres connection pool > AI budget > API request concurrency. Phases 03 / 04 / 05 address each in turn.
- **Stretch target** (post-epic): CPX41 scale-up + sync-worker-on-separate-process for 100+ orgs

## Phases

- [ ] Phase 01: **Org data model + tenancy migration** → `01-org-data-model.md`
- [ ] Phase 02: **Org-scoped auth + access** → `02-org-scoped-auth.md`
- [ ] Phase 03: **Sync worker extraction** → `03-sync-worker-extraction.md`
- [ ] Phase 04: **Per-org quotas + rate limits** → `04-per-org-quotas.md`
- [ ] Phase 05: **Query performance hardening** → `05-query-performance.md`
- [ ] Phase 06: **Self-serve signup + onboarding** → `06-self-serve-signup.md`
- [ ] Phase 07: **Super-admin ops dashboard** → `07-super-admin-ops.md`

## Dependency graph

```
01 ─┬──> 02 ─┬──> 03 ─────┐
    │        ├──> 04 ─────┼──> 07
    │        │            │
    │        └──> 06 <────┘   (06 also depends on 04)
    └──> 05
```

## Acceptance criteria (epic-level)

- [ ] Any new visitor can create an org at `/signup` without operator intervention
- [ ] Two separate orgs can use DevPulse simultaneously with **zero** data overlap (auditable via E2E test that creates 3 orgs, seeds distinct data, and asserts isolation across every list/detail endpoint)
- [ ] A single noisy tenant cannot degrade performance for others (syncs concurrency-capped, rate limits per-org, AI budget per-org)
- [ ] Sentinel errors and logs are taggable/filterable by `org_id`
- [ ] Existing single-tenant production data is migrated into a "default" org with zero data loss
- [ ] Super-admin can see all orgs, their usage/spend/sync health, and suspend a misbehaving org in under 30 seconds
- [ ] Full test: 50 seeded orgs on staging, simulated concurrent traffic, p95 API latency stays under 500ms and all syncs complete within their interval

## Risks & open questions for later phases

- **Migration of existing prod data**: DevPulse is not yet in production (per user memory), so this is greenfield — no customers to migrate. Confirms we can use a simple "create default org, stamp all existing rows" migration without a zero-downtime dance.
- **GitHub App installation transferability**: if a user installs the App on their personal account then later creates an org, we need a way to re-parent the install. Deferred to Phase 02 design.
- **Linear workspace ownership**: Linear API keys are workspace-scoped. We store them per-org; if two orgs claim the same workspace we reject the second. Phase 02 handles the conflict path.
- **Super-admin identity**: super-admin is a platform-level role, not per-org. Initial approach: a hardcoded allowlist of GitHub logins in env (`DEVPULSE_SUPER_ADMINS=anders-vedal,…`). Phase 07 can upgrade to a `super_admins` table.
- **Observability per-org**: adding `org_id` to every structlog event is cheap (middleware injection) but needs consistent field naming. Phase 02 establishes the convention.
