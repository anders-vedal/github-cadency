"""Integration tests for Phase 01 Linear sync depth:
comments, history events, attachments, relations, SLA fields, and bot detection."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Developer,
    ExternalIssue,
    ExternalIssueAttachment,
    ExternalIssueComment,
    ExternalIssueHistoryEvent,
    ExternalIssueRelation,
    IntegrationConfig,
)
from app.services.encryption import encrypt_token
from app.services.linear_sync import LinearClient, sync_linear_issues


@pytest_asyncio.fixture
async def linear_integration(db_session: AsyncSession) -> IntegrationConfig:
    config = IntegrationConfig(
        type="linear",
        display_name="Linear",
        api_key=encrypt_token("test_key"),
        workspace_id="wsp_1",
        workspace_name="Test Workspace",
        status="active",
    )
    db_session.add(config)
    await db_session.commit()
    await db_session.refresh(config)
    return config


@pytest_asyncio.fixture
async def two_issues(
    db_session: AsyncSession, linear_integration: IntegrationConfig
) -> list[ExternalIssue]:
    """Pre-seed two issues so relation tests can link them."""
    issues = []
    for ident in ("ENG-1", "ENG-2"):
        iss = ExternalIssue(
            integration_id=linear_integration.id,
            external_id=f"linear_{ident}",
            identifier=ident,
            title=f"Issue {ident}",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(iss)
        issues.append(iss)
    await db_session.commit()
    for i in issues:
        await db_session.refresh(i)
    return issues


def _issue_node(
    *,
    ext_id: str = "linear_ENG-100",
    identifier: str = "ENG-100",
    title: str = "Fix login bug",
    comments: list | None = None,
    history: list | None = None,
    attachments: list | None = None,
    relations: list | None = None,
    sla_status: str | None = None,
) -> dict:
    return {
        "id": ext_id,
        "identifier": identifier,
        "title": title,
        "description": "Users report that login fails intermittently.",
        "state": {"name": "In Progress", "type": "started"},
        "priority": 2,
        "priorityLabel": "High",
        "estimate": 3.0,
        "labels": {"nodes": [{"id": "lbl_bug", "name": "bug"}]},
        "assignee": None,
        "creator": None,
        "project": None,
        "cycle": None,
        "parent": None,
        "createdAt": "2026-04-01T10:00:00.000Z",
        "startedAt": "2026-04-02T09:00:00.000Z",
        "completedAt": None,
        "canceledAt": None,
        "updatedAt": "2026-04-10T14:00:00.000Z",
        "url": f"https://linear.app/test/{identifier}",
        # SLA timestamps drive the derived sla_status — slaStatus is no longer
        # queried directly (not a real field on Issue per Linear's schema).
        "slaStartedAt": "2026-04-01T10:00:00.000Z" if sla_status else None,
        # Far future breach so derivation doesn't classify as "Breached".
        "slaBreachesAt": "2099-12-31T10:00:00.000Z" if sla_status else None,
        # high_risk_at in the past triggers HighRisk derivation when set.
        "slaHighRiskAt": "2026-04-10T10:00:00.000Z" if sla_status == "HighRisk" else None,
        "slaMediumRiskAt": None,
        "slaType": "calendar" if sla_status else None,
        "triagedAt": "2026-04-01T11:00:00.000Z",
        "subscribers": {"nodes": [{"id": "u1"}, {"id": "u2"}]},
        "reactionData": [{"emoji": "👍", "count": 2}],
        "comments": {
            "pageInfo": {"hasNextPage": False},
            "nodes": comments or [],
        },
        "history": {
            "pageInfo": {"hasNextPage": False},
            "nodes": history or [],
        },
        "attachments": {"nodes": attachments or []},
        "relations": {"nodes": relations or []},
    }


@pytest.mark.asyncio
async def test_sync_persists_comments_with_bot_detection(
    db_session: AsyncSession, linear_integration: IntegrationConfig
):
    """Comments sync correctly with botActor-based is_system_generated flag."""
    human_comment = {
        "id": "cmt_1",
        "parent": None,
        "user": {"id": "u_1", "email": "alice@example.com"},
        "externalUser": None,
        "botActor": None,
        "createdAt": "2026-04-02T10:00:00.000Z",
        "updatedAt": "2026-04-02T10:00:00.000Z",
        "editedAt": None,
        "body": "Looks good to me!",
        "reactionData": None,
    }
    bot_comment = {
        "id": "cmt_2",
        "parent": None,
        "user": None,
        "externalUser": None,
        "botActor": {"type": "github", "subType": "pr_link", "name": "GitHub"},
        "createdAt": "2026-04-03T10:00:00.000Z",
        "updatedAt": "2026-04-03T10:00:00.000Z",
        "editedAt": None,
        "body": "PR #42 merged",
        "reactionData": None,
    }

    node = _issue_node(comments=[human_comment, bot_comment])

    client = LinearClient("k")
    with patch.object(
        client,
        "query",
        new=AsyncMock(
            return_value={"issues": {"pageInfo": {"hasNextPage": False}, "nodes": [node]}}
        ),
    ):
        counts = await sync_linear_issues(client, db_session, linear_integration.id)
    await client.close()

    assert counts["issues"] == 1
    assert counts["comments"] == 2

    rows = (
        await db_session.execute(
            select(ExternalIssueComment).order_by(ExternalIssueComment.external_id)
        )
    ).scalars().all()
    assert len(rows) == 2

    human = next(r for r in rows if r.external_id == "cmt_1")
    bot = next(r for r in rows if r.external_id == "cmt_2")
    assert human.is_system_generated is False
    assert human.bot_actor_type is None
    assert human.body_preview == "Looks good to me!"

    assert bot.is_system_generated is True
    assert bot.bot_actor_type == "github"


@pytest.mark.asyncio
async def test_sync_persists_comment_reply_thread(
    db_session: AsyncSession, linear_integration: IntegrationConfig
):
    """Replies resolve parent_comment_id after both rows are flushed."""
    parent = {
        "id": "cmt_parent",
        "parent": None,
        "user": {"id": "u_1", "email": "alice@example.com"},
        "externalUser": None,
        "botActor": None,
        "createdAt": "2026-04-02T10:00:00.000Z",
        "updatedAt": "2026-04-02T10:00:00.000Z",
        "editedAt": None,
        "body": "Parent comment",
        "reactionData": None,
    }
    child = {
        "id": "cmt_child",
        "parent": {"id": "cmt_parent"},
        "user": {"id": "u_2", "email": "bob@example.com"},
        "externalUser": None,
        "botActor": None,
        "createdAt": "2026-04-02T11:00:00.000Z",
        "updatedAt": "2026-04-02T11:00:00.000Z",
        "editedAt": None,
        "body": "Reply to parent",
        "reactionData": None,
    }

    node = _issue_node(comments=[parent, child])
    client = LinearClient("k")
    with patch.object(
        client,
        "query",
        new=AsyncMock(
            return_value={"issues": {"pageInfo": {"hasNextPage": False}, "nodes": [node]}}
        ),
    ):
        await sync_linear_issues(client, db_session, linear_integration.id)
    await client.close()

    parent_row = (
        await db_session.execute(
            select(ExternalIssueComment).where(ExternalIssueComment.external_id == "cmt_parent")
        )
    ).scalar_one()
    child_row = (
        await db_session.execute(
            select(ExternalIssueComment).where(ExternalIssueComment.external_id == "cmt_child")
        )
    ).scalar_one()
    assert child_row.parent_comment_id == parent_row.id
    assert parent_row.parent_comment_id is None


@pytest.mark.asyncio
async def test_sync_persists_history_with_all_fromto_columns(
    db_session: AsyncSession, linear_integration: IntegrationConfig
):
    """A single history event with multiple changed fields persists as one row with all columns."""
    history_event = {
        "id": "hist_1",
        "createdAt": "2026-04-03T10:00:00.000Z",
        "actor": {"id": "u_1", "email": "alice@example.com"},
        "botActor": None,
        "fromState": {"id": "st_todo", "name": "Todo", "type": "unstarted"},
        "toState": {"id": "st_prog", "name": "In Progress", "type": "started"},
        "fromAssignee": None,
        "toAssignee": {"id": "u_1", "email": "alice@example.com"},
        "fromEstimate": 2.0,
        "toEstimate": 5.0,
        "fromPriority": 1,
        "toPriority": 2,
        "fromCycle": None,
        "toCycle": None,
        "fromProject": None,
        "toProject": None,
        "fromParent": None,
        "toParent": None,
        "addedLabelIds": ["lbl_urgent"],
        "removedLabelIds": [],
        "archived": False,
        "autoArchived": False,
        "autoClosed": False,
    }

    node = _issue_node(history=[history_event])
    client = LinearClient("k")
    with patch.object(
        client,
        "query",
        new=AsyncMock(
            return_value={"issues": {"pageInfo": {"hasNextPage": False}, "nodes": [node]}}
        ),
    ):
        counts = await sync_linear_issues(client, db_session, linear_integration.id)
    await client.close()

    assert counts["history"] == 1
    row = (
        await db_session.execute(select(ExternalIssueHistoryEvent))
    ).scalar_one()

    assert row.from_state == "Todo"
    assert row.to_state == "In Progress"
    assert row.from_state_category == "todo"
    assert row.to_state_category == "in_progress"
    assert row.from_estimate == 2.0
    assert row.to_estimate == 5.0
    assert row.from_priority == 1
    assert row.to_priority == 2
    assert row.added_label_ids == ["lbl_urgent"]


@pytest.mark.asyncio
async def test_sync_persists_attachments_with_normalized_type(
    db_session: AsyncSession, linear_integration: IntegrationConfig
):
    """Attachments get normalized_source_type: github_pr, github_commit, github, other."""
    attachments = [
        {
            "id": "att_pr",
            "url": "https://github.com/acme/repo/pull/42",
            "sourceType": "github",
            "title": "Fix login",
            "metadata": {"status": "open"},
            "createdAt": "2026-04-02T10:00:00.000Z",
            "updatedAt": "2026-04-02T10:00:00.000Z",
            "creator": {"id": "u_1", "email": "alice@example.com"},
        },
        {
            "id": "att_commit",
            "url": "https://github.com/acme/repo/commit/abc1234",
            "sourceType": "github",
            "title": None,
            "metadata": None,
            "createdAt": "2026-04-02T11:00:00.000Z",
            "updatedAt": None,
            "creator": None,  # system-generated via integration
        },
    ]

    node = _issue_node(attachments=attachments)
    client = LinearClient("k")
    with patch.object(
        client,
        "query",
        new=AsyncMock(
            return_value={"issues": {"pageInfo": {"hasNextPage": False}, "nodes": [node]}}
        ),
    ):
        counts = await sync_linear_issues(client, db_session, linear_integration.id)
    await client.close()

    assert counts["attachments"] == 2
    rows = (
        await db_session.execute(
            select(ExternalIssueAttachment).order_by(ExternalIssueAttachment.external_id)
        )
    ).scalars().all()
    att_by_id = {r.external_id: r for r in rows}
    assert att_by_id["att_pr"].normalized_source_type == "github_pr"
    assert att_by_id["att_commit"].normalized_source_type == "github_commit"
    assert att_by_id["att_commit"].is_system_generated is True
    assert att_by_id["att_pr"].is_system_generated is False


@pytest.mark.asyncio
async def test_sync_persists_relations_bidirectionally(
    db_session: AsyncSession,
    linear_integration: IntegrationConfig,
    two_issues: list[ExternalIssue],
):
    """`blocks` relation on issue A creates both A->B(blocks) and B->A(blocked_by) rows."""
    # Use ENG-1 as the sync target with a `blocks` relation to ENG-2
    eng1, eng2 = two_issues

    node = {
        **_issue_node(ext_id=eng1.external_id, identifier=eng1.identifier),
        "relations": {
            "nodes": [
                {
                    "id": "rel_1",
                    "type": "blocks",
                    "relatedIssue": {"id": eng2.external_id},
                }
            ]
        },
    }

    client = LinearClient("k")
    with patch.object(
        client,
        "query",
        new=AsyncMock(
            return_value={"issues": {"pageInfo": {"hasNextPage": False}, "nodes": [node]}}
        ),
    ):
        counts = await sync_linear_issues(client, db_session, linear_integration.id)
    await client.close()

    # Expect 2 relation rows: (eng1 blocks eng2) + (eng2 blocked_by eng1)
    assert counts["relations"] == 2
    rows = (await db_session.execute(select(ExternalIssueRelation))).scalars().all()
    types = sorted(r.relation_type for r in rows)
    assert types == ["blocked_by", "blocks"]

    forward = next(r for r in rows if r.relation_type == "blocks")
    reverse = next(r for r in rows if r.relation_type == "blocked_by")
    assert forward.issue_id == eng1.id
    assert forward.related_issue_id == eng2.id
    assert reverse.issue_id == eng2.id
    assert reverse.related_issue_id == eng1.id


@pytest.mark.asyncio
async def test_sync_is_idempotent(
    db_session: AsyncSession, linear_integration: IntegrationConfig
):
    """Running sync twice does not duplicate comments / history / attachments."""
    comment = {
        "id": "cmt_1",
        "parent": None,
        "user": {"id": "u_1", "email": "alice@example.com"},
        "externalUser": None,
        "botActor": None,
        "createdAt": "2026-04-02T10:00:00.000Z",
        "updatedAt": "2026-04-02T10:00:00.000Z",
        "editedAt": None,
        "body": "Initial comment",
        "reactionData": None,
    }
    node = _issue_node(comments=[comment])
    response = {"issues": {"pageInfo": {"hasNextPage": False}, "nodes": [node]}}

    client = LinearClient("k")
    with patch.object(client, "query", new=AsyncMock(return_value=response)):
        await sync_linear_issues(client, db_session, linear_integration.id)
        await sync_linear_issues(client, db_session, linear_integration.id)
    await client.close()

    count = (
        await db_session.execute(
            select(func.count()).select_from(ExternalIssueComment)
        )
    ).scalar()
    assert count == 1

    issue_count = (
        await db_session.execute(select(func.count()).select_from(ExternalIssue))
    ).scalar()
    assert issue_count == 1


@pytest.mark.asyncio
async def test_sync_populates_sla_and_triage_fields(
    db_session: AsyncSession, linear_integration: IntegrationConfig
):
    """SLA and triage fields land on ExternalIssue."""
    node = _issue_node(sla_status="HighRisk")
    client = LinearClient("k")
    with patch.object(
        client,
        "query",
        new=AsyncMock(
            return_value={"issues": {"pageInfo": {"hasNextPage": False}, "nodes": [node]}}
        ),
    ):
        await sync_linear_issues(client, db_session, linear_integration.id)
    await client.close()

    issue = (await db_session.execute(select(ExternalIssue))).scalar_one()
    assert issue.sla_status == "HighRisk"
    assert issue.sla_type == "calendar"
    assert issue.sla_started_at is not None
    assert issue.sla_breaches_at is not None
    assert issue.triaged_at is not None
    assert issue.subscribers_count == 2
    assert issue.reaction_data == [{"emoji": "👍", "count": 2}]


@pytest.mark.asyncio
async def test_sync_counters_include_expansions(
    db_session: AsyncSession, linear_integration: IntegrationConfig
):
    """Pagination-pending expansions bump the expansions_triggered counter."""
    node = _issue_node()
    # Simulate pagination-pending on comments
    node["comments"]["pageInfo"] = {"hasNextPage": True, "endCursor": "abc"}
    node["history"]["pageInfo"] = {"hasNextPage": True, "endCursor": "def"}

    client = LinearClient("k")
    with patch.object(
        client,
        "query",
        new=AsyncMock(
            return_value={"issues": {"pageInfo": {"hasNextPage": False}, "nodes": [node]}}
        ),
    ):
        counts = await sync_linear_issues(client, db_session, linear_integration.id)
    await client.close()

    assert counts["expansions_triggered"] == 2


@pytest.mark.asyncio
async def test_sync_paginates_comments_and_history_beyond_first_page(
    db_session: AsyncSession, linear_integration: IntegrationConfig
):
    """When hasNextPage is true, follow-up pages are fetched (not silently dropped)."""
    initial_comment = {
        "id": "cmt_page1",
        "parent": None,
        "user": {"id": "u1", "email": "alice@example.com"},
        "externalUser": None,
        "botActor": None,
        "createdAt": "2026-04-01T12:00:00.000Z",
        "updatedAt": "2026-04-01T12:00:00.000Z",
        "editedAt": None,
        "body": "First-page comment",
        "reactionData": None,
    }
    initial_history = {
        "id": "hist_page1",
        "createdAt": "2026-04-01T13:00:00.000Z",
        "actor": {"id": "u1", "email": "alice@example.com"},
        "botActor": None,
        "fromState": {"id": "s0", "name": "Triage", "type": "triage"},
        "toState": {"id": "s1", "name": "Todo", "type": "unstarted"},
        "fromAssignee": None,
        "toAssignee": None,
        "fromEstimate": None,
        "toEstimate": None,
        "fromPriority": None,
        "toPriority": None,
        "fromCycle": None,
        "toCycle": None,
        "fromProject": None,
        "toProject": None,
        "fromParent": None,
        "toParent": None,
        "addedLabelIds": [],
        "removedLabelIds": [],
        "archived": False,
        "autoArchived": False,
        "autoClosed": False,
    }
    node = _issue_node(comments=[initial_comment], history=[initial_history])
    # Initial page: 1 comment, 1 history — more pages to come.
    node["comments"]["pageInfo"] = {"hasNextPage": True, "endCursor": "c_cursor_1"}
    node["history"]["pageInfo"] = {"hasNextPage": True, "endCursor": "h_cursor_1"}

    page2_comment = {
        "id": "cmt_page2_a",
        "parent": None,
        "user": {"id": "u2", "email": "alice@example.com"},
        "externalUser": None,
        "botActor": None,
        "createdAt": "2026-04-02T10:00:00.000Z",
        "updatedAt": "2026-04-02T10:00:00.000Z",
        "editedAt": None,
        "body": "Second-page comment body",
        "reactionData": None,
    }
    page3_comment = {**page2_comment, "id": "cmt_page3_a", "body": "Third-page comment"}

    page2_history = {
        "id": "hist_page2_a",
        "createdAt": "2026-04-02T10:05:00.000Z",
        "actor": {"id": "u2", "email": "alice@example.com"},
        "botActor": None,
        "fromState": {"id": "s1", "name": "Todo", "type": "unstarted"},
        "toState": {"id": "s2", "name": "In Progress", "type": "started"},
        "fromAssignee": None,
        "toAssignee": None,
        "fromEstimate": None,
        "toEstimate": None,
        "fromPriority": None,
        "toPriority": None,
        "fromCycle": None,
        "toCycle": None,
        "fromProject": None,
        "toProject": None,
        "fromParent": None,
        "toParent": None,
        "addedLabelIds": [],
        "removedLabelIds": [],
        "archived": False,
        "autoArchived": False,
        "autoClosed": False,
    }

    call_count = {"n": 0}

    async def fake_query(query_text: str, variables: dict | None = None):
        call_count["n"] += 1
        if "issues(" in query_text:
            return {"issues": {"pageInfo": {"hasNextPage": False}, "nodes": [node]}}
        if "comments(first:" in query_text:
            # First paginated fetch → still more; second → exhausted.
            cursor = (variables or {}).get("cursor")
            if cursor == "c_cursor_1":
                return {
                    "issue": {
                        "comments": {
                            "pageInfo": {"hasNextPage": True, "endCursor": "c_cursor_2"},
                            "nodes": [page2_comment],
                        }
                    }
                }
            return {
                "issue": {
                    "comments": {
                        "pageInfo": {"hasNextPage": False},
                        "nodes": [page3_comment],
                    }
                }
            }
        if "history(first:" in query_text:
            return {
                "issue": {
                    "history": {
                        "pageInfo": {"hasNextPage": False},
                        "nodes": [page2_history],
                    }
                }
            }
        return {}

    client = LinearClient("k")
    with patch.object(client, "query", new=AsyncMock(side_effect=fake_query)):
        counts = await sync_linear_issues(client, db_session, linear_integration.id)
    await client.close()

    # 1 initial + 2 extra (page 2 + page 3) = 3 comments persisted
    assert counts["comments"] == 3
    # 1 initial + 1 extra page = 2 history events persisted
    assert counts["history"] == 2
    # Expansions counter only bumps from the initial batched response, not follow-up pages.
    assert counts["expansions_triggered"] == 2
