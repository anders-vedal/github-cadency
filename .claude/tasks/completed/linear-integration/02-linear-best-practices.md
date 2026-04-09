# Linear Best Practices: Workflow & Configuration Guide

> Priority: High | Effort: Small | Type: Documentation + Configuration
> Dependency: Should be established before or alongside `01-linear-integration.md`

## Context

Adopting Linear is only valuable if the team uses it consistently and in a way that produces clean, queryable data. This task defines the workflow conventions, naming standards, and configuration choices that maximize the value of Linear both as a standalone PM tool and as a data source for DevPulse.

Linear's strength is its opinionated defaults — the goal here is to work *with* those defaults, not fight them, while establishing the few team conventions Linear doesn't enforce.

## Deliverables

### 1. Workspace Configuration

#### Team Structure
- **One Linear team per engineering squad/team** (maps to DevPulse `team` field on developers)
- Team names should match DevPulse team names exactly (enables auto-correlation)
- Cross-team work uses Linear Projects (not team reassignment)

#### Workflow States
Use Linear's default workflow states — they map cleanly to DevPulse status categories:

| Linear State | DevPulse `status_category` | Notes |
|---|---|---|
| Triage | `triage` | New issues land here. Must be triaged before entering backlog. |
| Backlog | `backlog` | Accepted but not scheduled for a cycle |
| Todo | `todo` | Committed to current cycle, not started |
| In Progress | `in_progress` | Actively being worked on |
| In Review | `in_progress` | PR open, awaiting review (auto-transitions via GitHub integration) |
| Done | `done` | Completed |
| Cancelled | `cancelled` | Won't do |

**Do not add custom states unless there's a clear workflow gap.** Every custom state adds noise to metrics. If you need sub-states, use labels instead.

#### Priority Levels
Use Linear's built-in priority consistently:

| Priority | When to Use | SLA Target (suggested) |
|---|---|---|
| Urgent (P0) | Production incident, data loss, security | Response: 1h, Resolution: 4h |
| High (P1) | Blocks other work, customer-facing regression | Response: 4h, Resolution: 2 days |
| Medium (P2) | Normal feature work, non-blocking bugs | Response: 1 day, Resolution: sprint |
| Low (P3) | Nice-to-have, polish, minor improvements | No SLA, prioritize in planning |
| None | Unprioritized (should be triaged) | Triage within 1 business day |

**Rule: Every issue must have a priority set before leaving Triage.**

#### Estimation
- **Use Linear's built-in estimates** (story points or t-shirt sizes — pick one, be consistent)
- Recommended: Linear's exponential scale (1, 2, 4, 8) — forces coarse-grained estimates which are more accurate
- **Every issue entering a cycle must have an estimate.** This is non-negotiable for velocity tracking.
- Sub-issues inherit parent estimate only if not individually estimated

### 2. Cycle (Sprint) Conventions

#### Cadence
- **2-week cycles** (Linear default) — recommended for most teams
- Consistent start day (Monday recommended, matches Linear default)
- Cycles should be created in advance (Linear auto-creates if configured)

#### Cycle Discipline
- **Plan at cycle start:** Move issues from Backlog → Todo at the beginning of the cycle. This is the committed scope.
- **No scope additions after day 2** unless P0/P1. Mid-cycle additions are tracked as scope creep by DevPulse.
- **Incomplete work:** At cycle end, consciously decide per issue:
  - Move to next cycle (carry-over — tracked by DevPulse)
  - Return to backlog (descoped — not a failure, just a priority call)
  - Cancel (won't do)
- **Never auto-roll everything.** The act of deciding per issue is the planning discipline.

#### What Goes Into a Cycle
- Estimated issues only
- Assigned to a specific developer
- Priority set
- Clear acceptance criteria (in description or linked doc)

#### What Stays in Backlog
- Unprioritized ideas
- Unestimated work
- Blocked issues (until unblocked)
- "Someday" items

### 3. Issue Conventions

#### Titles
- Start with a verb: "Add ...", "Fix ...", "Update ...", "Remove ...", "Investigate ..."
- Be specific: "Fix login timeout on slow connections" not "Fix login"
- No issue type prefix in title (Linear has a type field): not "BUG: Fix login" but "Fix login" with type=Bug

#### Descriptions
- **Required for anything entering a cycle.** Backlog items can have minimal descriptions.
- Template (suggested):

```markdown
## What
[One sentence: what needs to change]

## Why
[Context: why this matters, who asked for it, what breaks without it]

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2

## Notes
[Optional: technical approach, links, screenshots]
```

#### Labels
- Use labels for **cross-cutting concerns**, not for categorization that Linear handles natively
- Good labels: `needs-design`, `needs-qa`, `blocked`, `spike`, `tech-debt`, `customer-reported`
- Bad labels: `bug` (use issue type), `high-priority` (use priority), `sprint-42` (use cycles), `backend` (use project/team)
- DevPulse work category rules can match on Linear labels — keep them consistent

#### Sub-issues
- Use for breaking down large issues (>4 points)
- Each sub-issue should be independently deliverable and testable
- Estimate sub-issues individually (don't rely on parent rollup)

### 4. GitHub Integration

#### Branch Naming
Linear auto-generates branch names from issue titles. Use them — this is how DevPulse links PRs to Linear issues:

```
feat/eng-123-add-user-search
fix/eng-456-login-timeout
```

- Format: `{type}/{identifier}-{slug}`
- The `ENG-123` identifier is what DevPulse matches on
- Don't rename branches after creation (breaks the link)

#### PR Conventions
- **Include Linear issue identifier in PR title or description:** `[ENG-123] Add user search`
- Linear's GitHub integration auto-links PRs to issues when branch names match
- One PR per Linear issue (preferred). If multiple PRs, all should reference the same identifier.
- When a PR closes a Linear issue, Linear auto-transitions to Done on merge

#### Automations (Linear settings)
Enable these Linear automations for clean data flow:

| Trigger | Action | Why |
|---|---|---|
| Branch created with issue ID | Move issue to In Progress | Accurate start-time tracking |
| PR opened | Move issue to In Review | Distinguishes coding from review |
| PR merged | Move issue to Done | Auto-close on delivery |
| PR closed (not merged) | Move issue back to In Progress | Abandoned PR shouldn't close issue |

### 5. Project Conventions

- **One Linear Project per initiative/epic** (multi-sprint effort with a defined goal)
- Set target dates (enables DevPulse project health tracking)
- Use milestones within projects for phase gates
- Update project status weekly (On Track / At Risk / Off Track)
- Lead = the person accountable for the project's delivery

### 6. Triage Conventions

- **Triage inbox is checked daily** by team lead or rotating triager
- Every issue in Triage gets: priority set, team assigned, type set
- Target: <24h average triage time (DevPulse tracks this)
- Issues from external sources (customer reports, bugs from monitoring) land in Triage automatically via Linear integrations or API

### 7. What DevPulse Tracks from These Conventions

| Convention | DevPulse Metric | What Bad Looks Like |
|---|---|---|
| Estimate every cycle issue | Estimation accuracy | Lots of unestimated items = can't track velocity |
| No mid-cycle additions | Scope creep rate | >20% scope creep = planning is broken |
| Triage daily | Triage latency | >2 days avg = work entering pipeline without review |
| Set priorities | Priority distribution | >30% urgent/high = everything is a fire |
| Use branch naming | Work alignment | <70% PR linkage = lots of untracked work |
| Update project status | Project health | Stale projects = no visibility into initiative progress |
| Cycle discipline | Completion rate | <70% = over-committing or poor estimation |
| Consistent teams | Team velocity trend | Can't benchmark teams if membership is fluid |

### 8. Anti-patterns to Avoid

| Anti-pattern | Why It's Bad | What to Do Instead |
|---|---|---|
| Everything is Urgent | Metrics become meaningless | Reserve P0 for actual incidents |
| Skipping estimation | No velocity data | Estimate before entering cycle |
| 50-item cycles | Completion rate always low | 8-15 issues per dev per cycle |
| Using Linear as a wiki | Issues become stale docs | Link to docs, don't embed |
| Re-estimating after completion | Estimation accuracy is fiction | Estimate once, learn from gaps |
| Custom states for every team | Inconsistent data across teams | Use default states + labels |
| Never closing old issues | Backlog becomes a graveyard | Monthly backlog grooming, cancel stale items |
| Ignoring Triage | Issues skip review | Auto-triage = no triage |

## Acceptance Criteria

- [ ] Workspace configuration documented and applied
- [ ] Team structure matches DevPulse team naming
- [ ] Priority levels defined with SLA targets
- [ ] Cycle conventions documented (cadence, discipline, what enters/stays)
- [ ] Issue conventions documented (titles, descriptions, labels, sub-issues)
- [ ] GitHub integration configured (automations, branch naming)
- [ ] Project conventions documented (naming, health updates, leads)
- [ ] Triage workflow established
- [ ] Anti-patterns documented
- [ ] Team walkthrough/onboarding completed
