"""Unit tests for pure functions in the stats and AI analysis services."""
import pytest

from app.services.stats import (
    _linear_regression,
    _percentile_band,
    _percentiles,
    _trend_direction,
)
from app.schemas.schemas import BenchmarkMetric, TrendDirection
from app.services.ai_analysis import _truncate


# --- _linear_regression ---


class TestLinearRegression:
    def test_empty_list(self):
        slope, intercept = _linear_regression([])
        assert slope == 0.0
        assert intercept == 0.0

    def test_single_value(self):
        slope, intercept = _linear_regression([5.0])
        assert slope == 0.0
        assert intercept == 5.0

    def test_two_values_increasing(self):
        slope, intercept = _linear_regression([1.0, 3.0])
        assert slope == pytest.approx(2.0)
        assert intercept == pytest.approx(1.0)

    def test_two_values_decreasing(self):
        slope, intercept = _linear_regression([4.0, 2.0])
        assert slope == pytest.approx(-2.0)
        assert intercept == pytest.approx(4.0)

    def test_flat_line(self):
        slope, intercept = _linear_regression([3.0, 3.0, 3.0, 3.0])
        assert slope == pytest.approx(0.0)
        assert intercept == pytest.approx(3.0)

    def test_perfect_linear(self):
        # y = 2x + 1 → values at x=0,1,2,3: [1, 3, 5, 7]
        slope, intercept = _linear_regression([1.0, 3.0, 5.0, 7.0])
        assert slope == pytest.approx(2.0)
        assert intercept == pytest.approx(1.0)

    def test_noisy_increasing(self):
        values = [1.0, 2.5, 2.0, 4.0, 5.0]
        slope, _ = _linear_regression(values)
        assert slope > 0  # should detect upward trend

    def test_noisy_decreasing(self):
        values = [5.0, 4.5, 3.0, 2.5, 1.0]
        slope, _ = _linear_regression(values)
        assert slope < 0  # should detect downward trend


# --- _percentiles ---


class TestPercentiles:
    def test_single_value(self):
        result = _percentiles([5.0])
        assert result.p25 == 5.0
        assert result.p50 == 5.0
        assert result.p75 == 5.0

    def test_empty_list(self):
        result = _percentiles([])
        assert result.p25 == 0.0
        assert result.p50 == 0.0
        assert result.p75 == 0.0

    def test_known_values(self):
        # With 4 values [1, 2, 3, 4]: p25=1.75, p50=2.5, p75=3.25
        result = _percentiles([1.0, 2.0, 3.0, 4.0])
        assert result.p25 == pytest.approx(1.75, abs=0.01)
        assert result.p50 == pytest.approx(2.5, abs=0.01)
        assert result.p75 == pytest.approx(3.25, abs=0.01)

    def test_identical_values(self):
        result = _percentiles([7.0, 7.0, 7.0])
        assert result.p25 == 7.0
        assert result.p50 == 7.0
        assert result.p75 == 7.0

    def test_returns_benchmark_metric(self):
        result = _percentiles([1.0, 2.0])
        assert isinstance(result, BenchmarkMetric)


# --- _percentile_band ---


class TestPercentileBand:
    def setup_method(self):
        self.metric = BenchmarkMetric(p25=10.0, p50=20.0, p75=30.0)

    def test_below_p25(self):
        assert _percentile_band(5.0, self.metric) == "below_p25"

    def test_p25_to_p50(self):
        assert _percentile_band(15.0, self.metric) == "p25_to_p50"

    def test_p50_to_p75(self):
        assert _percentile_band(25.0, self.metric) == "p50_to_p75"

    def test_above_p75(self):
        assert _percentile_band(35.0, self.metric) == "above_p75"

    # Lower-is-better metrics (inverted)
    def test_lower_is_better_low_value_is_good(self):
        # Low value → above_p75 (best)
        assert _percentile_band(5.0, self.metric, "time_to_merge_h") == "above_p75"

    def test_lower_is_better_high_value_is_bad(self):
        # High value → below_p25 (worst)
        assert _percentile_band(35.0, self.metric, "time_to_merge_h") == "below_p25"

    def test_lower_is_better_mid_value(self):
        assert _percentile_band(15.0, self.metric, "time_to_first_review_h") == "p50_to_p75"

    def test_lower_is_better_review_turnaround(self):
        assert _percentile_band(25.0, self.metric, "review_turnaround_h") == "p25_to_p50"


# --- _trend_direction ---


class TestTrendDirection:
    def test_stable_small_change(self):
        result = _trend_direction(0.01, 8, 10.0, True)
        assert result.direction == "stable"
        assert abs(result.change_pct) < 5.0

    def test_improving_higher_is_better(self):
        # slope > 0, polarity True → improving
        result = _trend_direction(2.0, 8, 10.0, True)
        assert result.direction == "improving"

    def test_worsening_higher_is_better(self):
        # slope < 0, polarity True → worsening
        result = _trend_direction(-2.0, 8, 10.0, True)
        assert result.direction == "worsening"

    def test_improving_lower_is_better(self):
        # slope < 0, polarity False → improving (going down is good)
        result = _trend_direction(-2.0, 8, 10.0, False)
        assert result.direction == "improving"

    def test_worsening_lower_is_better(self):
        # slope > 0, polarity False → worsening (going up is bad)
        result = _trend_direction(2.0, 8, 10.0, False)
        assert result.direction == "worsening"

    def test_neutral_polarity_always_stable(self):
        result = _trend_direction(5.0, 8, 10.0, None)
        assert result.direction == "stable"

    def test_returns_trend_direction_model(self):
        result = _trend_direction(0.0, 8, 10.0, True)
        assert isinstance(result, TrendDirection)

    def test_change_pct_calculation(self):
        # slope=1.0, n_periods=8, first_val=10
        # predicted_change = 1.0 * 7 = 7.0
        # change_pct = 7.0 / 10.0 * 100 = 70.0
        result = _trend_direction(1.0, 8, 10.0, True)
        assert result.change_pct == pytest.approx(70.0)

    def test_first_val_zero_uses_baseline_1(self):
        # baseline = max(abs(0), 1.0) = 1.0
        result = _trend_direction(1.0, 8, 0.0, True)
        assert result.change_pct == pytest.approx(700.0)


# --- _truncate ---


class TestTruncate:
    def test_none(self):
        assert _truncate(None) == ""

    def test_empty(self):
        assert _truncate("") == ""

    def test_short_text(self):
        assert _truncate("hello") == "hello"

    def test_exactly_500(self):
        text = "a" * 500
        assert _truncate(text) == text

    def test_over_500_truncated(self):
        text = "a" * 600
        result = _truncate(text)
        assert len(result) == 500
        assert result == "a" * 500
