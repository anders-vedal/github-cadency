# Task P3-04b: AI Integration for Issue Creator Stats

## Phase
Phase 3 — Make It Proactive

## Status
completed

## Blocked By
- P3-04-issue-creator-analytics

## Blocks
None

## Description
Extend `POST /api/ai/one-on-one-prep` context with issue creator stats. When the developer being prepped has created issues (is a team lead/PO), include their issue creator stats so Claude can surface patterns like:
- "Issues you create without checklists take 2.3x longer to close"
- "30% of your issues are reopened vs 10% team average"

## Deliverables

### backend/app/services/ai_analysis.py (extend)
In the 1:1 prep data gathering:
- [x] Check if the developer has created issues (query `Issue.creator_github_username == dev.github_username`)
- [x] If yes, call `get_issue_creator_stats()` filtered to that user, and include the per-creator metrics + team averages in the AI context
- [x] Add a prompt section instructing Claude to analyze the creator's issue quality patterns

### No frontend changes needed
The AI result renderer already handles arbitrary structured output.

## Files Modified
- `backend/app/services/ai_analysis.py` — added issue creator stats gathering (step 8) in `run_one_on_one_prep()`, extended `ONE_ON_ONE_SYSTEM_PROMPT` with issue quality analysis guidelines
- `CLAUDE.md` — updated AI analysis pattern description, added P3-04b to completed improvements
- `docs/API.md` — updated "Context gathered" for `POST /api/ai/one-on-one-prep`
