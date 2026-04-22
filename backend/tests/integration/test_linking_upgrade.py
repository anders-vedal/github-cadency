"""Phase 02 tests — 4-pass linker with confidence tiers + linkage quality summary."""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    ExternalIssue,
    ExternalIssueAttachment,
    IntegrationConfig,
    PRExternalIssueLink,
    PullRequest,
    Repository,
)
from app.services.encryption import encrypt_token
from app.services.linear_sync import link_prs_to_external_issues, run_linear_relink
from app.services.linkage_quality import get_link_quality_summary


@pytest_asyncio.fixture
async def linear_integration(db_session: AsyncSession) -> IntegrationConfig:
    config = IntegrationConfig(
        type="linear",
        display_name="Linear",
        api_key=encrypt_token("k"),
        workspace_id="wsp",
        workspace_name="Test",
        status="active",
    )
    db_session.add(config)
    await db_session.commit()
    await db_session.refresh(config)
    return config


@pytest_asyncio.fixture
async def repo(db_session: AsyncSession) -> Repository:
    r = Repository(name="repo", full_name="acme/repo", github_id=1)
    db_session.add(r)
    await db_session.commit()
    await db_session.refresh(r)
    return r


@pytest_asyncio.fixture
async def issues(
    db_session: AsyncSession, linear_integration: IntegrationConfig
) -> list[ExternalIssue]:
    out = []
    for ident in ("ENG-100", "ENG-200"):
        iss = ExternalIssue(
            integration_id=linear_integration.id,
            external_id=f"linear_{ident}",
            identifier=ident,
            title=f"Issue {ident}",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(iss)
        out.append(iss)
    await db_session.commit()
    for i in out:
        await db_session.refresh(i)
    return out


async def _make_pr(
    db: AsyncSession,
    repo: Repository,
    number: int,
    *,
    title: str = "Test PR",
    head_branch: str = "feat/test",
    body: str = "",
) -> PullRequest:
    pr = PullRequest(
        github_id=10_000 + number,
        repo_id=repo.id,
        number=number,
        title=title,
        body=body,
        state="open",
        head_branch=head_branch,
        base_branch="main",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        html_url=f"https://github.com/acme/repo/pull/{number}",
    )
    db.add(pr)
    await db.commit()
    await db.refresh(pr)
    return pr


@pytest.mark.asyncio
async def test_pass1_attachment_high_confidence(
    db_session: AsyncSession,
    linear_integration: IntegrationConfig,
    repo: Repository,
    issues: list[ExternalIssue],
):
    """A Linear attachment with github_pr URL links at HIGH confidence."""
    pr = await _make_pr(db_session, repo, 42, title="does not mention issue")

    att = ExternalIssueAttachment(
        issue_id=issues[0].id,
        external_id="att_pr_1",
        url="https://github.com/acme/repo/pull/42",
        source_type="github",
        normalized_source_type="github_pr",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(att)
    await db_session.commit()

    new_links = await link_prs_to_external_issues(db_session, linear_integration.id)

    assert new_links >= 1
    rows = (await db_session.execute(select(PRExternalIssueLink))).scalars().all()
    link = next(r for r in rows if r.pull_request_id == pr.id)
    assert link.link_source == "linear_attachment"
    assert link.link_confidence == "high"
    assert link.external_issue_id == issues[0].id


@pytest.mark.asyncio
async def test_pass4_body_low_confidence(
    db_session: AsyncSession,
    linear_integration: IntegrationConfig,
    repo: Repository,
    issues: list[ExternalIssue],
):
    """An issue key only in the PR body yields LOW confidence."""
    pr = await _make_pr(
        db_session,
        repo,
        99,
        title="Plain PR with no key",
        head_branch="feat/plain",
        body="Mentions ENG-100 in the body only",
    )

    await link_prs_to_external_issues(db_session, linear_integration.id)

    link = (
        await db_session.execute(
            select(PRExternalIssueLink).where(PRExternalIssueLink.pull_request_id == pr.id)
        )
    ).scalar_one()
    assert link.link_source == "body"
    assert link.link_confidence == "low"


@pytest.mark.asyncio
async def test_branch_upgrades_low_body_to_medium(
    db_session: AsyncSession,
    linear_integration: IntegrationConfig,
    repo: Repository,
    issues: list[ExternalIssue],
):
    """If both branch and body contain the key, the existing low link upgrades to medium."""
    pr = await _make_pr(
        db_session,
        repo,
        150,
        title="PR",
        head_branch="feat/ENG-100-fix",
        body="Fixes ENG-100",
    )

    await link_prs_to_external_issues(db_session, linear_integration.id)

    link = (
        await db_session.execute(
            select(PRExternalIssueLink).where(PRExternalIssueLink.pull_request_id == pr.id)
        )
    ).scalar_one()
    # Branch wins (medium) over body (low) — branch is tried first in the loop,
    # and if body tried first had registered low, branch would upgrade to medium.
    assert link.link_confidence == "medium"
    assert link.link_source == "branch"


@pytest.mark.asyncio
async def test_attachment_upgrades_branch_to_high(
    db_session: AsyncSession,
    linear_integration: IntegrationConfig,
    repo: Repository,
    issues: list[ExternalIssue],
):
    """Attachment pass upgrades an existing medium branch link to high."""
    pr = await _make_pr(
        db_session,
        repo,
        200,
        head_branch="feat/ENG-100-fix",
    )

    att = ExternalIssueAttachment(
        issue_id=issues[0].id,
        external_id="att_pr_200",
        url="https://github.com/acme/repo/pull/200",
        source_type="github",
        normalized_source_type="github_pr",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(att)
    await db_session.commit()

    await link_prs_to_external_issues(db_session, linear_integration.id)

    link = (
        await db_session.execute(
            select(PRExternalIssueLink).where(PRExternalIssueLink.pull_request_id == pr.id)
        )
    ).scalar_one()
    assert link.link_confidence == "high"
    assert link.link_source == "linear_attachment"


@pytest.mark.asyncio
async def test_relink_is_idempotent(
    db_session: AsyncSession,
    linear_integration: IntegrationConfig,
    repo: Repository,
    issues: list[ExternalIssue],
):
    """Running the linker twice produces the same link count and no duplicates."""
    await _make_pr(db_session, repo, 1, head_branch="feat/ENG-100-a")
    await _make_pr(db_session, repo, 2, head_branch="feat/ENG-200-b")

    new_first = await link_prs_to_external_issues(db_session, linear_integration.id)
    new_second = await link_prs_to_external_issues(db_session, linear_integration.id)

    assert new_first == 2
    assert new_second == 0  # idempotent — no new links on second run

    rows = (await db_session.execute(select(PRExternalIssueLink))).scalars().all()
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_multi_issue_links_one_per_pair(
    db_session: AsyncSession,
    linear_integration: IntegrationConfig,
    repo: Repository,
    issues: list[ExternalIssue],
):
    """A PR referencing two issues creates two link rows (one per issue)."""
    pr = await _make_pr(
        db_session,
        repo,
        3,
        title="Fix ENG-100 and ENG-200",
        head_branch="feat/multi",
    )

    await link_prs_to_external_issues(db_session, linear_integration.id)

    rows = (
        await db_session.execute(
            select(PRExternalIssueLink).where(PRExternalIssueLink.pull_request_id == pr.id)
        )
    ).scalars().all()
    linked_issues = sorted(r.external_issue_id for r in rows)
    assert linked_issues == sorted(i.id for i in issues)


@pytest.mark.asyncio
async def test_link_quality_summary_shape(
    db_session: AsyncSession,
    linear_integration: IntegrationConfig,
    repo: Repository,
    issues: list[ExternalIssue],
):
    """get_link_quality_summary returns expected counters and fields."""
    await _make_pr(db_session, repo, 10, head_branch="feat/ENG-100-a")  # linked medium
    unlinked = await _make_pr(db_session, repo, 11, head_branch="feat/no-issue", body="")

    await link_prs_to_external_issues(db_session, linear_integration.id)

    summary = await get_link_quality_summary(db_session, integration_id=linear_integration.id)

    assert summary["total_prs"] == 2
    assert summary["linked_prs"] == 1
    assert 0.0 < summary["linkage_rate"] < 1.0
    assert summary["by_confidence"]["medium"] == 1
    assert summary["by_source"].get("branch") == 1
    # unlinked_recent includes the unlinked PR (just created, within 30 days)
    assert any(u["pr_id"] == unlinked.id for u in summary["unlinked_recent"])


@pytest.mark.asyncio
async def test_run_linear_relink_creates_sync_event(
    db_session: AsyncSession,
    linear_integration: IntegrationConfig,
    repo: Repository,
    issues: list[ExternalIssue],
):
    """run_linear_relink records a SyncEvent with status completed."""
    await _make_pr(db_session, repo, 20, head_branch="feat/ENG-100-z")
    sync_event = await run_linear_relink(db_session, linear_integration.id)
    assert sync_event.status == "completed"
    assert sync_event.sync_type == "linear"
