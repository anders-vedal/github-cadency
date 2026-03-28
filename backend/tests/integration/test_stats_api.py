"""Integration tests for the /api/stats endpoints."""
import pytest

from app.models.models import Developer


class TestDeveloperStats:
    @pytest.mark.asyncio
    async def test_developer_stats_with_data(
        self, client, sample_developer, sample_pr, sample_review, sample_issue
    ):
        resp = await client.get(f"/api/stats/developer/{sample_developer.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["prs_merged"] == 1
        assert data["prs_opened"] == 1
        assert data["total_additions"] == 50
        assert data["total_deletions"] == 10
        assert data["total_changed_files"] == 3
        assert data["issues_closed"] == 1

    @pytest.mark.asyncio
    async def test_developer_stats_empty(self, client, sample_developer):
        resp = await client.get(f"/api/stats/developer/{sample_developer.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["prs_merged"] == 0
        assert data["prs_opened"] == 0

    @pytest.mark.asyncio
    async def test_developer_stats_not_found(self, client):
        resp = await client.get("/api/stats/developer/999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_developer_stats_reviews_given(
        self, client, sample_developer_b, sample_review
    ):
        resp = await client.get(f"/api/stats/developer/{sample_developer_b.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["reviews_given"]["approved"] == 1

    @pytest.mark.asyncio
    async def test_developer_stats_with_percentiles(
        self, client, sample_developer, sample_developer_b, sample_pr
    ):
        resp = await client.get(
            f"/api/stats/developer/{sample_developer.id}?include_percentiles=true"
        )
        assert resp.status_code == 200
        data = resp.json()
        # With 2 devs, percentiles should be computed
        assert "percentiles" in data


class TestTeamStats:
    @pytest.mark.asyncio
    async def test_team_stats_empty(self, client):
        resp = await client.get("/api/stats/team")
        assert resp.status_code == 200
        assert resp.json()["developer_count"] == 0

    @pytest.mark.asyncio
    async def test_team_stats_with_data(
        self, client, sample_developer, sample_pr, sample_review
    ):
        resp = await client.get("/api/stats/team")
        assert resp.status_code == 200
        data = resp.json()
        assert data["developer_count"] >= 1
        assert data["total_prs"] >= 1
        assert data["total_merged"] >= 1

    @pytest.mark.asyncio
    async def test_team_stats_filter_by_team(
        self, client, sample_developer, sample_pr
    ):
        resp = await client.get("/api/stats/team?team=backend")
        data = resp.json()
        assert data["developer_count"] >= 1

        resp = await client.get("/api/stats/team?team=nonexistent")
        data = resp.json()
        assert data["developer_count"] == 0


class TestRepoStats:
    @pytest.mark.asyncio
    async def test_repo_stats_with_data(
        self, client, sample_repo, sample_pr, sample_review, sample_issue
    ):
        resp = await client.get(f"/api/stats/repo/{sample_repo.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_prs"] >= 1
        assert data["total_merged"] >= 1
        assert data["total_issues"] >= 1
        assert data["total_reviews"] >= 1

    @pytest.mark.asyncio
    async def test_repo_stats_not_found(self, client):
        resp = await client.get("/api/stats/repo/999")
        assert resp.status_code == 404


class TestBenchmarks:
    @pytest.mark.asyncio
    async def test_benchmarks_empty(self, client):
        resp = await client.get("/api/stats/benchmarks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sample_size"] == 0
        assert data["metrics"] == {}

    @pytest.mark.asyncio
    async def test_benchmarks_with_data(
        self, client, sample_developer, sample_developer_b, sample_pr
    ):
        resp = await client.get("/api/stats/benchmarks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sample_size"] == 2
        assert "prs_merged" in data["metrics"]
        assert "p25" in data["metrics"]["prs_merged"]


class TestTrends:
    @pytest.mark.asyncio
    async def test_developer_trends(self, client, sample_developer, sample_pr):
        resp = await client.get(
            f"/api/stats/developer/{sample_developer.id}/trends?periods=4"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["developer_id"] == sample_developer.id
        assert len(data["periods"]) == 4
        assert "trends" in data
        assert "prs_merged" in data["trends"]

    @pytest.mark.asyncio
    async def test_trends_not_found(self, client):
        resp = await client.get("/api/stats/developer/999/trends")
        assert resp.status_code == 404


class TestCollaboration:
    @pytest.mark.asyncio
    async def test_collaboration_empty(self, client):
        resp = await client.get("/api/stats/collaboration")
        assert resp.status_code == 200
        data = resp.json()
        assert data["matrix"] == []

    @pytest.mark.asyncio
    async def test_collaboration_with_reviews(
        self, client, sample_developer, sample_developer_b, sample_pr, sample_review
    ):
        resp = await client.get("/api/stats/collaboration")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["matrix"]) >= 1
        assert "insights" in data


class TestWorkload:
    @pytest.mark.asyncio
    async def test_workload_empty(self, client):
        resp = await client.get("/api/stats/workload")
        assert resp.status_code == 200
        data = resp.json()
        assert data["developers"] == []

    @pytest.mark.asyncio
    async def test_workload_with_data(
        self, client, sample_developer, sample_pr
    ):
        resp = await client.get("/api/stats/workload")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["developers"]) >= 1
        assert "alerts" in data
