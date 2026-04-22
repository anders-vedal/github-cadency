# Phase 06: Security hardening

**Status:** completed
**Priority:** Medium
**Type:** security
**Apps:** devpulse
**Effort:** small
**Parent:** linear-insights-v2-fixes/00-overview.md

## Blocked By
- None

## Blocks
- None

## Description

Two security concerns from the review: admin-editable `ClassifierRule.pattern` has no length
or ReDoS guard (currently safe because rule types do string equality, but the door is open),
and `sanitize_preview` has known gaps around raw API keys without a keyword prefix.

## Deliverables

### `backend/app/services/classifier_rules.py` + `backend/app/api/classifier_rules.py` — pattern validation

**Gap** (classifier_rules.py lines 71-98, classifier_rules.py API lines 28-35): admin-created
rules accept arbitrary text in `pattern`. Today rule types do substring / set-membership
checks (safe). The risk: when a `regex` rule_type is added later, an admin can paste a
catastrophically-backtracking pattern that hangs the DORA v2 request path.

**Fix**:
1. Import the existing `_validate_regex_safe()` guard from
   `backend/app/services/work_categories.py` — it already implements nested-quantifier /
   unbounded-repetition detection that the project uses elsewhere.
2. Add a length cap (e.g., `len(pattern) <= 200`) regardless of rule_type.
3. In `_validate()` on `ClassifierRuleCreate`, dispatch based on `rule_type`:
   - `substring` / `exact` / `label_match`: only enforce the length cap.
   - `regex` (future-proofing, whether currently wired or not): enforce length cap AND call
     `_validate_regex_safe(pattern)`. Raise `ValueError` with a helpful message on failure.
4. The validation runs at both API-ingest time (Pydantic validator) and service-level
   (`_validate()` before DB write) as belt-and-braces.
5. Add a test that a known-bad regex pattern (e.g., `(a+)+b` or `^(a|aa)+$`) is rejected;
   that an overlong pattern is rejected; that safe patterns pass.

Document in the admin UI help text (`frontend/src/pages/admin/ClassifierRules.tsx`) that
patterns are length-capped and regex patterns are ReDoS-validated.

### `backend/app/services/linear_sync.py` — strengthen `sanitize_preview`

**Gap**: the 40-char hex regex (`\b[0-9a-f]{40}\b`) only catches SHAs. Modern secrets (GitHub
PATs like `ghp_*`, Linear API keys like `lin_api_*`, JWTs, OpenAI `sk-*`) pass through when
no `Bearer`/`token`/`api_key` prefix precedes them.

**Fix**: extend the sanitization pattern set with known prefix patterns:
- `ghp_[A-Za-z0-9]{30,}` (GitHub PAT)
- `ghs_[A-Za-z0-9]{30,}` (GitHub OAuth server token)
- `github_pat_[A-Za-z0-9_]{30,}` (fine-grained PAT)
- `lin_api_[A-Za-z0-9]{30,}` (Linear API key)
- `sk-[A-Za-z0-9]{20,}` (OpenAI-style key)
- `sk-ant-[A-Za-z0-9-]{30,}` (Anthropic key)
- Generic base64-ish long token: `\b[A-Za-z0-9+/=]{40,}\b` — this one is broad, add only if
  the cost of false positives on legitimate base64 blobs is acceptable; safer to omit.

Reuse the same `<REDACTED>` placeholder. Keep email, UUID, and generic credential patterns.
Add unit tests in `test_linear_sanitize.py` for each new pattern.

## Testing

- Extend `backend/tests/unit/test_linear_sanitize.py` with one test per new redaction
  pattern (6+ new tests).
- New test file or extension `backend/tests/services/test_classifier_rules_validation.py`:
  - Rejects ReDoS-prone regex patterns
  - Rejects over-length patterns
  - Accepts safe patterns
  - Admin-role enforcement on CRUD endpoints (pair with Phase 11's
    `test_visibility_enforcement.py` — may live there depending on scope split)

## Acceptance criteria

- [x] `ClassifierRule.pattern` is length-capped (`MAX_PATTERN_LENGTH = 200`) and
      ReDoS-validated when `rule_type` is in `REGEX_RULE_TYPES` (currently
      `email_pattern`; extensible for future regex-backed rule types)
- [x] `sanitize_preview` redacts GitHub classic + fine-grained PATs, GitHub OAuth
      tokens, Linear API keys, Anthropic keys, and OpenAI-style keys without requiring
      a `Bearer` / `token=` / `api_key=` prefix
- [x] Admin UI help text documents the 200-char cap and regex validation
- [x] Regression tests cover every new redaction pattern and every rejected-pattern case

## Implementation notes

- `classifier_rules._validate_pattern` runs on both create AND update (belt-and-braces
  so direct service calls are covered even when the Pydantic body validator is skipped).
  Reuses `work_categories._validate_regex_safe` for the ReDoS heuristic (nested
  quantifier + trailing repetition pattern match).
- Prefix-anchored redactions cover: `ghp_`, `ghs_`, `gho_`, `ghu_`, `ghr_`,
  `github_pat_`, `lin_api_`, `sk-ant-`, `sk-`. Anthropic pattern runs before the
  generic OpenAI `sk-` pattern so `sk-ant-…` gets labelled correctly. Placeholder
  format is `[REDACTED:<provider>]` so logs/previews keep the diagnostic label without
  the secret.
- `PATCH /api/admin/classifier-rules/{id}` now catches `ValidationError` and returns
  400 (previously only `POST` did).

## Files Modified

- `backend/app/services/classifier_rules.py`
- `backend/app/services/linear_sync.py` (sanitize_preview patterns)
- `backend/app/api/classifier_rules.py` (PATCH error handling)
- `frontend/src/pages/admin/ClassifierRules.tsx` (help text + `maxLength={200}`)
