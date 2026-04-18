# Product Context — GitHub Cadency (DevPulse)

## Purpose

Engineering intelligence platform that tracks developer activity across GitHub repos — PRs, code reviews, cycle times, team benchmarks, workload distribution. Ingests data via a read-only GitHub App. Deterministic metric computation with optional on-demand AI analysis via Claude API.

## North Star

Give engineering leads a single dashboard showing team health metrics that would otherwise require manual spreadsheet aggregation across repos.

## What This Product IS NOT

- Not a code quality tool — it measures activity and velocity, not code correctness
- Not a developer surveillance tool — aggregate team metrics, not individual monitoring
- Not a project management tool — it reads GitHub data, it doesn't manage tasks or sprints
- Not connected to other Nordlabs apps — self-contained, no Claros/Nexus dependency
- Not yet a paid product — pre-revenue, used internally

## Target Users

1. **Engineering lead** — needs team velocity metrics, PR review cycle times, workload distribution. Wants: weekly trend dashboards, anomaly detection, benchmark comparisons.
2. **Developer** (self-serve) — wants to see their own contribution patterns and review load.

## Strategic Priorities (Q2 2026)

1. Core metrics reliability — PR cycle time, review turnaround, merge frequency
2. AI analysis quality — on-demand Claude-powered insights on team patterns
3. Internal dogfooding — use it on Nordlabs' own repos to validate the product

## Domain Glossary

- **Cycle time** — time from PR open to merge
- **Review turnaround** — time from review request to first review
- **GitHub App** — the read-only OAuth integration that ingests repo activity (not a GitHub Actions app)
- **Benchmark** — a team-level aggregate metric compared against historical baselines

## Ecosystem Position

Self-contained product. No runtime dependencies on any other Nordlabs app. Shares infrastructure patterns but is architecturally independent. May become a paid product in the future.
