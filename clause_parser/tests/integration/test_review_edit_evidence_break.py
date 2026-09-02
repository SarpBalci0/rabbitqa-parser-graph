"""§9.1: a reviewer edit that breaks evidence-span fidelity is rejected with 422
(via EvidenceFidelityViolation), and no persisted state changes (FR-016)."""

import pytest

from clause_parser.src.api.reviews import EvidenceFidelityViolation, DecisionRequest, submit_decision_handler
from clause_parser.src.db.obligation_repository import ObligationRepository
from clause_parser.tests.integration.test_review_accept import _seed_one_pending_revision


def test_edit_that_changes_verbatim_text_off_document_fails_fidelity(tmp_path):
    session, revision_id = _seed_one_pending_revision(tmp_path)
    obl_repo = ObligationRepository(session)
    before = obl_repo.get_revision(revision_id)["proposal"]

    with pytest.raises(EvidenceFidelityViolation):
        submit_decision_handler(
            revision_id,
            DecisionRequest(
                reviewer_id="reviewer-1",
                action="edit",
                rationale="Trying to fix the text",
                edits={"source_evidence": {"verbatim_text": "This text is not actually in the document."}},
            ),
            session=session,
        )

    after = obl_repo.get_revision(revision_id)["proposal"]
    assert after == before
    assert after["governance"]["review_status"] == "pending"


def test_valid_edit_to_legal_semantics_is_accepted(tmp_path):
    session, revision_id = _seed_one_pending_revision(tmp_path)
    obl_repo = ObligationRepository(session)
    original_object = obl_repo.get_revision(revision_id)["proposal"]["legal_semantics"]["object"]

    updated = submit_decision_handler(
        revision_id,
        DecisionRequest(
            reviewer_id="reviewer-1",
            action="edit",
            rationale="Corrected the object field.",
            edits={"legal_semantics": {"object": "the competent authority (corrected)"}},
        ),
        session=session,
    )

    assert updated["governance"]["review_status"] == "edited"
    assert updated["legal_semantics"]["object"] == "the competent authority (corrected)"
    history = updated["governance"]["revision_history"]
    assert history[-1]["diff"] == {
        "legal_semantics.object": {"old": original_object, "new": "the competent authority (corrected)"}
    }
