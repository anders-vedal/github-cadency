"""Phase 11 — MetricSpec registry validation tests."""

import pytest

from app.services.metric_spec import (
    BANNED_METRICS,
    MetricSpec,
    REGISTRY,
    REGISTRY_BY_KEY,
    get_catalog,
    validate_registry,
)


class TestMetricSpec:
    def test_activity_metric_requires_paired_outcome(self):
        with pytest.raises(ValueError) as exc:
            MetricSpec(
                key="foo_activity",
                label="Foo",
                category="throughput",
                is_activity=True,
                paired_outcome_key=None,
            )
        assert "paired_outcome_key" in str(exc.value)

    def test_non_activity_no_pair_required(self):
        spec = MetricSpec(
            key="foo_outcome",
            label="Foo",
            category="flow",
            is_activity=False,
        )
        assert spec.paired_outcome_key is None

    def test_activity_with_pair_valid(self):
        spec = MetricSpec(
            key="foo_a",
            label="Foo",
            category="throughput",
            is_activity=True,
            paired_outcome_key="bar_outcome",
        )
        assert spec.paired_outcome_key == "bar_outcome"


class TestRegistry:
    def test_validate_registry_passes(self):
        # Should not raise
        validate_registry()

    def test_all_activity_metrics_have_pair(self):
        for m in REGISTRY:
            if m.is_activity:
                assert m.paired_outcome_key is not None, (
                    f"{m.key} is activity but has no paired_outcome_key"
                )
                assert m.paired_outcome_key in REGISTRY_BY_KEY, (
                    f"{m.key} pairs with unknown {m.paired_outcome_key}"
                )

    def test_banned_metrics_documented(self):
        assert len(BANNED_METRICS) >= 4
        # Must include LOC ban
        keys = {b["key"] for b in BANNED_METRICS}
        assert "lines_of_code_per_dev" in keys
        assert "commits_per_dev" in keys

    def test_creator_outcome_is_self_visibility_default(self):
        m = REGISTRY_BY_KEY["avg_downstream_pr_review_rounds"]
        assert m.visibility_default == "self"
        assert m.goodhart_risk == "high"

    def test_distribution_metrics_marked(self):
        distribution_metrics = [m for m in REGISTRY if m.is_distribution]
        # Expect lead time, MTTR, cycle time, etc. to be marked distribution
        assert any(m.key == "lead_time_p50_s" for m in distribution_metrics)
        assert any(m.key == "cycle_time_p50_s" for m in distribution_metrics)


class TestCatalog:
    def test_get_catalog_shape(self):
        cat = get_catalog()
        assert "metrics" in cat
        assert "banned" in cat
        assert len(cat["metrics"]) == len(REGISTRY)
        assert len(cat["banned"]) == len(BANNED_METRICS)

    def test_catalog_metric_fields(self):
        cat = get_catalog()
        m = cat["metrics"][0]
        required_fields = {
            "key",
            "label",
            "category",
            "is_activity",
            "paired_outcome_key",
            "visibility_default",
            "is_distribution",
            "goodhart_risk",
            "goodhart_notes",
            "description",
        }
        assert set(m.keys()) == required_fields
