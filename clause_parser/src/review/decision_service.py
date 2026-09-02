"""Reviewer decision application: accept, edit, reject, escalate.

Per rabbitqa_spec_v1.1.0.md §5.5 and §9.1 Review scenarios:
- rationale MUST be non-empty (400 otherwise) — FR-015.
- edit REQUIRES non-null edits and MUST re-run ValidationReport on the edited
  version before persisting — an edit that fails evidence-span fidelity is
  rejected with 422, not silently accepted (FR-016).
- every accept/edit records a revision_history entry in the same operation as the
  status change (FR-014) — enforced at the repository layer (ObligationRepository.
  apply_decision, see clause_parser/src/db/obligation_repository.py), which this
  service calls rather than writing to the table directly.
"""

from __future__ import annotations

from datetime import datetime, timezone

from clause_parser.src.db.obligation_repository import ObligationRepository
from clause_parser.src.review.diff import apply_edits_to_proposal, compute_diff
from clause_parser.src.validate.validator import validate_proposal

_ACTION_TO_STATUS = {
    "accept": "accepted",
    "edit": "edited",
    "reject": "rejected",
    "escalate": "escalated",
}


class EmptyRationaleError(Exception):
    """FR-015: reviewer decision submitted with empty/missing rationale."""


class EditRequiresEditsError(Exception):
    """§5.5: 'edit' action REQUIRES non-null edits."""


class EditBreaksEvidenceFidelityError(Exception):
    """FR-016: an edit that fails evidence-span fidelity is rejected (422), not
    silently accepted — no persisted state changes."""

    def __init__(self, validation_report: dict):
        self.validation_report = validation_report
        super().__init__("Edit breaks evidence-span fidelity; rejected, no state changed.")


class EscalatedRecordNotPresentableError(Exception):
    """§2.3: an escalated record 'MUST NOT be presentable to a reviewer for
    accept/edit'. reject/escalate remain available on it."""


def apply_review_decision(
    revision_id: str,
    *,
    reviewer_id: str,
    action: str,
    rationale: str,
    edits: dict | None,
    canonical_text: str,
    valid_anchor_ids: set[str],
    obligation_repository: ObligationRepository,
) -> dict:
    if action not in _ACTION_TO_STATUS:
        raise ValueError(f"Unknown action: {action}")

    if not rationale or not rationale.strip():
        raise EmptyRationaleError("rationale MUST be non-empty (FR-015).")

    revision = obligation_repository.get_revision(revision_id)
    if revision is None:
        raise ValueError(f"No such revision: {revision_id}")

    current_status = revision["proposal"].get("governance", {}).get("review_status")
    if current_status == "escalated" and action in ("accept", "edit"):
        raise EscalatedRecordNotPresentableError(
            f"Revision {revision_id} is escalated and MUST NOT be presented for accept/edit (§2.3)."
        )

    updated_proposal_payload = None
    entry_diff = None

    if action == "edit":
        if not edits:
            raise EditRequiresEditsError("'edit' action requires non-null edits.")

        original_proposal = revision["proposal"]
        entry_diff = compute_diff(original_proposal, edits)
        candidate_proposal = apply_edits_to_proposal(original_proposal, edits)

        # Re-run Step 6 validation on the edited version before persisting (FR-016).
        report = validate_proposal(
            candidate_proposal, canonical_text=canonical_text, valid_anchor_ids=valid_anchor_ids
        )
        fidelity_check = next(
            c for c in report["checks"] if c["check_name"] == "evidence_span_fidelity"
        )
        if fidelity_check["status"] == "fail":
            raise EditBreaksEvidenceFidelityError(report)

        updated_proposal_payload = candidate_proposal

    revision_history_entry = {
        "reviewer_id": reviewer_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "rationale": rationale,
        "diff": entry_diff,
    }

    return obligation_repository.apply_decision(
        revision_id,
        new_review_status=_ACTION_TO_STATUS[action],
        revision_history_entry=revision_history_entry,
        updated_proposal_payload=updated_proposal_payload,
    )
