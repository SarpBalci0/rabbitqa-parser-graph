"""Contract test: export payload validates against GraphSnapshotExport.schema.json."""

from clause_parser.src.db.document_repository import DocumentRepository
from clause_parser.src.db.obligation_repository import ObligationRepository
from compliance_graph.src.db.changeset_repository import ChangesetRepository
from compliance_graph.src.export.exporter import build_export
from compliance_graph.tests.conftest import build_published_snapshot
from shared_contracts.py.validation import validate


def test_export_validates_against_schema(tmp_path):
    session, store, snapshot_id, _ = build_published_snapshot(tmp_path)

    export_payload = build_export(
        snapshot_id,
        graph_store=store,
        changeset_repository=ChangesetRepository(session),
        document_repository=DocumentRepository(session),
        obligation_repository=ObligationRepository(session),
    )
    validate(export_payload, "GraphSnapshotExport.schema.json")
    assert len(export_payload["obligations"]) == 1
