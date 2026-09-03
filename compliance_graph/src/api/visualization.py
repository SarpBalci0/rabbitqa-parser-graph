"""GET /v1/graph/snapshots/{snapshot_id}/proof-path-view, per
rabbitqa_spec_v1.1.0.md §5.11: renders the §3.3 proof-path for one obligation as a
static SVG diagram, reusing run_proof_path_query (§5.9) unchanged -- no independent
graph traversal (§4.5). Error responses use the standard JSON envelope even though
the success response is HTML (§5.11: "a 400/404 from it is never an HTML error
page")."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from clause_parser.src.api.errors import NotFoundError, SchemaValidationHttpError
from clause_parser.src.db.obligation_repository import ObligationRepository
from compliance_graph.src.publisher.snapshot import GraphStore
from compliance_graph.src.query.proof_path import run_proof_path_query
from compliance_graph.src.visualization import proof_path_renderer


def render_proof_path_view_handler(
    snapshot_id: str, clause_id: str, *, graph_store: GraphStore, obligation_repository: ObligationRepository
) -> str:
    if not clause_id:
        raise SchemaValidationHttpError("clause_id query parameter is required.")

    if not graph_store.is_published(snapshot_id):
        raise NotFoundError(
            "No published proof-path found for this clause_id in this snapshot.",
            {"snapshot_id": snapshot_id, "clause_id": clause_id},
        )

    results = run_proof_path_query(snapshot_id, graph_store=graph_store, obligation_repository=obligation_repository)
    result = next((r for r in results if r["clause_id"] == clause_id), None)
    if result is None or result.get("review_status") != "accepted":
        raise NotFoundError(
            "No published proof-path found for this clause_id in this snapshot.",
            {"snapshot_id": snapshot_id, "clause_id": clause_id},
        )

    body = proof_path_renderer.render(result)
    if body is None:
        # Incomplete chain -- same uniform 404 pathway as every other "nothing
        # complete to show" case (research.md "Not-found semantics").
        raise NotFoundError(
            "No published proof-path found for this clause_id in this snapshot.",
            {"snapshot_id": snapshot_id, "clause_id": clause_id},
        )

    return body


def build_router(graph_store_factory, obligation_repository_factory) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/graph/snapshots/{snapshot_id}/proof-path-view", response_class=HTMLResponse)
    def get_proof_path_view(snapshot_id: str, clause_id: str = ""):
        body = render_proof_path_view_handler(
            snapshot_id,
            clause_id,
            graph_store=graph_store_factory(),
            obligation_repository=obligation_repository_factory(),
        )
        return HTMLResponse(content=body)

    return router
