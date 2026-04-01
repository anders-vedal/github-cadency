"""Unit tests for work category classification logic (pure function, no DB)."""

import pytest

from app.services.work_categories import _validate_regex_safe, classify_work_item_with_rules


class FakeRule:
    """Minimal rule object for testing classify_work_item_with_rules."""

    def __init__(self, id, match_type, match_value, category_key, priority, case_sensitive=False):
        self.id = id
        self.match_type = match_type
        self.match_value = match_value
        self.category_key = category_key
        self.priority = priority
        self.case_sensitive = case_sensitive


SAMPLE_RULES = [
    FakeRule(1, "label", "bug", "bugfix", 1),
    FakeRule(2, "label", "enhancement", "feature", 2),
    FakeRule(3, "label", "chore", "tech_debt", 3),
    FakeRule(4, "label", "ci", "ops", 4),
    FakeRule(5, "issue_type", "Bug", "bugfix", 50),
    FakeRule(6, "issue_type", "Epic", "feature", 51),
    FakeRule(7, "issue_type", "Feature", "feature", 52),
    FakeRule(8, "issue_type", "Task", "tech_debt", 53),
    FakeRule(10, "title_regex", r"\bfix(?:es|ed)?\b", "bugfix", 100),
    FakeRule(11, "title_regex", r"\bfeat(?:ure)?\b|\badd(?:s|ed)?\s", "feature", 101),
    FakeRule(12, "prefix", "[INFRA]", "ops", 200),
]


def test_label_match():
    cat, src = classify_work_item_with_rules(["bug"], "Some title", SAMPLE_RULES)
    assert cat == "bugfix"
    assert src == "label"


def test_label_case_insensitive():
    cat, src = classify_work_item_with_rules(["BUG"], "Some title", SAMPLE_RULES)
    assert cat == "bugfix"
    assert src == "label"


def test_label_priority_order():
    """First matching rule wins based on priority."""
    cat, src = classify_work_item_with_rules(["enhancement", "bug"], None, SAMPLE_RULES)
    # "bug" has priority 1, "enhancement" has priority 2 — bug wins
    assert cat == "bugfix"


def test_title_regex_match():
    cat, src = classify_work_item_with_rules([], "Fix broken login", SAMPLE_RULES)
    assert cat == "bugfix"
    assert src == "title"


def test_title_regex_no_match():
    cat, src = classify_work_item_with_rules([], "Update README", SAMPLE_RULES)
    assert cat == "unknown"
    assert src == ""


def test_prefix_match():
    cat, src = classify_work_item_with_rules([], "[INFRA] Setup monitoring", SAMPLE_RULES)
    assert cat == "ops"
    assert src == "prefix"


def test_prefix_case_insensitive():
    cat, src = classify_work_item_with_rules([], "[infra] setup monitoring", SAMPLE_RULES)
    assert cat == "ops"
    assert src == "prefix"


def test_label_takes_precedence_over_title():
    """Label rules have lower priority numbers so they're checked first."""
    cat, src = classify_work_item_with_rules(["enhancement"], "Fix something", SAMPLE_RULES)
    assert cat == "feature"
    assert src == "label"


def test_empty_inputs():
    cat, src = classify_work_item_with_rules(None, None, SAMPLE_RULES)
    assert cat == "unknown"
    assert src == ""


def test_empty_rules():
    cat, src = classify_work_item_with_rules(["bug"], "Fix something", [])
    assert cat == "unknown"
    assert src == ""


def test_case_sensitive_rule():
    rules = [
        FakeRule(1, "label", "BUG", "bugfix", 1, case_sensitive=True),
    ]
    # Exact case matches
    cat, _ = classify_work_item_with_rules(["BUG"], None, rules)
    assert cat == "bugfix"

    # Wrong case doesn't match
    cat, _ = classify_work_item_with_rules(["bug"], None, rules)
    assert cat == "unknown"


def test_invalid_regex_skipped():
    """Invalid regex rules are skipped without crashing."""
    rules = [
        FakeRule(1, "title_regex", "[invalid", "bugfix", 1),
        FakeRule(2, "title_regex", r"\bfeat(?:ure)?\b", "feature", 2),
    ]
    cat, src = classify_work_item_with_rules([], "Add new feature", rules)
    assert cat == "feature"
    assert src == "title"


def test_feature_title_match():
    cat, src = classify_work_item_with_rules([], "Add new search functionality", SAMPLE_RULES)
    assert cat == "feature"
    assert src == "title"


# --- Issue type tests ---


def test_issue_type_match():
    cat, src = classify_work_item_with_rules([], "Some issue", SAMPLE_RULES, issue_type="Bug")
    assert cat == "bugfix"
    assert src == "issue_type"


def test_issue_type_case_insensitive():
    cat, src = classify_work_item_with_rules([], "Some issue", SAMPLE_RULES, issue_type="bug")
    assert cat == "bugfix"
    assert src == "issue_type"


def test_issue_type_epic():
    cat, src = classify_work_item_with_rules([], "Epic work", SAMPLE_RULES, issue_type="Epic")
    assert cat == "feature"
    assert src == "issue_type"


def test_issue_type_none_skips():
    """When issue_type is None, issue_type rules are skipped."""
    cat, src = classify_work_item_with_rules([], "Update README", SAMPLE_RULES, issue_type=None)
    assert cat == "unknown"
    assert src == ""


def test_label_takes_precedence_over_issue_type():
    """Label rules have lower priority numbers so they win over issue_type rules."""
    cat, src = classify_work_item_with_rules(["enhancement"], "Some title", SAMPLE_RULES, issue_type="Bug")
    assert cat == "feature"
    assert src == "label"


def test_issue_type_case_sensitive():
    rules = [
        FakeRule(1, "issue_type", "Bug", "bugfix", 1, case_sensitive=True),
    ]
    cat, src = classify_work_item_with_rules([], "title", rules, issue_type="Bug")
    assert cat == "bugfix"
    assert src == "issue_type"

    cat, src = classify_work_item_with_rules([], "title", rules, issue_type="bug")
    assert cat == "unknown"
    assert src == ""


# --- ReDoS protection tests ---


def test_validate_regex_safe_valid():
    """Valid patterns pass without error."""
    _validate_regex_safe(r"\bfix(?:es|ed)?\b")
    _validate_regex_safe(r"feat|add")
    _validate_regex_safe(r"[A-Z]+")


def test_validate_regex_safe_invalid_syntax():
    """Patterns that don't compile raise ValueError."""
    with pytest.raises(ValueError, match="Invalid regex"):
        _validate_regex_safe("[invalid")


@pytest.mark.parametrize("pattern", [
    r"(a+)+$",
    r"(x*)*",
    r"(a|b+)+",
    r"(.*a)*",
    r"([a-z]+)*",
])
def test_validate_regex_safe_nested_quantifiers(pattern):
    """Patterns with nested quantifiers are rejected."""
    with pytest.raises(ValueError, match="nested quantifiers"):
        _validate_regex_safe(pattern)


def test_validate_regex_safe_allows_non_nested():
    """Single quantifiers inside groups are fine."""
    _validate_regex_safe(r"(a+)")          # quantifier inside group, no outer quantifier
    _validate_regex_safe(r"(foo|bar)+")    # alternation with outer quantifier, no inner quantifier
    _validate_regex_safe(r"\d{2,4}")       # bounded quantifier
