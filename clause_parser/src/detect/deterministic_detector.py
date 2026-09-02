"""Step 2: Detect (deterministic baseline).

Per rabbitqa_spec_v1.1.0.md §4.1 step 2: "Deterministic classifier baseline
REQUIRED; LLM-assisted refinement MAY be layered on top but the deterministic
pass MUST run first and its output MUST be logged separately."

Baseline heuristic: a paragraph-level anchor is a normative-passage candidate if its
text contains a modal verb from the controlled modality vocabulary (shall/must/may/
should); everything else is a hard negative. This is intentionally simple — it is the
deterministic floor the pipeline requires, not a claim of full recall.
"""

from __future__ import annotations

from dataclasses import dataclass

_MODAL_PATTERN = None


def _modal_words() -> tuple[str, ...]:
    return ("shall", "must", "may", "should")


@dataclass(frozen=True)
class DetectionResult:
    anchor_id: str
    char_start: int
    char_end: int
    text: str
    is_normative_candidate: bool
    matched_modal: str | None


def detect_normative_spans(
    canonical_text: str, paragraph_anchors: list
) -> list[DetectionResult]:
    """paragraph_anchors: list of AnchorNode (or dict-like) with anchor_id, char_start,
    char_end, type == 'paragraph'."""
    results: list[DetectionResult] = []
    modals = _modal_words()
    for anchor in paragraph_anchors:
        anchor_type = anchor.type if hasattr(anchor, "type") else anchor["type"]
        if anchor_type != "paragraph":
            continue
        char_start = anchor.char_start if hasattr(anchor, "char_start") else anchor["char_start"]
        char_end = anchor.char_end if hasattr(anchor, "char_end") else anchor["char_end"]
        anchor_id = anchor.anchor_id if hasattr(anchor, "anchor_id") else anchor["anchor_id"]
        text = canonical_text[char_start:char_end]
        lowered = text.lower()
        matched = next((m for m in modals if f" {m} " in f" {lowered} "), None)
        results.append(
            DetectionResult(
                anchor_id=anchor_id,
                char_start=char_start,
                char_end=char_end,
                text=text,
                is_normative_candidate=matched is not None,
                matched_modal=matched,
            )
        )
    return results
