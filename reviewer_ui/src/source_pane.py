"""Reviewer workspace source pane, per rabbitqa_spec_v1.1.0.md §6.1:
"Source pane showing the verbatim source text with the current proposal's evidence
span highlighted, and the stable anchor label visible."

CLI implementation (§6: "however implemented — web form or CLI").
"""

from __future__ import annotations

_HIGHLIGHT_START = ">>>"
_HIGHLIGHT_END = "<<<"


def render_source_pane(
    *, canonical_text: str, char_start: int, char_end: int, anchor_id: str, anchor_label: str | None
) -> str:
    """Renders the canonical document text with the evidence span visibly
    highlighted and the stable anchor label shown alongside it."""
    before = canonical_text[:char_start]
    span = canonical_text[char_start:char_end]
    after = canonical_text[char_end:]

    label = anchor_label or anchor_id
    lines = [
        f"Anchor: {label}  ({anchor_id})",
        "-" * 60,
        f"{before}{_HIGHLIGHT_START}{span}{_HIGHLIGHT_END}{after}",
    ]
    return "\n".join(lines)
