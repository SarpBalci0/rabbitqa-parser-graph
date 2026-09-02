"""Tests for PDF ingestion in clause_parser.src.canonicalize.document_registry,
per rabbitqa_spec_v1.1.0.md §2.1/§5.1 (spec_version 1.1.0):
- successful PDF registration populates source_format + extraction_metadata
- a PDF with no extractable text layer MUST raise PdfNoTextLayerError and MUST
  NOT create a CanonicalDocument
- a PDF whose extraction confidence is below the configured threshold MUST
  raise PdfExtractionLowConfidenceError and MUST NOT create a CanonicalDocument
- idempotency/conflict detection is keyed on raw-byte checksum, unaffected by
  source_format
"""

from __future__ import annotations

import pytest

from clause_parser.src.canonicalize.document_registry import (
    PdfExtractionLowConfidenceError,
    register_document,
)
from clause_parser.src.canonicalize.pdf_extractor import PdfNoTextLayerError
from clause_parser.src.canonicalize.raw_storage import RawStorage
from clause_parser.src.db.document_repository import DocumentRepository
from clause_parser.tests.pdf_fixtures import blank_pdf, minimal_pdf_with_text
from shared_contracts.py.db import configure, get_engine_singleton, get_session
from shared_contracts.py.tables import create_all


def _fresh_deps(tmp_path):
    configure("sqlite:///:memory:")
    create_all(get_engine_singleton())
    repo = DocumentRepository(get_session())
    storage = RawStorage(tmp_path / "raw")
    return repo, storage


def test_pdf_registration_populates_source_format_and_extraction_metadata(tmp_path):
    repo, storage = _fresh_deps(tmp_path)
    pdf_bytes = minimal_pdf_with_text("Article 1. The operator shall notify within 30 days.")

    result = register_document(
        raw_bytes=pdf_bytes,
        instrument="NIS2",
        source_version="v1",
        source_format="pdf",
        repository=repo,
        raw_storage=storage,
    )

    assert result.created is True
    payload = result.document_payload
    assert payload["source_format"] == "pdf"
    assert payload["extraction_metadata"]["confidence"] == 1.0
    assert payload["extraction_metadata"]["extraction_method"].startswith("pypdf-")
    assert "The operator shall notify within 30 days." in payload["_canonical_text"]
    assert payload["schema_version"] == "1.1.0"


def test_text_registration_still_sets_source_format_text(tmp_path):
    repo, storage = _fresh_deps(tmp_path)
    result = register_document(
        raw_bytes=b"Article 1\n1. The operator shall act.\n",
        instrument="NIS2",
        source_version="v1",
        source_format="text",
        repository=repo,
        raw_storage=storage,
    )
    assert result.document_payload["source_format"] == "text"
    assert result.document_payload["extraction_metadata"] is None


def test_blank_pdf_blocks_registration(tmp_path):
    repo, storage = _fresh_deps(tmp_path)
    with pytest.raises(PdfNoTextLayerError):
        register_document(
            raw_bytes=blank_pdf(),
            instrument="NIS2",
            source_version="v1",
            source_format="pdf",
            repository=repo,
            raw_storage=storage,
        )
    # No CanonicalDocument was created for the rejected content.
    assert repo.get_by_instrument_and_source_version("NIS2", "v1") is None


def test_low_confidence_extraction_blocks_registration(tmp_path, monkeypatch):
    repo, storage = _fresh_deps(tmp_path)
    pdf_bytes = minimal_pdf_with_text("Article 1. The operator shall notify within 30 days.")
    # A clean extraction always scores exactly 1.0 (see test_pdf_extractor.py);
    # setting the threshold above that deterministically exercises the gate
    # without needing to simulate genuine PDF corruption end-to-end here.
    monkeypatch.setenv("RABBITQA_PDF_MIN_CONFIDENCE", "1.01")

    with pytest.raises(PdfExtractionLowConfidenceError) as excinfo:
        register_document(
            raw_bytes=pdf_bytes,
            instrument="NIS2",
            source_version="v1",
            source_format="pdf",
            repository=repo,
            raw_storage=storage,
        )
    assert excinfo.value.confidence == 1.0
    assert excinfo.value.threshold == 1.01
    assert repo.get_by_instrument_and_source_version("NIS2", "v1") is None
