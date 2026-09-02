"""§9.1/§6.5: full decision history (reviewer, timestamp, decision, rationale) is
retrievable for a clause.

NOTE: the "and its superseded prior article versions" half of §6.5's requirement is
DEFERRED to User Story 4 per tasks.md T053 (user-confirmed during implementation) —
supersession is only modeled via compliance_graph's SUPERSEDES relationship, which
doesn't exist yet in this pass. Only the clause's own history is tested here.
"""

from clause_parser.src.api.clauses import get_parse_revisions_handler
from clause_parser.src.api.reviews import DecisionRequest, submit_decision_handler
from clause_parser.tests.integration.test_review_accept import _seed_one_pending_revision


def test_full_decision_history_retrievable_for_a_clause(tmp_path):
    session, revision_id = _seed_one_pending_revision(tmp_path)

    submit_decision_handler(
        revision_id,
        DecisionRequest(
            reviewer_id="reviewer-1",
            action="edit",
            rationale="First pass correction.",
            edits={"legal_semantics": {"scope": "EU-wide"}},
        ),
        session=session,
    )
    submit_decision_handler(
        revision_id,
        DecisionRequest(reviewer_id="reviewer-2", action="accept", rationale="Looks correct now."),
        session=session,
    )

    from clause_parser.src.db.obligation_repository import ObligationRepository

    obl_repo = ObligationRepository(session)
    clause_id = obl_repo.get_revision(revision_id)["proposal"]["identity"]["clause_id"]

    revisions = get_parse_revisions_handler(clause_id, session=session)
    assert len(revisions) == 1
    history = revisions[0]["revision_history"]
    assert [h["action"] for h in history] == ["edit", "accept"]
    assert [h["reviewer_id"] for h in history] == ["reviewer-1", "reviewer-2"]
    assert all(h["rationale"] for h in history)
    assert all(h["timestamp"] for h in history)
