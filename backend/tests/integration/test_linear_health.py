"""Phase 03 — Linear Usage Health service tests."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Developer,
    ExternalIssue,
    ExternalIssueComment,
    IntegrationConfig,
    PRExternalIssueLink,
    PullRequest,
    Repository,
)
from app.services.encryption import encrypt_token
from app.services.linear_health import get_linear_usage_health, is_linear_primary


@pytest_asyncio.fixture
async def linear_integration(db_session: AsyncSession) -> IntegrationConfig:
    config = IntegrationConfig(
        type="linear",
        display_name="Linear",
        api_key=encrypt_token("k"),
        workspace_id="wsp",
        workspace_name="Test",
        status="active",
        is_primary_issue_source=True,
    )
    db_session.add(config)
    await db_session.commit()
    await db_session.refresh(config)
    return config


@pytest_asyncio.fixture
async def devs(db_session: AsyncSession) -> list[Developer]:
    out = []
    for i in range(3):
        d = Developer(
            github_username=f"user{i}",
            display_name=f"User {i}",
            email=f"u{i}@example.com",
            is_active=True,
        )
        db_session.add(d)
        out.append(d)
    await db_session.commit()
    for d in out:
        await db_session.refresh(d)
    return out


@pytest.mark.asyncio
async def test_is_linear_primary_true(
    db_session: AsyncSession, linear_integration: IntegrationConfig
):
    assert await is_linear_primary(db_session) is True


@pytest.mark.asyncio
async def test_is_linear_primary_false_without_integration(db_session: AsyncSession):
    assert await is_linear_primary(db_session) is False


@pytest.mark.asyncio
async def test_empty_range_returns_zeros(
    db_session: AsyncSession, linear_integration: IntegrationConfig
):
    result = await get_linear_usage_health(db_session)
    assert result["adoption"]["total_pr_count"] == 0
    assert result["adoption"]["linkage_rate"] == 0.0
    assert result["dialogue_health"]["median_comments_per_issue"] == 0.0
    assert result["creator_outcome"]["top_creators"] == []


@pytest.mark.asyncio
async def test_adoption_signal_computes_linkage_rate(
    db_session: AsyncSession,
    linear_integration: IntegrationConfig,
    devs: list[Developer],
):
    # Create a repo and 3 merged PRs, 2 of which are linked
    repo = Repository(name="r", full_name="acme/r", github_id=99)
    db_session.add(repo)
    await db_session.commit()
    await db_session.refresh(repo)

    issue = ExternalIssue(
        integration_id=linear_integration.id,
        external_id="i1",
        identifier="ENG-1",
        title="Issue 1",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(issue)
    await db_session.commit()
    await db_session.refresh(issue)

    now = datetime.now(timezone.utc)
    prs = []
    for i in range(3):
        pr = PullRequest(
            github_id=1000 + i,
            repo_id=repo.id,
            number=i,
            title=f"PR {i}",
            state="merged",
            is_merged=True,
            created_at=now - timedelta(days=10),
            updated_at=now,
            merged_at=now - timedelta(days=1),
            head_branch="main",
            base_branch="main",
        )
        db_session.add(pr)
        prs.append(pr)
    await db_session.commit()
    for pr in prs:
        await db_session.refresh(pr)

    # Link 2 of 3 PRs
    for pr in prs[:2]:
        db_session.add(
            PRExternalIssueLink(
                pull_request_id=pr.id,
                external_issue_id=issue.id,
                link_source="title",
                link_confidence="medium",
            )
        )
    await db_session.commit()

    result = await get_linear_usage_health(db_session)
    assert result["adoption"]["total_pr_count"] == 3
    assert result["adoption"]["linked_pr_count"] == 2
    assert abs(result["adoption"]["linkage_rate"] - (2 / 3)) < 0.001


@pytest.mark.asyncio
async def test_dialogue_health_counts_exclude_system_comments(
    db_session: AsyncSession,
    linear_integration: IntegrationConfig,
):
    now = datetime.now(timezone.utc)
    issue = ExternalIssue(
        integration_id=linear_integration.id,
        external_id="i1",
        identifier="ENG-1",
        title="Issue",
        created_at=now - timedelta(days=5),
        updated_at=now,
    )
    db_session.add(issue)
    await db_session.commit()
    await db_session.refresh(issue)

    # 1 human comment, 2 bot comments
    db_session.add(
        ExternalIssueComment(
            issue_id=issue.id,
            external_id="c1",
            body_length=5,
            body_preview="hello",
            created_at=now,
            is_system_generated=False,
        )
    )
    db_session.add(
        ExternalIssueComment(
            issue_id=issue.id,
            external_id="c2",
            body_length=5,
            body_preview="bot1",
            created_at=now,
            is_system_generated=True,
            bot_actor_type="github",
        )
    )
    db_session.add(
        ExternalIssueComment(
            issue_id=issue.id,
            external_id="c3",
            body_length=5,
            body_preview="bot2",
            created_at=now,
            is_system_generated=True,
            bot_actor_type="workflow",
        )
    )
    await db_session.commit()

    result = await get_linear_usage_health(db_session)
    # Only 1 human comment counted, on 1 issue → median = 1
    assert result["dialogue_health"]["median_comments_per_issue"] == 1.0


@pytest.mark.asyncio
async def test_autonomy_self_picked_vs_pushed(
    db_session: AsyncSession,
    linear_integration: IntegrationConfig,
    devs: list[Developer],
):
    now = datetime.now(timezone.utc)
    # 2 self-picked (creator == assignee)
    # 1 pushed (different)
    for i, (creator, assignee) in enumerate([
        (devs[0], devs[0]),
        (devs[1], devs[1]),
        (devs[2], devs[0]),
    ]):
        db_session.add(
            ExternalIssue(
                integration_id=linear_integration.id,
                external_id=f"ai{i}",
                identifier=f"ENG-{i}",
                title=f"Issue {i}",
                creator_developer_id=creator.id,
                assignee_developer_id=assignee.id,
                created_at=now - timedelta(days=5),
                updated_at=now,
            )
        )
    await db_session.commit()

    result = await get_linear_usage_health(db_session)
    assert result["autonomy"]["self_picked_count"] == 2
    assert result["autonomy"]["pushed_count"] == 1
    assert abs(result["autonomy"]["self_picked_pct"] - (2 / 3)) < 0.001


@pytest.mark.asyncio
async def test_spec_quality_median_description_length(
    db_session: AsyncSession,
    linear_integration: IntegrationConfig,
):
    now = datetime.now(timezone.utc)
    lengths = [200, 150, 100, 50, 10]
    for i, length in enumerate(lengths):
        db_session.add(
            ExternalIssue(
                integration_id=linear_integration.id,
                external_id=f"s{i}",
                identifier=f"S-{i}",
                title=f"Issue {i}",
                description_length=length,
                created_at=now - timedelta(days=5),
                updated_at=now,
            )
        )
    await db_session.commit()

    result = await get_linear_usage_health(db_session)
    # Median of [10,50,100,150,200] = 100
    assert result["spec_quality"]["median_description_length"] == 100


@pytest.mark.asyncio
async def test_creator_outcome_top_creators(
    db_session: AsyncSession,
    linear_integration: IntegrationConfig,
    devs: list[Developer],
):
    now = datetime.now(timezone.utc)
    # devs[0] creates 3 issues, devs[1] creates 1, devs[2] creates 2
    for i, creator in enumerate([devs[0], devs[0], devs[0], devs[1], devs[2], devs[2]]):
        db_session.add(
            ExternalIssue(
                integration_id=linear_integration.id,
                external_id=f"co{i}",
                identifier=f"CO-{i}",
                title=f"Issue {i}",
                creator_developer_id=creator.id,
                created_at=now - timedelta(days=5),
                updated_at=now,
            )
        )
    await db_session.commit()

    result = await get_linear_usage_health(db_session)
    top = result["creator_outcome"]["top_creators"]
    assert len(top) >= 2
    # Top creator should be devs[0] with 3 issues
    assert top[0]["developer_id"] == devs[0].id
    assert top[0]["issues_created"] == 3
