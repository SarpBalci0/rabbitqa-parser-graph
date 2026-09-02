"""Reviewer workspace structured field editor, per rabbitqa_spec_v1.1.0.md §6.2:
"A structured editor with one input per legal_semantics field — free-text edits
MUST be captured as a diff object attached to the resulting revision_history
entry."

CLI implementation. Reuses clause_parser.src.review.diff (the same diff-computation
code the real API endpoint uses) so the UI layer and the server-enforced invariant
can never silently diverge in how a diff is computed.
"""

from __future__ import annotations

from clause_parser.src.review.diff import compute_diff

_EDITABLE_LEGAL_SEMANTICS_FIELDS = (
    "norm_type",
    "actor",
    "modality",
    "action",
    "object",
    "scope",
    "trigger",
    "deadline",
    "frequency",
    "conditions",
    "exceptions",
)


def render_field_editor(legal_semantics: dict) -> str:
    """One input line per legal_semantics field, per §6.2."""
    lines = ["Structured editor — one field per line:"]
    for field in _EDITABLE_LEGAL_SEMANTICS_FIELDS:
        lines.append(f"  {field}: {legal_semantics.get(field)!r}")
    return "\n".join(lines)


def build_edit_payload(
    original_proposal: dict, field_edits: dict[str, object]
) -> tuple[dict, dict]:
    """field_edits: {field_name: new_value} for legal_semantics fields only, as
    entered through the CLI editor. Returns (edits_payload_for_api, diff_preview) —
    edits_payload_for_api is what gets sent to POST /v1/reviews/{revision}/decisions
    as the 'edits' field; diff_preview is what the reviewer sees before submitting."""
    for field in field_edits:
        if field not in _EDITABLE_LEGAL_SEMANTICS_FIELDS:
            raise ValueError(f"'{field}' is not an editable legal_semantics field.")

    edits_payload = {"legal_semantics": field_edits}
    diff_preview = compute_diff(original_proposal, edits_payload)
    return edits_payload, diff_preview
