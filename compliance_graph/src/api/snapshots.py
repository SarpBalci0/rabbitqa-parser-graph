"""GET /v1/graph/snapshots/{id}, per rabbitqa_spec_v1.0.0.md §5.8:
"Response 200: snapshot metadata + ontology_version + lineage
(superseded_snapshot_id chain)."
"""

from __future__ import annotations

from fastapi import APIRouter

from clause_parser.src.api.errors import NotFoundError
from compliance_graph.src.publisher.snapshot import GraphStore


def get_snapshot_handler(snapshot_id: str, *, graph_store: GraphStore) -> dict:
    metadata = graph_store.get_snapshot(snapshot_id)
    if metadata is None:
        raise NotFoundError(f"No such snapshot: {snapshot_id}")

    lineage = [metadata.snapshot_id]
    cursor = metadata.superseded_snapshot_id
    while cursor is not None:
        lineage.append(cursor)
        prior = graph_store.get_snapshot(cursor)
        cursor = prior.superseded_snapshot_id if prior else None

    return {
        "snapshot_id": metadata.snapshot_id,
        "ontology_version": metadata.ontology_version,
        "valid_from": metadata.valid_from,
        "superseded_snapshot_id": metadata.superseded_snapshot_id,
        "published_at": metadata.published_at,
        "lineage": lineage,
    }


def build_router(graph_store_factory) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/graph/snapshots/{snapshot_id}")
    def get_snapshot(snapshot_id: str):
        return get_snapshot_handler(snapshot_id, graph_store=graph_store_factory())

    return router
