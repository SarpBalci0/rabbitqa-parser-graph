"""Ontology reference tables, per rabbitqa_spec_v1.0.0.md §3.1/§3.2 (mirrored
exactly in data-model.md §6.1/§6.2). This module is the single source of truth the
constraints engine (engine.py) validates every GraphChangeSet against — the node
type list, required-properties map, and the exhaustive relationship allow-list are
never duplicated or hand-copied anywhere else.

"Any relationship proposal outside this table MUST fail constraint_report
validation. This table is exhaustive for v1 — extending it requires a spec version
bump." (§3.2)
"""

from __future__ import annotations

ontology_version = "1.0.0"

# §3.1 — Node type -> required properties (informational; not schema-enforced beyond
# NODE_TYPES membership, since `properties` is a free-form object in GraphChangeSet's
# schema — required-property completeness is a constraint-engine-level check, not a
# JSON-Schema-level one).
NODE_TYPE_REQUIRED_PROPERTIES: dict[str, tuple[str, ...]] = {
    "Regulation": ("instrument", "source_version"),
    "Provision": ("anchor_id", "label"),
    "Definition": ("term", "anchor_id"),
    "Obligation": ("clause_id", "norm_type"),
    "Actor": ("name", "role_category"),
    "Action": ("description",),
    "Condition": ("description",),
    "Exception": ("description",),
    "Deadline": ("type", "normalized_iso"),  # normalized_iso is nullable but MUST be present
    "Control": ("control_id", "name"),
    "Risk": ("risk_id", "name"),
    "EvidenceRequirement": ("evidence_id", "description"),
    "Asset": ("asset_id", "name", "asset_type"),
    "System": ("system_id", "name"),
    "API": ("api_id", "name"),
    "Dataset": ("dataset_id", "name"),
    "TestAsset": ("test_id", "name"),
    "Agent": ("agent_id", "role"),
}

NODE_TYPES: frozenset[str] = frozenset(NODE_TYPE_REQUIRED_PROPERTIES)

# §3.2 — Relationship type -> exhaustive set of allowed (from_type, to_type) pairs.
# REFERENCES and DEFINES have multiple/open-ended allowed target shapes per the
# spec's prose; encoded precisely below rather than approximated.
_ANY_LEGAL_MEANING_NODE = NODE_TYPES - {"Agent"}  # "(any legal-meaning node)" per §3.2;
# Agent is explicitly "not a graph actor" (§3.1), so excluded from "legal-meaning".

RELATIONSHIP_ALLOWED_PAIRS: dict[str, frozenset[tuple[str, str]]] = {
    "DERIVED_FROM": frozenset({("Obligation", "Provision")}),
    "IMPOSES_ON": frozenset({("Obligation", "Actor")}),
    "REQUIRES": frozenset({("Obligation", "Action")}),
    "CONDITIONED_BY": frozenset({("Obligation", "Condition")}),
    "EXCEPTION_TO": frozenset({("Obligation", "Exception")}),
    "REFERENCES": frozenset({("Provision", "Provision"), ("Provision", "Definition")}),
    "DEFINES": frozenset({("Definition", target) for target in _ANY_LEGAL_MEANING_NODE}),
    "AMENDS": frozenset({("Provision", "Provision")}),
    "SUPERSEDES": frozenset({("Regulation", "Regulation")}),  # snapshot-level only (§3.2)
    "APPLIES_TO": frozenset({("Obligation", "Actor")}),
    "MAPS_TO_CONTROL": frozenset({("Obligation", "Control"), ("Risk", "Control")}),
    "AFFECTS_ASSET": frozenset({("Obligation", "Asset"), ("Control", "Asset")}),
    "SATISFIED_BY": frozenset({("Control", "EvidenceRequirement")}),
    "EVIDENCED_BY": frozenset({("EvidenceRequirement", "TestAsset")}),
}

RELATIONSHIP_TYPES: frozenset[str] = frozenset(RELATIONSHIP_ALLOWED_PAIRS)


def is_pair_allowed(relationship_type: str, from_type: str, to_type: str) -> bool:
    """§3.2: 'Any relationship proposal outside this table MUST fail
    constraint_report validation.' Unknown relationship_type is also disallowed
    (fails closed, not open)."""
    allowed_pairs = RELATIONSHIP_ALLOWED_PAIRS.get(relationship_type)
    if allowed_pairs is None:
        return False
    return (from_type, to_type) in allowed_pairs
