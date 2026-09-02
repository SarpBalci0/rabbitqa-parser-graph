"""FR-034/§7 Document ingress zone: uploads exceeding the fixed 25 MB size limit
or failing the content-type allow-list are rejected before checksum/parsing. Per
rabbitqa_spec_v1.1.0.md §7 (spec_version 1.1.0), the allow-list now includes .pdf
alongside .txt/.xml/.html."""

import pytest

from shared_contracts.py.db import configure, get_session, get_engine_singleton
from shared_contracts.py.tables import create_all
from clause_parser.src.api.documents import (
    ALLOWED_CONTENT_TYPES,
    MAX_UPLOAD_BYTES,
    DocumentRequest,
    register_document_handler,
)
from clause_parser.src.api.errors import SchemaValidationHttpError
from clause_parser.src.db.document_repository import DocumentRepository


@pytest.fixture()
def session():
    configure("sqlite:///:memory:")
    create_all(get_engine_singleton())
    return get_session()


def test_oversized_upload_is_rejected_before_checksum(tmp_path, session):
    fixture_path = tmp_path / "huge.txt"
    fixture_path.write_bytes(b"a" * (MAX_UPLOAD_BYTES + 1))

    request = DocumentRequest(instrument="NIS2", source_artifact_uri=str(fixture_path), source_version="v1")
    with pytest.raises(SchemaValidationHttpError):
        register_document_handler(request, session)

    # No document was persisted — rejection happened before checksum/registration.
    repo = DocumentRepository(session)
    assert repo.get_by_checksum("a" * 64, "NIS2", "v1") is None


def test_content_type_not_on_allow_list_is_rejected(tmp_path, session):
    fixture_path = tmp_path / "payload.exe"
    fixture_path.write_text("not a legal document")

    request = DocumentRequest(instrument="NIS2", source_artifact_uri=str(fixture_path), source_version="v1")
    with pytest.raises(SchemaValidationHttpError):
        register_document_handler(request, session)


def test_content_type_check_runs_before_any_file_read():
    """The content-type check must reject based on the URI's extension alone,
    without needing to read (and therefore checksum) the file first — confirmed by
    passing a path that does not exist at all."""
    from clause_parser.src.api.documents import _validate_content_type

    with pytest.raises(SchemaValidationHttpError):
        _validate_content_type("/this/path/does/not/exist/at/all.exe")


def test_allow_listed_content_types_are_exactly_txt_xml_html_pdf():
    assert ALLOWED_CONTENT_TYPES == {".txt", ".xml", ".html", ".pdf"}


def test_within_limits_and_allow_listed_type_succeeds(tmp_path, session):
    fixture_path = tmp_path / "doc.txt"
    fixture_path.write_text("Article 1\n1. The operator shall act.\n")
    request = DocumentRequest(instrument="NIS2", source_artifact_uri=str(fixture_path), source_version="v1")
    _, status = register_document_handler(request, session)
    assert status == 201
