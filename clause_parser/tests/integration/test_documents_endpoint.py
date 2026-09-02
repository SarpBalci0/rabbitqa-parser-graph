"""Integration tests for the POST /v1/documents handler (T039/T043), covering
§9.1's Ingestion Given/When/Then and the §5.1 (spec_version 1.0.2) 409 conflict case.
"""

import pytest

from shared_contracts.py.db import configure, get_session, get_engine_singleton
from shared_contracts.py.tables import create_all
from clause_parser.src.api.documents import (
    ConflictHttpError,
    DocumentRequest,
    register_document_handler,
)
from clause_parser.src.api.errors import SchemaValidationHttpError


@pytest.fixture()
def session(tmp_path, monkeypatch):
    configure("sqlite:///:memory:")
    create_all(get_engine_singleton())
    monkeypatch.chdir(tmp_path)
    return get_session()


def _write_fixture(tmp_path, name="doc.txt", text="Article 1\n1. The operator shall notify within 30 days.\n"):
    path = tmp_path / name
    path.write_text(text)
    return str(path)


def test_first_registration_returns_201(tmp_path, session):
    uri = _write_fixture(tmp_path)
    request = DocumentRequest(instrument="NIS2", source_artifact_uri=uri, source_version="v1")
    payload, status = register_document_handler(request, session)
    assert status == 201
    assert payload["instrument"] == "NIS2"
    assert payload["document_id"].startswith("doc_")


def test_reregistering_identical_bytes_returns_200_not_201(tmp_path, session):
    uri = _write_fixture(tmp_path)
    request = DocumentRequest(instrument="NIS2", source_artifact_uri=uri, source_version="v1")
    first, first_status = register_document_handler(request, session)
    second, second_status = register_document_handler(request, session)
    assert first_status == 201
    assert second_status == 200
    assert first["document_id"] == second["document_id"]


def test_different_content_same_source_version_returns_409(tmp_path, session):
    uri1 = _write_fixture(tmp_path, "doc1.txt", "Article 1\n1. The operator shall notify within 30 days.\n")
    uri2 = _write_fixture(tmp_path, "doc2.txt", "Article 1\n1. A completely different obligation text.\n")

    register_document_handler(
        DocumentRequest(instrument="NIS2", source_artifact_uri=uri1, source_version="v1"), session
    )
    with pytest.raises(ConflictHttpError):
        register_document_handler(
            DocumentRequest(instrument="NIS2", source_artifact_uri=uri2, source_version="v1"), session
        )


def test_unsupported_content_type_rejected(tmp_path, session):
    uri = _write_fixture(tmp_path, "doc.exe")
    request = DocumentRequest(instrument="NIS2", source_artifact_uri=uri, source_version="v1")
    with pytest.raises(SchemaValidationHttpError):
        register_document_handler(request, session)


def test_missing_file_returns_checksum_error(tmp_path, session):
    request = DocumentRequest(
        instrument="NIS2", source_artifact_uri=str(tmp_path / "missing.txt"), source_version="v1"
    )
    with pytest.raises(SchemaValidationHttpError):
        register_document_handler(request, session)
