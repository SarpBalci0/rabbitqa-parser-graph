"""Fail/needs_review routing rule, per rabbitqa_spec_v1.1.0.md §2.3:

"any fail on evidence_span_fidelity or schema_validity forces overall_status = fail
and the record MUST NOT be presentable to a reviewer for accept/edit — it routes to
escalated automatically. All other single fail(s) force overall_status =
needs_review, which is presentable but flagged."
"""

from __future__ import annotations

_HARD_FAIL_CHECKS = {"evidence_span_fidelity", "schema_validity"}


def compute_overall_status(checks: list[dict]) -> str:
    statuses_by_name = {c["check_name"]: c["status"] for c in checks}

    hard_fail = any(statuses_by_name.get(name) == "fail" for name in _HARD_FAIL_CHECKS)
    if hard_fail:
        return "fail"

    any_other_fail = any(
        status == "fail" for name, status in statuses_by_name.items() if name not in _HARD_FAIL_CHECKS
    )
    if any_other_fail:
        return "needs_review"

    return "pass"


def route_review_status(overall_status: str) -> str:
    """Maps a ValidationReport.overall_status to the initial governance.review_status
    for a freshly-validated proposal. 'fail' -> escalated automatically (never
    presented as ordinary pending work); everything else stays 'pending' (including
    'needs_review', which is presentable but flagged, per §2.3)."""
    if overall_status == "fail":
        return "escalated"
    return "pending"
