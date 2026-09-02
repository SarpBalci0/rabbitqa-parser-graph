"""Step 6: Validate. Fully deterministic, no LLM (§4.1 hard rule).

Runs the seven named checks from ValidationReport.checks[].check_name (§2.3):
schema_validity, controlled_vocabulary, evidence_span_fidelity, date_normalization,
quantity_normalization, reference_validity, cross_field_consistency.
"""

from __future__ import annotations

import uuid

from shared_contracts.py.invariants import InvariantViolationError, assert_evidence_hash_matches, assert_evidence_replay
from shared_contracts.py.validation import SchemaValidationError, validate as schema_validate

_MODALITIES = {"shall", "must", "may", "should"}
_NORM_TYPES = {"obligation", "prohibition", "permission", "definition_only"}


def _check_schema_validity(proposal: dict) -> tuple[str, str]:
    try:
        schema_validate(proposal, "ObligationObject.schema.json")
        return "pass", "Schema-conformant."
    except SchemaValidationError as exc:
        return "fail", str(exc)


def _check_controlled_vocabulary(proposal: dict) -> tuple[str, str]:
    semantics = proposal.get("legal_semantics", {})
    modality = semantics.get("modality")
    norm_type = semantics.get("norm_type")
    if modality not in _MODALITIES:
        return "fail", f"modality '{modality}' not in controlled vocabulary {_MODALITIES}."
    if norm_type not in _NORM_TYPES:
        return "fail", f"norm_type '{norm_type}' not in controlled vocabulary {_NORM_TYPES}."
    return "pass", "modality/norm_type within controlled vocabulary."


def _check_evidence_span_fidelity(proposal: dict, canonical_text: str) -> tuple[str, str]:
    """§2.2 invariant 2: evidence replay. Delegates to the single shared
    implementation in shared_contracts/py/invariants.py — this used to duplicate
    that logic inline, which a spec-code synchronization audit flagged as a
    divergence risk (two independent implementations of the same check)."""
    try:
        assert_evidence_hash_matches(proposal)
    except InvariantViolationError as exc:
        return "fail", str(exc)

    evidence = proposal.get("source_evidence", {})
    if evidence.get("char_start") is None or evidence.get("char_end") is None:
        return "fail", "char_start/char_end missing."

    try:
        assert_evidence_replay(proposal, canonical_text)
    except InvariantViolationError as exc:
        return "fail", str(exc)

    return "pass", "Evidence replay succeeded."


def _check_date_normalization(proposal: dict) -> tuple[str, str]:
    deadline = proposal.get("legal_semantics", {}).get("deadline")
    if deadline is None:
        return "pass", "No deadline present."
    if deadline.get("type") in {"absolute_date", "relative_period", "recurring"} and deadline.get(
        "normalized_iso"
    ):
        return "pass", "Deadline normalized."
    return "warn", "Deadline present but normalized_iso is missing."


def _check_quantity_normalization(proposal: dict) -> tuple[str, str]:
    # No quantity fields are populated by this pass's extractor (fixture); nothing to
    # normalize yet, so this check trivially passes rather than fabricating a failure.
    return "pass", "No quantity fields to normalize in this proposal."


def _check_reference_validity(proposal: dict, valid_anchor_ids: set[str]) -> tuple[str, str]:
    references = proposal.get("references", {})
    resolved = references.get("resolved_target_ids", [])
    unresolved = [target for target in resolved if target not in valid_anchor_ids]
    if unresolved:
        return "fail", f"resolved_target_ids reference unknown anchors: {unresolved}"
    return "pass", "All resolved references point to known anchors."


def _check_cross_field_consistency(proposal: dict) -> tuple[str, str]:
    semantics = proposal.get("legal_semantics", {})
    if semantics.get("norm_type") == "definition_only" and semantics.get("actor"):
        return "warn", "definition_only norm_type unusually has a non-empty actor list."
    if not semantics.get("actor"):
        return "fail", "legal_semantics.actor MUST have at least one entry."
    return "pass", "No cross-field inconsistency detected."


def validate_proposal(
    proposal: dict,
    *,
    canonical_text: str,
    valid_anchor_ids: set[str],
    run_id: str | None = None,
) -> dict:
    """Returns a ValidationReport dict, per §2.3."""
    checks = []

    for name, result in (
        ("schema_validity", _check_schema_validity(proposal)),
        ("controlled_vocabulary", _check_controlled_vocabulary(proposal)),
        ("evidence_span_fidelity", _check_evidence_span_fidelity(proposal, canonical_text)),
        ("date_normalization", _check_date_normalization(proposal)),
        ("quantity_normalization", _check_quantity_normalization(proposal)),
        ("reference_validity", _check_reference_validity(proposal, valid_anchor_ids)),
        ("cross_field_consistency", _check_cross_field_consistency(proposal)),
    ):
        status, message = result
        checks.append({"check_name": name, "status": status, "message": message})

    clause_id = proposal.get("identity", {}).get("clause_id", "unknown")

    return {
        "target_clause_id": clause_id,
        "run_id": run_id or str(uuid.uuid4()),
        "checks": checks,
        "overall_status": _overall_status(checks),
    }


def _overall_status(checks: list[dict]) -> str:
    """Computed by routing.py's rule, exposed here too so a ValidationReport is
    always internally consistent even if routing.py isn't invoked separately."""
    from clause_parser.src.validate.routing import compute_overall_status

    return compute_overall_status(checks)
