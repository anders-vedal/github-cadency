"""Unit tests for DORA metrics (P4-01 + P1-01 CFR/MTTR)."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Deployment, PullRequest, Repository
from app.services.stats import (
    _cfr_band,
    _deploy_frequency_band,
    _lead_time_band,
    _mttr_band,
    _overall_dora_band,
    get_dora_metrics,
)
from app.services.github_sync import detect_deployment_failures


NOW = datetime.now(timezone.utc)
ONE_WEEK_AGO = NOW - timedelta(days=7)
TWO_WEEKS_AGO = NOW - timedelta(days=14)


@pytest_asyncio.fixture
async def dora_repo(db_session: AsyncSession) -> Repository:
    repo = Repository(
        github_id=88888,
        name="dora-repo",
        full_name="org/dora-repo",
        is_tracked=True,
        default_branch="main",
        created_at=NOW,
    )
    db_session.add(repo)
    await db_session.commit()
    await db_session.refresh(repo)
    return repo


# ---------------------------------------------------------------------------
# Band classification tests
# ---------------------------------------------------------------------------


class TestDeployFrequencyBand:
    def test_elite(self):
        assert _deploy_frequency_band(2.0) == "elite"

    def test_high(self):
        assert _deploy_frequency_band(0.5) == "high"

    def test_medium(self):
        assert _deploy_frequency_band(0.1) == "medium"

    def test_low(self):
        assert _deploy_frequency_band(0.01) == "low"

    def test_boundary_elite(self):
        """Exactly 1/day is not elite (need >1)."""
        assert _deploy_frequency_band(1.0) == "high"

    def test_boundary_high(self):
        """Exactly 1/week (1/7) is high."""
        assert _deploy_frequency_band(1 / 7) == "high"

    def test_boundary_medium(self):
        """Exactly 1/month (1/30) is medium."""
        assert _deploy_frequency_band(1 / 30) == "medium"


class TestLeadTimeBand:
    def test_elite(self):
        assert _lead_time_band(0.5) == "elite"

    def test_high(self):
        assert _lead_time_band(12.0) == "high"

    def test_medium(self):
        assert _lead_time_band(72.0) == "medium"

    def test_low(self):
        assert _lead_time_band(200.0) == "low"

    def test_boundary_elite(self):
        """Exactly 1 hour is high, not elite."""
        assert _lead_time_band(1.0) == "high"

    def test_boundary_high(self):
        """Exactly 24 hours is medium, not high."""
        assert _lead_time_band(24.0) == "medium"

    def test_boundary_medium(self):
        """Exactly 168 hours (7 days) is low, not medium."""
        assert _lead_time_band(168.0) == "low"


# ---------------------------------------------------------------------------
# get_dora_metrics tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_returns_defaults(db_session: AsyncSession):
    """No deployments should return zero-value defaults."""
    result = await get_dora_metrics(db_session, TWO_WEEKS_AGO, NOW)
    assert result.total_deployments == 0
    assert result.deploy_frequency == 0.0
    assert result.deploy_frequency_band == "low"
    assert result.avg_lead_time_hours is None
    assert result.deployments == []


@pytest.mark.asyncio
async def test_deploy_frequency(
    db_session: AsyncSession, dora_repo: Repository
):
    """Deploy frequency should be total_deploys / period_days."""
    # 3 deployments over 7 days
    for i in range(3):
        db_session.add(Deployment(
            repo_id=dora_repo.id,
            workflow_run_id=1000 + i,
            environment="production",
            status="success",
            deployed_at=NOW - timedelta(days=i * 2),
            workflow_name="deploy",
            sha=f"{'a' * 39}{i}",
        ))
    await db_session.commit()

    result = await get_dora_metrics(db_session, ONE_WEEK_AGO, NOW)
    assert result.total_deployments == 3
    assert result.deploy_frequency == round(3 / 7, 3)
    assert result.period_days == 7


@pytest.mark.asyncio
async def test_lead_time_computed(
    db_session: AsyncSession, dora_repo: Repository
):
    """Deployments with lead_time_s should produce avg_lead_time_hours."""
    db_session.add(Deployment(
        repo_id=dora_repo.id,
        workflow_run_id=2001,
        environment="production",
        status="success",
        deployed_at=NOW - timedelta(days=1),
        lead_time_s=7200,  # 2 hours
        workflow_name="deploy",
    ))
    db_session.add(Deployment(
        repo_id=dora_repo.id,
        workflow_run_id=2002,
        environment="production",
        status="success",
        deployed_at=NOW - timedelta(days=3),
        lead_time_s=14400,  # 4 hours
        workflow_name="deploy",
    ))
    await db_session.commit()

    result = await get_dora_metrics(db_session, ONE_WEEK_AGO, NOW)
    assert result.avg_lead_time_hours == 3.0  # (2+4)/2
    assert result.lead_time_band == "high"  # <24h


@pytest.mark.asyncio
async def test_failed_deployments_excluded_from_count(
    db_session: AsyncSession, dora_repo: Repository
):
    """Only successful deployments count toward frequency."""
    db_session.add(Deployment(
        repo_id=dora_repo.id,
        workflow_run_id=3001,
        status="success",
        deployed_at=NOW - timedelta(days=1),
        workflow_name="deploy",
    ))
    db_session.add(Deployment(
        repo_id=dora_repo.id,
        workflow_run_id=3002,
        status="failure",
        deployed_at=NOW - timedelta(days=2),
        workflow_name="deploy",
    ))
    await db_session.commit()

    result = await get_dora_metrics(db_session, ONE_WEEK_AGO, NOW)
    assert result.total_deployments == 1


@pytest.mark.asyncio
async def test_repo_filter(
    db_session: AsyncSession, dora_repo: Repository
):
    """Filtering by repo_id should scope results."""
    db_session.add(Deployment(
        repo_id=dora_repo.id,
        workflow_run_id=4001,
        status="success",
        deployed_at=NOW - timedelta(days=1),
        workflow_name="deploy",
    ))
    await db_session.commit()

    # Matching repo
    result = await get_dora_metrics(db_session, ONE_WEEK_AGO, NOW, repo_id=dora_repo.id)
    assert result.total_deployments == 1

    # Non-existent repo
    result_empty = await get_dora_metrics(db_session, ONE_WEEK_AGO, NOW, repo_id=99999)
    assert result_empty.total_deployments == 0


@pytest.mark.asyncio
async def test_date_range_filtering(
    db_session: AsyncSession, dora_repo: Repository
):
    """Deployments outside date range should be excluded."""
    db_session.add(Deployment(
        repo_id=dora_repo.id,
        workflow_run_id=5001,
        status="success",
        deployed_at=NOW - timedelta(days=60),
        workflow_name="deploy",
    ))
    await db_session.commit()

    result = await get_dora_metrics(db_session, ONE_WEEK_AGO, NOW)
    assert result.total_deployments == 0


@pytest.mark.asyncio
async def test_deployments_list_limited_to_20(
    db_session: AsyncSession, dora_repo: Repository
):
    """Recent deployments list should be capped at 20."""
    for i in range(25):
        db_session.add(Deployment(
            repo_id=dora_repo.id,
            workflow_run_id=6000 + i,
            status="success",
            deployed_at=NOW - timedelta(hours=i),
            workflow_name="deploy",
        ))
    await db_session.commit()

    result = await get_dora_metrics(db_session, ONE_WEEK_AGO, NOW)
    assert len(result.deployments) == 20
    assert result.total_deployments == 25


@pytest.mark.asyncio
async def test_deployment_detail_fields(
    db_session: AsyncSession, dora_repo: Repository
):
    """Deployment detail should include repo_name and lead_time_hours."""
    db_session.add(Deployment(
        repo_id=dora_repo.id,
        workflow_run_id=7001,
        environment="production",
        status="success",
        sha="a" * 40,
        deployed_at=NOW - timedelta(days=1),
        workflow_name="deploy-prod",
        lead_time_s=3600,
    ))
    await db_session.commit()

    result = await get_dora_metrics(db_session, ONE_WEEK_AGO, NOW)
    assert len(result.deployments) == 1
    d = result.deployments[0]
    assert d.repo_name == "org/dora-repo"
    assert d.environment == "production"
    assert d.workflow_name == "deploy-prod"
    assert d.lead_time_hours == 1.0
    assert d.sha == "a" * 40


# ---------------------------------------------------------------------------
# CFR / MTTR band classification tests (P1-01)
# ---------------------------------------------------------------------------


class TestCFRBand:
    def test_elite(self):
        assert _cfr_band(3.0) == "elite"

    def test_high(self):
        assert _cfr_band(10.0) == "high"

    def test_medium(self):
        assert _cfr_band(30.0) == "medium"

    def test_low(self):
        assert _cfr_band(50.0) == "low"

    def test_boundary_elite(self):
        assert _cfr_band(5.0) == "high"

    def test_boundary_high(self):
        assert _cfr_band(15.0) == "medium"

    def test_boundary_medium(self):
        assert _cfr_band(45.0) == "low"

    def test_zero(self):
        assert _cfr_band(0.0) == "elite"


class TestMTTRBand:
    def test_elite(self):
        assert _mttr_band(0.5) == "elite"

    def test_high(self):
        assert _mttr_band(12.0) == "high"

    def test_medium(self):
        assert _mttr_band(72.0) == "medium"

    def test_low(self):
        assert _mttr_band(200.0) == "low"

    def test_boundary_elite(self):
        assert _mttr_band(1.0) == "high"

    def test_boundary_high(self):
        assert _mttr_band(24.0) == "medium"


class TestOverallDORABand:
    def test_all_elite(self):
        assert _overall_dora_band("elite", "elite", "elite", "elite") == "elite"

    def test_one_low(self):
        assert _overall_dora_band("elite", "high", "elite", "low") == "low"

    def test_mixed(self):
        assert _overall_dora_band("elite", "high", "medium", "high") == "medium"

    def test_all_low(self):
        assert _overall_dora_band("low", "low", "low", "low") == "low"


# ---------------------------------------------------------------------------
# detect_deployment_failures tests (P1-01)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_failure_from_failed_workflow(
    db_session: AsyncSession, dora_repo: Repository
):
    """Workflow runs with non-success conclusion should be flagged as failures."""
    dep_fail = Deployment(
        repo_id=dora_repo.id,
        workflow_run_id=8001,
        status="failure",
        deployed_at=NOW - timedelta(days=2),
        workflow_name="deploy",
    )
    dep_success = Deployment(
        repo_id=dora_repo.id,
        workflow_run_id=8002,
        status="success",
        deployed_at=NOW - timedelta(days=1),
        workflow_name="deploy",
    )
    db_session.add_all([dep_fail, dep_success])
    await db_session.commit()

    await detect_deployment_failures(db_session, dora_repo)
    await db_session.refresh(dep_fail)
    await db_session.refresh(dep_success)

    assert dep_fail.is_failure is True
    assert dep_fail.failure_detected_via == "failed_deploy"
    assert dep_fail.recovery_deployment_id == dep_success.id
    assert dep_fail.recovery_time_s is not None
    assert dep_success.is_failure is False


@pytest.mark.asyncio
async def test_detect_failure_from_revert_pr(
    db_session: AsyncSession, dora_repo: Repository
):
    """A revert PR merged within 48h after a deployment should flag that deployment."""
    dep = Deployment(
        repo_id=dora_repo.id,
        workflow_run_id=9001,
        status="success",
        deployed_at=NOW - timedelta(days=2),
        workflow_name="deploy",
    )
    db_session.add(dep)
    await db_session.flush()

    # Revert PR merged 1 hour after deployment
    revert_pr = PullRequest(
        github_id=90001,
        repo_id=dora_repo.id,
        number=101,
        title='Revert "Some feature"',
        state="closed",
        is_merged=True,
        is_revert=True,
        merged_at=dep.deployed_at + timedelta(hours=1),
        created_at=dep.deployed_at + timedelta(minutes=30),
    )
    db_session.add(revert_pr)
    await db_session.commit()

    await detect_deployment_failures(db_session, dora_repo)
    await db_session.refresh(dep)

    assert dep.is_failure is True
    assert dep.failure_detected_via == "revert_pr"


@pytest.mark.asyncio
async def test_detect_failure_from_hotfix_pr(
    db_session: AsyncSession, dora_repo: Repository
):
    """A hotfix PR (by branch prefix) merged after deployment should flag failure."""
    dep = Deployment(
        repo_id=dora_repo.id,
        workflow_run_id=9101,
        status="success",
        deployed_at=NOW - timedelta(days=2),
        workflow_name="deploy",
    )
    db_session.add(dep)
    await db_session.flush()

    hotfix_pr = PullRequest(
        github_id=91001,
        repo_id=dora_repo.id,
        number=201,
        title="Fix critical login issue",
        head_branch="hotfix/login-crash",
        state="closed",
        is_merged=True,
        is_revert=False,
        merged_at=dep.deployed_at + timedelta(hours=3),
        created_at=dep.deployed_at + timedelta(hours=2),
    )
    db_session.add(hotfix_pr)
    await db_session.commit()

    await detect_deployment_failures(db_session, dora_repo)
    await db_session.refresh(dep)

    assert dep.is_failure is True
    assert dep.failure_detected_via == "hotfix_pr"


@pytest.mark.asyncio
async def test_detect_failure_from_hotfix_label(
    db_session: AsyncSession, dora_repo: Repository
):
    """A PR with a hotfix label merged after deployment should flag failure."""
    dep = Deployment(
        repo_id=dora_repo.id,
        workflow_run_id=9201,
        status="success",
        deployed_at=NOW - timedelta(days=2),
        workflow_name="deploy",
    )
    db_session.add(dep)
    await db_session.flush()

    hotfix_pr = PullRequest(
        github_id=92001,
        repo_id=dora_repo.id,
        number=301,
        title="Emergency database fix",
        head_branch="feature/db-fix",
        state="closed",
        is_merged=True,
        is_revert=False,
        labels=[{"name": "urgent"}],
        merged_at=dep.deployed_at + timedelta(hours=5),
        created_at=dep.deployed_at + timedelta(hours=4),
    )
    db_session.add(hotfix_pr)
    await db_session.commit()

    await detect_deployment_failures(db_session, dora_repo)
    await db_session.refresh(dep)

    assert dep.is_failure is True
    assert dep.failure_detected_via == "hotfix_pr"


@pytest.mark.asyncio
async def test_no_failures_detected(
    db_session: AsyncSession, dora_repo: Repository
):
    """When there are no failure signals, deployments should remain clean."""
    for i in range(3):
        db_session.add(Deployment(
            repo_id=dora_repo.id,
            workflow_run_id=9300 + i,
            status="success",
            deployed_at=NOW - timedelta(days=i + 1),
            workflow_name="deploy",
        ))
    await db_session.commit()

    await detect_deployment_failures(db_session, dora_repo)

    result = await get_dora_metrics(db_session, TWO_WEEKS_AGO, NOW)
    assert result.failure_deployments == 0
    assert result.change_failure_rate == 0.0


@pytest.mark.asyncio
async def test_cfr_and_mttr_computation(
    db_session: AsyncSession, dora_repo: Repository
):
    """CFR and MTTR should be computed from failure data."""
    # 3 total deployments: 1 failure + 2 success
    dep_ok1 = Deployment(
        repo_id=dora_repo.id,
        workflow_run_id=9401,
        status="success",
        deployed_at=NOW - timedelta(days=5),
        workflow_name="deploy",
    )
    dep_fail = Deployment(
        repo_id=dora_repo.id,
        workflow_run_id=9402,
        status="failure",
        deployed_at=NOW - timedelta(days=3),
        workflow_name="deploy",
    )
    dep_ok2 = Deployment(
        repo_id=dora_repo.id,
        workflow_run_id=9403,
        status="success",
        deployed_at=NOW - timedelta(days=1),
        workflow_name="deploy",
    )
    db_session.add_all([dep_ok1, dep_fail, dep_ok2])
    await db_session.commit()

    await detect_deployment_failures(db_session, dora_repo)

    result = await get_dora_metrics(db_session, TWO_WEEKS_AGO, NOW)
    assert result.failure_deployments == 1
    # CFR = 1/3 * 100 = 33.33%
    assert result.change_failure_rate == pytest.approx(33.33, abs=0.1)
    assert result.cfr_band == "medium"
    # MTTR should be ~2 days (failure at day 3, recovery at day 1)
    assert result.avg_mttr_hours is not None
    assert result.avg_mttr_hours > 0
    assert result.overall_band is not None


@pytest.mark.asyncio
async def test_failure_without_recovery(
    db_session: AsyncSession, dora_repo: Repository
):
    """A failure with no subsequent success should have no recovery time."""
    dep = Deployment(
        repo_id=dora_repo.id,
        workflow_run_id=9501,
        status="failure",
        deployed_at=NOW - timedelta(days=1),
        workflow_name="deploy",
    )
    db_session.add(dep)
    await db_session.commit()

    await detect_deployment_failures(db_session, dora_repo)
    await db_session.refresh(dep)

    assert dep.is_failure is True
    assert dep.recovered_at is None
    assert dep.recovery_time_s is None

    result = await get_dora_metrics(db_session, TWO_WEEKS_AGO, NOW)
    assert result.failure_deployments == 1
    assert result.avg_mttr_hours is None
