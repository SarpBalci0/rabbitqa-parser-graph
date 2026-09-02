"""Tests for the two enforceable §6.3/§6.4 UX gates: ReviewSession's
guard_accept_or_edit and GraphApprovalSession's guard_approval."""

import pytest

from reviewer_ui.src.validation_panel import AcceptWithoutValidationViewError, ReviewSession
from reviewer_ui.src.graph_diff_preview import ApprovalWithoutPreviewError, GraphApprovalSession
from reviewer_ui.src.field_editor import build_edit_payload
from reviewer_ui.src.source_pane import render_source_pane
from reviewer_ui.src.history_view import render_history_view


def _report():
    return {"run_id": "r1", "checks": [], "overall_status": "pass"}


def test_accept_blocked_until_validation_report_viewed():
    session = ReviewSession()
    with pytest.raises(AcceptWithoutValidationViewError):
        session.guard_accept_or_edit("revision-1")


def test_accept_allowed_after_validation_report_viewed():
    session = ReviewSession()
    session.view_validation_report("revision-1", _report())
    session.guard_accept_or_edit("revision-1")  # does not raise


def test_viewing_one_revision_does_not_unlock_another():
    session = ReviewSession()
    session.view_validation_report("revision-1", _report())
    with pytest.raises(AcceptWithoutValidationViewError):
        session.guard_accept_or_edit("revision-2")


def test_approval_blocked_until_preview_recorded():
    session = GraphApprovalSession()
    with pytest.raises(ApprovalWithoutPreviewError):
        session.guard_approval("cs_1")


def test_field_editor_rejects_non_editable_field():
    original = {"legal_semantics": {"action": "notify"}}
    with pytest.raises(ValueError):
        build_edit_payload(original, {"not_a_real_field": "x"})


def test_field_editor_produces_diff_matching_shared_diff_module():
    original = {"legal_semantics": {"action": "notify", "object": "authority"}}
    edits_payload, diff_preview = build_edit_payload(original, {"object": "the competent authority"})
    assert edits_payload == {"legal_semantics": {"object": "the competent authority"}}
    assert diff_preview == {
        "legal_semantics.object": {"old": "authority", "new": "the competent authority"}
    }


def test_source_pane_highlights_evidence_span():
    text = "Article 1\n1. The operator shall act.\n"
    span = "1. The operator shall act.\n"
    char_start = text.index(span)
    rendered = render_source_pane(
        canonical_text=text,
        char_start=char_start,
        char_end=char_start + len(span),
        anchor_id="doc_x:v1:article-1/paragraph-1",
        anchor_label="Article 1(1)",
    )
    assert "Article 1(1)" in rendered
    assert f">>>{span}<<<" in rendered


def test_history_view_notes_no_supersession_when_none_exists():
    rendered = render_history_view("clause-1", [])
    assert "has not been superseded" in rendered


def test_history_view_renders_superseded_article_history():
    superseded = [
        {
            "source_version": "v1",
            "clause_id": "doc_x:v1:article-21/paragraph-1",
            "revision_history": [
                {"timestamp": "t1", "reviewer_id": "r1", "action": "accept", "rationale": "ok"}
            ],
        }
    ]
    rendered = render_history_view("doc_x:v2:article-21/paragraph-1", [], superseded)
    assert "source_version v1" in rendered
    assert "r1 -> accept: ok" in rendered
