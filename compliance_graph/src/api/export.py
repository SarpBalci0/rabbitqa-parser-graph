"""GET /v1/graph/snapshots/{id}/export, per rabbitqa_spec_v1.0.0.md §5.10:
"Response 200: GraphSnapshotExport, schema-validated before being returned."
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.orm import Session

from clause_parser.src.api.errors import NotFoundError
from clause_parser.src.db.document_repository import DocumentRepository
from clause_parser.src.db.obligation_repository import ObligationRepository
from compliance_graph.src.db.changeset_repository import ChangesetRepository
from compliance_graph.src.export.exporter import build_export
from compliance_graph.src.publisher.snapshot import GraphStore
from shared_contracts.py.validation import validate


def export_snapshot_handler(snapshot_id: str, *, session: Session, graph_store: GraphStore) -> dict:
    if not graph_store.is_published(snapshot_id):
        raise NotFoundError(f"No such published snapshot: {snapshot_id}")

    export_payload = build_export(
        snapshot_id,
        graph_store=graph_store,
        changeset_repository=ChangesetRepository(session),
        document_repository=DocumentRepository(session),
        obligation_repository=ObligationRepository(session),
    )
    validate(export_payload, "GraphSnapshotExport.schema.json")
    return export_payload


def build_router(session_factory, graph_store_factory) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/graph/snapshots/{snapshot_id}/export")
    def get_export(snapshot_id: str):
        session = session_factory()
        try:
            return export_snapshot_handler(snapshot_id, session=session, graph_store=graph_store_factory())
        finally:
            session.close()

    return router
