"""Integration tests for per-developer issue linkage stats."""
import pytest
from datetime import timedelta

from app.models.models import Developer, PullRequest

from conftest import NOW, ONE_WEEK_AGO


class TestIssueLinkageByDeveloper:
    @pytest.mark.asyncio
    async def test_linkage_by_developer_basic(
        self, client, sample_developer, sample_repo, db_session
    ):
        """Test per-developer linkage with mixed linked/unlinked PRs."""
        # Create a PR linked to an issue
        pr_linked = PullRequest(
            github_id=501,
            repo_id=sample_repo.id,
            author_id=sample_developer.id,
            number=10,
            title="Fixes login bug",
            body="Fixes #42",
            state="closed",
            is_merged=True,
            created_at=ONE_WEEK_AGO,
            merged_at=NOW,
            closes_issue_numbers=[42],
        )
        # Create a PR without linkage
        pr_unlinked = PullRequest(
            github_id=502,
            repo_id=sample_repo.id,
            author_id=sample_developer.id,
            number=11,
            title="Update readme",
            body="Just updating docs",
            state="closed",
            is_merged=True,
            created_at=ONE_WEEK_AGO,
            merged_at=NOW,
            closes_issue_numbers=[],
        )
        db_session.add_all([pr_linked, pr_unlinked])
        await db_session.commit()

        resp = await client.get("/api/stats/issue-linkage/developers")
        assert resp.status_code == 200
        data = resp.json()

        assert data["team_average_rate"] > 0
        assert data["attention_threshold"] == 0.2

        # Find our developer in the results
        dev_rows = [d for d in data["developers"] if d["developer_id"] == sample_developer.id]
        assert len(dev_rows) == 1
        row = dev_rows[0]
        assert row["prs_total"] == 2
        assert row["prs_linked"] == 1
        assert row["linkage_rate"] == 0.5

    @pytest.mark.asyncio
    async def test_linkage_empty_period(self, client, sample_developer):
        """No PRs in period → empty developer list."""
        resp = await client.get("/api/stats/issue-linkage/developers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["developers"] == []
        assert data["team_average_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_linkage_attention_developers(
        self, client, sample_developer, sample_developer_b, sample_repo, db_session
    ):
        """Developers below threshold appear in attention list."""
        # Developer A: 0% linkage (1 PR, no links)
        pr_a = PullRequest(
            github_id=601,
            repo_id=sample_repo.id,
            author_id=sample_developer.id,
            number=20,
            title="No link PR",
            body="No issue ref",
            state="closed",
            is_merged=True,
            created_at=ONE_WEEK_AGO,
            merged_at=NOW,
            closes_issue_numbers=[],
        )
        # Developer B: 100% linkage (1 PR, linked)
        pr_b = PullRequest(
            github_id=602,
            repo_id=sample_repo.id,
            author_id=sample_developer_b.id,
            number=21,
            title="Fixes issue",
            body="Closes #5",
            state="closed",
            is_merged=True,
            created_at=ONE_WEEK_AGO,
            merged_at=NOW,
            closes_issue_numbers=[5],
        )
        db_session.add_all([pr_a, pr_b])
        await db_session.commit()

        resp = await client.get("/api/stats/issue-linkage/developers")
        assert resp.status_code == 200
        data = resp.json()

        # Developer A (0%) should be in attention list
        attention_ids = [d["developer_id"] for d in data["attention_developers"]]
        assert sample_developer.id in attention_ids
        assert sample_developer_b.id not in attention_ids

    @pytest.mark.asyncio
    async def test_linkage_excludes_system_and_non_contributor_roles(
        self, client, sample_developer, sample_repo, db_session
    ):
        """Developers with `system` or `non_contributor` roles (bots, designers)
        must not appear in per-developer issue linkage stats — PR workflow metrics
        shouldn't judge accounts that don't author human-curated PRs."""
        bot = Developer(
            github_username="dependabot[bot]",
            display_name="dependabot[bot]",
            role="system_account",
            app_role="developer",
            is_active=True,
            created_at=NOW,
        )
        designer = Developer(
            github_username="designer1",
            display_name="Designer One",
            role="designer",
            app_role="developer",
            is_active=True,
            created_at=NOW,
        )
        db_session.add_all([bot, designer])
        await db_session.flush()
        db_session.add_all([
            PullRequest(
                github_id=901, repo_id=sample_repo.id, author_id=bot.id, number=40,
                title="Bump lib", body="", state="closed", is_merged=True,
                created_at=ONE_WEEK_AGO, merged_at=NOW, closes_issue_numbers=[],
            ),
            PullRequest(
                github_id=902, repo_id=sample_repo.id, author_id=designer.id, number=41,
                title="Tweak CSS", body="", state="closed", is_merged=True,
                created_at=ONE_WEEK_AGO, merged_at=NOW, closes_issue_numbers=[],
            ),
            PullRequest(
                github_id=903, repo_id=sample_repo.id, author_id=sample_developer.id, number=42,
                title="Real work", body="", state="closed", is_merged=True,
                created_at=ONE_WEEK_AGO, merged_at=NOW, closes_issue_numbers=[],
            ),
        ])
        await db_session.commit()

        resp = await client.get("/api/stats/issue-linkage/developers")
        assert resp.status_code == 200
        data = resp.json()

        dev_ids = {d["developer_id"] for d in data["developers"]}
        assert bot.id not in dev_ids
        assert designer.id not in dev_ids
        assert sample_developer.id in dev_ids

        attention_ids = {d["developer_id"] for d in data["attention_developers"]}
        assert bot.id not in attention_ids
        assert designer.id not in attention_ids

    @pytest.mark.asyncio
    async def test_linkage_team_filter(
        self, client, sample_developer, sample_developer_b, sample_repo, db_session
    ):
        """Team filter restricts results to that team."""
        pr = PullRequest(
            github_id=701,
            repo_id=sample_repo.id,
            author_id=sample_developer.id,
            number=30,
            title="Backend PR",
            body="Some work",
            state="closed",
            is_merged=True,
            created_at=ONE_WEEK_AGO,
            merged_at=NOW,
            closes_issue_numbers=[],
        )
        db_session.add(pr)
        await db_session.commit()

        # sample_developer is team="backend"
        resp = await client.get("/api/stats/issue-linkage/developers?team=backend")
        assert resp.status_code == 200
        data = resp.json()
        dev_ids = [d["developer_id"] for d in data["developers"]]
        assert sample_developer.id in dev_ids

        # Non-existent team → empty
        resp2 = await client.get("/api/stats/issue-linkage/developers?team=nonexistent")
        assert resp2.status_code == 200
        assert resp2.json()["developers"] == []


class TestDeveloperStatsLinkage:
    @pytest.mark.asyncio
    async def test_linkage_fields_on_developer_stats(
        self, client, sample_developer, sample_repo, db_session
    ):
        """Developer stats include prs_linked_to_issue and issue_linkage_rate."""
        pr_linked = PullRequest(
            github_id=801,
            repo_id=sample_repo.id,
            author_id=sample_developer.id,
            number=40,
            title="Linked PR",
            body="Closes #10",
            state="closed",
            is_merged=True,
            created_at=ONE_WEEK_AGO,
            merged_at=NOW,
            closes_issue_numbers=[10],
        )
        pr_unlinked = PullRequest(
            github_id=802,
            repo_id=sample_repo.id,
            author_id=sample_developer.id,
            number=41,
            title="Unlinked PR",
            body="No issue",
            state="closed",
            is_merged=True,
            created_at=ONE_WEEK_AGO,
            merged_at=NOW,
            closes_issue_numbers=[],
        )
        db_session.add_all([pr_linked, pr_unlinked])
        await db_session.commit()

        resp = await client.get(f"/api/stats/developer/{sample_developer.id}")
        assert resp.status_code == 200
        data = resp.json()

        assert data["prs_linked_to_issue"] == 1
        assert data["issue_linkage_rate"] == 0.5

    @pytest.mark.asyncio
    async def test_linkage_rate_none_when_no_prs(self, client, sample_developer):
        """No PRs → linkage_rate is null, prs_linked is 0."""
        resp = await client.get(f"/api/stats/developer/{sample_developer.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["prs_linked_to_issue"] == 0
        assert data["issue_linkage_rate"] is None
