# Task M-06: Add Retry/Timeout to Claude API Calls

## Severity
Medium

## Status
done

## Blocked By
None

## Blocks
None

## Description
Claude API calls in `services/ai_analysis.py` (`_call_claude_and_store()`) have no retry or timeout handling. If the Anthropic API returns a transient error (network timeout, 502, 503, rate limit), the exception propagates directly as an HTTP 500 to the user.

### Fix
1. Add a timeout to the `anthropic.AsyncAnthropic` client (e.g., 120s)
2. Wrap `client.messages.create()` with retry logic for transient errors (429, 500, 502, 503, 529)
3. Use exponential backoff (2s, 8s, 30s) consistent with the GitHub API retry pattern in `github_get()`
4. Return a user-friendly error message on final failure instead of a raw 500

Note: The Anthropic Python SDK has built-in retry support via `max_retries` parameter on the client constructor.

### Files
- `backend/app/services/ai_analysis.py` — `_call_claude_and_store()`

### Architecture Docs
- `docs/architecture/SERVICE-LAYER.md` — AI Integration section
- `docs/architecture/DATA-FLOWS.md` — AI Analysis Lifecycle section
