"""Integration tests for GitHub PR timeline sync + aggregate derivation (Phase 09)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Developer,
    PRTimelineEvent,
    PullRequest,
    Repository,
)
from app.services.github_timeline import (
    TYPENAME_TO_EVENT_TYPE,
    derive_pr_aggregates,
    fetch_pr_timeline_batch,
    persist_timeline_events,
)


NOW = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def repo(db_session: AsyncSession) -> Repository:
    r = Repository(
        github_id=99,
        name="widgets",
        full_name="acme/widgets",
        is_tracked=True,
        created_at=NOW,
    )
    db_session.add(r)
    await db_session.commit()
    await db_session.refresh(r)
    return r


@pytest_asyncio.fixture
async def author(db_session: AsyncSession) -> Developer:
    dev = Developer(
        github_username="author",
        display_name="Author",
        is_active=True,
        app_role="developer",
        created_at=NOW,
        updated_at=NOW,
    )
    db_session.add(dev)
    await db_session.commit()
    await db_session.refresh(dev)
    return dev


@pytest_asyncio.fixture
async def pr(
    db_session: AsyncSession, repo: Repository, author: Developer
) -> PullRequest:
    row = PullRequest(
        github_id=1001,
        repo_id=repo.id,
        author_id=author.id,
        number=42,
        title="Add widgets",
        state="open",
        is_merged=False,
        created_at=NOW - timedelta(days=2),
        updated_at=NOW,
        first_review_at=NOW - timedelta(hours=20),
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return row


# ── persist_timeline_events + derive_pr_aggregates ───────────────────────


@pytest.mark.asyncio
async def test_persist_force_push_events_and_derive_bounce_count(
    db_session: AsyncSession, pr: PullRequest
):
    """Three force-push events, two after first_review_at -> bounce count 2."""
    # first_review_at is 20h ago. Put two force-pushes AFTER it, one BEFORE.
    nodes = [
        {
            "__typename": "HeadRefForcePushedEvent",
            "id": "FP1_before_review",
            "createdAt": (NOW - timedelta(hours=30)).isoformat().replace(
                "+00:00", "Z"
            ),
            "actor": {"login": "author"},
            "beforeCommit": {"oid": "a" * 40},
            "afterCommit": {"oid": "b" * 40},
        },
        {
            "__typename": "HeadRefForcePushedEvent",
            "id": "FP2_after_review",
            "createdAt": (NOW - timedelta(hours=10)).isoformat().replace(
                "+00:00", "Z"
            ),
            "actor": {"login": "author"},
            "beforeCommit": {"oid": "c" * 40},
            "afterCommit": {"oid": "d" * 40},
        },
        {
            "__typename": "HeadRefForcePushedEvent",
            "id": "FP3_after_review",
            "createdAt": (NOW - timedelta(hours=5)).isoformat().replace(
                "+00:00", "Z"
            ),
            "actor": {"login": "author"},
            "beforeCommit": {"oid": "e" * 40},
            "afterCommit": {"oid": "f" * 40},
        },
    ]

    counts = await persist_timeline_events(db_session, pr, nodes)
    assert counts["inserted"] == 3

    await derive_pr_aggregates(db_session, pr)
    await db_session.refresh(pr)

    assert pr.force_push_count_after_first_review == 2


@pytest.mark.asyncio
async def test_persist_is_idempotent_by_external_id(
    db_session: AsyncSession, pr: PullRequest
):
    """Same node persisted twice -> 1 inserted, 1 updated, no duplicate row."""
    node = {
        "__typename": "ReadyForReviewEvent",
        "id": "RFR-1",
        "createdAt": (NOW - timedelta(hours=30)).isoformat().replace(
            "+00:00", "Z"
        ),
        "actor": {"login": "author"},
    }

    first = await persist_timeline_events(db_session, pr, [node])
    second = await persist_timeline_events(db_session, pr, [node])

    assert first["inserted"] == 1
    assert second["updated"] == 1
    rows = (
        await db_session.execute(
            select(PRTimelineEvent).where(PRTimelineEvent.pr_id == pr.id)
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].event_type == "ready_for_review"


@pytest.mark.asyncio
async def test_derive_ready_for_review_and_draft_flips(
    db_session: AsyncSession, pr: PullRequest
):
    """Two ready-for-review + one converted-to-draft -> draft_flip_count=3, ready_for_review_at=earliest."""
    earlier = (NOW - timedelta(hours=30)).isoformat().replace("+00:00", "Z")
    later = (NOW - timedelta(hours=25)).isoformat().replace("+00:00", "Z")
    draft = (NOW - timedelta(hours=28)).isoformat().replace("+00:00", "Z")
    nodes = [
        {
            "__typename": "ReadyForReviewEvent",
            "id": "RFR-earlier",
            "createdAt": earlier,
            "actor": {"login": "author"},
        },
        {
            "__typename": "ConvertToDraftEvent",
            "id": "CTD-1",
            "createdAt": draft,
            "actor": {"login": "author"},
        },
        {
            "__typename": "ReadyForReviewEvent",
            "id": "RFR-later",
            "createdAt": later,
            "actor": {"login": "author"},
        },
    ]

    await persist_timeline_events(db_session, pr, nodes)
    await derive_pr_aggregates(db_session, pr)
    await db_session.refresh(pr)

    assert pr.draft_flip_count == 3
    # ready_for_review_at = EARLIEST ready_for_review event
    assert pr.ready_for_review_at is not None
    assert pr.ready_for_review_at.hour == (NOW - timedelta(hours=30)).hour


@pytest.mark.asyncio
async def test_derive_review_requested_count(
    db_session: AsyncSession, pr: PullRequest
):
    """Each review_requested event increments the count (distinct reviewers don't de-dupe here)."""
    nodes = [
        {
            "__typename": "ReviewRequestedEvent",
            "id": "RR-1",
            "createdAt": (NOW - timedelta(hours=40)).isoformat().replace(
                "+00:00", "Z"
            ),
            "actor": {"login": "author"},
            "requestedReviewer": {"login": "reviewer-a"},
        },
        {
            "__typename": "ReviewRequestedEvent",
            "id": "RR-2",
            "createdAt": (NOW - timedelta(hours=38)).isoformat().replace(
                "+00:00", "Z"
            ),
            "actor": {"login": "author"},
            "requestedReviewer": {"login": "reviewer-b"},
        },
    ]

    await persist_timeline_events(db_session, pr, nodes)
    await derive_pr_aggregates(db_session, pr)
    await db_session.refresh(pr)
    assert pr.review_requested_count == 2


@pytest.mark.asyncio
async def test_derive_merge_queue_waited_seconds(
    db_session: AsyncSession, pr: PullRequest
):
    """added_to_merge_queue -> removed_from_merge_queue interval on merged PR."""
    pr.is_merged = True
    pr.merged_at = NOW
    pr.state = "closed"
    await db_session.commit()

    added = NOW - timedelta(minutes=45)
    removed = NOW - timedelta(minutes=5)
    nodes = [
        {
            "__typename": "AddedToMergeQueueEvent",
            "id": "AMQ-1",
            "createdAt": added.isoformat().replace("+00:00", "Z"),
            "actor": {"login": "author"},
        },
        {
            "__typename": "RemovedFromMergeQueueEvent",
            "id": "RMQ-1",
            "createdAt": removed.isoformat().replace("+00:00", "Z"),
            "actor": {"login": "author"},
            "reason": "MERGE",
        },
    ]

    await persist_timeline_events(db_session, pr, nodes)
    await derive_pr_aggregates(db_session, pr)
    await db_session.refresh(pr)

    assert pr.merge_queue_waited_s == int((removed - added).total_seconds())


@pytest.mark.asyncio
async def test_derive_renamed_and_dismissed_counts(
    db_session: AsyncSession, pr: PullRequest
):
    """renamed_title_count and dismissed_review_count both derived from event rows."""
    nodes = [
        {
            "__typename": "RenamedTitleEvent",
            "id": "RT-1",
            "createdAt": (NOW - timedelta(hours=22)).isoformat().replace(
                "+00:00", "Z"
            ),
            "actor": {"login": "author"},
            "previousTitle": "WIP: something",
            "currentTitle": "Add widgets",
        },
        {
            "__typename": "ReviewDismissedEvent",
            "id": "RD-1",
            "createdAt": (NOW - timedelta(hours=15)).isoformat().replace(
                "+00:00", "Z"
            ),
            "actor": {"login": "author"},
            "dismissalMessage": "stale",
            "review": {"author": {"login": "reviewer-a"}},
        },
    ]
    await persist_timeline_events(db_session, pr, nodes)
    await derive_pr_aggregates(db_session, pr)
    await db_session.refresh(pr)

    assert pr.renamed_title_count == 1
    assert pr.dismissed_review_count == 1


@pytest.mark.asyncio
async def test_unknown_typename_is_skipped(
    db_session: AsyncSession, pr: PullRequest
):
    nodes = [
        {
            "__typename": "SomeTypeWeDoNotModel",
            "id": "X-1",
            "createdAt": NOW.isoformat().replace("+00:00", "Z"),
        }
    ]
    counts = await persist_timeline_events(db_session, pr, nodes)
    assert counts["inserted"] == 0
    assert counts["skipped"] == 1


@pytest.mark.asyncio
async def test_event_data_json_captures_label_and_rename_details(
    db_session: AsyncSession, pr: PullRequest
):
    """Type-specific fields land in the data JSONB column for downstream use."""
    nodes = [
        {
            "__typename": "LabeledEvent",
            "id": "LE-1",
            "createdAt": NOW.isoformat().replace("+00:00", "Z"),
            "actor": {"login": "author"},
            "label": {"name": "needs-review", "color": "ededed"},
        },
        {
            "__typename": "RenamedTitleEvent",
            "id": "RN-1",
            "createdAt": NOW.isoformat().replace("+00:00", "Z"),
            "actor": {"login": "author"},
            "previousTitle": "WIP",
            "currentTitle": "Add widgets",
        },
    ]
    await persist_timeline_events(db_session, pr, nodes)

    rows = (
        await db_session.execute(
            select(PRTimelineEvent).where(PRTimelineEvent.pr_id == pr.id)
        )
    ).scalars().all()
    by_type = {r.event_type: r for r in rows}
    assert by_type["labeled"].data["label_name"] == "needs-review"
    assert by_type["renamed_title"].data["previous_title"] == "WIP"
    assert by_type["renamed_title"].data["current_title"] == "Add widgets"


# ── fetch_pr_timeline_batch (GraphQL) ────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_pr_timeline_batch_parses_aliased_response():
    """A mocked GraphQL response with two aliased PRs returns a dict keyed by PR number."""
    mock_payload = {
        "data": {
            "pr1": {
                "pullRequest": {
                    "timelineItems": {
                        "nodes": [
                            {
                                "__typename": "ReadyForReviewEvent",
                                "id": "RFR-1",
                                "createdAt": NOW.isoformat().replace(
                                    "+00:00", "Z"
                                ),
                                "actor": {"login": "author"},
                            }
                        ]
                    }
                }
            },
            "pr2": {
                "pullRequest": {
                    "timelineItems": {
                        "nodes": [
                            {
                                "__typename": "HeadRefForcePushedEvent",
                                "id": "FP-1",
                                "createdAt": NOW.isoformat().replace(
                                    "+00:00", "Z"
                                ),
                                "actor": {"login": "author"},
                                "beforeCommit": {"oid": "aa"},
                                "afterCommit": {"oid": "bb"},
                            }
                        ]
                    }
                }
            },
            "rateLimit": {
                "cost": 2,
                "remaining": 4998,
                "resetAt": NOW.isoformat().replace("+00:00", "Z"),
            },
        }
    }

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = mock_payload

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_resp)

    out = await fetch_pr_timeline_batch(
        mock_client, token="t", repo_owner="acme", repo_name="widgets", pr_numbers=[1, 2]
    )

    assert set(out.keys()) == {1, 2}
    assert out[1][0]["__typename"] == "ReadyForReviewEvent"
    assert out[2][0]["__typename"] == "HeadRefForcePushedEvent"


@pytest.mark.asyncio
async def test_fetch_pr_timeline_batch_empty_input_short_circuits():
    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock()
    out = await fetch_pr_timeline_batch(
        mock_client, token="t", repo_owner="a", repo_name="b", pr_numbers=[]
    )
    assert out == {}
    mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_pr_timeline_batch_chunks_large_inputs():
    """More than batch_size PRs should produce multiple GraphQL requests."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    # Return empty data each call so parsing doesn't reference any alias.
    mock_resp.json.return_value = {"data": {"rateLimit": {"cost": 1, "remaining": 9, "resetAt": NOW.isoformat().replace("+00:00", "Z")}}}

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_resp)

    pr_numbers = list(range(1, 6))  # 5 PRs
    await fetch_pr_timeline_batch(
        mock_client,
        token="t",
        repo_owner="a",
        repo_name="b",
        pr_numbers=pr_numbers,
        batch_size=2,
    )
    # 5 PRs / batch size 2 -> 3 requests (2+2+1)
    assert mock_client.post.await_count == 3


def test_typename_to_event_type_covers_all_known_types():
    """Sanity: the mapping table covers every event type the derive step needs."""
    required = {
        "HeadRefForcePushedEvent",
        "ReadyForReviewEvent",
        "ConvertToDraftEvent",
        "ReviewRequestedEvent",
        "ReviewDismissedEvent",
        "RenamedTitleEvent",
        "AddedToMergeQueueEvent",
        "RemovedFromMergeQueueEvent",
        "AutoMergeEnabledEvent",
        "AutoMergeDisabledEvent",
    }
    assert required.issubset(set(TYPENAME_TO_EVENT_TYPE.keys()))
