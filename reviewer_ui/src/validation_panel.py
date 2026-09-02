"""Reviewer workspace validator findings/confidence panel, per
rabbitqa_spec_v1.0.0.md §6.3: "Validator findings and per-field confidence
displayed before the reviewer can submit a decision (MUST NOT allow 'accept' to be
submitted without the ValidationReport having been fetched and rendered in the
same session — this is a UX-level MUST, not enforceable server-side, but the
server MUST independently re-validate on submit regardless of what the UI
showed)."

The server-side re-validation half of this rule is enforced in
clause_parser/src/api/reviews.py (T055) and does not depend on this module at
all — this module implements ONLY the UX-level gate: a per-session guard object
that refuses to let the CLI proceed to an 'accept' submission call until the
ValidationReport for that exact revision has been rendered in this session.
"""

from __future__ import annotations


def render_validation_panel(validation_report: dict) -> str:
    lines = [f"ValidationReport (run_id={validation_report['run_id']}):"]
    for check in validation_report["checks"]:
        lines.append(f"  [{check['status'].upper():^12}] {check['check_name']}: {check['message']}")
    lines.append(f"Overall: {validation_report['overall_status'].upper()}")
    return "\n".join(lines)


class AcceptWithoutValidationViewError(Exception):
    """§6.3 UX-level gate: 'accept' cannot be submitted for a revision whose
    ValidationReport was never fetched/rendered in this CLI session."""


class ReviewSession:
    """Tracks, per CLI session, which revision_ids have had their
    ValidationReport rendered — the UX-level gate §6.3 describes. This is
    deliberately NOT the security boundary (that's the server's independent
    re-validation, T055) — this class exists only to model the UX MUST so it's
    testable, matching the spec's own framing of it as UX-level, not
    security-level."""

    def __init__(self) -> None:
        self._viewed_revision_ids: set[str] = set()

    def view_validation_report(self, revision_id: str, validation_report: dict) -> str:
        self._viewed_revision_ids.add(revision_id)
        return render_validation_panel(validation_report)

    def guard_accept_or_edit(self, revision_id: str) -> None:
        if revision_id not in self._viewed_revision_ids:
            raise AcceptWithoutValidationViewError(
                f"Revision {revision_id}'s ValidationReport must be fetched and "
                "rendered in this session before accept/edit can be submitted."
            )
