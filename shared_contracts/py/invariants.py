"""Cross-field invariants that JSON Schema's `pattern` keyword cannot express
(it has no way to reference a sibling property's value), per rabbitqa_spec_v1.1.0.md
§2.2. These run alongside shared_contracts.py.validation.validate() wherever an
ObligationObject is persisted.
"""

from __future__ import annotations

import hashlib
from typing import Any


class InvariantViolationError(Exception):
    pass


def assert_clause_id_derivation(payload: dict[str, Any]) -> None:
    """§2.2 identity.clause_id: 'MUST be derived from identity + structural anchor,
    never from model output.' Concretely: clause_id MUST start with
    f"{document_id}:{source_version}:". See ObligationObject.schema.json's clause_id
    description for why this can't be a JSON Schema pattern alone."""
    identity = payload.get("identity", {})
    document_id = identity.get("document_id")
    source_version = identity.get("source_version")
    clause_id = identity.get("clause_id", "")
    expected_prefix = f"{document_id}:{source_version}:"
    if not clause_id.startswith(expected_prefix):
        raise InvariantViolationError(
            f"clause_id '{clause_id}' is not derived from identity "
            f"(expected prefix '{expected_prefix}')."
        )


def assert_evidence_hash_matches(payload: dict[str, Any]) -> None:
    """§2.2 invariant 1: evidence_hash == sha256(verbatim_text)."""
    evidence = payload.get("source_evidence", {})
    verbatim_text = evidence.get("verbatim_text", "")
    evidence_hash = evidence.get("evidence_hash", "")
    computed = hashlib.sha256(verbatim_text.encode("utf-8")).hexdigest()
    if computed != evidence_hash:
        raise InvariantViolationError(
            f"evidence_hash '{evidence_hash}' does not match sha256(verbatim_text) '{computed}'."
        )


def assert_evidence_replay(payload: dict[str, Any], canonical_text: str) -> None:
    """§2.2 invariant 2 ('evidence replay'): verbatim_text ==
    CanonicalDocument.text[char_start:char_end] for the matching document_id +
    source_version. Callers pass in the already-looked-up canonical_text for that
    exact (document_id, source_version) pair."""
    evidence = payload.get("source_evidence", {})
    char_start = evidence.get("char_start")
    char_end = evidence.get("char_end")
    verbatim_text = evidence.get("verbatim_text", "")
    actual = canonical_text[char_start:char_end] if char_start is not None and char_end is not None else None
    if actual != verbatim_text:
        raise InvariantViolationError(
            "evidence replay failed: verbatim_text is not an exact substring of the "
            "canonical document at [char_start, char_end)."
        )


def assert_clause_id_globally_unique(clause_id: str, existing_clause_ids: set[str]) -> None:
    """§2.2 invariant 3: clause_id globally unique per (document_id, source_version).
    Caller is expected to have already scoped existing_clause_ids to that pair."""
    if clause_id in existing_clause_ids:
        raise InvariantViolationError(f"clause_id '{clause_id}' is not unique within its (document_id, source_version).")


def assert_reviewed_record_invariants(payload: dict[str, Any]) -> None:
    """§2.2 invariants 4 & 5, which MUST hold whenever review_status is accepted or
    edited: revision_history non-empty, and every rationale non-empty."""
    governance = payload.get("governance", {})
    if governance.get("review_status") not in {"accepted", "edited"}:
        return
    history = governance.get("revision_history", [])
    if not history:
        raise InvariantViolationError("accepted/edited record MUST have a non-empty revision_history.")
    for entry in history:
        if not entry.get("rationale"):
            raise InvariantViolationError("every revision_history entry's rationale MUST be non-empty.")
