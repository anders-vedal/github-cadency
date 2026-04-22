"""Phase 10 — AI cohort classification tests."""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import PRReview, PullRequest, Repository
from app.services.ai_cohort import (
    AIDetectionRules,
    classify_ai_cohort,
    classify_ai_cohorts_batch,
    default_rules,
)


@pytest_asyncio.fixture
async def repo(db_session: AsyncSession) -> Repository:
    r = Repository(name="r", full_name="acme/r", github_id=5)
    db_session.add(r)
    await db_session.commit()
    await db_session.refresh(r)
    return r


async def _make_pr(
    db: AsyncSession,
    repo: Repository,
    number: int,
    *,
    labels: list[str] | None = None,
) -> PullRequest:
    pr = PullRequest(
        github_id=90_000 + number,
        repo_id=repo.id,
        number=number,
        title=f"PR {number}",
        state="merged",
        is_merged=True,
        labels=labels or [],
        head_branch="x",
        base_branch="main",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(pr)
    await db.commit()
    await db.refresh(pr)
    return pr


async def _add_review(db: AsyncSession, pr: PullRequest, reviewer: str) -> None:
    db.add(
        PRReview(
            pr_id=pr.id,
            github_id=pr.github_id * 10 + hash(reviewer) % 1000,
            reviewer_github_username=reviewer,
            state="approved",
            submitted_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()


@pytest.mark.asyncio
async def test_human_pr(db_session: AsyncSession, repo: Repository):
    pr = await _make_pr(db_session, repo, 1)
    await _add_review(db_session, pr, "alice")
    cohort = await classify_ai_cohort(db_session, pr)
    assert cohort == "human"


@pytest.mark.asyncio
async def test_ai_reviewed_by_copilot(db_session: AsyncSession, repo: Repository):
    pr = await _make_pr(db_session, repo, 2)
    await _add_review(db_session, pr, "github-copilot[bot]")
    cohort = await classify_ai_cohort(db_session, pr)
    assert cohort == "ai_reviewed"


@pytest.mark.asyncio
async def test_ai_authored_by_label(db_session: AsyncSession, repo: Repository):
    pr = await _make_pr(db_session, repo, 3, labels=["ai-authored", "bug"])
    await _add_review(db_session, pr, "alice")
    cohort = await classify_ai_cohort(db_session, pr)
    assert cohort == "ai_authored"


@pytest.mark.asyncio
async def test_hybrid(db_session: AsyncSession, repo: Repository):
    pr = await _make_pr(db_session, repo, 4, labels=["copilot"])
    await _add_review(db_session, pr, "claude[bot]")
    cohort = await classify_ai_cohort(db_session, pr)
    assert cohort == "hybrid"


@pytest.mark.asyncio
async def test_batch_classification(db_session: AsyncSession, repo: Repository):
    pr1 = await _make_pr(db_session, repo, 10)
    await _add_review(db_session, pr1, "alice")

    pr2 = await _make_pr(db_session, repo, 11)
    await _add_review(db_session, pr2, "github-copilot[bot]")

    pr3 = await _make_pr(db_session, repo, 12, labels=["ai-authored"])
    await _add_review(db_session, pr3, "bob")

    result = await classify_ai_cohorts_batch(db_session, [pr1.id, pr2.id, pr3.id])
    assert result[pr1.id] == "human"
    assert result[pr2.id] == "ai_reviewed"
    assert result[pr3.id] == "ai_authored"


def test_default_rules_populated():
    r = default_rules()
    assert "github-copilot[bot]" in r.reviewer_usernames
    assert "ai-authored" in r.author_labels
