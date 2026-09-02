"""Step 4: Extract orchestration.

Calls the Extraction Agent and assembles a full ObligationObjectProposal (identity +
source_evidence + legal_semantics + references stub + governance stub), per
rabbitqa_spec_v1.1.0.md §4.1 step 4 and §2.2. clause_id is derived purely from
identity + structural anchor here — never taken from agent output (§2.2 identity
description, and the assert_clause_id_derivation invariant this must satisfy).
"""

from __future__ import annotations

from clause_parser.src.agents.extraction_agent import MODEL_VERSION, PROMPT_VERSION, run_extraction
from clause_parser.src.decompose.decomposer import CandidateSpan


def build_clause_id(document_id: str, source_version: str, span: CandidateSpan) -> str:
    """Pure function of identity + structural anchor — never model output."""
    return f"{document_id}:{source_version}:{span.anchor_id.split(':', 2)[-1]}"


def extract_proposal(
    *,
    span: CandidateSpan,
    document_id: str,
    source_version: str,
    instrument: str,
    language: str,
    anchor_label: str | None,
    controlled_vocabulary: list[str],
    trace_id: str | None = None,
) -> dict:
    clause_id = build_clause_id(document_id, source_version, span)

    agent_output = run_extraction(
        span_text=span.text,
        anchor_id=span.anchor_id,
        anchor_label=anchor_label,
        char_start=span.char_start,
        char_end=span.char_end,
        controlled_vocabulary=controlled_vocabulary,
        trace_id=trace_id,
        clause_id=clause_id,
    )

    return {
        "identity": {
            "document_id": document_id,
            "source_version": source_version,
            "language": language,
            "jurisdiction": "EU",
            "instrument": instrument,
            "clause_id": clause_id,
            "schema_version": "1.0.0",
        },
        "source_evidence": agent_output["source_evidence"],
        "legal_semantics": agent_output["legal_semantics"],
        "references": {
            "definition_links": [],
            "related_articles": [],
            "annex_references": [],
            "resolved_target_ids": [],
        },
        "governance": {
            "field_confidence": {},
            "ambiguity_flag": False,
            "inference_flag": True,
            "model_version": MODEL_VERSION,
            "prompt_version": PROMPT_VERSION,
            "review_status": "pending",
            "revision_history": [],
        },
    }
