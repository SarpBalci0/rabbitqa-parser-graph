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

import functools
import io
import os
import re
from dataclasses import dataclass, field

import pypdf

DEFAULT_CONFIDENCE_THRESHOLD = 0.5
_HYPHEN_BREAK_RE = re.compile(r"[a-z]-\n[a-z]")
# §2.1 (spec_version 1.1.2/1.1.3): a mid-word break with NO hyphen (e.g. a
# fixed-width PDF layout wrapping "remote" as "remo" + line break + "te") is not
# caught by _HYPHEN_BREAK_RE, since there is no hyphen to key off — but it's the
# same broken-word risk. Flag it (lower confidence, add a warning); never attempt
# to rejoin, since a legitimate line-final word immediately followed by a line-
# initial word looks identical to this pattern and rejoining could silently
# alter legal text content (see §2.1 invariants).
#
# Raw presence of this pattern is a bad signal on its own: an empirical scan
# (spec_version 1.1.3, see rabbitqa_spec_v1.1.0.md §12 changelog) against 26
# real-world PDFs plus a real prose-style report PDF found this pattern also
# fires on two ordinary, correctly-spelled adjacent words that pypdf extracted
# without a space at the line-wrap boundary (very common: "a"+"condition",
# "computer"+"main") — 82-99.8% of raw matches were this kind of false
# positive, not a genuinely broken word. A dictionary check disambiguates the
# two cases the same way a human would: a genuinely broken word's left fragment
# ("remo") is not itself a real word, while a false positive's left fragment
# ("a", "computer") already is one.
_BROKEN_WORD_RE = re.compile(r"[a-z]\n[a-z]")
_LEFT_WORD_RUN_RE = re.compile(r"[a-z]+$")
_RIGHT_WORD_RUN_RE = re.compile(r"^[a-z]+")
_DICTIONARY_PATHS = (
    "/usr/share/dict/words",
    "/usr/share/dict/american-english",
    "/usr/share/dict/british-english",
    "/usr/dict/words",
)
_REPLACEMENT_CHAR = "�"


@functools.lru_cache(maxsize=1)
def _load_word_dictionary() -> frozenset[str] | None:
    """Best-effort: use a system word list to disambiguate a genuinely broken
    word from two ordinary words pypdf extracted without an inter-line space,
    per the false-positive analysis above. Returns None if no known dictionary
    file is present on this host — callers MUST fall back to the conservative,
    lower-precision presence-only check in that case (see _classify_broken_word_
    matches), never silently skip the check altogether. This is a deliberate,
    documented determinism trade-off (see rabbitqa_spec_v1.1.0.md §2.1,
    spec_version 1.1.3): the confidence score for a given PDF byte-for-byte
    input can differ across hosts depending on dictionary availability."""
    for path in _DICTIONARY_PATHS:
        if os.path.exists(path):
            try:
                with open(path, encoding="latin-1") as f:
                    return frozenset(line.strip().lower() for line in f if line.strip())
            except OSError:
                continue
    return None


def _classify_broken_word_matches(text: str) -> tuple[list[tuple[str, str]], bool]:
    """Returns (likely_genuine_breaks, dictionary_available). When a dictionary
    is available, a match is kept only if the rejoined fragment is a real word
    AND the left fragment alone is not (i.e. it doesn't already stand on its
    own) — see the false-positive analysis above _BROKEN_WORD_RE. When no
    dictionary is available, every raw match is kept (the old, low-precision
    behavior) so the check still fires rather than going silent."""
    dictionary = _load_word_dictionary()
    matches = list(_BROKEN_WORD_RE.finditer(text))
    if dictionary is None:
        return [(m.group(0)[0], m.group(0)[-1]) for m in matches], False

    kept: list[tuple[str, str]] = []
    for m in matches:
        break_idx = m.start() + 1
        left_run = _LEFT_WORD_RUN_RE.search(text[:break_idx])
        right_run = _RIGHT_WORD_RUN_RE.search(text[break_idx + 1 :])
        left = left_run.group(0) if left_run else ""
        right = right_run.group(0) if right_run else ""
        joined = left + right
        if joined in dictionary and left not in dictionary:
            kept.append((left, right))
    return kept, True


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

    broken_word_matches, dictionary_available = _classify_broken_word_matches(text)
    if broken_word_matches:
        if dictionary_available:
            warnings.append("possible broken word (mid-word line break without hyphen)")
        else:
            warnings.append(
                "possible broken word (mid-word line break without hyphen) — "
                "no system dictionary available on this host to distinguish a "
                "genuine break from two ordinary adjacent words; low precision"
            )
        confidence -= 0.2

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
