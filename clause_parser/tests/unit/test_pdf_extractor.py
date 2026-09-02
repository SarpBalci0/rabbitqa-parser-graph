"""Tests for clause_parser.src.canonicalize.pdf_extractor, per rabbitqa_spec_v1.1.0.md
§2.1 (spec_version 1.1.0): deterministic PDF text extraction, the empty-text-layer
rejection (PdfNoTextLayerError), and the confidence heuristic that feeds the §5.1
PDF_EXTRACTION_LOW_CONFIDENCE gate.
"""

from __future__ import annotations

import pytest

from clause_parser.src.canonicalize.pdf_extractor import (
    PdfNoTextLayerError,
    _confidence_threshold,
    _score_confidence,
    extract_pdf_text,
)
from clause_parser.tests.pdf_fixtures import blank_pdf, minimal_pdf_with_text


def test_extracts_text_from_pdf_with_text_layer():
    pdf_bytes = minimal_pdf_with_text("Article 1. The operator shall notify within 30 days.")
    result = extract_pdf_text(pdf_bytes)
    assert "The operator shall notify within 30 days." in result.text
    assert result.confidence == 1.0
    assert result.warnings == []
    assert result.extraction_method.startswith("pypdf-")


def test_blank_pdf_raises_no_text_layer_error():
    with pytest.raises(PdfNoTextLayerError):
        extract_pdf_text(blank_pdf())


def test_replacement_characters_lower_confidence_and_produce_warning():
    # Simulates the extracted-text output of a genuinely font/encoding-corrupted
    # PDF (real corruption happens inside the PDF's font/cmap tables, not by
    # embedding U+FFFD as a literal PDF string glyph) by exercising the scoring
    # heuristic directly on text containing the replacement character.
    confidence, warnings = _score_confidence("Corrupted �� text run")
    assert confidence < 1.0
    assert any("replacement characters" in w for w in warnings)


def test_hyphenation_break_lowers_confidence_and_warns():
    text = "The oper-\nator shall comply with every applicable requirement in full."
    confidence, warnings = _score_confidence(text)
    assert confidence < 1.0
    assert any("hyphenation-break" in w for w in warnings)


def test_clean_text_scores_full_confidence_with_no_warnings():
    text = "Article 1. The operator shall notify the competent authority within 30 days."
    confidence, warnings = _score_confidence(text)
    assert confidence == 1.0
    assert warnings == []


def test_confidence_threshold_defaults_when_env_unset(monkeypatch):
    monkeypatch.delenv("RABBITQA_PDF_MIN_CONFIDENCE", raising=False)
    assert _confidence_threshold() == 0.5


def test_confidence_threshold_reads_env_override(monkeypatch):
    monkeypatch.setenv("RABBITQA_PDF_MIN_CONFIDENCE", "0.9")
    assert _confidence_threshold() == 0.9
