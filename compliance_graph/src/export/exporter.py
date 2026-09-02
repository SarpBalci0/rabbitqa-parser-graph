"""Export builder, per rabbitqa_spec_v1.0.0.md §2.5 and §7:

"GraphSnapshotExport MUST only ever be produced from a snapshot whose every
included obligation has review_status in {accepted, edited}. Exporting from a
pending/escalated/rejected obligation is a contract violation" and "If any link in
this chain cannot be resolved for a given exported obligation, that obligation MUST
NOT appear in the export — this is a hard gate, not a warning." Both gates apply
independently and silently (no error for the whole export) — this module never
raises for an individual excluded obligation, it just omits it.
"""

from __future__ import annotations

from typing import Any

from clause_parser.src.db.document_repository import DocumentRepository
from clause_parser.src.db.obligation_repository import ObligationRepository
from compliance_graph.src.db.changeset_repository import ChangesetRepository
from compliance_graph.src.export.manifest import build_and_log_manifest
from compliance_graph.src.export.provenance import resolve_provenance_chain
from compliance_graph.src.publisher.snapshot import GraphStore
from llm_gateway.logging import DEFAULT_AGENT_CALL_LOG, AgentCallLog


def _node_lookup(nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {n["node_id"]: n for n in nodes}


def build_export(
    snapshot_id: str,
    *,
    graph_store: GraphStore,
    changeset_repository: ChangesetRepository,
    document_repository: DocumentRepository,
    obligation_repository: ObligationRepository,
    agent_call_log: AgentCallLog = DEFAULT_AGENT_CALL_LOG,
) -> dict[str, Any]:
    metadata = graph_store.get_snapshot(snapshot_id)
    if metadata is None:
        raise ValueError(f"No such published snapshot: {snapshot_id}")

    published_changesets = changeset_repository.list_published_by_snapshot(snapshot_id)

    included: list[dict[str, Any]] = []
    excluded_clause_ids: list[str] = []

    for changeset in published_changesets:
        nodes = _node_lookup(changeset["proposed_nodes"])
        relationships = changeset["proposed_relationships"]

        for clause_id in changeset["source_clause_ids"]:
            revisions = obligation_repository.list_revisions_for_clause(clause_id)
            obligation = revisions[-1]["proposal"] if revisions else None

            # Gate 1 (§2.5): review_status MUST be accepted or edited.
            review_status = obligation["governance"]["review_status"] if obligation else None
            if review_status not in ("accepted", "edited"):
                excluded_clause_ids.append(clause_id)
                continue

            # Gate 2 (§7): every provenance link MUST resolve.
            chain = resolve_provenance_chain(
                clause_id,
                document_repository=document_repository,
                obligation_repository=obligation_repository,
                changeset_repository=changeset_repository,
                agent_call_log=agent_call_log,
            )
            if not chain.resolved:
                excluded_clause_ids.append(clause_id)
                continue

            obligation_node_id = next(
                (n["node_id"] for n in nodes.values() if n["type"] == "Obligation" and n["properties"].get("clause_id") == clause_id),
                None,
            )
            if obligation_node_id is None:
                excluded_clause_ids.append(clause_id)
                continue

            mapped_controls = [
                r["to_node_id"]
                for r in relationships
                if r["from_node_id"] == obligation_node_id
                and r["type"] == "MAPS_TO_CONTROL"
                and nodes.get(r["to_node_id"], {}).get("type") == "Control"
            ]
            mapped_assets = [
                r["to_node_id"]
                for r in relationships
                if r["from_node_id"] == obligation_node_id
                and r["type"] == "AFFECTS_ASSET"
                and nodes.get(r["to_node_id"], {}).get("type") == "Asset"
            ]
            mapped_evidence: list[str] = []
            for control_id in mapped_controls:
                mapped_evidence.extend(
                    r["to_node_id"]
                    for r in relationships
                    if r["from_node_id"] == control_id
                    and r["type"] == "SATISFIED_BY"
                    and nodes.get(r["to_node_id"], {}).get("type") == "EvidenceRequirement"
                )

            confidence = min(
                (obligation["governance"].get("field_confidence") or {}).values(),
                default=1.0,
            )

            included.append(
                {
                    "clause_id": clause_id,
                    "obligation_node_id": obligation_node_id,
                    "mapped_controls": mapped_controls,
                    "mapped_assets": mapped_assets,
                    "mapped_evidence": mapped_evidence,
                    "review_status": review_status,
                    "source_anchor": obligation["source_evidence"]["anchor_id"],
                    "confidence": confidence,
                }
            )

    build_and_log_manifest(
        snapshot_id=snapshot_id,
        included_clause_ids=[o["clause_id"] for o in included],
        excluded_clause_ids=excluded_clause_ids,
    )

    return {
        "snapshot_id": metadata.snapshot_id,
        "ontology_version": metadata.ontology_version,
        "valid_from": metadata.valid_from,
        "superseded_snapshot_id": metadata.superseded_snapshot_id,
        "obligations": included,
        "schema_version": "1.0.0",
    }
