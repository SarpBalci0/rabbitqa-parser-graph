"""POST /v1/documents endpoint.

Per rabbitqa_spec_v1.1.0.md §5.1 (spec_version 1.1.0) and §7 Document ingress zone:
reject uploads exceeding a fixed 25 MB size limit (§7 — not configurable, unlike the
PDF extraction-confidence threshold); validate content-type against an allow-list
including text/plain and application/pdf; run malware scan before persisting;
compute checksum before any parsing step touches the content; for source_format
"pdf", reject at ingress (422) a PDF with no extractable text layer or with
extraction confidence below the configured threshold.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from clause_parser.src.api.errors import BusinessRuleViolation, SchemaValidationHttpError
from clause_parser.src.canonicalize.document_registry import (
    SUPPORTED_SOURCE_FORMATS,
    DocumentVersionConflictError,
    PdfExtractionLowConfidenceError,
    register_document,
)
from clause_parser.src.canonicalize.pdf_extractor import PdfNoTextLayerError
from clause_parser.src.canonicalize.raw_storage import RawStorage
from clause_parser.src.db.document_repository import DocumentRepository
from shared_contracts.py.validation import SchemaValidationError, validate

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25MB — fixed per §7 (spec_version 1.1.0), not configurable.
ALLOWED_CONTENT_TYPES = {".txt", ".xml", ".html", ".pdf"}


class ConflictHttpError(BusinessRuleViolation):
    status_code = 409
    code = "document_version_conflict"


class PdfNoTextLayerHttpError(BusinessRuleViolation):
    code = "PDF_NO_TEXT_LAYER"


class PdfExtractionLowConfidenceHttpError(BusinessRuleViolation):
    code = "PDF_EXTRACTION_LOW_CONFIDENCE"


class DocumentRequest(BaseModel):
    instrument: str
    source_artifact_uri: str
    source_version: str
    source_format: str = "text"


def _read_source_artifact(uri: str) -> bytes:
    """Reads a local file:// or plain-path source artifact. No real external system
    integration is in scope (§1.2 non-goal); a richer fetcher can replace this
    without changing the endpoint contract."""
    parsed = urlparse(uri)
    path = Path(parsed.path if parsed.scheme in ("", "file") else uri)
    return path.read_bytes()


def _malware_scan(raw_bytes: bytes) -> None:
    """Placeholder scan hook per §7 ('run malware scan before persisting'). No real
    scanner is wired in for this pass — this function is the enforced call site so a
    real scanner can be substituted without moving where in the pipeline it runs."""
    return None


def _validate_content_type(uri: str) -> None:
    suffix = Path(urlparse(uri).path or uri).suffix.lower()
    if suffix not in ALLOWED_CONTENT_TYPES:
        raise SchemaValidationHttpError(
            f"Unsupported content type '{suffix}'. Allowed: {sorted(ALLOWED_CONTENT_TYPES)}"
        )


def register_document_handler(request: DocumentRequest, session: Session) -> tuple[dict, int]:
    """Returns (CanonicalDocument payload, http_status). Kept as a plain function
    (rather than an inline route) so it's directly unit-testable without a running
    FastAPI app."""
    if request.source_format not in SUPPORTED_SOURCE_FORMATS:
        raise SchemaValidationHttpError(
            f"Unsupported source_format '{request.source_format}'. "
            f"Allowed: {list(SUPPORTED_SOURCE_FORMATS)}"
        )

    _validate_content_type(request.source_artifact_uri)

    try:
        raw_bytes = _read_source_artifact(request.source_artifact_uri)
    except OSError as exc:
        raise SchemaValidationHttpError(f"checksum cannot be computed: {exc}") from exc

    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        raise SchemaValidationHttpError(
            f"Upload exceeds the fixed {MAX_UPLOAD_BYTES}-byte size limit (§7)."
        )

    _malware_scan(raw_bytes)  # checksum is computed next, inside register_document —
    # malware scan runs before persistence, checksum runs before parsing touches content.

    repository = DocumentRepository(session)
    raw_storage = RawStorage()

    try:
        result = register_document(
            raw_bytes=raw_bytes,
            instrument=request.instrument,
            source_version=request.source_version,
            source_format=request.source_format,
            repository=repository,
            raw_storage=raw_storage,
        )
    except DocumentVersionConflictError as exc:
        raise ConflictHttpError(str(exc)) from exc
    except PdfNoTextLayerError as exc:
        raise PdfNoTextLayerHttpError(str(exc)) from exc
    except PdfExtractionLowConfidenceError as exc:
        raise PdfExtractionLowConfidenceHttpError(
            str(exc), details={"confidence": exc.confidence, "warnings": exc.warnings}
        ) from exc

    payload = {k: v for k, v in result.document_payload.items() if not k.startswith("_")}
    try:
        validate(payload, "CanonicalDocument.schema.json")
    except SchemaValidationError as exc:
        raise SchemaValidationHttpError(str(exc)) from exc

    return payload, (200 if not result.created else 201)


def build_router(session_factory) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/documents", status_code=201)
    def post_document(request: DocumentRequest):
        session = session_factory()
        try:
            payload, status_code = register_document_handler(request, session)
        finally:
            session.close()
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=status_code, content=payload)

    return router
