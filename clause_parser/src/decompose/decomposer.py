"""Step 3: Decompose.

Per rabbitqa_spec_v1.0.0.md §4.1 step 3: split normative spans into atomic candidate
obligation spans, retaining shared conditions/exceptions via a parent_span_id link;
record whether decomposition used a deterministic method or an LLM in governance
metadata (FR-010).

Baseline (deterministic) strategy: one paragraph-level normative span already IS one
atomic candidate span for the MVP fixture corpus (no further sentence-level splitting
attempted yet) — this is a conservative, honest floor, not a claim of full semantic
decomposition. Each candidate retains parent_span_id = None since paragraph-level
spans in the fixture corpus don't yet exhibit shared-condition patterns requiring
multiple children per span; the field exists so a richer splitter can populate it
later without changing the downstream contract.
"""

from __future__ import annotations

from dataclasses import dataclass

from clause_parser.src.detect.deterministic_detector import DetectionResult


@dataclass(frozen=True)
class CandidateSpan:
    span_id: str
    anchor_id: str
    char_start: int
    char_end: int
    text: str
    parent_span_id: str | None
    decomposition_method: str  # "deterministic" | "llm"


def decompose_normative_spans(
    detections: list[DetectionResult],
) -> list[CandidateSpan]:
    candidates: list[CandidateSpan] = []
    for detection in detections:
        if not detection.is_normative_candidate:
            continue
        candidates.append(
            CandidateSpan(
                span_id=f"{detection.anchor_id}:span-0",
                anchor_id=detection.anchor_id,
                char_start=detection.char_start,
                char_end=detection.char_end,
                text=detection.text,
                parent_span_id=None,
                decomposition_method="deterministic",
            )
        )
    return candidates
