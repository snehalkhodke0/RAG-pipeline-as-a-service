"""Reciprocal Rank Fusion: combines multiple ranked id lists into one fused ranking.

score(d) = sum over lists containing d of 1 / (k + rank_in_list(d)), rank is 1-indexed.
Pure function, independent of the database, so it is directly unit-testable.
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple, TypeVar

T = TypeVar("T")


def reciprocal_rank_fusion(ranked_lists: Sequence[Sequence[T]], k: int = 60) -> List[Tuple[T, float]]:
    """Returns (id, fused_score) pairs sorted by descending score. Ties break by the
    id's own ordering (stable, deterministic) so callers get reproducible results.
    """
    scores: Dict[T, float] = {}
    first_seen_order: Dict[T, int] = {}
    counter = 0

    for ranked in ranked_lists:
        for rank, item in enumerate(ranked, start=1):
            if item not in first_seen_order:
                first_seen_order[item] = counter
                counter += 1
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)

    return sorted(scores.items(), key=lambda pair: (-pair[1], first_seen_order[pair[0]]))
