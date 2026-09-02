"""clause_parser pipeline: orchestrates §4.1 steps 1-6 in fixed order for every
detected normative span of an already-registered CanonicalDocument. No step is
skippable or reorderable (§4.1 hard rule; step 6 never invokes an LLM).
"""

from __future__ import annotations

import uuid

from clause_parser.src.decompose.decomposer import decompose_normative_spans
from clause_parser.src.detect.deterministic_detector import detect_normative_spans
from clause_parser.src.detect.llm_refinement import apply_refinement
from clause_parser.src.db.obligation_repository import ObligationRepository
from clause_parser.src.extract.extractor import extract_proposal
from clause_parser.src.resolve.resolver import resolve_references
from clause_parser.src.validate.routing import route_review_status
from clause_parser.src.validate.validator import validate_proposal

_DEFAULT_CONTROLLED_VOCABULARY = [
    "operator",
    "essential entity",
    "important entity",
    "competent authority",
    "CSIRT",
    "manufacturer",
    "provider",
]


def run_parse_job(
    document_payload: dict,
    *,
    obligation_repository: ObligationRepository,
    controlled_vocabulary: list[str] | None = None,
    definitions_index: dict[str, str] | None = None,
    trace_id: str | None = None,
) -> dict:
    """Returns a validation_summary dict: {"total", "pass", "needs_review", "fail"}.

    trace_id doubles as the parse job's run_id, stamped onto every ValidationReport
    produced in this run (§7 provenance chain: "parse job run_id... -> ValidationReport").
    Always resolved to a concrete value (generated if the caller doesn't supply one)
    so provenance resolution (compliance_graph/src/export/provenance.py) never finds
    this link unresolvable due to a missing trace_id."""
    trace_id = trace_id or str(uuid.uuid4())
    canonical_text = document_payload["_canonical_text"]
    structure = document_payload["structure"]
    document_id = document_payload["document_id"]
    source_version = document_payload["source_version"]
    instrument = document_payload["instrument"]
    language = document_payload.get("language", "en")

    valid_anchor_ids = {a["anchor_id"] for a in structure}
    controlled_vocabulary = controlled_vocabulary or _DEFAULT_CONTROLLED_VOCABULARY
    definitions_index = definitions_index or {}

    class _AnchorView:
        def __init__(self, d):
            self.anchor_id = d["anchor_id"]
            self.type = d["type"]
            self.label = d.get("label")
            self.char_start = d["char_start"]
            self.char_end = d["char_end"]

    anchor_views = [_AnchorView(a) for a in structure]

    # Step 2: Detect (deterministic baseline logged separately from any refinement).
    baseline_detections = detect_normative_spans(canonical_text, anchor_views)
    baseline_detections, refined_detections = apply_refinement(baseline_detections)

    # Step 3: Decompose.
    candidate_spans = decompose_normative_spans(refined_detections)

    label_by_anchor = {a.anchor_id: a.label for a in anchor_views}

    summary = {"total": 0, "pass": 0, "needs_review": 0, "fail": 0}

    for span in candidate_spans:
        # Step 4: Extract.
        proposal = extract_proposal(
            span=span,
            document_id=document_id,
            source_version=source_version,
            instrument=instrument,
            language=language,
            anchor_label=label_by_anchor.get(span.anchor_id),
            controlled_vocabulary=controlled_vocabulary,
            trace_id=trace_id,
        )

        # Step 5: Resolve.
        proposal = resolve_references(
            proposal,
            definitions_index=definitions_index,
            candidate_mentions=[],
            trace_id=trace_id,
        )

        # Step 6: Validate (no LLM).
        report = validate_proposal(
            proposal, canonical_text=canonical_text, valid_anchor_ids=valid_anchor_ids, run_id=trace_id
        )
        proposal["governance"]["review_status"] = route_review_status(report["overall_status"])

        obligation_repository.create_revision(proposal, report)

        summary["total"] += 1
        summary[report["overall_status"]] = summary.get(report["overall_status"], 0) + 1

    return summary
