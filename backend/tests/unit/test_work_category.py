"""Unit tests for work categorization — pure functions, no DB needed."""

import pytest
from datetime import datetime, timezone, timedelta

from app.services.work_category import (
    classify_work_item,
    cross_reference_pr_categories,
    _auto_granularity,
    _build_period_trend,
)


class TestClassifyWorkItem:
    def test_label_bug(self):
        assert classify_work_item(["bug"], "some title") == "bugfix"

    def test_label_enhancement(self):
        assert classify_work_item(["enhancement"], "some title") == "feature"

    def test_label_case_insensitive(self):
        assert classify_work_item(["BUG"], "some title") == "bugfix"
        assert classify_work_item(["Enhancement"], None) == "feature"

    def test_label_chore(self):
        assert classify_work_item(["chore"], "update stuff") == "tech_debt"

    def test_label_ci(self):
        assert classify_work_item(["ci"], "pipeline change") == "ops"

    def test_label_docs(self):
        assert classify_work_item(["docs"], "update readme") == "ops"

    def test_label_first_match_wins(self):
        assert classify_work_item(["feature", "bug"], "title") == "feature"
        assert classify_work_item(["bug", "feature"], "title") == "bugfix"

    def test_title_fix(self):
        assert classify_work_item(None, "fix: crash on login") == "bugfix"
        assert classify_work_item([], "Fixed null pointer") == "bugfix"

    def test_title_feat(self):
        assert classify_work_item(None, "feat: add search") == "feature"
        assert classify_work_item([], "Add user profiles") == "feature"

    def test_title_refactor(self):
        assert classify_work_item(None, "refactor auth module") == "tech_debt"

    def test_title_bump(self):
        assert classify_work_item(None, "bump dependencies") == "tech_debt"

    def test_title_ci(self):
        assert classify_work_item(None, "ci: update pipeline") == "ops"

    def test_title_docs(self):
        assert classify_work_item(None, "docs: update API reference") == "ops"

    def test_label_precedence_over_title(self):
        assert classify_work_item(["feature"], "fix something") == "feature"
        assert classify_work_item(["bug"], "feat: add new thing") == "bugfix"

    def test_unknown_no_signals(self):
        assert classify_work_item(None, "update something") == "unknown"
        assert classify_work_item([], "some change") == "unknown"

    def test_none_inputs(self):
        assert classify_work_item(None, None) == "unknown"

    def test_empty_labels_and_title(self):
        assert classify_work_item([], "") == "unknown"

    def test_label_with_whitespace(self):
        assert classify_work_item([" bug "], "title") == "bugfix"


class TestCrossReferencePrCategories:
    def test_inherits_from_linked_issue(self):
        prs = [{"category": "unknown", "repo_id": 1, "closes_issue_numbers": [10]}]
        issues_by_key = {(1, 10): "bugfix"}
        result = cross_reference_pr_categories(prs, issues_by_key)
        assert result[0]["category"] == "bugfix"

    def test_most_common_category(self):
        prs = [{"category": "unknown", "repo_id": 1, "closes_issue_numbers": [10, 11, 12]}]
        issues_by_key = {(1, 10): "bugfix", (1, 11): "bugfix", (1, 12): "feature"}
        result = cross_reference_pr_categories(prs, issues_by_key)
        assert result[0]["category"] == "bugfix"

    def test_skips_unknown_issues(self):
        prs = [{"category": "unknown", "repo_id": 1, "closes_issue_numbers": [10]}]
        issues_by_key = {(1, 10): "unknown"}
        result = cross_reference_pr_categories(prs, issues_by_key)
        assert result[0]["category"] == "unknown"

    def test_non_unknown_pr_unchanged(self):
        prs = [{"category": "feature", "repo_id": 1, "closes_issue_numbers": [10]}]
        issues_by_key = {(1, 10): "bugfix"}
        result = cross_reference_pr_categories(prs, issues_by_key)
        assert result[0]["category"] == "feature"

    def test_no_linked_issues(self):
        prs = [{"category": "unknown", "repo_id": 1, "closes_issue_numbers": []}]
        issues_by_key = {}
        result = cross_reference_pr_categories(prs, issues_by_key)
        assert result[0]["category"] == "unknown"

    def test_none_closes_issue_numbers(self):
        prs = [{"category": "unknown", "repo_id": 1, "closes_issue_numbers": None}]
        issues_by_key = {(1, 10): "bugfix"}
        result = cross_reference_pr_categories(prs, issues_by_key)
        assert result[0]["category"] == "unknown"

    def test_missing_issue_key(self):
        prs = [{"category": "unknown", "repo_id": 1, "closes_issue_numbers": [99]}]
        issues_by_key = {(1, 10): "bugfix"}
        result = cross_reference_pr_categories(prs, issues_by_key)
        assert result[0]["category"] == "unknown"


class TestAutoGranularity:
    def test_short_range_weekly(self):
        now = datetime.now(timezone.utc)
        assert _auto_granularity(now - timedelta(days=30), now) == "weekly"
        assert _auto_granularity(now - timedelta(days=90), now) == "weekly"

    def test_long_range_monthly(self):
        now = datetime.now(timezone.utc)
        assert _auto_granularity(now - timedelta(days=91), now) == "monthly"
        assert _auto_granularity(now - timedelta(days=180), now) == "monthly"


class TestBuildPeriodTrend:
    def test_weekly_buckets(self):
        now = datetime(2026, 3, 28, tzinfo=timezone.utc)
        start = now - timedelta(days=28)
        pr_items = [
            {"category": "feature", "merged_at": start + timedelta(days=1)},
            {"category": "bugfix", "merged_at": start + timedelta(days=8)},
            {"category": "feature", "merged_at": start + timedelta(days=15)},
        ]
        issue_items = [
            {"category": "bugfix", "created_at": start + timedelta(days=2)},
        ]
        periods = _build_period_trend(pr_items, issue_items, start, now, "weekly")
        assert len(periods) == 4
        assert all(p.period_label for p in periods)
        total_pr_count = sum(sum(p.pr_categories.values()) for p in periods)
        assert total_pr_count == 3

    def test_monthly_buckets(self):
        start = datetime(2025, 10, 1, tzinfo=timezone.utc)
        end = datetime(2026, 3, 28, tzinfo=timezone.utc)
        pr_items = [
            {"category": "feature", "merged_at": datetime(2025, 11, 15, tzinfo=timezone.utc)},
            {"category": "ops", "merged_at": datetime(2026, 1, 10, tzinfo=timezone.utc)},
        ]
        periods = _build_period_trend(pr_items, [], start, end, "monthly")
        assert len(periods) >= 5
        total_pr_count = sum(sum(p.pr_categories.values()) for p in periods)
        assert total_pr_count == 2

    def test_empty_items(self):
        now = datetime(2026, 3, 28, tzinfo=timezone.utc)
        start = now - timedelta(days=14)
        periods = _build_period_trend([], [], start, now, "weekly")
        assert len(periods) == 2
        assert all(sum(p.pr_categories.values()) == 0 for p in periods)
