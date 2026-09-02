"""Entity resolution: match extracted actors/objects to existing Actor/Asset nodes
by fuzzy+exact match with a confidence score, per rabbitqa_spec_v1.1.0.md §4.3.

MUST NOT: "Auto-merge nodes above a threshold without a reviewer decision recorded."
This module therefore only ever PROPOSES matches with a confidence score — it never
writes a merge decision itself. The caller (Graph Mapping Agent / reviewer workflow)
is responsible for recording an explicit decision before any merge takes effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True)
class ExistingEntity:
    node_id: str
    name: str
    node_type: str  # "Actor" | "Asset"


@dataclass(frozen=True)
class MatchCandidate:
    candidate_name: str
    matched_node_id: str | None
    matched_name: str | None
    confidence: float
    match_type: str  # "exact" | "fuzzy" | "none"


def _normalize(name: str) -> str:
    return name.strip().lower()


def resolve_entity(candidate_name: str, existing: list[ExistingEntity]) -> MatchCandidate:
    """Returns a single best MatchCandidate — never merges, only proposes."""
    normalized_candidate = _normalize(candidate_name)

    for entity in existing:
        if _normalize(entity.name) == normalized_candidate:
            return MatchCandidate(
                candidate_name=candidate_name,
                matched_node_id=entity.node_id,
                matched_name=entity.name,
                confidence=1.0,
                match_type="exact",
            )

    best: ExistingEntity | None = None
    best_ratio = 0.0
    for entity in existing:
        ratio = SequenceMatcher(None, normalized_candidate, _normalize(entity.name)).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best = entity

    if best is not None and best_ratio >= 0.6:
        return MatchCandidate(
            candidate_name=candidate_name,
            matched_node_id=best.node_id,
            matched_name=best.name,
            confidence=round(best_ratio, 4),
            match_type="fuzzy",
        )

    return MatchCandidate(
        candidate_name=candidate_name,
        matched_node_id=None,
        matched_name=None,
        confidence=0.0,
        match_type="none",
    )


def resolve_entities(candidate_names: list[str], existing: list[ExistingEntity]) -> list[MatchCandidate]:
    return [resolve_entity(name, existing) for name in candidate_names]
