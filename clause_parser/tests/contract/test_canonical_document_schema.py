"""Contract test: registered CanonicalDocument validates against
shared_contracts/schemas/CanonicalDocument.schema.json."""

from shared_contracts.py.db import configure, get_session, get_engine_singleton
from shared_contracts.py.tables import create_all
from shared_contracts.py.validation import validate
from clause_parser.src.api.documents import DocumentRequest, register_document_handler


def test_registered_document_validates_against_schema(tmp_path):
    configure("sqlite:///:memory:")
    create_all(get_engine_singleton())
    session = get_session()

    fixture_path = tmp_path / "doc.txt"
    fixture_path.write_text("Article 1\n1. The operator shall act.\n")

    payload, status = register_document_handler(
        DocumentRequest(instrument="NIS2", source_artifact_uri=str(fixture_path), source_version="v1"),
        session,
    )
    assert status == 201
    validate(payload, "CanonicalDocument.schema.json")
