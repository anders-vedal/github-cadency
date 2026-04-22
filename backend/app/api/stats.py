from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, require_admin
from app.models.database import get_db
from app.models.models import Developer, Repository
from app.schemas.schemas import (
    AppRole,
    AuthUser,
    BenchmarkGroupResponse,
    BenchmarkGroupUpdate,
    BenchmarksV2Response,
    CICheckFailuresResponse,
    CIStatsResponse,
    CodeChurnResponse,
    DORAMetricsResponse,
    CollaborationPairDetail,
    CollaborationResponse,
    CollaborationTrendsResponse,
    DeveloperStatsResponse,
    DeveloperStatsWithPercentilesResponse,
    DeveloperTrendsResponse,
    IssueCreatorStatsResponse,
    IssueLinkageByDeveloper,
    IssueLinkageStats,
    IssueQualityStats,
    RepoStatsResponse,
    RepoSummaryItem,
    RiskAssessment,
    RiskSummaryResponse,
    StalePRsResponse,
    TeamStatsResponse,
    UnassignedRoleCountResponse,
    RecategorizeRequest,
    WorkAllocationItem,
    WorkAllocationItemsResponse,
    WorkAllocationResponse,
    WorkloadResponse,
)
from app.services.collaboration import get_collaboration, get_collaboration_pair_detail, get_collaboration_trends
from app.services.risk import get_pr_risk, get_risk_summary
from app.services.work_categories import load_valid_categories
from app.services.work_category import get_work_allocation, get_work_allocation_items, recategorize_item
from app.services.stats import (
    get_benchmark_groups,
    get_benchmarks_v2,
    update_benchmark_group,
    get_check_failure_details,
    get_ci_stats,
    get_code_churn,
    get_dora_metrics,
    get_developer_stats,
    get_developer_stats_with_percentiles,
    get_developer_trends,
    get_issue_creator_stats,
    get_issue_label_distribution,
    get_issue_linkage_by_developer,
    get_issue_linkage_stats,
    get_issue_quality_stats,
    get_repo_stats,
    get_repos_summary,
    get_stale_prs,
    get_team_stats,
    get_workload,
)

router = APIRouter()


@router.get(
    "/stats/developer/{developer_id}",
    response_model=DeveloperStatsResponse | DeveloperStatsWithPercentilesResponse,
)
async def developer_stats(
    developer_id: int,
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    include_percentiles: bool = Query(False),
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.app_role != AppRole.admin and user.developer_id != developer_id:
        raise HTTPException(status_code=403, detail="Access denied")
    dev = await db.get(Developer, developer_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found")
    if include_percentiles:
        return await get_developer_stats_with_percentiles(
            db, developer_id, date_from, date_to
        )
    return await get_developer_stats(db, developer_id, date_from, date_to)


@router.get("/stats/team", response_model=TeamStatsResponse)
async def team_stats(
    team: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await get_team_stats(db, team, date_from, date_to)


@router.get("/stats/repos/summary", response_model=list[RepoSummaryItem])
async def repos_summary(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    _: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_repos_summary(db, date_from, date_to)


@router.get("/stats/repo/{repo_id}", response_model=RepoStatsResponse)
async def repo_stats(
    repo_id: int,
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    _: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = await db.get(Repository, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return await get_repo_stats(db, repo_id, date_from, date_to)


@router.get("/stats/benchmark-groups", response_model=list[BenchmarkGroupResponse])
async def benchmark_groups(
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await get_benchmark_groups(db)


@router.patch("/stats/benchmark-groups/{group_key}", response_model=BenchmarkGroupResponse)
async def patch_benchmark_group(
    group_key: str,
    update: BenchmarkGroupUpdate,
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await update_benchmark_group(db, group_key, update)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stats/benchmarks", response_model=BenchmarksV2Response)
async def benchmarks(
    group: str | None = Query(None),
    team: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await get_benchmarks_v2(db, group, team, date_from, date_to)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/stats/developer/{developer_id}/trends",
    response_model=DeveloperTrendsResponse,
)
async def developer_trends(
    developer_id: int,
    periods: int = Query(8, ge=2, le=52),
    period_type: str = Query("week"),
    sprint_length_days: int = Query(14, ge=7, le=28),
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.app_role != AppRole.admin and user.developer_id != developer_id:
        raise HTTPException(status_code=403, detail="Access denied")
    dev = await db.get(Developer, developer_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found")
    return await get_developer_trends(
        db, developer_id, periods, period_type, sprint_length_days
    )


@router.get("/stats/collaboration", response_model=CollaborationResponse)
async def collaboration(
    team: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await get_collaboration(db, team, date_from, date_to)


@router.get(
    "/stats/collaboration/trends", response_model=CollaborationTrendsResponse
)
async def collaboration_trends(
    team: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await get_collaboration_trends(db, team, date_from, date_to)


@router.get("/stats/collaboration/pair", response_model=CollaborationPairDetail)
async def collaboration_pair_detail(
    reviewer_id: int = Query(...),
    author_id: int = Query(...),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await get_collaboration_pair_detail(db, reviewer_id, author_id, date_from, date_to)


@router.get("/stats/stale-prs", response_model=StalePRsResponse)
async def stale_prs(
    team: str | None = Query(None),
    threshold_hours: int = Query(24, ge=1, le=720),
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await get_stale_prs(db, team, threshold_hours)


@router.get("/stats/workload", response_model=WorkloadResponse)
async def workload(
    team: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await get_workload(db, team, date_from, date_to)


@router.get("/stats/issue-linkage", response_model=IssueLinkageStats)
async def issue_linkage(
    team: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await get_issue_linkage_stats(db, team, date_from, date_to)


@router.get("/stats/issue-linkage/developers", response_model=IssueLinkageByDeveloper)
async def issue_linkage_by_developer(
    team: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await get_issue_linkage_by_developer(db, team, date_from, date_to)


@router.get("/stats/issues/quality", response_model=IssueQualityStats)
async def issue_quality(
    team: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await get_issue_quality_stats(db, team, date_from, date_to)


@router.get("/stats/issues/labels", response_model=dict[str, int])
async def issue_labels(
    team: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await get_issue_label_distribution(db, team, date_from, date_to)


@router.get("/stats/issues/creators", response_model=IssueCreatorStatsResponse)
async def issue_creator_stats(
    team: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await get_issue_creator_stats(db, team, date_from, date_to)


@router.get("/stats/pr/{pr_id}/risk", response_model=RiskAssessment)
async def pr_risk(
    pr_id: int,
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    assessment = await get_pr_risk(db, pr_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Pull request not found")
    return assessment


@router.get("/stats/risk-summary", response_model=RiskSummaryResponse)
async def risk_summary(
    team: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    min_risk_level: Literal["low", "medium", "high", "critical"] = Query("medium"),
    scope: Literal["all", "open", "merged"] = Query("all"),
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await get_risk_summary(db, team, date_from, date_to, min_risk_level, scope)


@router.get("/stats/repo/{repo_id}/churn", response_model=CodeChurnResponse)
async def code_churn(
    repo_id: int,
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    repo = await db.get(Repository, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return await get_code_churn(db, repo_id, date_from, date_to, limit)


@router.get("/stats/ci", response_model=CIStatsResponse)
async def ci_stats(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    repo_id: int | None = Query(None),
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await get_ci_stats(db, date_from, date_to, repo_id)


@router.get("/stats/ci/check-failures", response_model=CICheckFailuresResponse)
async def ci_check_failures(
    check_name: str = Query(..., min_length=1, max_length=255),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    repo_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await get_check_failure_details(
        db, check_name, date_from, date_to, repo_id, limit
    )


@router.get("/stats/dora", response_model=DORAMetricsResponse)
async def dora_metrics(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    repo_id: int | None = Query(None),
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await get_dora_metrics(db, date_from, date_to, repo_id)


@router.get("/stats/work-allocation", response_model=WorkAllocationResponse)
async def work_allocation(
    team: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    use_ai: bool = Query(False),
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await get_work_allocation(db, team, date_from, date_to, use_ai)


@router.get("/stats/work-allocation/items", response_model=WorkAllocationItemsResponse)
async def work_allocation_items(
    category: str = Query(...),
    type: str = Query("all"),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    valid_cats = await load_valid_categories(db)
    if category not in valid_cats:
        raise HTTPException(status_code=422, detail=f"category must be one of: {', '.join(sorted(valid_cats))}")
    if type not in ("all", "pr", "issue"):
        raise HTTPException(status_code=422, detail="type must be one of: all, pr, issue")
    return await get_work_allocation_items(db, category, type, date_from, date_to, page, page_size)


@router.patch("/stats/work-allocation/items/{item_type}/{item_id}/category", response_model=WorkAllocationItem)
async def recategorize_work_item(
    item_type: str,
    item_id: int,
    body: RecategorizeRequest,
    _: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if item_type not in ("pr", "issue"):
        raise HTTPException(status_code=400, detail="item_type must be 'pr' or 'issue'")
    try:
        return await recategorize_item(db, item_type, item_id, body.category)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
