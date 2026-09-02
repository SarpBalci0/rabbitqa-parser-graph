"""Unit tests for canonicalization idempotency, checksum computation, and
anchor_id purity, per tasks.md T101 (§2.1 invariants).

Note: anchor_id idempotency across a full document is already covered end-to-end
by clause_parser/tests/integration/test_anchor_id_idempotency.py — this file adds
focused unit coverage for checksum computation specifically (not otherwise directly
unit-tested; only exercised indirectly via document_registry integration tests) plus
the pure-function property of _make_anchor_id in isolation.
"""

import hashlib

import pytest

from clause_parser.src.canonicalize.canonicalizer import (
    AnchorIdCollisionError,
    build_structure,
    canonicalize_text,
)
from clause_parser.src.canonicalize.document_registry import compute_checksum


def test_compute_checksum_matches_hashlib_sha256():
    content = b"Article 1\n1. The operator shall act.\n"
    assert compute_checksum(content) == hashlib.sha256(content).hexdigest()


def test_compute_checksum_is_deterministic():
    content = b"same bytes every time"
    assert compute_checksum(content) == compute_checksum(content)


def test_compute_checksum_differs_for_different_content():
    assert compute_checksum(b"content A") != compute_checksum(b"content B")


def test_canonicalize_text_is_idempotent():
    """Canonicalizing already-canonical text is a no-op — a second pass MUST NOT
    keep transforming it (would break re-ingestion byte-identity)."""
    raw = "Article 1\r\n1. Text with\r\nCRLF line endings.\n\n\n\nExtra blank lines.\n"
    once = canonicalize_text(raw)
    twice = canonicalize_text(once)
    assert once == twice


def test_canonicalize_text_normalizes_line_endings_and_blank_lines():
    raw = "line one\r\nline two\n\n\n\nline three\n"
    result = canonicalize_text(raw)
    assert "\r" not in result
    assert "\n\n\n" not in result


def test_anchor_id_is_pure_function_of_document_id_source_version_and_text_only():
    """Building structure twice from identical (canonical_text, document_id,
    source_version) inputs yields byte-identical anchor_ids — no dependency on
    call order, timing, or any other hidden state."""
    text = canonicalize_text("Article 5\n1. Some obligation text here.\n")
    first = build_structure(text, document_id="doc_stable123", source_version="v9")
    second = build_structure(text, document_id="doc_stable123", source_version="v9")
    assert [a.anchor_id for a in first] == [a.anchor_id for a in second]


def test_anchor_id_changes_only_when_a_component_changes():
    text = canonicalize_text("Article 5\n1. Some obligation text here.\n")
    base = build_structure(text, document_id="doc_a", source_version="v1")
    diff_doc = build_structure(text, document_id="doc_b", source_version="v1")
    diff_version = build_structure(text, document_id="doc_a", source_version="v2")

    base_ids = {a.anchor_id for a in base}
    assert base_ids.isdisjoint({a.anchor_id for a in diff_doc})
    assert base_ids.isdisjoint({a.anchor_id for a in diff_version})


def test_article_heading_with_parenthetical_suffix_gets_its_own_anchor():
    """Regression test for a real bug found via evaluation/corpus/ testing:
    '_ARTICLE_RE' required the whole line to be exactly 'Article N', so a heading
    like 'Article 4 (Amendment to Article 1)' was never recognized — its content
    was silently absorbed into the PRECEDING article, and paragraph numbering
    restarted at '1.', producing a genuine duplicate anchor_id (a §2.2 invariant
    3 violation) with no error anywhere. Confirms the fix: the heading now gets
    its own anchor, and no collision occurs."""
    text = canonicalize_text(
        "Article 3\n\n1. First article's paragraph.\n\n"
        "Article 4 (Amendment to Article 1)\n\n1. Amendment text here.\n"
    )
    structure = build_structure(text, document_id="doc_x", source_version="v1")
    paths = [a.anchor_id.split(":", 2)[-1] for a in structure]

    assert "article-4" in paths
    assert "article-4/paragraph-1" in paths
    assert paths.count("article-3/paragraph-1") == 1  # not duplicated by the absorbed content
    assert len(paths) == len(set(paths))  # no collisions at all


def test_last_article_span_does_not_swallow_a_trailing_annex():
    """Regression test for a real evidence-contamination bug found via
    evaluation/corpus/ testing: without an annex-heading boundary, the LAST
    recognized article's last paragraph span ran to end-of-document, silently
    including an entire trailing Annex (heading + table) inside that
    paragraph's own verbatim_text/evidence_hash — not just a missing anchor
    type, but the clause's evidence no longer faithfully representing only
    that clause."""
    text = canonicalize_text(
        "Article 1\n\n1. Some obligation text.\n\n"
        "Annex I — Illustrative Table\n\n| Field | Value |\n|---|---|\n| A | B |\n"
    )
    structure = build_structure(text, document_id="doc_x", source_version="v1")
    last_paragraph = [a for a in structure if "paragraph-1" in a.anchor_id][0]
    span_text = text[last_paragraph.char_start : last_paragraph.char_end]
    assert "Annex I" not in span_text
    assert "Illustrative Table" not in span_text


def test_anchor_id_collision_raises_loudly_not_silently():
    """Defense-in-depth: even for a heading format not anticipated by any regex
    fix, a collision must fail loudly rather than silently corrupt anchor_id
    uniqueness. Constructed directly via a duplicate-producing scenario the
    regex genuinely cannot distinguish (two articles both literally named
    'Article 1', which is a legitimate thing for THIS guard to catch even though
    it's a different root cause than the parenthetical-heading bug above)."""
    text = canonicalize_text("Article 1\n\n1. First.\n\nArticle 1\n\n1. Second, duplicate heading.\n")
    with pytest.raises(AnchorIdCollisionError):
        build_structure(text, document_id="doc_x", source_version="v1")
