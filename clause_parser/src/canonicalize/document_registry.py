"""Checksum computation + content-based idempotent document registration.

Per rabbitqa_spec_v1.1.0.md FR-001/FR-002 and §9.1 Ingestion scenario: registering
byte-identical content twice for the same instrument resolves to the same
document_id; the second call is a lookup, not a new record.

Per §2.1 (spec_version 1.1.0): when source_format is "pdf", PDF text extraction
(clause_parser.src.canonicalize.pdf_extractor) MUST run before canonicalization,
and a low-confidence or empty extraction MUST block registration entirely — see
PdfNoTextLayerError / PdfExtractionLowConfidenceError below.
"""

from __future__ import annotations

import hashlib
import random
import string
from datetime import datetime, timezone

from clause_parser.src.canonicalize.canonicalizer import build_structure, canonicalize_text
from clause_parser.src.canonicalize.pdf_extractor import (
    PdfNoTextLayerError,
    extract_pdf_text,
    _confidence_threshold,
)
from clause_parser.src.canonicalize.raw_storage import RawStorage
from clause_parser.src.db.document_repository import DocumentRepository

SUPPORTED_SOURCE_FORMATS = ("text", "pdf")


class DocumentVersionConflictError(Exception):
    """Raised per §5.1 (spec_version 1.0.2): the (instrument, source_version) is
    already registered with DIFFERENT content. A pinned source_version is immutable
    once registered — the caller must use a new source_version for revised content."""

    def __init__(self, instrument: str, source_version: str):
        self.instrument = instrument
        self.source_version = source_version
        super().__init__(
            f"({instrument}, {source_version}) is already registered with different content; "
            "a pinned source_version is immutable — register revised content under a new source_version."
        )


class PdfExtractionLowConfidenceError(Exception):
    """Raised per §5.1 (spec_version 1.1.0): PDF text was extracted but the
    deterministic extraction step's confidence fell below the configured
    threshold. Registration MUST fail rather than silently persist unreliable
    text — this is a hard gate, not a warning."""

    def __init__(self, confidence: float, threshold: float, warnings: list[str]):
        self.confidence = confidence
        self.threshold = threshold
        self.warnings = warnings
        super().__init__(
            f"PDF extraction confidence {confidence:.2f} is below the configured "
            f"threshold {threshold:.2f}; warnings: {warnings}"
        )


def compute_checksum(raw_bytes: bytes) -> str:
    return hashlib.sha256(raw_bytes).hexdigest()


def _generate_document_id() -> str:
    """document_id itself is an opaque identifier (pattern doc_[a-z0-9]{12}); it is
    NOT the pure-function anchor_id (that's derived from document_id+source_version+
    structural_path per §2.1). Generated once at first registration and then reused
    for every subsequent lookup of the same content."""
    alphabet = string.ascii_lowercase + string.digits
    suffix = "".join(random.choices(alphabet, k=12))
    return f"doc_{suffix}"


class RegistrationResult:
    def __init__(self, document_payload: dict, created: bool):
        self.document_payload = document_payload
        self.created = created


def register_document(
    *,
    raw_bytes: bytes,
    instrument: str,
    source_version: str,
    language: str = "en",
    source_format: str = "text",
    repository: DocumentRepository,
    raw_storage: RawStorage,
) -> RegistrationResult:
    if source_format not in SUPPORTED_SOURCE_FORMATS:
        raise ValueError(f"Unsupported source_format: {source_format!r}")

    checksum = compute_checksum(raw_bytes)

    existing = repository.get_by_checksum(checksum, instrument, source_version)
    if existing is not None:
        return RegistrationResult(existing, created=False)

    conflicting = repository.get_by_instrument_and_source_version(instrument, source_version)
    if conflicting is not None:
        raise DocumentVersionConflictError(instrument, source_version)

    # §2.1 (spec_version 1.1.0): PDF extraction MUST run before canonicalization,
    # and MUST gate registration entirely on failure/low confidence — before any
    # document_id is generated or raw bytes are persisted.
    extraction_metadata = None
    if source_format == "pdf":
        extraction = extract_pdf_text(raw_bytes)  # raises PdfNoTextLayerError on empty extraction
        threshold = _confidence_threshold()
        if extraction.confidence < threshold:
            raise PdfExtractionLowConfidenceError(
                confidence=extraction.confidence, threshold=threshold, warnings=extraction.warnings
            )
        source_text = extraction.text
        extraction_metadata = {
            "extraction_method": extraction.extraction_method,
            "confidence": extraction.confidence,
            "warnings": extraction.warnings,
        }
    else:
        source_text = raw_bytes.decode("utf-8")

    document_id = _generate_document_id()
    raw_extension = "pdf" if source_format == "pdf" else "txt"
    raw_key = f"{document_id}/{source_version}/source.{raw_extension}"
    raw_uri = raw_storage.put(raw_key, raw_bytes)

    canonical_text = canonicalize_text(source_text)
    structure = build_structure(canonical_text, document_id=document_id, source_version=source_version)

    payload = {
        "document_id": document_id,
        "source_version": source_version,
        "instrument": instrument,
        "checksum_sha256": checksum,
        "language": language,
        "jurisdiction": "EU",
        "structure": [
            {
                "anchor_id": a.anchor_id,
                "type": a.type,
                "label": a.label,
                "char_start": a.char_start,
                "char_end": a.char_end,
                "parent_anchor_id": a.parent_anchor_id,
            }
            for a in structure
        ],
        "raw_storage_uri": raw_uri,
        "source_format": source_format,
        "extraction_metadata": extraction_metadata,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": "1.1.0",
        # Not part of the CanonicalDocument schema; kept alongside for pipeline use.
        "_canonical_text": canonical_text,
    }
    repository.create(payload)
    return RegistrationResult(payload, created=True)
