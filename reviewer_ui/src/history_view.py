"""Reviewer workspace prior-revision history view, per rabbitqa_spec_v1.1.0.md
§6.5: "Prior-revision history: reviewer identity, timestamp, decision, and
rationale for every past revision of the clause and, separately, for prior
versions of the source regulation article if superseded."

Both halves are rendered here. The superseded-article half (T053) is resolved via
compliance_graph.src.query.article_history.resolve_superseded_article_history,
which walks the graph's real SUPERSEDES chain (§3.2) — not fabricated, and empty
(not an error) when the clause's article has never been superseded.
"""

from __future__ import annotations

from typing import Any


def render_history_view(
    clause_id: str,
    revision_history: list[dict],
    superseded_article_history: list[dict[str, Any]] | None = None,
) -> str:
    lines = [f"Revision history for {clause_id}:"]
    if not revision_history:
        lines.append("  (no decisions recorded yet)")
    for entry in revision_history:
        lines.append(
            f"  [{entry['timestamp']}] {entry['reviewer_id']} -> {entry['action']}: {entry['rationale']}"
        )
        if entry.get("diff"):
            lines.append(f"    diff: {entry['diff']}")

    lines.append("")
    lines.append("Prior versions of the source regulation article (§6.5, if superseded):")
    if not superseded_article_history:
        lines.append("  (this article has not been superseded by a later pinned version)")
    else:
        for prior in superseded_article_history:
            lines.append(f"  -- source_version {prior['source_version']} (clause {prior['clause_id']}):")
            if not prior["revision_history"]:
                lines.append("       (no decisions recorded)")
            for entry in prior["revision_history"]:
                lines.append(
                    f"       [{entry['timestamp']}] {entry['reviewer_id']} -> {entry['action']}: {entry['rationale']}"
                )

    return "\n".join(lines)
