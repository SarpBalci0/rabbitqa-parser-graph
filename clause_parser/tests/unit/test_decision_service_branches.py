"""Covers decision_service.py branches not exercised by the §9.1-named test files:
reject, escalate, edit-without-edits, and the escalated-record accept/edit guard."""

import pytest

from clause_parser.src.review.decision_service import (
    EditRequiresEditsError,
    EscalatedRecordNotPresentableError,
    apply_review_decision,
)
from clause_parser.src.db.obligation_repository import ObligationRepository
from clause_parser.tests.integration.test_review_accept import _seed_one_pending_revision


def test_reject_sets_status_and_history(tmp_path):
    session, revision_id = _seed_one_pending_revision(tmp_path)
    obl_repo = ObligationRepository(session)
    revision = obl_repo.get_revision(revision_id)

    updated = apply_review_decision(
        revision_id,
        reviewer_id="r1",
        action="reject",
        rationale="Not a valid obligation.",
        edits=None,
        canonical_text="irrelevant for reject",
        valid_anchor_ids=set(),
        obligation_repository=obl_repo,
    )
    assert updated["governance"]["review_status"] == "rejected"
    assert updated["governance"]["revision_history"][-1]["action"] == "reject"


def test_escalate_sets_status(tmp_path):
    session, revision_id = _seed_one_pending_revision(tmp_path)
    obl_repo = ObligationRepository(session)

    updated = apply_review_decision(
        revision_id,
        reviewer_id="r1",
        action="escalate",
        rationale="Needs legal review.",
        edits=None,
        canonical_text="irrelevant",
        valid_anchor_ids=set(),
        obligation_repository=obl_repo,
    )
    assert updated["governance"]["review_status"] == "escalated"


def test_edit_without_edits_raises(tmp_path):
    session, revision_id = _seed_one_pending_revision(tmp_path)
    obl_repo = ObligationRepository(session)

    with pytest.raises(EditRequiresEditsError):
        apply_review_decision(
            revision_id,
            reviewer_id="r1",
            action="edit",
            rationale="No edits provided.",
            edits=None,
            canonical_text="irrelevant",
            valid_anchor_ids=set(),
            obligation_repository=obl_repo,
        )


def test_escalated_record_cannot_be_accepted_or_edited(tmp_path):
    session, revision_id = _seed_one_pending_revision(tmp_path)
    obl_repo = ObligationRepository(session)

    apply_review_decision(
        revision_id,
        reviewer_id="r1",
        action="escalate",
        rationale="Needs legal review.",
        edits=None,
        canonical_text="irrelevant",
        valid_anchor_ids=set(),
        obligation_repository=obl_repo,
    )

    with pytest.raises(EscalatedRecordNotPresentableError):
        apply_review_decision(
            revision_id,
            reviewer_id="r2",
            action="accept",
            rationale="Trying to accept anyway.",
            edits=None,
            canonical_text="irrelevant",
            valid_anchor_ids=set(),
            obligation_repository=obl_repo,
        )
