"""§3.3 proof-path query and a 'coverage' pattern, per rabbitqa_spec_v1.1.0.md
§5.9: "Every query response MUST include, per path: clause_id, verbatim_text (from
evidence), review_status, graph_snapshot_id."

Joins the graph's raw path results (clause_id, path, graph_snapshot_id — see
GraphStore.query_proof_path) with the ObligationObject store (clause_parser) to
attach verbatim_text/review_status, since those live on the pre-graph record, not
as graph node properties (§3.1: Obligation only requires clause_id, norm_type).
"""

from __future__ import annotations

from typing import Any

from clause_parser.src.db.obligation_repository import ObligationRepository
from compliance_graph.src.publisher.snapshot import GraphStore


def _latest_obligation_for_clause(clause_id: str, obligation_repository: ObligationRepository) -> dict | None:
    revisions = obligation_repository.list_revisions_for_clause(clause_id)
    return revisions[-1]["proposal"] if revisions else None


def run_proof_path_query(
    snapshot_id: str, *, graph_store: GraphStore, obligation_repository: ObligationRepository
) -> list[dict[str, Any]]:
    raw_results = graph_store.query_proof_path(snapshot_id)
    enriched: list[dict[str, Any]] = []
    for result in raw_results:
        obligation = _latest_obligation_for_clause(result["clause_id"], obligation_repository)
        enriched.append(
            {
                "clause_id": result["clause_id"],
                "path": result["path"],
                "verbatim_text": obligation["source_evidence"]["verbatim_text"] if obligation else "",
                "review_status": obligation["governance"]["review_status"] if obligation else "",
                "graph_snapshot_id": result["graph_snapshot_id"],
            }
        )
    return enriched


def run_coverage_query(
    snapshot_id: str, *, graph_store: GraphStore, obligation_repository: ObligationRepository
) -> list[dict[str, Any]]:
    """A second query pattern per §5.9's request shape ("pattern":
    "proof_path"|"coverage"). The technical spec defines the request/response
    envelope for 'coverage' but not its specific traversal — reusing the proof-path
    result shape here (same enrichment) is a reasonable minimal implementation,
    not a distinct spec-defined pattern; flagged as such rather than presented as
    normative."""
    return run_proof_path_query(
        snapshot_id, graph_store=graph_store, obligation_repository=obligation_repository
    )
