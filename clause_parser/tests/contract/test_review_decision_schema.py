"""Contract test: the updated ObligationObject returned from a decision validates
against ObligationObject.schema.json."""

from shared_contracts.py.validation import validate
from clause_parser.src.api.reviews import DecisionRequest, submit_decision_handler
from clause_parser.tests.integration.test_review_accept import _seed_one_pending_revision


def test_updated_obligation_object_validates_against_schema(tmp_path):
    session, revision_id = _seed_one_pending_revision(tmp_path)

    updated = submit_decision_handler(
        revision_id,
        DecisionRequest(reviewer_id="reviewer-1", action="accept", rationale="Correctly extracted."),
        session=session,
    )

    validate(updated, "ObligationObject.schema.json")
