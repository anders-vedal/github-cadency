"""Tests for Phase 01 body preview sanitization + attachment URL classification."""

from app.services.linear_sync import normalize_attachment_source, sanitize_preview


class TestSanitizePreview:
    def test_strips_email(self):
        result = sanitize_preview("Contact jane@example.com for details")
        assert "jane@example.com" not in result
        assert "[EMAIL]" in result

    def test_strips_bearer_token(self):
        result = sanitize_preview("Authorization: Bearer abc123xyz789")
        assert "abc123xyz789" not in result
        assert "[CREDENTIAL]" in result

    def test_strips_api_key(self):
        result = sanitize_preview("api_key=sk-abcdefghijklmnop")
        assert "sk-abcdefghijklmnop" not in result
        assert "[CREDENTIAL]" in result

    def test_strips_uuid(self):
        result = sanitize_preview(
            "Linear issue id 550e8400-e29b-41d4-a716-446655440000 broke"
        )
        assert "550e8400-e29b-41d4-a716-446655440000" not in result
        assert "[UUID]" in result

    def test_strips_git_sha(self):
        result = sanitize_preview("See commit abc1234567890def1234567890abcdef12345678 for fix")
        assert "abc1234567890def1234567890abcdef12345678" not in result
        assert "[SHA]" in result

    def test_strips_password_assignment(self):
        result = sanitize_preview("password: hunter2")
        assert "hunter2" not in result
        assert "[REDACTED]" in result

    def test_truncates_to_max_len(self):
        long_text = "word " * 200
        result = sanitize_preview(long_text, max_len=50)
        assert len(result) <= 50
        assert result.endswith("…")

    def test_collapses_whitespace(self):
        result = sanitize_preview("foo   bar\n\n\nbaz\t\tqux")
        assert result == "foo bar baz qux"

    def test_returns_none_for_empty(self):
        assert sanitize_preview("") is None
        assert sanitize_preview(None) is None

    def test_preserves_safe_content(self):
        result = sanitize_preview("The login button is broken on mobile")
        assert result == "The login button is broken on mobile"


class TestNormalizeAttachmentSource:
    def test_github_pr_url(self):
        assert (
            normalize_attachment_source("github", "https://github.com/acme/repo/pull/42")
            == "github_pr"
        )

    def test_github_commit_url(self):
        assert (
            normalize_attachment_source(
                "github", "https://github.com/acme/repo/commit/abc1234"
            )
            == "github_commit"
        )

    def test_github_issue_url(self):
        assert (
            normalize_attachment_source("github", "https://github.com/acme/repo/issues/7")
            == "github_issue"
        )

    def test_github_generic_url(self):
        assert (
            normalize_attachment_source("github", "https://github.com/acme/repo")
            == "github"
        )

    def test_slack_attachment(self):
        assert normalize_attachment_source("slack", "https://slack.com/x") == "slack"

    def test_figma_attachment(self):
        assert normalize_attachment_source("figma", "https://figma.com/file/abc") == "figma"

    def test_unknown_source_preserved(self):
        assert normalize_attachment_source("custom", "https://example.com") == "custom"

    def test_url_based_fallback_for_github(self):
        # No sourceType but URL is github
        assert (
            normalize_attachment_source(None, "https://github.com/acme/repo/pull/1")
            == "github_pr"
        )

    def test_other_default(self):
        assert normalize_attachment_source(None, "https://random.example.com") == "other"
