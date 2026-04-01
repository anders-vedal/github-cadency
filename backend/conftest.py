"""
Shared test fixtures for the DevPulse backend test suite.

Uses SQLite (aiosqlite) in-memory for tests to avoid requiring PostgreSQL.
JSONB columns are compiled as JSON for SQLite compatibility.
"""
import os

# Set test env vars before importing app modules
os.environ.setdefault("GITHUB_WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-testing-only!!")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("ENCRYPTION_KEY", "HViiPG4E1XXNkvkcJGrWinBJiegO2KKYy5fuwUg1U-s=")

import pytest_asyncio
from datetime import datetime, timedelta, timezone

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Patch JSONB → JSON for SQLite before importing models
import sqlalchemy.dialects.sqlite.base as sqlite_base

sqlite_base.SQLiteTypeCompiler.visit_JSONB = sqlite_base.SQLiteTypeCompiler.visit_JSON

from app.api.auth import create_jwt, get_current_user
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
    RoleDefinition,
    SyncEvent,
    Team,
    WorkCategory,
    WorkCategoryRule,
)
from app.schemas.schemas import AuthUser

WEBHOOK_SECRET = "test-webhook-secret"


def make_admin_token(developer_id: int = 1, github_username: str = "admin") -> str:
    return create_jwt(developer_id, github_username, "admin")


def make_developer_token(developer_id: int = 2, github_username: str = "testuser") -> str:
    return create_jwt(developer_id, github_username, "developer")


DEFAULT_ROLES = [
    ("developer", "Developer", "code_contributor", 1),
    ("senior_developer", "Senior Developer", "code_contributor", 2),
    ("lead", "Engineering Lead", "code_contributor", 3),
    ("architect", "Architect", "code_contributor", 4),
    ("devops", "DevOps Engineer", "code_contributor", 5),
    ("senior_devops", "Senior DevOps Engineer", "code_contributor", 6),
    ("qa", "QA Engineer", "code_contributor", 7),
    ("intern", "Intern", "code_contributor", 8),
    ("product_manager", "Product Manager", "issue_contributor", 9),
    ("product_owner", "Product Owner", "issue_contributor", 10),
    ("engineering_manager", "Engineering Manager", "issue_contributor", 11),
    ("scrum_master", "Scrum Master", "issue_contributor", 12),
    ("designer", "Designer", "non_contributor", 13),
    ("other", "Other", "non_contributor", 14),
    ("system_account", "System Account", "system", 15),
]

DEFAULT_TEAMS = [
    ("platform", 1),
    ("backend", 2),
]

DEFAULT_WORK_CATEGORIES = [
    ("feature", "Feature", "#3b82f6", False, 1, "New functionality or enhancements that add user-facing value."),
    ("bugfix", "Bug Fix", "#ef4444", False, 2, "Fixes for defects, regressions, or incorrect behavior."),
    ("tech_debt", "Tech Debt", "#f59e0b", False, 3, "Refactoring, dependency updates, code cleanup, and internal improvements."),
    ("ops", "Ops", "#22c55e", False, 4, "Infrastructure, CI/CD, deployment, monitoring, and documentation changes."),
    ("unknown", "Unknown", "#94a3b8", False, 5, "Items that could not be automatically classified by any rule."),
]

DEFAULT_WORK_CATEGORY_RULES = [
    # Label rules
    ("label", "feature", "feature", 1),
    ("label", "enhancement", "feature", 2),
    ("label", "bug", "bugfix", 10),
    ("label", "bugfix", "bugfix", 11),
    ("label", "fix", "bugfix", 12),
    ("label", "hotfix", "bugfix", 14),
    ("label", "refactor", "tech_debt", 22),
    ("label", "chore", "tech_debt", 25),
    ("label", "deps", "tech_debt", 28),
    ("label", "ci", "ops", 33),
    ("label", "docs", "ops", 41),
    # Title regex rules
    ("title_regex", r"\bfix(?:es|ed)?\b|\bbug\b|\bhotfix\b|\bregression\b", "bugfix", 100),
    ("title_regex", r"\bfeat(?:ure)?\b|\badd(?:s|ed)?\s", "feature", 101),
    ("title_regex", r"\brefactor\b|\bcleanup\b|\btech.?debt\b|\bchore\b|\bdeps?\b|\bbump\b", "tech_debt", 102),
    ("title_regex", r"\bci\b|\bcd\b|\bdeploy\b|\binfra\b|\bconfig\b|\bdocs?\b|\bmonitoring\b", "ops", 103),
]


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed role definitions and teams (mirrors migration 027+029 seed data)
    factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        for role_key, display_name, category, order in DEFAULT_ROLES:
            session.add(RoleDefinition(
                role_key=role_key,
                display_name=display_name,
                contribution_category=category,
                display_order=order,
                is_default=True,
            ))
        for team_name, order in DEFAULT_TEAMS:
            session.add(Team(name=team_name, display_order=order))
        for key, name, color, excluded, order, desc in DEFAULT_WORK_CATEGORIES:
            session.add(WorkCategory(
                category_key=key, display_name=name, description=desc, color=color,
                exclude_from_stats=excluded, display_order=order, is_default=True,
            ))
        for match_type, match_value, cat_key, priority in DEFAULT_WORK_CATEGORY_RULES:
            session.add(WorkCategoryRule(
                match_type=match_type, match_value=match_value,
                case_sensitive=False, category_key=cat_key, priority=priority,
            ))
        await session.commit()

    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(engine, sample_admin):
    """HTTP client authenticated as admin — for standard API tests."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    token = make_admin_token(developer_id=sample_admin.id, github_username=sample_admin.github_username)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def developer_client(engine, sample_developer):
    """HTTP client authenticated as a regular developer."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    token = make_developer_token(developer_id=sample_developer.id, github_username=sample_developer.github_username)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def raw_client(engine):
    """HTTP client WITHOUT auth — for testing auth behavior."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# --- Data factory fixtures ---

NOW = datetime.now(timezone.utc)
ONE_DAY_AGO = NOW - timedelta(days=1)
ONE_WEEK_AGO = NOW - timedelta(days=7)


@pytest_asyncio.fixture
async def sample_admin(db_session: AsyncSession) -> Developer:
    dev = Developer(
        github_username="admin",
        display_name="Admin User",
        email="admin@example.com",
        role="lead",
        team="platform",
        app_role="admin",
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )
    db_session.add(dev)
    await db_session.commit()
    await db_session.refresh(dev)
    return dev


@pytest_asyncio.fixture
async def sample_developer(db_session: AsyncSession) -> Developer:
    dev = Developer(
        github_username="testuser",
        display_name="Test User",
        email="test@example.com",
        role="developer",
        team="backend",
        app_role="developer",
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
        app_role="developer",
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
        labels=["bug"],
        merged_by_username="reviewer",
        head_branch="fix/critical-bug",
        base_branch="main",
        is_self_merged=False,
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
