"""Integration tests for configurable work categories API."""

import pytest


@pytest.mark.asyncio
async def test_list_categories(client):
    resp = await client.get("/api/work-categories")
    assert resp.status_code == 200
    cats = resp.json()
    assert len(cats) >= 5
    keys = [c["category_key"] for c in cats]
    assert "feature" in keys
    assert "bugfix" in keys
    assert "unknown" in keys
    # Verify ordering
    orders = [c["display_order"] for c in cats]
    assert orders == sorted(orders)


@pytest.mark.asyncio
async def test_list_rules(client):
    resp = await client.get("/api/work-categories/rules")
    assert resp.status_code == 200
    rules = resp.json()
    assert len(rules) > 0
    # Rules should be sorted by priority
    priorities = [r["priority"] for r in rules]
    assert priorities == sorted(priorities)


@pytest.mark.asyncio
async def test_create_category(client):
    resp = await client.post("/api/work-categories", json={
        "category_key": "epic",
        "display_name": "Epic",
        "color": "#8b5cf6",
        "exclude_from_stats": True,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["category_key"] == "epic"
    assert data["display_name"] == "Epic"
    assert data["color"] == "#8b5cf6"
    assert data["exclude_from_stats"] is True
    assert data["is_default"] is False


@pytest.mark.asyncio
async def test_create_category_duplicate(client):
    resp = await client.post("/api/work-categories", json={
        "category_key": "feature",
        "display_name": "Dup",
        "color": "#000000",
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_category_invalid_key(client):
    resp = await client.post("/api/work-categories", json={
        "category_key": "Bad-Key",
        "display_name": "Bad",
        "color": "#000000",
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_category_invalid_color(client):
    resp = await client.post("/api/work-categories", json={
        "category_key": "test_cat",
        "display_name": "Test",
        "color": "red",
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_update_category(client):
    resp = await client.patch("/api/work-categories/feature", json={
        "display_name": "Feature Work",
        "color": "#0000ff",
    })
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Feature Work"
    assert resp.json()["color"] == "#0000ff"


@pytest.mark.asyncio
async def test_update_unknown_exclude_rejected(client):
    resp = await client.patch("/api/work-categories/unknown", json={
        "exclude_from_stats": True,
    })
    assert resp.status_code == 409  # "Cannot exclude" is a conflict, not 404


@pytest.mark.asyncio
async def test_delete_default_rejected(client):
    resp = await client.delete("/api/work-categories/feature")
    assert resp.status_code == 409
    assert "default" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_custom_category(client):
    # Create then delete
    await client.post("/api/work-categories", json={
        "category_key": "temp_cat",
        "display_name": "Temp",
        "color": "#123456",
    })
    resp = await client.delete("/api/work-categories/temp_cat")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_create_rule(client):
    resp = await client.post("/api/work-categories/rules", json={
        "match_type": "label",
        "match_value": "epic",
        "category_key": "feature",
        "priority": 50,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["match_type"] == "label"
    assert data["match_value"] == "epic"
    assert data["category_key"] == "feature"
    assert data["priority"] == 50


@pytest.mark.asyncio
async def test_create_rule_invalid_match_type(client):
    resp = await client.post("/api/work-categories/rules", json={
        "match_type": "invalid",
        "match_value": "test",
        "category_key": "feature",
        "priority": 1,
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_rule_invalid_regex(client):
    resp = await client.post("/api/work-categories/rules", json={
        "match_type": "title_regex",
        "match_value": "[invalid",
        "category_key": "feature",
        "priority": 1,
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_rule_nonexistent_category(client):
    resp = await client.post("/api/work-categories/rules", json={
        "match_type": "label",
        "match_value": "test",
        "category_key": "nonexistent",
        "priority": 1,
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_update_rule(client):
    # Create a rule first
    create_resp = await client.post("/api/work-categories/rules", json={
        "match_type": "label",
        "match_value": "test_update",
        "category_key": "feature",
        "priority": 99,
    })
    rule_id = create_resp.json()["id"]

    resp = await client.patch(f"/api/work-categories/rules/{rule_id}", json={
        "match_value": "updated_value",
        "priority": 50,
    })
    assert resp.status_code == 200
    assert resp.json()["match_value"] == "updated_value"
    assert resp.json()["priority"] == 50


@pytest.mark.asyncio
async def test_delete_rule(client):
    create_resp = await client.post("/api/work-categories/rules", json={
        "match_type": "label",
        "match_value": "to_delete",
        "category_key": "feature",
        "priority": 999,
    })
    rule_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/work-categories/rules/{rule_id}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_reclassify(client, db_session, sample_repo):
    """Test reclassify endpoint updates PR/issue categories."""
    from app.models.models import Issue, PullRequest

    from conftest import NOW

    # Create a PR with a label that maps to bugfix
    pr = PullRequest(
        github_id=9001, repo_id=sample_repo.id, number=100,
        title="Some PR", labels=["bug"], state="closed",
        is_merged=True, merged_at=NOW,
        work_category=None, work_category_source=None,
    )
    db_session.add(pr)

    # Create an issue with title matching feature
    issue = Issue(
        github_id=9002, repo_id=sample_repo.id, number=200,
        title="Add new feature for users", labels=[],
        state="open", created_at=NOW,
        work_category=None, work_category_source=None,
    )
    db_session.add(issue)

    # Create a manually categorized PR (should not be reclassified)
    manual_pr = PullRequest(
        github_id=9003, repo_id=sample_repo.id, number=101,
        title="Fix something", labels=["bug"], state="closed",
        is_merged=True, merged_at=NOW,
        work_category="ops", work_category_source="manual",
    )
    db_session.add(manual_pr)
    await db_session.commit()

    resp = await client.post("/api/work-categories/reclassify")
    assert resp.status_code == 200
    data = resp.json()
    assert data["prs_updated"] >= 1
    assert data["issues_updated"] >= 1

    # Verify PR was classified as bugfix (label "bug" matches)
    await db_session.refresh(pr)
    assert pr.work_category == "bugfix"
    assert pr.work_category_source == "label"

    # Verify issue was classified as feature (title match)
    await db_session.refresh(issue)
    assert issue.work_category == "feature"
    assert issue.work_category_source == "title"

    # Verify manual override was preserved
    await db_session.refresh(manual_pr)
    assert manual_pr.work_category == "ops"
    assert manual_pr.work_category_source == "manual"


@pytest.mark.asyncio
async def test_create_category_with_description(client):
    resp = await client.post("/api/work-categories", json={
        "category_key": "security",
        "display_name": "Security",
        "description": "Security-related fixes and hardening work.",
        "color": "#dc2626",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["description"] == "Security-related fixes and hardening work."


@pytest.mark.asyncio
async def test_update_category_description(client):
    resp = await client.patch("/api/work-categories/feature", json={
        "description": "New features and enhancements.",
    })
    assert resp.status_code == 200
    assert resp.json()["description"] == "New features and enhancements."


@pytest.mark.asyncio
async def test_default_categories_have_descriptions(client):
    resp = await client.get("/api/work-categories")
    cats = {c["category_key"]: c for c in resp.json()}
    assert cats["feature"]["description"] is not None
    assert cats["bugfix"]["description"] is not None
    assert cats["unknown"]["description"] is not None


@pytest.mark.asyncio
async def test_create_issue_type_rule(client):
    resp = await client.post("/api/work-categories/rules", json={
        "match_type": "issue_type",
        "match_value": "Bug",
        "description": "Maps GitHub Bug issue type to bugfix category.",
        "category_key": "bugfix",
        "priority": 55,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["match_type"] == "issue_type"
    assert data["match_value"] == "Bug"
    assert data["description"] == "Maps GitHub Bug issue type to bugfix category."


@pytest.mark.asyncio
async def test_create_rule_with_description(client):
    resp = await client.post("/api/work-categories/rules", json={
        "match_type": "label",
        "match_value": "hotfix",
        "description": "Catches hotfix labels from the triage workflow.",
        "category_key": "bugfix",
        "priority": 15,
    })
    assert resp.status_code == 201
    assert resp.json()["description"] == "Catches hotfix labels from the triage workflow."


@pytest.mark.asyncio
async def test_reclassify_with_issue_type(client, db_session, sample_repo):
    """Reclassify respects issue_type rules."""
    from app.models.models import Issue, WorkCategoryRule

    from conftest import NOW

    # Add an issue_type rule
    rule = WorkCategoryRule(
        match_type="issue_type", match_value="Epic",
        category_key="feature", priority=55, case_sensitive=False,
    )
    db_session.add(rule)

    # Create an issue with issue_type
    issue = Issue(
        github_id=9010, repo_id=sample_repo.id, number=300,
        title="Platform rewrite", labels=[], state="open",
        created_at=NOW, issue_type="Epic",
        work_category=None, work_category_source=None,
    )
    db_session.add(issue)
    await db_session.commit()

    resp = await client.post("/api/work-categories/reclassify")
    assert resp.status_code == 200

    await db_session.refresh(issue)
    assert issue.work_category == "feature"
    assert issue.work_category_source == "issue_type"


@pytest.mark.asyncio
async def test_scan_suggestions_empty(client):
    """No PRs/issues → no suggestions."""
    resp = await client.post("/api/work-categories/suggestions")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_scan_suggestions_finds_uncovered_labels(client, db_session, sample_repo):
    """Labels not covered by existing rules appear as suggestions."""
    from app.models.models import PullRequest

    from conftest import NOW

    # Create PRs with labels — "bug" is covered, "priority-high" is not
    pr1 = PullRequest(
        github_id=8001, repo_id=sample_repo.id, number=500,
        title="Fix stuff", labels=["bug", "priority-high"], state="open",
    )
    pr2 = PullRequest(
        github_id=8002, repo_id=sample_repo.id, number=501,
        title="More stuff", labels=["priority-high", "wontfix"], state="open",
    )
    db_session.add_all([pr1, pr2])
    await db_session.commit()

    resp = await client.post("/api/work-categories/suggestions")
    assert resp.status_code == 200
    data = resp.json()

    values = {s["match_value"] for s in data}
    assert "priority-high" in values
    assert "wontfix" in values
    assert "bug" not in values  # covered by existing rule

    # Check usage count
    ph = next(s for s in data if s["match_value"] == "priority-high")
    assert ph["usage_count"] == 2
    assert ph["match_type"] == "label"


@pytest.mark.asyncio
async def test_scan_suggestions_finds_issue_types(client, db_session, sample_repo):
    """Uncovered issue types appear as suggestions."""
    from app.models.models import Issue

    from conftest import NOW

    issue = Issue(
        github_id=8010, repo_id=sample_repo.id, number=600,
        title="New epic", labels=[], state="open",
        created_at=NOW, issue_type="Epic",
    )
    db_session.add(issue)
    await db_session.commit()

    resp = await client.post("/api/work-categories/suggestions")
    assert resp.status_code == 200
    data = resp.json()

    epic = next((s for s in data if s["match_value"] == "Epic"), None)
    assert epic is not None
    assert epic["match_type"] == "issue_type"
    assert epic["suggested_category"] == "unknown"  # "Epic" doesn't match any hint keywords


@pytest.mark.asyncio
async def test_scan_suggestions_sorted_by_usage(client, db_session, sample_repo):
    """Results are sorted by usage count descending."""
    from app.models.models import PullRequest

    pr1 = PullRequest(
        github_id=8020, repo_id=sample_repo.id, number=700,
        title="A", labels=["rare-label"], state="open",
    )
    pr2 = PullRequest(
        github_id=8021, repo_id=sample_repo.id, number=701,
        title="B", labels=["common-label"], state="open",
    )
    pr3 = PullRequest(
        github_id=8022, repo_id=sample_repo.id, number=702,
        title="C", labels=["common-label"], state="open",
    )
    db_session.add_all([pr1, pr2, pr3])
    await db_session.commit()

    resp = await client.post("/api/work-categories/suggestions")
    data = resp.json()

    # Filter to our test labels
    test_suggestions = [s for s in data if s["match_value"] in ("rare-label", "common-label")]
    assert len(test_suggestions) >= 2
    assert test_suggestions[0]["match_value"] == "common-label"
    assert test_suggestions[0]["usage_count"] == 2


@pytest.mark.asyncio
async def test_bulk_create_rules(client):
    """Bulk endpoint creates multiple rules at once."""
    resp = await client.post("/api/work-categories/rules/bulk", json={
        "rules": [
            {
                "match_type": "label",
                "match_value": "bulk-test-1",
                "category_key": "feature",
                "priority": 45,
                "case_sensitive": False,
            },
            {
                "match_type": "label",
                "match_value": "bulk-test-2",
                "category_key": "bugfix",
                "priority": 45,
                "case_sensitive": False,
            },
        ],
    })
    assert resp.status_code == 201
    assert resp.json()["created"] == 2

    # Verify rules exist
    rules_resp = await client.get("/api/work-categories/rules")
    rule_values = [r["match_value"] for r in rules_resp.json()]
    assert "bulk-test-1" in rule_values
    assert "bulk-test-2" in rule_values


@pytest.mark.asyncio
async def test_bulk_create_rules_invalid_category(client):
    """Bulk create rejects if any rule references a nonexistent category."""
    resp = await client.post("/api/work-categories/rules/bulk", json={
        "rules": [
            {
                "match_type": "label",
                "match_value": "valid",
                "category_key": "nonexistent",
                "priority": 45,
                "case_sensitive": False,
            },
        ],
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_bulk_create_rules_empty(client):
    """Empty rules list creates nothing."""
    resp = await client.post("/api/work-categories/rules/bulk", json={"rules": []})
    assert resp.status_code == 201
    assert resp.json()["created"] == 0


@pytest.mark.asyncio
async def test_suggestions_requires_admin(developer_client):
    """Developer users cannot access suggestions endpoint."""
    resp = await developer_client.post("/api/work-categories/suggestions")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_bulk_create_requires_admin(developer_client):
    """Developer users cannot bulk-create rules."""
    resp = await developer_client.post("/api/work-categories/rules/bulk", json={"rules": []})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_developer_cannot_mutate(developer_client):
    """Regular developers can read but not create/update/delete."""
    # Can read
    resp = await developer_client.get("/api/work-categories")
    assert resp.status_code == 200

    resp = await developer_client.get("/api/work-categories/rules")
    assert resp.status_code == 200

    # Cannot write
    resp = await developer_client.post("/api/work-categories", json={
        "category_key": "test", "display_name": "Test", "color": "#000000",
    })
    assert resp.status_code == 403

    resp = await developer_client.post("/api/work-categories/reclassify")
    assert resp.status_code == 403


# --- ReDoS protection ---


@pytest.mark.asyncio
async def test_create_rule_nested_quantifier_rejected(client):
    """Regex patterns with nested quantifiers are rejected (ReDoS protection)."""
    resp = await client.post("/api/work-categories/rules", json={
        "match_type": "title_regex",
        "match_value": "(a+)+$",
        "category_key": "feature",
        "priority": 999,
    })
    assert resp.status_code == 409
    assert "nested quantifiers" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_rule_valid_regex_accepted(client):
    """Non-dangerous regex patterns are still accepted."""
    resp = await client.post("/api/work-categories/rules", json={
        "match_type": "title_regex",
        "match_value": r"\bhotfix\b",
        "category_key": "bugfix",
        "priority": 998,
    })
    assert resp.status_code == 201


# --- Schema max_length validation ---


@pytest.mark.asyncio
async def test_create_rule_match_value_too_long(client):
    resp = await client.post("/api/work-categories/rules", json={
        "match_type": "label",
        "match_value": "x" * 1001,
        "category_key": "feature",
        "priority": 1,
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_category_display_name_too_long(client):
    resp = await client.post("/api/work-categories", json={
        "category_key": "testlong",
        "display_name": "x" * 201,
        "color": "#000000",
    })
    assert resp.status_code == 422
