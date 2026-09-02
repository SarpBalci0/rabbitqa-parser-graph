"""Constraints engine: ontology + cardinality + provenance checks, per
rabbitqa_spec_v1.1.0.md §2.4 and §3.2.

"Run ontology + cardinality + provenance checks (§2.4)... MUST NOT: Skip
validation for changesets flagged 'small' or 'obvious' — every changeset is
validated identically." (§4.3) There is exactly one code path here; no size- or
confidence-based shortcut exists.

Rule names correspond exactly to shared_contracts/schemas/ConstraintReport.schema.json's
rule_name enum (see that file's own $comment for why it's an interim, non-root-spec
contract): obligation_derived_from_provision, obligation_imposes_on_actor,
maps_to_control_endpoint_restriction, evidenced_by_endpoint_restriction,
no_dangling_node_reference, relationship_type_pair_allowed.
"""

from __future__ import annotations

from typing import Any

from compliance_graph.src.constraints.ontology import is_pair_allowed


def _node_types(proposed_nodes: list[dict[str, Any]]) -> dict[str, str]:
    return {n["node_id"]: n["type"] for n in proposed_nodes}


def check_relationship_type_pair_allowed(
    proposed_relationships: list[dict[str, Any]], node_types: dict[str, str]
) -> dict[str, Any]:
    """§3.2: every relationship's (type, from_type, to_type) MUST be in the
    exhaustive allow-list. Checks EVERY relationship, not a sample — no relationship
    type/pair is exempt, including ones this rule shares semantics with (see
    maps_to_control/evidenced_by below, which restate two entries of this same table
    for direct spec-traceability of §2.4's explicit bullets)."""
    offending: list[dict[str, str]] = []
    for rel in proposed_relationships:
        from_type = node_types.get(rel["from_node_id"])
        to_type = node_types.get(rel["to_node_id"])
        if from_type is None or to_type is None:
            continue  # dangling reference — reported by no_dangling_node_reference, not here
        if not is_pair_allowed(rel["type"], from_type, to_type):
            offending.append(
                {"from_node_id": rel["from_node_id"], "to_node_id": rel["to_node_id"], "type": rel["type"]}
            )

    if offending:
        return {
            "rule_name": "relationship_type_pair_allowed",
            "status": "fail",
            "message": f"{len(offending)} relationship(s) use a type/pair not in the §3.2 allow-list.",
            "offending_relationship": offending[0],
        }
    return {
        "rule_name": "relationship_type_pair_allowed",
        "status": "pass",
        "message": "Every relationship's type/pair is in the §3.2 allow-list.",
    }


def check_obligation_derived_from_provision(
    proposed_nodes: list[dict[str, Any]], proposed_relationships: list[dict[str, Any]]
) -> dict[str, Any]:
    """§2.4: 'Every Obligation node MUST have exactly one outgoing DERIVED_FROM to
    a Provision.'"""
    obligation_ids = [n["node_id"] for n in proposed_nodes if n["type"] == "Obligation"]
    node_types = _node_types(proposed_nodes)

    offending: list[str] = []
    for obligation_id in obligation_ids:
        derived_from_count = sum(
            1
            for rel in proposed_relationships
            if rel["from_node_id"] == obligation_id
            and rel["type"] == "DERIVED_FROM"
            and node_types.get(rel["to_node_id"]) == "Provision"
        )
        if derived_from_count != 1:
            offending.append(obligation_id)

    if offending:
        return {
            "rule_name": "obligation_derived_from_provision",
            "status": "fail",
            "message": f"{len(offending)} Obligation node(s) lack exactly one DERIVED_FROM->Provision edge.",
            "offending_node_ids": offending,
        }
    return {
        "rule_name": "obligation_derived_from_provision",
        "status": "pass",
        "message": "Every Obligation node has exactly one DERIVED_FROM->Provision edge.",
    }


def check_obligation_imposes_on_actor(
    proposed_nodes: list[dict[str, Any]], proposed_relationships: list[dict[str, Any]]
) -> dict[str, Any]:
    """§2.4: 'Every Obligation node MUST have at least one outgoing IMPOSES_ON to
    an Actor.'"""
    obligation_ids = [n["node_id"] for n in proposed_nodes if n["type"] == "Obligation"]
    node_types = _node_types(proposed_nodes)

    offending: list[str] = []
    for obligation_id in obligation_ids:
        imposes_on_count = sum(
            1
            for rel in proposed_relationships
            if rel["from_node_id"] == obligation_id
            and rel["type"] == "IMPOSES_ON"
            and node_types.get(rel["to_node_id"]) == "Actor"
        )
        if imposes_on_count < 1:
            offending.append(obligation_id)

    if offending:
        return {
            "rule_name": "obligation_imposes_on_actor",
            "status": "fail",
            "message": f"{len(offending)} Obligation node(s) lack any IMPOSES_ON->Actor edge.",
            "offending_node_ids": offending,
        }
    return {
        "rule_name": "obligation_imposes_on_actor",
        "status": "pass",
        "message": "Every Obligation node has at least one IMPOSES_ON->Actor edge.",
    }


def check_maps_to_control_endpoint_restriction(
    proposed_relationships: list[dict[str, Any]], node_types: dict[str, str]
) -> dict[str, Any]:
    """§2.4: 'MAPS_TO_CONTROL edges MUST only originate from Obligation or Risk
    nodes and terminate at Control nodes.'"""
    offending: list[dict[str, str]] = []
    for rel in proposed_relationships:
        if rel["type"] != "MAPS_TO_CONTROL":
            continue
        from_type = node_types.get(rel["from_node_id"])
        to_type = node_types.get(rel["to_node_id"])
        if from_type not in ("Obligation", "Risk") or to_type != "Control":
            offending.append(
                {"from_node_id": rel["from_node_id"], "to_node_id": rel["to_node_id"], "type": rel["type"]}
            )

    if offending:
        return {
            "rule_name": "maps_to_control_endpoint_restriction",
            "status": "fail",
            "message": f"{len(offending)} MAPS_TO_CONTROL edge(s) violate the Obligation/Risk -> Control restriction.",
            "offending_relationship": offending[0],
        }
    return {
        "rule_name": "maps_to_control_endpoint_restriction",
        "status": "pass",
        "message": "All MAPS_TO_CONTROL edges originate from Obligation/Risk and terminate at Control.",
    }


def check_evidenced_by_endpoint_restriction(
    proposed_relationships: list[dict[str, Any]], node_types: dict[str, str]
) -> dict[str, Any]:
    """§2.4: 'EVIDENCED_BY edges MUST only terminate at EvidenceRequirement or
    TestAsset nodes.'"""
    offending: list[dict[str, str]] = []
    for rel in proposed_relationships:
        if rel["type"] != "EVIDENCED_BY":
            continue
        to_type = node_types.get(rel["to_node_id"])
        if to_type not in ("EvidenceRequirement", "TestAsset"):
            offending.append(
                {"from_node_id": rel["from_node_id"], "to_node_id": rel["to_node_id"], "type": rel["type"]}
            )

    if offending:
        return {
            "rule_name": "evidenced_by_endpoint_restriction",
            "status": "fail",
            "message": f"{len(offending)} EVIDENCED_BY edge(s) do not terminate at EvidenceRequirement/TestAsset.",
            "offending_relationship": offending[0],
        }
    return {
        "rule_name": "evidenced_by_endpoint_restriction",
        "status": "pass",
        "message": "All EVIDENCED_BY edges terminate at EvidenceRequirement/TestAsset.",
    }


def check_no_dangling_node_reference(
    proposed_nodes: list[dict[str, Any]],
    proposed_relationships: list[dict[str, Any]],
    published_node_ids: frozenset[str],
) -> dict[str, Any]:
    """§2.4: 'No relationship may reference a node_id not present in proposed_nodes
    or already published in base_snapshot_id.'

    published_node_ids defaults to an empty set when no graph publish/snapshot
    machinery exists yet (User Story 4, not yet built) — this is a documented
    limitation, not a silent behavior gap: with no snapshot to check against, only
    proposed_nodes can satisfy a reference, which is the conservative (fail-closed)
    reading."""
    known_ids = {n["node_id"] for n in proposed_nodes} | published_node_ids
    offending: list[dict[str, str]] = []
    for rel in proposed_relationships:
        if rel["from_node_id"] not in known_ids or rel["to_node_id"] not in known_ids:
            offending.append(
                {"from_node_id": rel["from_node_id"], "to_node_id": rel["to_node_id"], "type": rel["type"]}
            )

    if offending:
        return {
            "rule_name": "no_dangling_node_reference",
            "status": "fail",
            "message": f"{len(offending)} relationship(s) reference a node_id absent from proposed_nodes and any published snapshot.",
            "offending_relationship": offending[0],
        }
    return {
        "rule_name": "no_dangling_node_reference",
        "status": "pass",
        "message": "Every relationship references only known node_ids.",
    }


def run_all_checks(
    proposed_nodes: list[dict[str, Any]],
    proposed_relationships: list[dict[str, Any]],
    *,
    published_node_ids: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Runs all six named rules, identically, for every changeset regardless of
    size (§4.3 MUST NOT)."""
    node_types = _node_types(proposed_nodes)
    return [
        check_obligation_derived_from_provision(proposed_nodes, proposed_relationships),
        check_obligation_imposes_on_actor(proposed_nodes, proposed_relationships),
        check_maps_to_control_endpoint_restriction(proposed_relationships, node_types),
        check_evidenced_by_endpoint_restriction(proposed_relationships, node_types),
        check_no_dangling_node_reference(proposed_nodes, proposed_relationships, published_node_ids),
        check_relationship_type_pair_allowed(proposed_relationships, node_types),
    ]


def resolve_status_after_validation(constraint_overall_status: str, current_status: str) -> str:
    """§2.4: 'A GraphChangeSet with any constraint_report failure MUST have status
    forced to rejected — it is not eligible for the approval endpoint.' On a pass,
    status advances from draft to validated (still requires a separate explicit
    approval action per §4.3 — this never returns 'approved')."""
    if constraint_overall_status == "fail":
        return "rejected"
    if current_status == "draft":
        return "validated"
    return current_status
