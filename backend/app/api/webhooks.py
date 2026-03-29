import hashlib
import hmac
import logging

import httpx
from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select

from app.config import settings
from app.models.database import AsyncSessionLocal
from app.models.models import Issue, PullRequest, Repository
from app.services.github_sync import (
    compute_approval_metrics,
    github_get,
    github_get_paginated,
    recompute_review_quality_tiers,
    upsert_issue,
    upsert_issue_comment,
    upsert_pull_request,
    upsert_review,
    upsert_review_comment,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_signature(payload: bytes, signature: str) -> bool:
    expected = hmac.new(
        settings.github_webhook_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


@router.post("/webhooks/github", status_code=status.HTTP_200_OK)
async def github_webhook(
    request: Request,
    x_hub_signature_256: str = Header(...),
    x_github_event: str = Header(...),
):
    body = await request.body()

    if not verify_signature(body, x_hub_signature_256):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    payload = await request.json()

    async with AsyncSessionLocal() as db:
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                if x_github_event == "pull_request":
                    await handle_pull_request(db, client, payload)
                elif x_github_event == "pull_request_review":
                    await handle_pull_request_review(db, client, payload)
                elif x_github_event == "pull_request_review_comment":
                    await handle_pull_request_review_comment(db, client, payload)
                elif x_github_event == "issues":
                    await handle_issue(db, payload)
                elif x_github_event == "issue_comment":
                    await handle_issue_comment(db, payload)

                await db.commit()
            except Exception:
                logger.exception("Error processing webhook event %s", x_github_event)
                await db.rollback()
                raise

    return {"status": "ok"}


async def get_repo(db, repo_data: dict) -> Repository | None:
    result = await db.execute(
        select(Repository).where(Repository.github_id == repo_data["id"])
    )
    return result.scalar_one_or_none()


async def handle_pull_request(db, client: httpx.AsyncClient, payload: dict):
    repo = await get_repo(db, payload["repository"])
    if not repo or not repo.is_tracked:
        return

    pr = await upsert_pull_request(db, client, payload["pull_request"], repo)
    await db.flush()

    # Re-fetch reviews for this PR
    reviews_data = await github_get_paginated(
        client, f"/repos/{repo.full_name}/pulls/{pr.number}/reviews"
    )
    for review_data in reviews_data:
        await upsert_review(db, review_data, pr, client=client)

    # Re-fetch review comments and recompute quality tiers
    review_comments_data = await github_get_paginated(
        client, f"/repos/{repo.full_name}/pulls/{pr.number}/comments"
    )
    for comment_data in review_comments_data:
        await upsert_review_comment(db, comment_data, pr)
    await db.flush()
    await recompute_review_quality_tiers(db, pr)
    await compute_approval_metrics(db, pr)


async def handle_pull_request_review(db, client: httpx.AsyncClient, payload: dict):
    repo = await get_repo(db, payload["repository"])
    if not repo or not repo.is_tracked:
        return

    pr_data = payload["pull_request"]
    result = await db.execute(
        select(PullRequest).where(
            PullRequest.repo_id == repo.id,
            PullRequest.number == pr_data["number"],
        )
    )
    pr = result.scalar_one_or_none()
    if not pr:
        pr = await upsert_pull_request(db, client, pr_data, repo)
        await db.flush()

    await upsert_review(db, payload["review"], pr, client=client)

    # Fetch review comments and recompute quality tiers for accuracy
    review_comments_data = await github_get_paginated(
        client, f"/repos/{repo.full_name}/pulls/{pr.number}/comments"
    )
    for comment_data in review_comments_data:
        await upsert_review_comment(db, comment_data, pr)
    await db.flush()
    await recompute_review_quality_tiers(db, pr)
    await compute_approval_metrics(db, pr)


async def handle_pull_request_review_comment(
    db, client: httpx.AsyncClient, payload: dict
):
    repo = await get_repo(db, payload["repository"])
    if not repo or not repo.is_tracked:
        return

    pr_data = payload["pull_request"]
    result = await db.execute(
        select(PullRequest).where(
            PullRequest.repo_id == repo.id,
            PullRequest.number == pr_data["number"],
        )
    )
    pr = result.scalar_one_or_none()
    if not pr:
        return

    await upsert_review_comment(db, payload["comment"], pr)
    await db.flush()
    await recompute_review_quality_tiers(db, pr)


async def handle_issue(db, payload: dict):
    repo = await get_repo(db, payload["repository"])
    if not repo or not repo.is_tracked:
        return

    await upsert_issue(db, payload["issue"], repo)


async def handle_issue_comment(db, payload: dict):
    repo = await get_repo(db, payload["repository"])
    if not repo or not repo.is_tracked:
        return

    issue_data = payload["issue"]
    if "pull_request" in issue_data:
        return  # Skip PR comments — handled via PR review events

    result = await db.execute(
        select(Issue).where(
            Issue.repo_id == repo.id,
            Issue.number == issue_data["number"],
        )
    )
    issue = result.scalar_one_or_none()
    if not issue:
        issue = await upsert_issue(db, issue_data, repo)
        await db.flush()

    await upsert_issue_comment(db, payload["comment"], issue)
