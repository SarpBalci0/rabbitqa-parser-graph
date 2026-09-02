"""§9.1: empty-rationale decision is rejected (400), no state change."""

import pytest

from clause_parser.src.api.errors import SchemaValidationHttpError
from clause_parser.src.api.reviews import DecisionRequest, submit_decision_handler
from clause_parser.src.db.obligation_repository import ObligationRepository
from clause_parser.tests.integration.test_review_accept import _seed_one_pending_revision


def test_empty_rationale_rejected_and_state_unchanged(tmp_path):
    session, revision_id = _seed_one_pending_revision(tmp_path)
    obl_repo = ObligationRepository(session)
    before = obl_repo.get_revision(revision_id)["proposal"]

    with pytest.raises(SchemaValidationHttpError):
        submit_decision_handler(
            revision_id,
            DecisionRequest(reviewer_id="reviewer-1", action="accept", rationale=""),
            session=session,
        )

    after = obl_repo.get_revision(revision_id)["proposal"]
    assert after == before
    assert after["governance"]["review_status"] == "pending"
