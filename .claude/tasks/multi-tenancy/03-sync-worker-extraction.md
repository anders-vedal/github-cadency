# Phase 03: Sync worker extraction

**Status:** Planned
**Priority:** High
**Type:** infrastructure
**Apps:** devpulse
**Effort:** large
**Parent:** multi-tenancy/00-overview.md
**Dependencies:** multi-tenancy/02-org-scoped-auth.md

## Scope

Move GitHub and Linear syncs out of the in-process APScheduler and onto a dedicated worker process backed by a Redis queue (ARQ). Replace the global Postgres advisory lock with per-org locks. Stagger schedules so 50 tenants don't all hit `:00`. Cap concurrency so the worker RAM ceiling stays predictable. This is the phase that determines whether 30 concurrent tenant syncs makes the API server fall over.

## What "done" looks like

- A new `backend/app/worker/` module runs as a separate process (`uvicorn`-style entrypoint + docker-compose service)
- API container no longer runs any sync work — APScheduler is removed or reduced to a heartbeat only
- A per-org sync job is enqueued by either: (a) the org's configured schedule firing (scheduler-in-worker) or (b) a manual "sync now" API call (enqueue from API)
- Worker concurrency cap: configurable (default 5 concurrent sync jobs across all orgs)
- Per-org advisory lock: only one sync at a time for a given org, regardless of concurrency cap
- Schedule jitter: when N orgs all have an "hourly" sync, their fire times are spread across the hour (deterministic hash of `org_id` → offset 0–59 min)
- Redis is deployed in prod + staging (staging may share with other projects — TBD)
- Health endpoint `/api/system/worker` exposes queue depth, in-flight jobs, last-run-per-org
- A single noisy tenant's 4-hour sync does not block other orgs' scheduled runs

## Key design decisions

- **ARQ over Celery/RQ/Dramatiq**: ARQ is async-native (matches our asyncio codebase), minimal dependencies, Redis-only. Celery is overkill and sync-first. RQ doesn't support async workers well. Dramatiq is fine but less ergonomic with async.
- **Scheduler location**: put the schedule-fire logic *inside* the worker, not the API. The worker has a periodic "tick" task that queries `sync_schedule_config` rows due to fire, enqueues one job per org, respects jitter. API keeps no scheduler. Benefit: API restarts don't lose scheduled fires, scheduler availability is independent of API availability.
- **Per-org advisory lock key**: `hash(f"devpulse:sync:{org_id}")` as a 64-bit int passed to `pg_try_advisory_lock()`. Replaces the current global lock. A tenant holding the lock doesn't block other tenants, and lock release on worker crash is automatic (Postgres session ends = lock released).
- **Cancellation**: existing `_check_cancel()` pattern works — the job reads its `sync_event` row at batch boundaries and bails if `cancelled_at` is set. API endpoint for "cancel sync" writes to the DB row, worker sees it.
- **Concurrency cap**: ARQ's `max_jobs` setting. Phase 04 layers per-org quotas on top (e.g. free tier = 1 concurrent sync).
- **Crash behavior**: if a worker crashes mid-sync, the `sync_event` row stays `in_progress`. Add a worker-side "resume or fail" pass on startup — any row `in_progress` older than 1 hour with no heartbeat gets marked `failed`.
- **Where AI calls still run**: keep them in the API process for now. AI is user-initiated, not scheduled. If AI calls get long, revisit in a future phase.

## Checklist

### Infrastructure
- [ ] Add Redis to `docker-compose.yml` + `docker-compose.staging.yml` + prod compose (port 6379, persistent volume, AOF enabled)
- [ ] Add `REDIS_URL` to config + `.env.example`
- [ ] Add ARQ to `requirements.txt`

### Worker process
- [ ] `backend/app/worker/__init__.py` — ARQ `WorkerSettings` with job definitions and cron-like schedule tick
- [ ] `backend/app/worker/sync_jobs.py` — `run_github_sync_for_org(org_id)`, `run_linear_sync_for_org(org_id)` — wrappers around existing sync services that set up DB session, resolve org, acquire per-org lock, execute, release
- [ ] `backend/app/worker/scheduler_tick.py` — runs every minute; queries `sync_schedule_config` for orgs due to fire (next_run_at <= now), computes jitter, enqueues jobs, updates `next_run_at`
- [ ] Worker-entrypoint script (`backend/run_worker.py`) that ARQ invokes

### Lock migration
- [ ] Replace `pg_try_advisory_lock(constant)` in `github_sync.py` with `pg_try_advisory_lock(hash_of_org_id)`
- [ ] Same change in `linear_sync.py`
- [ ] Add unit test: two concurrent calls for same org → second blocks; two concurrent calls for different orgs → both proceed

### Scheduling
- [ ] Add `schedule_jitter_seconds` column to `sync_schedule_config` (0 default, backfilled as `hash(org_id) % (interval_minutes * 60)` on migration)
- [ ] `next_run_at` column (computed on each schedule save as `last_run_at + interval + jitter`)
- [ ] Scheduler-tick job reads `next_run_at`, not raw interval

### API
- [ ] Remove APScheduler from `main.py` (or reduce to a no-op stub so tests don't choke)
- [ ] `POST /api/sync/trigger` now enqueues an ARQ job instead of calling sync directly (returns immediately with sync_event_id)
- [ ] `POST /api/sync/cancel/{sync_event_id}` writes `cancelled_at` — worker picks it up on next batch boundary
- [ ] `GET /api/system/worker` — queue depth, in-flight, last-run-per-org (protected, admin-only)

### Docker / deploy
- [ ] New `worker` service in all compose files, sharing the backend image, entrypoint `python -m backend.app.worker`
- [ ] Dedicated env vars for worker (same Postgres, same Redis; no port exposure)
- [ ] Add worker to `deploy-staging.yml` + `deploy-prod.yml` compose-up

### Observability
- [ ] structlog event type `worker.job.started` / `.completed` / `.failed` / `.cancelled` with `org_id`, `sync_event_id`, `duration_ms`
- [ ] Prometheus metrics if obs stack is deployed: `worker_queue_depth`, `worker_in_flight`, `sync_duration_seconds{org_id, type}`

### Testing
- [ ] Integration test: enqueue 20 sync jobs across 10 orgs, concurrency cap at 5, assert ≤5 run simultaneously and each org's two jobs serialize
- [ ] Integration test: org A's long sync doesn't block org B's scheduled fire (B fires on schedule)
- [ ] Load test: simulate 50 orgs on staging with hourly schedule, observe memory/CPU/queue-depth over 3 hours

## Risks

- **Redis as new single point of failure**: without Redis, syncs stop. Mitigation for MVP: Redis with AOF persistence, single instance is fine (API still works without syncs). Later: Redis replication if uptime demands.
- **Worker crash mid-sync**: partial data committed via per-repo batch commits (existing pattern) — crash leaves valid partial state. The "resume or fail" pass on worker startup prevents stuck `in_progress` rows.
- **Schedule drift**: scheduler-tick uses absolute `next_run_at`, not relative intervals, so missed ticks don't cascade into delayed syncs indefinitely. A sync that was due 2h ago runs immediately at next tick.
- **Docker compose complexity**: one more service (worker) + Redis (if not already there). Acceptable cost.

## Out of scope (later phases)

- Per-org quotas on sync frequency / concurrency — Phase 04 (this phase makes quotas enforceable)
- Composite indexes that keep sync queries fast at 50-org scale — Phase 05
- Worker autoscaling — deferred, CPX21 single worker is enough for MVP capacity target
