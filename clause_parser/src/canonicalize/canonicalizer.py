"""Step 1: Canonicalize. Deterministic, no LLM.

Per rabbitqa_spec_v1.0.0.md §4.1 step 1 and §2.1 invariants:
- Canonicalization normalizes whitespace/encoding only; it MUST NOT alter legal
  text content.
- anchor_id generation MUST be a pure function of (document_id, source_version,
  structural_path) — never model output, run timestamp, or randomness. Re-ingesting
  identical source content MUST yield byte-identical anchor_ids.

This is a minimal but real deterministic structural splitter recognizing
"Article N" / numbered-paragraph patterns typical of EU legal instruments, sufficient
to exercise the pipeline end-to-end on fixture text. It is intentionally simple
(regex-based) rather than a full legal-document parser — extending its coverage
(annexes, tables, footnotes, recitals beyond the basic pattern) is future work, not
a silently-invented behavior: unmatched text becomes a single top-level "article"
anchor spanning the whole document so no content is ever dropped.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_ARTICLE_RE = re.compile(r"^Article\s+(\d+[a-zA-Z]?)(?:\s*\(.*\))?\s*$", re.MULTILINE)
_PARAGRAPH_RE = re.compile(r"^(\d+)\.\s+", re.MULTILINE)
_ANNEX_HEADING_RE = re.compile(r"^Annex\s+[IVXLCDM]+\b", re.MULTILINE)


@dataclass(frozen=True)
class AnchorNode:
    anchor_id: str
    type: str
    label: str | None
    char_start: int
    char_end: int
    parent_anchor_id: str | None


def canonicalize_text(raw_text: str) -> str:
    """Whitespace/encoding normalization only — never alters legal text content."""
    normalized = unicodedata.normalize("NFC", raw_text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse trailing whitespace on each line; collapse 3+ blank lines to 2.
    lines = [line.rstrip() for line in normalized.split("\n")]
    normalized = "\n".join(lines)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip("\n") + "\n"


def _make_anchor_id(document_id: str, source_version: str, structural_path: str) -> str:
    """Pure function of (document_id, source_version, structural_path) only."""
    return f"{document_id}:{source_version}:{structural_path}"


def build_structure(
    canonical_text: str, *, document_id: str, source_version: str
) -> list[AnchorNode]:
    """Splits canonical_text into article-level anchors, then paragraph-level
    anchors nested under each article, using deterministic regex matching only."""
    article_matches = list(_ARTICLE_RE.finditer(canonical_text))
    anchors: list[AnchorNode] = []

    if not article_matches:
        anchors.append(
            AnchorNode(
                anchor_id=_make_anchor_id(document_id, source_version, "document"),
                type="article",
                label=None,
                char_start=0,
                char_end=len(canonical_text),
                parent_anchor_id=None,
            )
        )
        return anchors

    # First "Annex N" heading, if any, caps the LAST recognized article's span.
    # Found via real corpus testing: without this, an article immediately
    # followed by an annex (annexes are NOT recognized as their own anchor type
    # by this module — see this function's own module docstring) had its last
    # paragraph's span run all the way to end-of-document, SILENTLY SWALLOWING
    # the entire annex text (including any tables) into that paragraph's own
    # verbatim_text/evidence_hash — real evidence contamination, not just a
    # missing-anchor-type gap: the clause's evidence no longer faithfully
    # represents only that clause. Annexes still get no anchor of their own
    # (still future work, per this module's existing documented limitation),
    # but article/paragraph spans no longer run past the boundary.
    first_annex_match = _ANNEX_HEADING_RE.search(canonical_text)
    document_ceiling = first_annex_match.start() if first_annex_match else len(canonical_text)

    for idx, match in enumerate(article_matches):
        article_number = match.group(1)
        article_start = match.start()
        article_end = (
            min(article_matches[idx + 1].start(), document_ceiling)
            if idx + 1 < len(article_matches)
            else document_ceiling
        )
        article_path = f"article-{article_number}"
        article_anchor_id = _make_anchor_id(document_id, source_version, article_path)
        anchors.append(
            AnchorNode(
                anchor_id=article_anchor_id,
                type="article",
                label=f"Article {article_number}",
                char_start=article_start,
                char_end=article_end,
                parent_anchor_id=None,
            )
        )
        anchors.extend(
            _build_paragraph_anchors(
                canonical_text,
                article_start=article_start,
                article_end=article_end,
                document_id=document_id,
                source_version=source_version,
                article_path=article_path,
                article_anchor_id=article_anchor_id,
            )
        )

    _assert_no_anchor_id_collisions(anchors)
    return anchors


class AnchorIdCollisionError(Exception):
    """§2.2 invariant 3 requires clause_id (built from anchor_id) to be globally
    unique per (document_id, source_version). Found via real corpus testing: an
    article heading format _ARTICLE_RE didn't recognize (e.g. a parenthetical
    suffix like "Article 4 (Amendment to Article 1)") caused that article's
    content to be silently absorbed into the PRECEDING recognized article, with
    paragraph numbering restarting at "1." — producing a genuine duplicate
    anchor_id with no error anywhere. Fixed at the regex level (see _ARTICLE_RE),
    but this is a second, structural guard: any future heading format this
    module's regexes don't anticipate now fails loudly here instead of silently
    corrupting anchor_id uniqueness downstream."""


def _assert_no_anchor_id_collisions(anchors: list[AnchorNode]) -> None:
    seen: dict[str, AnchorNode] = {}
    for anchor in anchors:
        if anchor.anchor_id in seen:
            raise AnchorIdCollisionError(
                f"anchor_id collision: '{anchor.anchor_id}' produced by both "
                f"[{seen[anchor.anchor_id].char_start}:{seen[anchor.anchor_id].char_end}] "
                f"and [{anchor.char_start}:{anchor.char_end}] — a heading format in the "
                "source text was not recognized by this module's article/paragraph "
                "regexes, causing content to be misattributed to the wrong article."
            )
        seen[anchor.anchor_id] = anchor


def _build_paragraph_anchors(
    canonical_text: str,
    *,
    article_start: int,
    article_end: int,
    document_id: str,
    source_version: str,
    article_path: str,
    article_anchor_id: str,
) -> list[AnchorNode]:
    body = canonical_text[article_start:article_end]
    para_matches = list(_PARAGRAPH_RE.finditer(body))
    anchors: list[AnchorNode] = []
    for idx, match in enumerate(para_matches):
        para_number = match.group(1)
        para_start = article_start + match.start()
        para_end = (
            article_start + para_matches[idx + 1].start()
            if idx + 1 < len(para_matches)
            else article_end
        )
        para_path = f"{article_path}/paragraph-{para_number}"
        anchors.append(
            AnchorNode(
                anchor_id=_make_anchor_id(document_id, source_version, para_path),
                type="paragraph",
                label=f"Article {article_path.split('-')[-1]}({para_number})",
                char_start=para_start,
                char_end=para_end,
                parent_anchor_id=article_anchor_id,
            )
        )
    return anchors
