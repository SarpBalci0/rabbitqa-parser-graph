"""Integration tests for PDF ingestion via POST /v1/documents, per
rabbitqa_spec_v1.1.0.md §5.1/§7 (spec_version 1.1.0): the source_format field,
content-type allow-listing of .pdf, and the two new 422 error cases
(PDF_NO_TEXT_LAYER, PDF_EXTRACTION_LOW_CONFIDENCE).
"""

from __future__ import annotations

import pytest

from clause_parser.src.api.documents import (
    DocumentRequest,
    PdfExtractionLowConfidenceHttpError,
    PdfNoTextLayerHttpError,
    register_document_handler,
)
from clause_parser.src.api.errors import SchemaValidationHttpError
from clause_parser.tests.pdf_fixtures import blank_pdf, minimal_pdf_with_text
from shared_contracts.py.db import configure, get_engine_singleton, get_session
from shared_contracts.py.tables import create_all


@pytest.fixture()
def session(tmp_path, monkeypatch):
    configure("sqlite:///:memory:")
    create_all(get_engine_singleton())
    monkeypatch.chdir(tmp_path)
    return get_session()


def _write_pdf_fixture(
    tmp_path, text="Article 1\n1. The operator shall notify within 30 days.", name="doc.pdf"
):
    path = tmp_path / name
    path.write_bytes(minimal_pdf_with_text(text))
    return str(path)


def test_pdf_registration_returns_201_with_source_format_pdf(tmp_path, session):
    uri = _write_pdf_fixture(tmp_path)
    request = DocumentRequest(
        instrument="NIS2", source_artifact_uri=uri, source_version="v1", source_format="pdf"
    )
    payload, status = register_document_handler(request, session)
    assert status == 201
    assert payload["source_format"] == "pdf"
    assert payload["extraction_metadata"]["confidence"] == 1.0


def test_source_format_defaults_to_text(tmp_path, session):
    path = tmp_path / "doc.txt"
    path.write_text("Article 1\n1. The operator shall act.\n")
    request = DocumentRequest(instrument="NIS2", source_artifact_uri=str(path), source_version="v1")
    payload, status = register_document_handler(request, session)
    assert status == 201
    assert payload["source_format"] == "text"


def test_invalid_source_format_rejected(tmp_path, session):
    uri = _write_pdf_fixture(tmp_path)
    request = DocumentRequest(
        instrument="NIS2", source_artifact_uri=uri, source_version="v1", source_format="docx"
    )
    with pytest.raises(SchemaValidationHttpError):
        register_document_handler(request, session)


def test_blank_pdf_returns_pdf_no_text_layer_error(tmp_path, session):
    path = tmp_path / "scanned.pdf"
    path.write_bytes(blank_pdf())
    request = DocumentRequest(
        instrument="NIS2", source_artifact_uri=str(path), source_version="v1", source_format="pdf"
    )
    with pytest.raises(PdfNoTextLayerHttpError) as excinfo:
        register_document_handler(request, session)
    assert excinfo.value.status_code == 422
    assert excinfo.value.code == "PDF_NO_TEXT_LAYER"


def test_low_confidence_pdf_returns_low_confidence_error(tmp_path, session, monkeypatch):
    monkeypatch.setenv("RABBITQA_PDF_MIN_CONFIDENCE", "1.01")
    uri = _write_pdf_fixture(tmp_path)
    request = DocumentRequest(
        instrument="NIS2", source_artifact_uri=uri, source_version="v1", source_format="pdf"
    )
    with pytest.raises(PdfExtractionLowConfidenceHttpError) as excinfo:
        register_document_handler(request, session)
    assert excinfo.value.status_code == 422
    assert excinfo.value.code == "PDF_EXTRACTION_LOW_CONFIDENCE"
    assert excinfo.value.details["confidence"] == 1.0
    assert excinfo.value.details["warnings"] == []
