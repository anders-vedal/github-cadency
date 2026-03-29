"""Unit tests for classify_pair_relationship() heuristic."""

from app.services.collaboration import PairRelationshipInput, classify_pair_relationship


def _make_input(**overrides) -> PairRelationshipInput:
    defaults = dict(
        total_reviews=10,
        reverse_reviews=10,
        approval_rate=0.5,
        changes_requested_rate=0.2,
        avg_quality_tier_score=2.0,
        comment_type_counts={"general": 5, "nit": 3},
        total_comments=8,
    )
    defaults.update(overrides)
    return PairRelationshipInput(**defaults)


def test_no_reviews():
    result = classify_pair_relationship(_make_input(total_reviews=0))
    assert result.label == "none"
    assert result.confidence == 1.0


def test_casual_few_reviews():
    result = classify_pair_relationship(_make_input(total_reviews=2, reverse_reviews=0))
    assert result.label == "casual"
    assert result.confidence == 0.5


def test_rubber_stamp():
    result = classify_pair_relationship(_make_input(
        total_reviews=10,
        reverse_reviews=2,
        approval_rate=0.95,
        changes_requested_rate=0.0,
        avg_quality_tier_score=0.5,
        comment_type_counts={"general": 2},
        total_comments=2,
    ))
    assert result.label == "rubber_stamp"
    assert result.confidence >= 0.8


def test_mentor():
    result = classify_pair_relationship(_make_input(
        total_reviews=15,
        reverse_reviews=2,
        approval_rate=0.6,
        changes_requested_rate=0.2,
        avg_quality_tier_score=2.5,
        comment_type_counts={"architectural": 8, "blocker": 5, "suggestion": 3},
        total_comments=16,
    ))
    assert result.label == "mentor"
    assert result.confidence >= 0.7


def test_gatekeeper():
    result = classify_pair_relationship(_make_input(
        total_reviews=12,
        reverse_reviews=1,
        approval_rate=0.4,
        changes_requested_rate=0.4,
        avg_quality_tier_score=1.5,
        comment_type_counts={"general": 5, "nit": 3},
        total_comments=8,
    ))
    assert result.label == "gatekeeper"
    assert result.confidence >= 0.7


def test_one_way_dependency():
    result = classify_pair_relationship(_make_input(
        total_reviews=12,
        reverse_reviews=1,
        approval_rate=0.7,
        changes_requested_rate=0.1,
        avg_quality_tier_score=1.5,
        comment_type_counts={"general": 5, "nit": 3},
        total_comments=8,
    ))
    assert result.label == "one_way_dependency"
    assert result.confidence >= 0.6


def test_peer_balanced():
    result = classify_pair_relationship(_make_input(
        total_reviews=8,
        reverse_reviews=8,
        approval_rate=0.6,
        changes_requested_rate=0.2,
        avg_quality_tier_score=2.0,
        comment_type_counts={"general": 5, "suggestion": 3},
        total_comments=8,
    ))
    assert result.label == "peer"
    assert result.confidence >= 0.6


def test_peer_fallback():
    """When no strong signal, falls back to peer with low confidence."""
    result = classify_pair_relationship(_make_input(
        total_reviews=5,
        reverse_reviews=2,
        approval_rate=0.6,
        changes_requested_rate=0.1,
        avg_quality_tier_score=1.5,
        comment_type_counts={"general": 3},
        total_comments=3,
    ))
    assert result.label == "peer"
    assert result.confidence < 0.6


def test_confidence_scales_with_volume():
    """More reviews should yield higher confidence for same pattern."""
    low = classify_pair_relationship(_make_input(
        total_reviews=4, reverse_reviews=4,
        approval_rate=0.5, changes_requested_rate=0.2,
        avg_quality_tier_score=2.0,
        comment_type_counts={"general": 2}, total_comments=2,
    ))
    high = classify_pair_relationship(_make_input(
        total_reviews=20, reverse_reviews=20,
        approval_rate=0.5, changes_requested_rate=0.2,
        avg_quality_tier_score=2.0,
        comment_type_counts={"general": 10}, total_comments=10,
    ))
    assert high.confidence >= low.confidence
