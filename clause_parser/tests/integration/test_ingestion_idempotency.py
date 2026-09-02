"""§9.1 Ingestion Given/When/Then, as its own file per tasks.md T022's named path:
registering byte-identical content twice returns the same document_id, second call
is 200 not 201. (Equivalent assertions also covered in test_documents_endpoint.py's
broader test suite; this file exists for 1:1 traceability to tasks.md.)"""

from shared_contracts.py.db import configure, get_session, get_engine_singleton
from shared_contracts.py.tables import create_all
from clause_parser.src.api.documents import DocumentRequest, register_document_handler


def test_byte_identical_reregistration_is_idempotent(tmp_path):
    configure("sqlite:///:memory:")
    create_all(get_engine_singleton())
    session = get_session()

    fixture_path = tmp_path / "doc.txt"
    fixture_path.write_text("Article 1\n1. The operator shall act.\n")
    request = DocumentRequest(instrument="NIS2", source_artifact_uri=str(fixture_path), source_version="v1")

    first_payload, first_status = register_document_handler(request, session)
    second_payload, second_status = register_document_handler(request, session)

    assert first_status == 201
    assert second_status == 200
    assert first_payload["document_id"] == second_payload["document_id"]
