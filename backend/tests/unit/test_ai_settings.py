"""Unit tests for AI settings service — cost computation and feature metadata."""

import pytest
from datetime import datetime, timezone

from app.services.ai_settings import compute_cost, FEATURE_META


class TestComputeCost:
    def test_basic_cost(self):
        # 1M input tokens at $3/M + 1M output at $15/M = $18
        cost = compute_cost(1_000_000, 1_000_000, 3.0, 15.0)
        assert cost == 18.0

    def test_small_call(self):
        # 5000 input + 3000 output at default pricing
        cost = compute_cost(5000, 3000, 3.0, 15.0)
        # 5000 * 3 / 1M + 3000 * 15 / 1M = 0.015 + 0.045 = 0.06
        assert cost == 0.06

    def test_zero_tokens(self):
        assert compute_cost(0, 0, 3.0, 15.0) == 0.0

    def test_custom_pricing(self):
        cost = compute_cost(10000, 5000, 1.0, 5.0)
        # 10000 * 1 / 1M + 5000 * 5 / 1M = 0.01 + 0.025 = 0.035
        assert cost == 0.035

    def test_large_call_precision(self):
        # 20K input + 4K output at Sonnet pricing
        cost = compute_cost(20000, 4000, 3.0, 15.0)
        # 20000 * 3 / 1M + 4000 * 15 / 1M = 0.06 + 0.06 = 0.12
        assert cost == 0.12


class TestFeatureMeta:
    def test_all_four_features_defined(self):
        assert set(FEATURE_META.keys()) == {
            "general_analysis",
            "one_on_one_prep",
            "team_health",
            "work_categorization",
        }

    def test_each_has_required_fields(self):
        for key, meta in FEATURE_META.items():
            assert "label" in meta, f"{key} missing label"
            assert "description" in meta, f"{key} missing description"
            assert "disabled_impact" in meta, f"{key} missing disabled_impact"
            assert "analysis_types" in meta, f"{key} missing analysis_types"

    def test_descriptions_are_nonempty(self):
        for key, meta in FEATURE_META.items():
            assert len(meta["description"]) > 20, f"{key} description too short"
            assert len(meta["disabled_impact"]) > 20, f"{key} disabled_impact too short"

    def test_general_analysis_covers_three_types(self):
        types = FEATURE_META["general_analysis"]["analysis_types"].split(",")
        assert set(types) == {"communication", "conflict", "sentiment"}
