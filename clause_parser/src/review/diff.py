"""Diff capture for free-text field edits, per rabbitqa_spec_v1.0.0.md §6.2:
"free-text edits MUST be captured as a diff object attached to the resulting
revision_history entry."

edits shape: a dict of top-level ObligationObject field-group patches, e.g.
{"legal_semantics": {"action": "..."}, "source_evidence": {"char_end": 120}}.
Editable groups are restricted to legal_semantics and source_evidence — identity
and governance are never reviewer-editable (identity is derived, never model/reviewer
output per §2.2; governance.review_status/revision_history are set exclusively by
the decision itself, never by the edits payload, so a caller can't smuggle a status
change or forged history through 'edits').
"""

from __future__ import annotations

from typing import Any

EDITABLE_GROUPS = {"legal_semantics", "source_evidence"}


def compute_diff(original_proposal: dict[str, Any], edits: dict[str, Any]) -> dict[str, Any]:
    """Returns {"group.field": {"old": ..., "new": ...}} for every field edits
    actually changes relative to the original proposal."""
    diff: dict[str, Any] = {}
    for group, group_edits in edits.items():
        if group not in EDITABLE_GROUPS or not isinstance(group_edits, dict):
            continue
        original_group = original_proposal.get(group, {})
        for field, new_value in group_edits.items():
            old_value = original_group.get(field)
            if old_value != new_value:
                diff[f"{group}.{field}"] = {"old": old_value, "new": new_value}
    return diff


def apply_edits_to_proposal(original_proposal: dict[str, Any], edits: dict[str, Any]) -> dict[str, Any]:
    """Returns a new proposal dict with only legal_semantics/source_evidence patched.
    Any other top-level key in edits (e.g. an attempt to smuggle a governance or
    identity change) is silently ignored, not applied."""
    updated = dict(original_proposal)
    for group, group_edits in edits.items():
        if group not in EDITABLE_GROUPS or not isinstance(group_edits, dict):
            continue
        updated_group = dict(updated.get(group, {}))
        updated_group.update(group_edits)
        updated[group] = updated_group

        if group == "source_evidence" and "verbatim_text" in group_edits and "evidence_hash" not in group_edits:
            import hashlib

            updated_group["evidence_hash"] = hashlib.sha256(
                updated_group["verbatim_text"].encode("utf-8")
            ).hexdigest()

    return updated
