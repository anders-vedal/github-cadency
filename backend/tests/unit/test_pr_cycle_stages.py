"""Unit tests for PR cycle-stage decomposition (Phase 09)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.pr_cycle_stages import (
    compute_pr_stage_durations,
    summarize_stage_samples,
    _percentile,
)


BASE = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)


def _pr(**kwargs):
    """Build a lightweight PR-like object for the pure compute function."""
    defaults = {
        "created_at": None,
        "ready_for_review_at": None,
        "first_review_at": None,
        "approved_at": None,
        "merged_at": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestComputePrStageDurations:
    def test_all_stages_present(self):
        pr = _pr(
            created_at=BASE,
            ready_for_review_at=BASE + timedelta(hours=2),
            first_review_at=BASE + timedelta(hours=3),
            approved_at=BASE + timedelta(hours=8),
            merged_at=BASE + timedelta(hours=10),
        )
        d = compute_pr_stage_durations(pr)
        assert d["open_to_ready_s"] == 2 * 3600
        assert d["ready_to_first_review_s"] == 1 * 3600
        assert d["first_review_to_approval_s"] == 5 * 3600
        assert d["approval_to_merge_s"] == 2 * 3600

    def test_ready_for_review_fallback_to_first_review(self):
        # ready_for_review_at is None (e.g. non-draft PR) — fallback applies to the
        # open-to-ready bucket only. The ready_to_first_review_s stage is unknown
        # (None) for non-draft PRs because there's no actual draft duration to measure.
        pr = _pr(
            created_at=BASE,
            ready_for_review_at=None,
            first_review_at=BASE + timedelta(hours=4),
            approved_at=BASE + timedelta(hours=6),
            merged_at=BASE + timedelta(hours=7),
        )
        d = compute_pr_stage_durations(pr)
        # open_to_ready_s uses the first_review_at fallback.
        assert d["open_to_ready_s"] == 4 * 3600
        # ready_to_first_review_s is None for non-draft PRs (no measurable stage).
        assert d["ready_to_first_review_s"] is None

    def test_missing_endpoints_return_none(self):
        pr = _pr(created_at=BASE, merged_at=BASE + timedelta(hours=1))
        d = compute_pr_stage_durations(pr)
        # No ready/review/approval endpoints — only None results.
        assert d["open_to_ready_s"] is None
        assert d["ready_to_first_review_s"] is None
        assert d["first_review_to_approval_s"] is None
        assert d["approval_to_merge_s"] is None

    def test_negative_duration_returned_as_none(self):
        # Clock skew: merged_at before approved_at
        pr = _pr(
            created_at=BASE,
            approved_at=BASE + timedelta(hours=3),
            merged_at=BASE + timedelta(hours=2),
        )
        d = compute_pr_stage_durations(pr)
        assert d["approval_to_merge_s"] is None

    def test_naive_datetime_is_coerced_to_utc(self):
        naive = datetime(2026, 4, 1, 12, 0)
        pr = _pr(
            created_at=naive,
            ready_for_review_at=naive.replace(hour=14),
        )
        d = compute_pr_stage_durations(pr)
        assert d["open_to_ready_s"] == 2 * 3600

    def test_pr_never_reached_ready_or_reviewed(self):
        # Only created_at known — all stages None.
        pr = _pr(created_at=BASE)
        d = compute_pr_stage_durations(pr)
        assert all(v is None for v in d.values())


class TestPercentile:
    def test_empty_returns_none(self):
        assert _percentile([], 0.5) is None

    def test_single_value(self):
        assert _percentile([42], 0.5) == 42
        assert _percentile([42], 0.9) == 42

    def test_median(self):
        assert _percentile([1, 2, 3, 4, 5], 0.5) == 3

    def test_p90_on_known_list(self):
        # 11 values: p90 ~ index 9 -> value 10 (interpolated).
        values = list(range(1, 12))  # 1..11
        assert _percentile(values, 0.9) == 10


class TestSummarizeStageSamples:
    def test_empty_samples_yield_none(self):
        out = summarize_stage_samples({})
        for stage in (
            "open_to_ready_s",
            "ready_to_first_review_s",
            "first_review_to_approval_s",
            "approval_to_merge_s",
        ):
            assert out[stage]["count"] == 0
            assert out[stage]["p50"] is None
            assert out[stage]["p75"] is None
            assert out[stage]["p90"] is None

    def test_mixed_samples(self):
        samples = {
            "open_to_ready_s": [60, 120, 180, 240, 300],
            "ready_to_first_review_s": [],
            "first_review_to_approval_s": [1000],
            "approval_to_merge_s": [10, 20, 30],
        }
        out = summarize_stage_samples(samples)
        assert out["open_to_ready_s"]["count"] == 5
        assert out["open_to_ready_s"]["p50"] == 180
        assert out["ready_to_first_review_s"]["count"] == 0
        assert out["ready_to_first_review_s"]["p50"] is None
        assert out["first_review_to_approval_s"]["p50"] == 1000
        assert out["approval_to_merge_s"]["p50"] == 20


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
