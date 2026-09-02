"""Optional LLM-assisted detection refinement, layered on top of the deterministic
baseline (clause_parser/src/detect/deterministic_detector.py) — per §4.1 step 2 the
deterministic pass always runs first and its output is logged separately; this
refinement never replaces it, only adds candidates the baseline may have missed.

No live LLM call is wired in for this MVP pass (research.md §7: no live LLM calls
in CI). This module defines the seam so a real llm_gateway-mediated call can be
plugged in later without changing the pipeline's step ordering.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Callable

from clause_parser.src.detect.deterministic_detector import DetectionResult

RefinementFn = Callable[[list[DetectionResult]], list[DetectionResult]]


def identity_refinement(baseline_results: list[DetectionResult]) -> list[DetectionResult]:
    """Default no-op refinement: returns the deterministic baseline unchanged.
    A real refinement function would only ever add is_normative_candidate=True
    flips on top of this — it MUST NOT remove or override the logged baseline pass."""
    return [replace(r) for r in baseline_results]


def apply_refinement(
    baseline_results: list[DetectionResult], refine_fn: RefinementFn | None = None
) -> tuple[list[DetectionResult], list[DetectionResult]]:
    """Returns (baseline_results, refined_results) so callers can log the baseline
    pass separately from the refined output, per §4.1's requirement."""
    refine_fn = refine_fn or identity_refinement
    refined = refine_fn(baseline_results)
    return baseline_results, refined
