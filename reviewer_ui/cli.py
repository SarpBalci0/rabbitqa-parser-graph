"""Runnable CLI reviewer workspace, per rabbitqa_spec_v1.1.0.md §6 ("however
implemented — web form or CLI"). Ties together source_pane.py, validation_panel.py,
field_editor.py, and history_view.py into one scriptable command against the same
shared SQLite store the two FastAPI services use.

Usage:
    python -m reviewer_ui.cli <clause_id> --action accept --reviewer <id> --rationale "..."
    python -m reviewer_ui.cli <clause_id> --action edit --reviewer <id> --rationale "..." \\
        --edit object="the competent authority (corrected)"
    python -m reviewer_ui.cli <clause_id> --show-only   # just render the panes, no decision
"""

from __future__ import annotations

import argparse
import sys

from clause_parser.src.api.reviews import DecisionRequest, submit_decision_handler
from clause_parser.src.db.document_repository import DocumentRepository
from clause_parser.src.db.obligation_repository import ObligationRepository
from reviewer_ui.src.field_editor import build_edit_payload, render_field_editor
from reviewer_ui.src.history_view import render_history_view
from reviewer_ui.src.source_pane import render_source_pane
from reviewer_ui.src.validation_panel import ReviewSession
from shared_contracts.py.db import configure, get_engine_singleton, get_session
from shared_contracts.py.tables import create_all


def _parse_edit_args(edit_args: list[str]) -> dict[str, str]:
    edits = {}
    for item in edit_args:
        if "=" not in item:
            raise SystemExit(f"--edit must be field=value, got: {item!r}")
        field, value = item.split("=", 1)
        edits[field] = value
    return edits


def main() -> int:
    parser = argparse.ArgumentParser(description="RabbitQA CLI reviewer workspace")
    parser.add_argument("clause_id")
    parser.add_argument("--action", choices=["accept", "edit", "reject", "escalate"])
    parser.add_argument("--reviewer", default="cli-reviewer")
    parser.add_argument("--rationale", default="")
    parser.add_argument("--edit", action="append", default=[], help="field=value, repeatable")
    parser.add_argument("--show-only", action="store_true")
    parser.add_argument("--db-url", default=None, help="defaults to sqlite:///./rabbitqa.db")
    args = parser.parse_args()

    configure(args.db_url)
    create_all(get_engine_singleton())
    session = get_session()

    obl_repo = ObligationRepository(session)
    doc_repo = DocumentRepository(session)

    revisions = obl_repo.list_revisions_for_clause(args.clause_id)
    if not revisions:
        print(f"No revisions found for clause_id={args.clause_id!r}", file=sys.stderr)
        return 1
    latest = revisions[-1]
    proposal = latest["proposal"]
    report = latest["validation_report"]

    identity = proposal["identity"]
    document = doc_repo.get(identity["document_id"], identity["source_version"])
    if document is None:
        print("Source document not found — cannot render source pane.", file=sys.stderr)
        return 1

    evidence = proposal["source_evidence"]

    # §6.1 Source pane
    print(
        render_source_pane(
            canonical_text=document["_canonical_text"],
            char_start=evidence["char_start"],
            char_end=evidence["char_end"],
            anchor_id=evidence["anchor_id"],
            anchor_label=evidence["anchor_id"],
        )
    )
    print()

    # §6.2 Structured field editor (view)
    print(render_field_editor(proposal["legal_semantics"]))
    print()

    # §6.3 Validator findings — MUST be fetched/rendered before accept/edit is
    # allowed in this session (server independently re-validates regardless).
    review_session = ReviewSession()
    print(review_session.view_validation_report(latest["revision_id"], report))
    print()

    # §6.5 Prior-revision history
    print(render_history_view(args.clause_id, proposal["governance"]["revision_history"]))
    print()

    if args.show_only or args.action is None:
        return 0

    review_session.guard_accept_or_edit(latest["revision_id"])  # raises if not viewed above

    edits_payload = None
    if args.action == "edit":
        field_edits = _parse_edit_args(args.edit)
        edits_payload, diff_preview = build_edit_payload(proposal, field_edits)
        print(f"Proposed diff: {diff_preview}")

    updated = submit_decision_handler(
        latest["revision_id"],
        DecisionRequest(
            reviewer_id=args.reviewer,
            action=args.action,
            rationale=args.rationale,
            edits=edits_payload,
        ),
        session=session,
    )
    print(f"\nDecision submitted: review_status={updated['governance']['review_status']!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
