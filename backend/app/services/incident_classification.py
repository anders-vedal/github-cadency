"""Phase 10 — Incident / hotfix classification rules.

Admin-configurable rules for what counts as an incident or hotfix when computing
Change Failure Rate. Rules are applied in priority order; first matching rule wins.

For now, default rules ship hard-coded; dynamic admin editing can be added later
via a new table (`incident_classifier_rules`).
"""

import re
from dataclasses import dataclass
from typing import Literal, Optional

IncidentKind = Literal["incident", "hotfix"] | None


@dataclass
class IncidentRule:
    rule_type: Literal[
        "linear_label", "linear_issue_type", "github_label", "pr_title_prefix", "revert_detection"
    ]
    pattern: str
    is_hotfix: bool
    is_incident: bool
    priority: int = 100

    def match_pr_title(self, title: str) -> bool:
        if self.rule_type == "pr_title_prefix":
            return title.lower().startswith(self.pattern.lower())
        if self.rule_type == "revert_detection":
            return title.startswith('Revert "') or 'This reverts commit' in title
        return False

    def match_github_label(self, labels: list[str]) -> bool:
        if self.rule_type != "github_label":
            return False
        labels_lower = [l.lower() for l in labels if isinstance(l, str)]
        return self.pattern.lower() in labels_lower

    def match_linear_label(self, labels: list[str]) -> bool:
        if self.rule_type != "linear_label":
            return False
        labels_lower = [l.lower() for l in labels if isinstance(l, str)]
        return self.pattern.lower() in labels_lower

    def match_linear_issue_type(self, issue_type: str | None) -> bool:
        if self.rule_type != "linear_issue_type":
            return False
        return (issue_type or "").lower() == self.pattern.lower()


def default_rules() -> list[IncidentRule]:
    return [
        IncidentRule(
            rule_type="revert_detection",
            pattern="",
            is_hotfix=True,
            is_incident=False,
            priority=10,
        ),
        IncidentRule(
            rule_type="pr_title_prefix",
            pattern="hotfix:",
            is_hotfix=True,
            is_incident=False,
            priority=20,
        ),
        IncidentRule(
            rule_type="pr_title_prefix",
            pattern="hotfix/",
            is_hotfix=True,
            is_incident=False,
            priority=20,
        ),
        IncidentRule(
            rule_type="pr_title_prefix",
            pattern="[HOTFIX]",
            is_hotfix=True,
            is_incident=False,
            priority=20,
        ),
        IncidentRule(
            rule_type="github_label",
            pattern="incident",
            is_hotfix=False,
            is_incident=True,
            priority=30,
        ),
        IncidentRule(
            rule_type="github_label",
            pattern="regression",
            is_hotfix=True,
            is_incident=False,
            priority=30,
        ),
        IncidentRule(
            rule_type="linear_label",
            pattern="sev-1",
            is_hotfix=False,
            is_incident=True,
            priority=40,
        ),
        IncidentRule(
            rule_type="linear_label",
            pattern="sev-2",
            is_hotfix=False,
            is_incident=True,
            priority=40,
        ),
        IncidentRule(
            rule_type="linear_label",
            pattern="incident",
            is_hotfix=False,
            is_incident=True,
            priority=40,
        ),
        IncidentRule(
            rule_type="linear_label",
            pattern="outage",
            is_hotfix=False,
            is_incident=True,
            priority=40,
        ),
    ]


def classify_pr(
    pr_title: str,
    github_labels: list[str] | None,
    linear_labels: list[str] | None = None,
    linear_issue_type: str | None = None,
    rules: list[IncidentRule] | None = None,
) -> IncidentKind:
    """Run all rules in priority order; first match returns the classification."""
    active_rules = sorted(rules or default_rules(), key=lambda r: r.priority)

    for r in active_rules:
        matched = False
        if r.rule_type == "pr_title_prefix":
            matched = r.match_pr_title(pr_title)
        elif r.rule_type == "revert_detection":
            matched = r.match_pr_title(pr_title)
        elif r.rule_type == "github_label":
            matched = r.match_github_label(github_labels or [])
        elif r.rule_type == "linear_label":
            matched = r.match_linear_label(linear_labels or [])
        elif r.rule_type == "linear_issue_type":
            matched = r.match_linear_issue_type(linear_issue_type)
        if matched:
            if r.is_incident:
                return "incident"
            if r.is_hotfix:
                return "hotfix"
    return None
