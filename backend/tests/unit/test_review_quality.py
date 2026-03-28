"""Unit tests for classify_review_quality — pure function, no DB needed."""
import pytest

from app.services.github_sync import classify_review_quality


class TestClassifyReviewQuality:
    # --- Thorough tier ---

    def test_thorough_long_body(self):
        assert classify_review_quality("APPROVED", 501, 0) == "thorough"

    def test_thorough_many_comments(self):
        assert classify_review_quality("COMMENTED", 10, 3) == "thorough"

    def test_thorough_long_body_and_comments(self):
        assert classify_review_quality("CHANGES_REQUESTED", 600, 5) == "thorough"

    def test_thorough_boundary_body_500(self):
        # body_length > 500 → thorough
        assert classify_review_quality("APPROVED", 500, 0) != "thorough"
        assert classify_review_quality("APPROVED", 501, 0) == "thorough"

    def test_thorough_boundary_comments_3(self):
        assert classify_review_quality("APPROVED", 10, 2) != "thorough"
        assert classify_review_quality("APPROVED", 10, 3) == "thorough"

    def test_thorough_changes_requested_long_body(self):
        # CHANGES_REQUESTED + body > 100 → thorough
        assert classify_review_quality("CHANGES_REQUESTED", 101, 0) == "thorough"

    def test_thorough_changes_requested_boundary_100(self):
        # body_length must be > 100 (not >=) for thorough via CHANGES_REQUESTED
        assert classify_review_quality("CHANGES_REQUESTED", 100, 0) != "thorough"

    # --- Standard tier ---

    def test_standard_mid_body(self):
        assert classify_review_quality("COMMENTED", 200, 0) == "standard"

    def test_standard_boundary_100(self):
        assert classify_review_quality("COMMENTED", 100, 0) == "standard"

    def test_standard_boundary_500(self):
        assert classify_review_quality("COMMENTED", 500, 0) == "standard"

    def test_standard_boundary_99(self):
        assert classify_review_quality("COMMENTED", 99, 0) != "standard"

    def test_standard_changes_requested_empty_body(self):
        # CHANGES_REQUESTED with empty body → "standard" (was "minimal")
        assert classify_review_quality("CHANGES_REQUESTED", 0, 0) == "standard"

    def test_standard_changes_requested_short_body(self):
        # CHANGES_REQUESTED with short body → "standard" (was "minimal")
        assert classify_review_quality("CHANGES_REQUESTED", 50, 0) == "standard"

    def test_standard_code_block_in_body(self):
        # Body with code block → "standard" even if short
        body = "Try this:\n```\nfoo()\n```"
        assert classify_review_quality("COMMENTED", 20, 0, body=body) == "standard"

    def test_standard_code_block_short_body(self):
        body = "```fix```"
        assert classify_review_quality("APPROVED", 9, 0, body=body) == "standard"

    # --- Rubber stamp tier ---

    def test_rubber_stamp_approved_short(self):
        assert classify_review_quality("APPROVED", 0, 0) == "rubber_stamp"

    def test_rubber_stamp_approved_body_19(self):
        assert classify_review_quality("APPROVED", 19, 0) == "rubber_stamp"

    def test_rubber_stamp_boundary_20(self):
        # body_length < 20 for rubber_stamp
        assert classify_review_quality("APPROVED", 20, 0) != "rubber_stamp"

    def test_not_rubber_stamp_if_not_approved(self):
        assert classify_review_quality("COMMENTED", 0, 0) != "rubber_stamp"
        assert classify_review_quality("CHANGES_REQUESTED", 5, 0) != "rubber_stamp"

    def test_not_rubber_stamp_with_inline_comments(self):
        # APPROVED + 15-char body but 2 inline comments → "minimal" (not "rubber_stamp")
        assert classify_review_quality("APPROVED", 15, 2) == "minimal"

    # --- Minimal tier ---

    def test_minimal_commented_short(self):
        assert classify_review_quality("COMMENTED", 50, 0) == "minimal"

    def test_minimal_no_state(self):
        assert classify_review_quality(None, 50, 0) == "minimal"

    # --- Priority: thorough > standard > rubber_stamp > minimal ---

    def test_thorough_beats_standard(self):
        # body=501 would qualify for standard too, but thorough wins
        assert classify_review_quality("APPROVED", 501, 0) == "thorough"

    def test_thorough_beats_rubber_stamp(self):
        # APPROVED + body < 20 + 3 comments → thorough (not rubber_stamp)
        assert classify_review_quality("APPROVED", 5, 3) == "thorough"

    # --- Backward compatibility ---

    def test_backward_compat_thorough_unchanged(self):
        # Existing thorough classifications still hold
        assert classify_review_quality("APPROVED", 501, 0) == "thorough"
        assert classify_review_quality("COMMENTED", 10, 3) == "thorough"

    def test_backward_compat_standard_unchanged(self):
        assert classify_review_quality("COMMENTED", 200, 0) == "standard"
        assert classify_review_quality("APPROVED", 300, 1) == "standard"

    # --- Comment type integration ---

    def test_thorough_architectural_comments(self):
        # 3+ architectural comments → thorough regardless of body length
        assert classify_review_quality("COMMENTED", 10, 0, architectural_comment_count=3) == "thorough"

    def test_not_thorough_fewer_architectural(self):
        assert classify_review_quality("COMMENTED", 10, 0, architectural_comment_count=2) != "thorough"

    def test_standard_blocker_comment(self):
        # Has blocker comment → minimum standard
        assert classify_review_quality("COMMENTED", 10, 0, has_blocker_comment=True) == "standard"

    def test_blocker_doesnt_override_thorough(self):
        # Already thorough from body length — blocker doesn't demote
        assert classify_review_quality("APPROVED", 501, 0, has_blocker_comment=True) == "thorough"

    def test_blocker_prevents_rubber_stamp(self):
        # Would be rubber_stamp, but blocker promotes to standard
        assert classify_review_quality("APPROVED", 5, 0, has_blocker_comment=True) == "standard"

    def test_architectural_prevents_rubber_stamp(self):
        assert classify_review_quality("APPROVED", 5, 0, architectural_comment_count=3) == "thorough"

    def test_defaults_backward_compatible(self):
        # New params default to False/0, so existing calls unchanged
        assert classify_review_quality("APPROVED", 0, 0) == "rubber_stamp"
        assert classify_review_quality("COMMENTED", 50, 0) == "minimal"
