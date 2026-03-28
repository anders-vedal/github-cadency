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

    # --- Standard tier ---

    def test_standard_mid_body(self):
        assert classify_review_quality("COMMENTED", 200, 0) == "standard"

    def test_standard_boundary_100(self):
        assert classify_review_quality("COMMENTED", 100, 0) == "standard"

    def test_standard_boundary_500(self):
        assert classify_review_quality("COMMENTED", 500, 0) == "standard"

    def test_standard_boundary_99(self):
        assert classify_review_quality("COMMENTED", 99, 0) != "standard"

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

    # --- Minimal tier ---

    def test_minimal_commented_short(self):
        assert classify_review_quality("COMMENTED", 50, 0) == "minimal"

    def test_minimal_changes_requested_short(self):
        assert classify_review_quality("CHANGES_REQUESTED", 50, 0) == "minimal"

    def test_minimal_no_state(self):
        assert classify_review_quality(None, 50, 0) == "minimal"

    # --- Priority: thorough > standard > rubber_stamp > minimal ---

    def test_thorough_beats_standard(self):
        # body=501 would qualify for standard too, but thorough wins
        assert classify_review_quality("APPROVED", 501, 0) == "thorough"

    def test_thorough_beats_rubber_stamp(self):
        # APPROVED + body < 20 + 3 comments → thorough (not rubber_stamp)
        assert classify_review_quality("APPROVED", 5, 3) == "thorough"
