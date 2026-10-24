"""RRF fusion tests: correct ordering given two known ranked lists. No database required."""

from __future__ import annotations

from app.services.rrf import reciprocal_rank_fusion


def test_rrf_fuses_two_known_ranked_lists() -> None:
    vector_ranked = ["a", "b", "c", "d"]
    keyword_ranked = ["c", "a", "e", "b"]

    fused = reciprocal_rank_fusion([vector_ranked, keyword_ranked], k=60)
    fused_ids = [item for item, _ in fused]

    # Hand-computed expected scores with k=60:
    # a: vector rank1 -> 1/61 ; keyword rank2 -> 1/62  => 0.032576...
    # b: vector rank2 -> 1/62 ; keyword rank4 -> 1/64  => 0.031754...
    # c: vector rank3 -> 1/63 ; keyword rank1 -> 1/61  => 0.032171...
    # d: vector rank4 -> 1/64                          => 0.015625
    # e: keyword rank3 -> 1/63                         => 0.015873
    expected_scores = {
        "a": 1 / 61 + 1 / 62,
        "b": 1 / 62 + 1 / 64,
        "c": 1 / 63 + 1 / 61,
        "d": 1 / 64,
        "e": 1 / 63,
    }
    for item, score in fused:
        assert score == expected_scores[item]

    # a > c > b > e > d
    assert fused_ids == ["a", "c", "b", "e", "d"]


def test_rrf_single_list_preserves_order() -> None:
    fused = reciprocal_rank_fusion([["x", "y", "z"]], k=60)
    assert [item for item, _ in fused] == ["x", "y", "z"]


def test_rrf_empty_lists() -> None:
    assert reciprocal_rank_fusion([], k=60) == []
    assert reciprocal_rank_fusion([[], []], k=60) == []


def test_rrf_item_only_in_one_list_ranks_below_items_in_both() -> None:
    fused = reciprocal_rank_fusion([["only_a"], ["shared", "only_b"]], k=60)
    scores = dict(fused)
    assert scores["only_a"] == 1 / 61
    assert scores["shared"] == 1 / 61
    assert scores["only_b"] == 1 / 62
