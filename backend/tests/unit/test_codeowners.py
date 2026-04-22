"""Unit tests for CODEOWNERS parsing and bypass detection (Phase 09)."""

from __future__ import annotations

import pytest

from app.services.codeowners import (
    check_bypass,
    matching_owners,
    parse_codeowners,
)


class TestParseCodeowners:
    def test_empty_input_returns_empty_list(self):
        assert parse_codeowners("") == []
        assert parse_codeowners("\n\n") == []

    def test_skips_comments_and_blank_lines(self):
        text = """
        # This is a comment
        # Another comment

        *.py    @alice
        """
        rules = parse_codeowners(text)
        assert rules == [("*.py", ["@alice"])]

    def test_strips_inline_comments(self):
        text = "*.py @alice # python owner\n"
        rules = parse_codeowners(text)
        assert rules == [("*.py", ["@alice"])]

    def test_multiple_owners_per_rule(self):
        text = "/backend/ @alice @bob @org/team\n"
        rules = parse_codeowners(text)
        assert rules == [("/backend/", ["@alice", "@bob", "@org/team"])]

    def test_preserves_order(self):
        text = "\n".join(
            [
                "*.py @alice",
                "*.ts @bob",
                "/backend/ @core-team",
            ]
        )
        rules = parse_codeowners(text)
        assert [r[0] for r in rules] == ["*.py", "*.ts", "/backend/"]

    def test_ignores_pattern_without_owner(self):
        text = "*.py\n*.ts @bob\n"
        rules = parse_codeowners(text)
        assert rules == [("*.ts", ["@bob"])]


class TestMatchingOwners:
    def test_no_rules_means_no_owners(self):
        assert matching_owners([], ["foo.py"]) == set()

    def test_no_paths_means_no_owners(self):
        rules = [("*.py", ["@alice"])]
        assert matching_owners(rules, []) == set()

    def test_extension_pattern_matches_anywhere(self):
        rules = [("*.py", ["@alice"])]
        assert matching_owners(rules, ["foo.py"]) == {"@alice"}
        assert matching_owners(rules, ["pkg/foo.py"]) == {"@alice"}

    def test_rooted_directory_pattern(self):
        rules = [("/backend/", ["@backend-team"])]
        assert matching_owners(rules, ["backend/app/main.py"]) == {"@backend-team"}
        assert matching_owners(rules, ["frontend/src/App.tsx"]) == set()

    def test_last_matching_rule_wins(self):
        # Earlier rule is generic; later rule overrides for /backend/.
        rules = [
            ("*.py", ["@alice"]),
            ("/backend/", ["@backend-team"]),
        ]
        # For backend/app/x.py — both match, last wins.
        assert matching_owners(rules, ["backend/app/x.py"]) == {"@backend-team"}
        # For scripts/x.py — only *.py matches.
        assert matching_owners(rules, ["scripts/x.py"]) == {"@alice"}

    def test_double_star_pattern(self):
        rules = [("**/test_*.py", ["@qa-team"])]
        assert matching_owners(rules, ["tests/test_foo.py"]) == {"@qa-team"}
        assert matching_owners(rules, ["pkg/sub/test_bar.py"]) == {"@qa-team"}


class TestCheckBypass:
    def test_unmerged_pr_never_a_bypass(self):
        rules = [("*.py", ["@alice"])]
        assert (
            check_bypass(
                ["foo.py"], rules, approver_tokens=[], merged=False
            )
            is False
        )

    def test_approved_review_decision_short_circuits(self):
        rules = [("*.py", ["@alice"])]
        assert (
            check_bypass(
                ["foo.py"], rules, approver_tokens=[], review_decision="APPROVED"
            )
            is False
        )

    def test_no_rules_returns_false(self):
        assert check_bypass(["foo.py"], [], approver_tokens=[]) is False

    def test_no_matching_owner_returns_false(self):
        rules = [("*.ts", ["@frontend-team"])]
        # Touched only .py files — no owner required.
        assert check_bypass(["foo.py"], rules, approver_tokens=[]) is False

    def test_bypass_when_no_owner_approved(self):
        rules = [("*.py", ["@alice"])]
        # Someone else approved, not alice.
        assert (
            check_bypass(["foo.py"], rules, approver_tokens=["bob"]) is True
        )

    def test_not_a_bypass_when_owner_approved(self):
        rules = [("*.py", ["@alice"])]
        assert (
            check_bypass(["foo.py"], rules, approver_tokens=["alice"]) is False
        )

    def test_handles_at_prefix_and_case_mismatch(self):
        rules = [("*.py", ["@Alice"])]
        # Approver tokens from GitHub reviews are lowercase bare logins.
        assert (
            check_bypass(["foo.py"], rules, approver_tokens=["alice"]) is False
        )

    def test_team_token_requires_explicit_team_approval(self):
        # Team tokens aren't auto-expanded — if only the team is a required
        # owner, bypass is true unless the exact team token is in approvers.
        rules = [("*.py", ["@org/backend"])]
        assert (
            check_bypass(["foo.py"], rules, approver_tokens=["alice"]) is True
        )
        assert (
            check_bypass(
                ["foo.py"], rules, approver_tokens=["@org/backend"]
            )
            is False
        )

    def test_multi_file_only_one_owner_approved(self):
        rules = [
            ("/backend/", ["@alice"]),
            ("/frontend/", ["@bob"]),
        ]
        # Changes in both — only alice approved.
        assert (
            check_bypass(
                ["backend/api.py", "frontend/App.tsx"],
                rules,
                approver_tokens=["alice"],
            )
            is True
        )
        # Both owners approved.
        assert (
            check_bypass(
                ["backend/api.py", "frontend/App.tsx"],
                rules,
                approver_tokens=["alice", "bob"],
            )
            is False
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
