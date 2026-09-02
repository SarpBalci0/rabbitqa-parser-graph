"""PDF text extraction — a distinct, deterministic step that MUST run before
canonicalization, never inside it.

Per rabbitqa_spec_v1.1.0.md §2.1 (spec_version 1.1.0): PDF text extraction MUST be
deterministic (no LLM call), and MUST produce an `extraction_metadata.confidence`
score and any `warnings` as part of the same step. A PDF with no extractable text
layer (scanned/image-only) or with confidence below a configured threshold MUST
NOT be canonicalized or registered — see §5.1's PDF_NO_TEXT_LAYER /
PDF_EXTRACTION_LOW_CONFIDENCE error cases. OCR MUST NOT be attempted (§1.2
non-goal); this module never falls back to it.

Confidence is a deterministic heuristic over the extracted text only (no model
call): it penalizes signals that indicate the text layer is unreliable —
Unicode replacement characters (font/encoding corruption), a high ratio of
non-printable characters, and mid-word hyphenation breaks or short average line
lengths suggestive of multi-column reordering. This is intentionally simple
(consistent with every other fixture/deterministic pass in this codebase, e.g.
clause_parser/src/agents/extraction_agent.py) rather than a real layout/OCR
quality model — extending it is future work, not silently invented behavior.
"""

from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass, field

import pypdf

DEFAULT_CONFIDENCE_THRESHOLD = 0.5
_HYPHEN_BREAK_RE = re.compile(r"[a-z]-\n[a-z]")
_REPLACEMENT_CHAR = "�"


class PdfNoTextLayerError(Exception):
    """Raised when zero characters of text can be extracted from the PDF (the
    scanned/image-only case). Per §5.1, this MUST map to a 422
    PDF_NO_TEXT_LAYER response and MUST NOT create a CanonicalDocument."""


@dataclass(frozen=True)
class PdfExtractionResult:
    text: str
    confidence: float
    warnings: list[str] = field(default_factory=list)
    extraction_method: str = f"pypdf-{pypdf.__version__}"


def _confidence_threshold() -> float:
    """Deliberately left as a configuration decision (§7), consistent with how
    the LLM provider allow-list is handled (§10) — reads
    RABBITQA_PDF_MIN_CONFIDENCE if set, else DEFAULT_CONFIDENCE_THRESHOLD."""
    raw = os.environ.get("RABBITQA_PDF_MIN_CONFIDENCE")
    if raw is None:
        return DEFAULT_CONFIDENCE_THRESHOLD
    return float(raw)


def _score_confidence(text: str) -> tuple[float, list[str]]:
    warnings: list[str] = []
    confidence = 1.0

    if _REPLACEMENT_CHAR in text:
        warnings.append("replacement characters detected — possible font/encoding corruption")
        confidence -= 0.4

    non_printable = sum(1 for ch in text if not ch.isprintable() and ch not in "\n\t")
    if len(text) > 0 and non_printable / len(text) > 0.02:
        warnings.append("high ratio of non-printable characters detected")
        confidence -= 0.3

    if _HYPHEN_BREAK_RE.search(text):
        warnings.append("hyphenation-break artifacts detected")
        confidence -= 0.15

    lines = [line for line in text.split("\n") if line.strip()]
    if lines:
        avg_len = sum(len(line) for line in lines) / len(lines)
        if avg_len < 25:
            warnings.append("short average line length — possible multi-column reordering")
            confidence -= 0.15

    return max(0.0, min(1.0, confidence)), warnings


def extract_pdf_text(raw_bytes: bytes) -> PdfExtractionResult:
    """Deterministic PDF text extraction. Raises PdfNoTextLayerError if zero
    characters are extracted. Never attempts OCR (§1.2 non-goal) — a PDF with
    no text layer is a rejection, not an OCR trigger."""
    reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
    page_texts = [page.extract_text() or "" for page in reader.pages]
    text = "\n\n".join(page_texts)

    if not text.strip():
        raise PdfNoTextLayerError(
            "No extractable text layer found in PDF (scanned/image-only document). "
            "OCR is out of scope for v1 (§1.2) — this is a rejection, not a fallback."
        )

    confidence, warnings = _score_confidence(text)
    return PdfExtractionResult(text=text, confidence=confidence, warnings=warnings)
