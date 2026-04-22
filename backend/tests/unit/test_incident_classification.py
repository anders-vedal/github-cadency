"""Unit tests for incident_classification rules.

Covers the default rule set + the Phase 02 push-to-main-without-review rule
added in linear-insights-v2-fixes.
"""

from __future__ import annotations

from app.services.incident_classification import (
    DEFAULT_ALLOWED_DIRECT_PUSH_PREFIXES,
    IncidentRule,
    classify_pr,
    default_rules,
)


class TestDefaultRules:
    def test_revert_detected_as_hotfix(self):
        assert classify_pr('Revert "bad commit"', None) == "hotfix"

    def test_hotfix_prefix_detected(self):
        assert classify_pr("hotfix: prod breakage", None) == "hotfix"

    def test_linear_sev1_label_detected_as_incident(self):
        assert classify_pr("Fix x", None, linear_labels=["sev-1"]) == "incident"

    def test_plain_pr_not_classified(self):
        assert classify_pr("Add feature", ["enhancement"]) is None


class TestDirectPushRule:
    """Phase 02 push-to-main classifier — new default rule."""

    def test_direct_push_with_unrecognised_prefix_is_incident(self):
        # "random: fix thing" starts with nothing in the allowed prefix list.
        result = classify_pr(
            "random: force-pushed straight to main",
            None,
            is_direct_push_to_main=True,
        )
        assert result == "incident"

    def test_direct_push_with_allowed_prefix_not_incident(self):
        # feat: is a conventional prefix; direct push with that prefix is
        # intentional, not an unreviewed incident candidate.
        for prefix in DEFAULT_ALLOWED_DIRECT_PUSH_PREFIXES:
            msg = f"{prefix}: normal change"
            result = classify_pr(msg, None, is_direct_push_to_main=True)
            assert result is None, f"{prefix!r} should be allowed"

    def test_direct_push_flag_required_to_activate_rule(self):
        # Without is_direct_push_to_main=True, the rule is inert — prevents
        # false positives on regular PRs whose titles happen to lack a prefix.
        assert classify_pr("random text", None) is None
        assert classify_pr("random text", None, is_direct_push_to_main=False) is None

    def test_explicit_allowed_prefixes_via_pattern(self):
        # Admin-supplied override narrows the allowlist.
        custom_rule = IncidentRule(
            rule_type="direct_push_no_review",
            pattern="deploy",
            is_hotfix=False,
            is_incident=True,
            priority=10,
        )
        assert (
            classify_pr(
                "deploy: prod push",
                None,
                rules=[custom_rule],
                is_direct_push_to_main=True,
            )
            is None
        )
        assert (
            classify_pr(
                "fix: typo",
                None,
                rules=[custom_rule],
                is_direct_push_to_main=True,
            )
            == "incident"
        )

    def test_revert_rule_still_wins_over_direct_push(self):
        # Reverts ship as hotfix via the priority=10 revert_detection rule; the
        # direct-push rule (priority=50) should not win when both could match.
        result = classify_pr(
            'Revert "previously merged"',
            None,
            is_direct_push_to_main=True,
        )
        assert result == "hotfix"


def test_default_rules_includes_direct_push_rule():
    rules = default_rules()
    types = {r.rule_type for r in rules}
    assert "direct_push_no_review" in types
