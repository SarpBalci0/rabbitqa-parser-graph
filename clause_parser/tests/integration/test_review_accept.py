"""§9.1 Review Given/When/Then: accept decision persists a revision_history entry
and sets review_status == "accepted"."""

from shared_contracts.py.db import configure, get_session, get_engine_singleton
from shared_contracts.py.tables import create_all
from clause_parser.src.api.documents import DocumentRequest, register_document_handler
from clause_parser.src.api.reviews import DecisionRequest, submit_decision_handler
from clause_parser.src.db.document_repository import DocumentRepository
from clause_parser.src.db.obligation_repository import ObligationRepository
from clause_parser.src.pipeline import run_parse_job


def _seed_one_pending_revision(tmp_path):
    configure("sqlite:///:memory:")
    create_all(get_engine_singleton())
    session = get_session()
    doc_repo = DocumentRepository(session)
    obl_repo = ObligationRepository(session)

    fixture_path = tmp_path / "doc.txt"
    fixture_path.write_text("Article 1\n1. The operator shall notify within 10 days.\n")
    payload, _ = register_document_handler(
        DocumentRequest(instrument="NIS2", source_artifact_uri=str(fixture_path), source_version="v1"),
        session,
    )
    full_payload = doc_repo.get(payload["document_id"], payload["source_version"])
    run_parse_job(full_payload, obligation_repository=obl_repo)

    clause_id = f"{payload['document_id']}:v1:article-1/paragraph-1"
    revision = obl_repo.list_revisions_for_clause(clause_id)[0]
    return session, revision["revision_id"]


def test_accept_decision_sets_status_and_appends_history(tmp_path):
    session, revision_id = _seed_one_pending_revision(tmp_path)

    updated = submit_decision_handler(
        revision_id,
        DecisionRequest(reviewer_id="reviewer-1", action="accept", rationale="Correctly extracted."),
        session=session,
    )

    assert updated["governance"]["review_status"] == "accepted"
    history = updated["governance"]["revision_history"]
    assert len(history) == 1
    assert history[0]["action"] == "accept"
    assert history[0]["reviewer_id"] == "reviewer-1"
    assert history[0]["rationale"] == "Correctly extracted."
