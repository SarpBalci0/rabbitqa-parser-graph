"""Shared fixture helper: produces a real, accepted ObligationObject by running the
actual US1 (ingest+parse) -> US2 (review/accept) pipeline, per the agreed approach
of using real pipeline output as US3's input rather than a hand-built fixture."""

from __future__ import annotations

from shared_contracts.py.db import configure, get_session, get_engine_singleton
from shared_contracts.py.tables import create_all
from clause_parser.src.api.documents import DocumentRequest, register_document_handler
from clause_parser.src.api.reviews import DecisionRequest, submit_decision_handler
from clause_parser.src.db.document_repository import DocumentRepository
from clause_parser.src.db.obligation_repository import ObligationRepository
from clause_parser.src.pipeline import run_parse_job


def build_accepted_obligation(tmp_path, *, text: str | None = None):
    """Runs the real ingest -> parse -> accept pipeline and returns
    (session, accepted_obligation_object_dict)."""
    configure("sqlite:///:memory:")
    create_all(get_engine_singleton())
    session = get_session()
    doc_repo = DocumentRepository(session)
    obl_repo = ObligationRepository(session)

    fixture_path = tmp_path / "doc.txt"
    fixture_path.write_text(
        text or "Article 21\n1. The operator shall notify the competent authority within 30 days.\n"
    )
    doc_payload, _ = register_document_handler(
        DocumentRequest(instrument="NIS2", source_artifact_uri=str(fixture_path), source_version="v1"),
        session,
    )
    full_doc = doc_repo.get(doc_payload["document_id"], doc_payload["source_version"])
    run_parse_job(full_doc, obligation_repository=obl_repo)

    clause_id = f"{doc_payload['document_id']}:v1:article-21/paragraph-1"
    revision = obl_repo.list_revisions_for_clause(clause_id)[0]

    accepted = submit_decision_handler(
        revision["revision_id"],
        DecisionRequest(reviewer_id="reviewer-1", action="accept", rationale="Correctly extracted."),
        session=session,
    )
    return session, accepted


def build_published_snapshot(tmp_path, *, text: str | None = None):
    """Runs the full ingest -> parse -> accept -> map -> validate -> approve ->
    publish pipeline and returns (session, store, snapshot_id, accepted_obligation)."""
    from compliance_graph.src.api.changesets import publish_changeset_handler, validate_changeset_handler
    from compliance_graph.src.db.changeset_repository import ChangesetRepository
    from compliance_graph.src.graph_mapping_agent.agent import propose_change_set
    from compliance_graph.src.publisher.in_memory_store import InMemoryGraphStore
    from compliance_graph.src.review.changeset_approval import approve_change_set

    session, accepted = build_accepted_obligation(tmp_path, text=text)
    changeset = propose_change_set(obligations=[accepted], base_snapshot_id=None)
    repo = ChangesetRepository(session)
    repo.create(changeset)
    validate_changeset_handler(changeset["changeset_id"], session=session)
    approve_change_set(changeset["changeset_id"], repository=repo)

    store = InMemoryGraphStore()
    result = publish_changeset_handler(changeset["changeset_id"], session=session, graph_store=store)
    return session, store, result["snapshot_id"], accepted
