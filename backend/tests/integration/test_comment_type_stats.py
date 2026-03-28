"""Integration tests for comment type distribution in developer stats."""
import pytest
from datetime import timedelta

from app.models.models import PRReview, PRReviewComment, PullRequest


class TestCommentTypeStats:
    @pytest.mark.asyncio
    async def test_comment_type_distribution(
        self, client, sample_developer, sample_developer_b, sample_pr, sample_review, db_session
    ):
        """Comment type distribution aggregates correctly by reviewer."""
        now = sample_review.submitted_at
        # Add review comments by sample_developer_b (the reviewer)
        comments = [
            PRReviewComment(github_id=1001, pr_id=sample_pr.id, review_id=sample_review.id,
                            author_github_username="testuser2", body="nit: rename this",
                            comment_type="nit", created_at=now),
            PRReviewComment(github_id=1002, pr_id=sample_pr.id, review_id=sample_review.id,
                            author_github_username="testuser2", body="nit: extra whitespace",
                            comment_type="nit", created_at=now),
            PRReviewComment(github_id=1003, pr_id=sample_pr.id, review_id=sample_review.id,
                            author_github_username="testuser2", body="blocker: SQL injection risk",
                            comment_type="blocker", created_at=now),
            PRReviewComment(github_id=1004, pr_id=sample_pr.id, review_id=sample_review.id,
                            author_github_username="testuser2", body="LGTM on this part",
                            comment_type="praise", created_at=now),
        ]
        for c in comments:
            db_session.add(c)
        await db_session.commit()

        resp = await client.get(f"/api/stats/developer/{sample_developer_b.id}")
        assert resp.status_code == 200
        data = resp.json()

        dist = data["comment_type_distribution"]
        assert dist["nit"] == 2
        assert dist["blocker"] == 1
        assert dist["praise"] == 1

    @pytest.mark.asyncio
    async def test_nit_ratio(
        self, client, sample_developer_b, sample_pr, sample_review, db_session
    ):
        """nit_ratio = nit_count / total_comments."""
        now = sample_review.submitted_at
        comments = [
            PRReviewComment(github_id=2001, pr_id=sample_pr.id, review_id=sample_review.id,
                            author_github_username="testuser2", body="nit: spacing",
                            comment_type="nit", created_at=now),
            PRReviewComment(github_id=2002, pr_id=sample_pr.id, review_id=sample_review.id,
                            author_github_username="testuser2", body="looks fine",
                            comment_type="general", created_at=now),
        ]
        for c in comments:
            db_session.add(c)
        await db_session.commit()

        resp = await client.get(f"/api/stats/developer/{sample_developer_b.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["nit_ratio"] == 0.5  # 1 nit / 2 total

    @pytest.mark.asyncio
    async def test_blocker_catch_rate(
        self, client, sample_developer_b, sample_pr, sample_review, db_session
    ):
        """blocker_catch_rate = reviews_with_blocker / total_reviews."""
        now = sample_review.submitted_at
        # One blocker comment on the review
        db_session.add(PRReviewComment(
            github_id=3001, pr_id=sample_pr.id, review_id=sample_review.id,
            author_github_username="testuser2", body="blocker: broken",
            comment_type="blocker", created_at=now,
        ))
        await db_session.commit()

        resp = await client.get(f"/api/stats/developer/{sample_developer_b.id}")
        assert resp.status_code == 200
        data = resp.json()
        # 1 review with blocker / 1 total review = 1.0
        assert data["blocker_catch_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_no_comments_defaults(self, client, sample_developer):
        """No comments → empty distribution, None ratios."""
        resp = await client.get(f"/api/stats/developer/{sample_developer.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["comment_type_distribution"] == {}
        assert data["nit_ratio"] is None
        assert data["blocker_catch_rate"] is None

    @pytest.mark.asyncio
    async def test_review_quality_promotion_blocker(
        self, client, sample_developer_b, sample_pr, sample_review, db_session
    ):
        """A review with a blocker comment gets promoted to at least 'standard'."""
        # sample_review has body_length=21, state=APPROVED → normally 'minimal'
        # But with a blocker comment, recompute should promote to 'standard'
        from app.services.github_sync import recompute_review_quality_tiers

        now = sample_review.submitted_at
        db_session.add(PRReviewComment(
            github_id=4001, pr_id=sample_pr.id, review_id=sample_review.id,
            author_github_username="testuser2", body="blocker: critical bug",
            comment_type="blocker", created_at=now,
        ))
        await db_session.flush()
        await recompute_review_quality_tiers(db_session, sample_pr)
        await db_session.commit()
        await db_session.refresh(sample_review)

        assert sample_review.quality_tier == "standard"

    @pytest.mark.asyncio
    async def test_review_quality_promotion_architectural(
        self, client, sample_developer_b, sample_pr, sample_review, db_session
    ):
        """A review with 3+ architectural comments gets promoted to 'thorough'."""
        from app.services.github_sync import recompute_review_quality_tiers

        now = sample_review.submitted_at
        for i in range(3):
            db_session.add(PRReviewComment(
                github_id=5001 + i, pr_id=sample_pr.id, review_id=sample_review.id,
                author_github_username="testuser2",
                body=f"This introduces tight coupling with module {i}",
                comment_type="architectural", created_at=now,
            ))
        await db_session.flush()
        await recompute_review_quality_tiers(db_session, sample_pr)
        await db_session.commit()
        await db_session.refresh(sample_review)

        assert sample_review.quality_tier == "thorough"
