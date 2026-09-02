"""Step 5: Resolve.

Per rabbitqa_spec_v1.1.0.md §4.1 step 5: deterministic normalizers (dates/
quantities) + Reference Agent-backed reference resolution, populating the
`references` block and normalizing legal_semantics.deadline.normalized_iso.
"""

from __future__ import annotations

import re

from clause_parser.src.agents.reference_agent import run_reference_resolution

_RELATIVE_DEADLINE_RE = re.compile(r"within\s+(\d+)\s+(hour|day|month|year)s?", re.IGNORECASE)
_ABSOLUTE_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_ARTICLE_MENTION_RE = re.compile(r"Article\s+\d+[a-zA-Z]?(?:\(\d+\))?")

# ISO-8601 duration: date components (D/M/Y) go directly after 'P'; time
# components (H/min/sec) require the 'T' time-designator, i.e. 'PT24H' not
# 'P24H'. Found and fixed during corpus expansion: the original code only
# recognized day/month/year and would have produced an invalid duration
# ('P24H') had 'hour' simply been added to the same bucket — several real
# clauses in this corpus use hour-based deadlines ('within 72 hours').
_DATE_UNIT_TO_ISO = {"day": "D", "month": "M", "year": "Y"}
_TIME_UNIT_TO_ISO = {"hour": "H"}


def extract_related_articles(text: str) -> list[str]:
    """Deterministic cross-reference detection (no LLM, no Reference Agent):
    finds literal 'Article N' / 'Article N(M)' mentions in the verbatim text and
    populates references.related_articles. This is intentionally simpler than
    the Reference Agent's resolved_target_ids (which needs a definitions_index
    and turns a mention into a resolved anchor_id) — related_articles is just
    the literal mention strings found in the source text, deduplicated in
    order of first appearance."""
    seen: list[str] = []
    for match in _ARTICLE_MENTION_RE.finditer(text):
        mention = match.group(0)
        if mention not in seen:
            seen.append(mention)
    return seen


def normalize_deadline(text: str) -> dict | None:
    """Deterministic date/quantity normalization (no LLM)."""
    absolute = _ABSOLUTE_DATE_RE.search(text)
    if absolute:
        return {
            "type": "absolute_date",
            "value": absolute.group(0),
            "normalized_iso": absolute.group(0),
        }
    relative = _RELATIVE_DEADLINE_RE.search(text)
    if relative:
        amount, unit = relative.group(1), relative.group(2).lower()
        if unit in _TIME_UNIT_TO_ISO:
            normalized_iso = f"PT{amount}{_TIME_UNIT_TO_ISO[unit]}"
        else:
            normalized_iso = f"P{amount}{_DATE_UNIT_TO_ISO.get(unit, 'D')}"
        return {
            "type": "relative_period",
            "value": relative.group(0),
            "normalized_iso": normalized_iso,
        }
    return None


def resolve_references(
    proposal: dict,
    *,
    definitions_index: dict[str, str],
    candidate_mentions: list[str],
    trace_id: str | None = None,
) -> dict:
    """Populates references.resolved_target_ids via the Reference Agent, and
    legal_semantics.deadline.normalized_iso via deterministic normalization.
    Returns a new proposal dict (does not mutate the input)."""
    resolved = dict(proposal)
    legal_semantics = dict(resolved["legal_semantics"])

    action_and_object = f"{legal_semantics.get('action', '')} {legal_semantics.get('object', '')}"
    deadline = normalize_deadline(action_and_object)
    if deadline is not None:
        legal_semantics["deadline"] = deadline
    resolved["legal_semantics"] = legal_semantics

    verbatim_text = proposal["source_evidence"]["verbatim_text"]
    related_articles = extract_related_articles(verbatim_text)
    if related_articles:
        references = dict(resolved.get("references", {}))
        references["related_articles"] = related_articles
        resolved["references"] = references

    if candidate_mentions:
        reference_output = run_reference_resolution(
            definitions_index=definitions_index,
            candidate_mentions=candidate_mentions,
            document_text_excerpt=proposal["source_evidence"]["verbatim_text"],
            trace_id=trace_id,
            clause_id=proposal.get("identity", {}).get("clause_id"),
        )
        references = dict(resolved.get("references", {}))
        references["resolved_target_ids"] = [
            c["target_anchor_id"] for c in reference_output["candidates"]
        ]
        resolved["references"] = references

    return resolved
