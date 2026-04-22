# Banned metrics

DevPulse deliberately does not surface these metrics. Each has been weaponized
in the industry often enough that "surface it with a disclaimer" isn't a safe
remedy — the existence of the number on a dashboard creates the incentive to
optimize it, regardless of framing.

The authoritative list is in `backend/app/services/metric_spec.py` as the
`BANNED_METRICS` constant, also exposed via `GET /api/metrics/catalog` under
the `banned` key. This document supplies rationale per entry.

Contributors who need one of these for research should compute it ad-hoc, not
by adding it to the registry — the banned status is an intentional guardrail.

## Lines of code per developer

**Banned because:** LOC per developer correlates negatively with code quality
in every empirical study. Rewarding LOC inevitably produces more lines to
review, maintain, and delete later. It disadvantages developers who simplify,
refactor, or delete code — the highest-leverage work.

**Pattern to use instead:** bus factor (`bus_factor_by_file`), team-aggregate
cycle time, review-round distribution. See `services/metric_spec.py` for the
full list of throughput + quality surrogates.

## Commits per developer

**Banned because:** incentivizes commit-padding and discourages meaningful
commit hygiene (squashing, amending, atomic commits). A developer who squashes
two WIP commits before pushing "loses" activity; a developer who pushes
five micro-commits for the same work "wins". Neither pattern correlates with
outcome.

**Pattern to use instead:** PR-level or issue-level throughput, paired with
change failure rate + rework rate (per DORA v2).

## Story points per sprint per developer

**Banned because:** per-individual velocity is weaponizable and blind to scope
decisions, task complexity, and blocker incidence. Story points are a planning
heuristic for a team's capacity, not a personnel-evaluation signal. Treating
them as the latter destroys the estimation integrity they depended on.

**Pattern to use instead:** team-level velocity trend (already surfaced on the
sprint planning page), scope creep rate, completion rate. Individual-level
queries redirect to a 404 for this reason.

## Time to first review as a KPI

**Banned because:** turning review latency into a target creates incentives
for rubber-stamp reviews. The metric is useful as a distribution
(`review_round_count` + first-response time) but dangerous as a number a team
commits to beating.

**Pattern to use instead:** ship the full distribution of first-response time
(DevPulse does this on the conversations page), and pair with review-round
count to catch "fast but shallow" patterns. Never surface "average time to
first review" as a single-number target.

## LOC-weighted impact score

**Banned because:** any composite score that factors in LOC inherits the LOC
bias — plus adds opacity, since consumers can't tell whether a high score came
from big changes, long tenure, or real impact. Research consistently finds
composite productivity scores correlate with subjective intuition, meaning
they provide no information beyond what reviewers already know.

**Pattern to use instead:** reviewer-count on PRs, bus-factor on files, code
churn on hotspot files — each of those is interpretable in isolation and
surfaces a real signal rather than an opaque blend.

## Raw sentiment per developer

**Banned because:** cross-cultural noise on individual sentiment scoring is
around 30% per published research. A "grumpy" sentiment flag for a developer
who speaks English as a second language, or who prefers terse writing, is
noise that looks like data. Per-individual sentiment is also surveillance-
adjacent: tracking mood across comments crosses the line from diagnostic
signal to personal monitoring.

**Pattern to use instead (future, opt-in):** team-aggregate sentiment trend
with explicit opt-in consent per SPACE recommendations. No per-developer
surfacing.

## Adding to the list

When you propose a new metric and ultimately reject it on Goodhart grounds,
add an entry here. The rationale is the value — future contributors will
otherwise re-propose the same idea and you'll have forgotten why it was
rejected.
