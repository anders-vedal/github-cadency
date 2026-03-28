"""
Shared test fixtures for the DevPulse backend test suite.

Uses SQLite (aiosqlite) in-memory for tests to avoid requiring PostgreSQL.
JSONB columns are compiled as JSON for SQLite compatibility.
"""
import os

# Set test env vars before importing app modules
os.environ.setdefault("DEVPULSE_ADMIN_TOKEN", "test-token-123")
os.environ.setdefault("GITHUB_WEBHOOK_SECRET", "test-webhook-secret")

import pytest_asyncio
from datetime import datetime, timedelta, timezone

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Patch JSONB → JSON for SQLite before importing models
import sqlalchemy.dialects.sqlite.base as sqlite_base

sqlite_base.SQLiteTypeCompiler.visit_JSONB = sqlite_base.SQLiteTypeCompiler.visit_JSON

from app.api.auth import require_auth
from app.main import app
from app.models.database import Base, get_db
from app.models.models import (
    Developer,
    Issue,
    IssueComment,
    PRReview,
    PRReviewComment,
    PullRequest,
    Repository,
    SyncEvent,
)

TEST_TOKEN = "test-token-123"
WEBHOOK_SECRET = "test-webhook-secret"


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(engine):
    """HTTP client with auth bypassed — for standard API tests."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    async def override_auth():
        return TEST_TOKEN

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_auth] = override_auth

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def raw_client(engine):
    """HTTP client WITHOUT auth bypass — for testing auth behavior."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    # Do NOT override require_auth

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# --- Data factory fixtures ---

NOW = datetime.now(timezone.utc)
ONE_DAY_AGO = NOW - timedelta(days=1)
ONE_WEEK_AGO = NOW - timedelta(days=7)


@pytest_asyncio.fixture
async def sample_developer(db_session: AsyncSession) -> Developer:
    dev = Developer(
        github_username="testuser",
        display_name="Test User",
        email="test@example.com",
        role="developer",
        team="backend",
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )
    db_session.add(dev)
    await db_session.commit()
    await db_session.refresh(dev)
    return dev


@pytest_asyncio.fixture
async def sample_developer_b(db_session: AsyncSession) -> Developer:
    dev = Developer(
        github_username="testuser2",
        display_name="Test User 2",
        email="test2@example.com",
        role="senior_developer",
        team="backend",
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )
    db_session.add(dev)
    await db_session.commit()
    await db_session.refresh(dev)
    return dev


@pytest_asyncio.fixture
async def sample_repo(db_session: AsyncSession) -> Repository:
    repo = Repository(
        github_id=12345,
        name="test-repo",
        full_name="org/test-repo",
        description="A test repository",
        language="Python",
        is_tracked=True,
        created_at=NOW,
    )
    db_session.add(repo)
    await db_session.commit()
    await db_session.refresh(repo)
    return repo


@pytest_asyncio.fixture
async def sample_pr(
    db_session: AsyncSession,
    sample_developer: Developer,
    sample_repo: Repository,
) -> PullRequest:
    pr = PullRequest(
        github_id=100,
        repo_id=sample_repo.id,
        author_id=sample_developer.id,
        number=1,
        title="Fix bug",
        body="Fixes a critical bug",
        state="closed",
        is_merged=True,
        additions=50,
        deletions=10,
        changed_files=3,
        created_at=ONE_WEEK_AGO,
        merged_at=ONE_DAY_AGO,
        time_to_merge_s=int((ONE_DAY_AGO - ONE_WEEK_AGO).total_seconds()),
    )
    db_session.add(pr)
    await db_session.commit()
    await db_session.refresh(pr)
    return pr


@pytest_asyncio.fixture
async def sample_review(
    db_session: AsyncSession,
    sample_pr: PullRequest,
    sample_developer_b: Developer,
) -> PRReview:
    submitted = ONE_DAY_AGO - timedelta(hours=2)
    review = PRReview(
        github_id=200,
        pr_id=sample_pr.id,
        reviewer_id=sample_developer_b.id,
        state="APPROVED",
        body="Looks good, nice fix!",
        body_length=21,
        quality_tier="minimal",
        submitted_at=submitted,
    )
    db_session.add(review)

    # Update PR first_review_at — compute delta before SQLite strips tzinfo
    sample_pr.first_review_at = submitted
    sample_pr.time_to_first_review_s = int(
        (submitted - ONE_WEEK_AGO).total_seconds()
    )

    await db_session.commit()
    await db_session.refresh(review)
    return review


@pytest_asyncio.fixture
async def sample_issue(
    db_session: AsyncSession,
    sample_developer: Developer,
    sample_repo: Repository,
) -> Issue:
    issue = Issue(
        github_id=300,
        repo_id=sample_repo.id,
        assignee_id=sample_developer.id,
        number=10,
        title="Bug report",
        body="Something is broken",
        state="closed",
        labels=["bug"],
        created_at=ONE_WEEK_AGO,
        closed_at=ONE_DAY_AGO,
        time_to_close_s=int((ONE_DAY_AGO - ONE_WEEK_AGO).total_seconds()),
    )
    db_session.add(issue)
    await db_session.commit()
    await db_session.refresh(issue)
    return issue
