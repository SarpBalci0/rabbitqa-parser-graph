"""POST /v1/graph/query, per rabbitqa_spec_v1.0.0.md §5.9:
"Rule: querying a snapshot_id that is not fully published (i.e. still draft/
validated/approved) MUST return 404, not partial data."

The 404 gate is enforced via GraphStore.is_published(), which is only ever True for
a snapshot_id that completed a successful publish() call — a changeset sitting at
draft/validated/approved status never reaches the GraphStore at all (see
publisher.py: graph_store.publish() is only called after every §5.7 precondition
holds), so there is no snapshot_id a still-unpublished changeset could produce that
is_published() would ever say yes to. This is structural, not a status-string check
that could be bypassed.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from clause_parser.src.api.errors import NotFoundError
from clause_parser.src.db.obligation_repository import ObligationRepository
from compliance_graph.src.publisher.snapshot import GraphStore
from compliance_graph.src.query.proof_path import run_coverage_query, run_proof_path_query


class GraphQueryRequest(BaseModel):
    snapshot_id: str
    pattern: str
    filters: dict = {}


def run_query_handler(
    request: GraphQueryRequest, *, graph_store: GraphStore, obligation_repository: ObligationRepository
) -> dict:
    if not graph_store.is_published(request.snapshot_id):
        raise NotFoundError(
            f"Snapshot {request.snapshot_id} is not fully published.", {"snapshot_id": request.snapshot_id}
        )

    if request.pattern == "proof_path":
        results = run_proof_path_query(
            request.snapshot_id, graph_store=graph_store, obligation_repository=obligation_repository
        )
    elif request.pattern == "coverage":
        results = run_coverage_query(
            request.snapshot_id, graph_store=graph_store, obligation_repository=obligation_repository
        )
    else:
        raise NotFoundError(f"Unknown query pattern: {request.pattern}")

    return {"results": results}


def build_router(graph_store_factory, obligation_repository_factory) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/graph/query")
    def post_query(request: GraphQueryRequest):
        return run_query_handler(
            request,
            graph_store=graph_store_factory(),
            obligation_repository=obligation_repository_factory(),
        )

    return router
