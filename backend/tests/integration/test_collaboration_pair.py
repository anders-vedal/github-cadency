"""Integration tests for GET /stats/collaboration/pair endpoint."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Developer, PRReview, PRReviewComment, PullRequest, Repository


NOW = datetime.now(timezone.utc)
ONE_WEEK_AGO = NOW - timedelta(days=7)


@pytest_asyncio.fixture
async def collab_data(
    db_session: AsyncSession,
    sample_admin: Developer,
    sample_developer: Developer,
    sample_repo: Repository,
):
    """Create review data: admin reviews developer's PRs."""
    prs = []
    for i in range(5):
        pr = PullRequest(
            github_id=5000 + i,
            repo_id=sample_repo.id,
            author_id=sample_developer.id,
            number=50 + i,
            title=f"Feature #{i}",
            state="closed",
            is_merged=True,
            additions=20 + i * 10,
            deletions=5,
            changed_files=2,
            created_at=ONE_WEEK_AGO + timedelta(days=i),
            merged_at=ONE_WEEK_AGO + timedelta(days=i, hours=4),
            html_url=f"https://github.com/org/test-repo/pull/{50 + i}",
        )
        db_session.add(pr)
        prs.append(pr)
    await db_session.flush()

    for i, pr in enumerate(prs):
        review = PRReview(
            github_id=6000 + i,
            pr_id=pr.id,
            reviewer_id=sample_admin.id,
            state="APPROVED" if i % 2 == 0 else "CHANGES_REQUESTED",
            body="Good work" if i % 2 == 0 else "Needs changes",
            body_length=10,
            quality_tier="standard" if i % 2 == 0 else "thorough",
            reviewer_github_username=sample_admin.github_username,
            submitted_at=ONE_WEEK_AGO + timedelta(days=i, hours=2),
        )
        db_session.add(review)

        comment = PRReviewComment(
            github_id=7000 + i,
            pr_id=pr.id,
            author_github_username=sample_admin.github_username,
            body="Consider refactoring this" if i % 2 == 0 else "This is a blocker",
            comment_type="architectural" if i % 2 == 0 else "blocker",
            created_at=ONE_WEEK_AGO + timedelta(days=i, hours=3),
        )
        db_session.add(comment)

    await db_session.commit()


@pytest.mark.asyncio
async def test_pair_detail_success(
    client: AsyncClient, collab_data, sample_admin: Developer, sample_developer: Developer
):
    resp = await client.get(
        f"/api/stats/collaboration/pair?reviewer_id={sample_admin.id}&author_id={sample_developer.id}"
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["reviewer_id"] == sample_admin.id
    assert data["author_id"] == sample_developer.id
    assert data["total_reviews"] == 5
    assert data["total_comments"] == 5
    assert len(data["recent_prs"]) == 5
    assert len(data["quality_tier_breakdown"]) > 0
    assert len(data["comment_type_breakdown"]) > 0
    assert data["relationship"]["label"] in [
        "mentor", "gatekeeper", "one_way_dependency", "peer", "casual", "rubber_stamp", "none",
    ]
    assert 0 <= data["relationship"]["confidence"] <= 1
    assert data["relationship"]["explanation"]


@pytest.mark.asyncio
async def test_pair_detail_empty(
    client: AsyncClient, sample_admin: Developer, sample_developer: Developer
):
    """No reviews between the pair returns zeroed response."""
    resp = await client.get(
        f"/api/stats/collaboration/pair?reviewer_id={sample_admin.id}&author_id={sample_developer.id}"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_reviews"] == 0
    assert data["relationship"]["label"] == "none"
    assert data["recent_prs"] == []


@pytest.mark.asyncio
async def test_pair_detail_404_unknown_developer(client: AsyncClient):
    resp = await client.get(
        "/api/stats/collaboration/pair?reviewer_id=99999&author_id=99998"
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_pair_detail_requires_admin(
    developer_client: AsyncClient, sample_admin: Developer, sample_developer: Developer
):
    resp = await developer_client.get(
        f"/api/stats/collaboration/pair?reviewer_id={sample_admin.id}&author_id={sample_developer.id}"
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_pair_detail_pr_links_to_github(
    client: AsyncClient, collab_data, sample_admin: Developer, sample_developer: Developer
):
    resp = await client.get(
        f"/api/stats/collaboration/pair?reviewer_id={sample_admin.id}&author_id={sample_developer.id}"
    )
    data = resp.json()
    for pr in data["recent_prs"]:
        assert pr["html_url"].startswith("https://github.com/")
        assert pr["repo_full_name"] == "org/test-repo"
