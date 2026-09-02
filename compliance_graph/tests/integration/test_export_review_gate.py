"""§9.1 Query & export Given/When/Then: an obligation with review_status not in
{accepted, edited} is excluded from the export payload — the export MUST NOT fail
silently by including it anyway.

The Graph Mapping Agent itself refuses to map a non-accepted obligation (§4.4), so
to exercise this gate realistically we publish two obligations that WERE accepted
at mapping time, then downgrade one of them via a later, real reviewer decision
(escalate) — modeling a re-review after graph mapping, not a hand-built violation.
"""

from clause_parser.src.api.documents import DocumentRequest, register_document_handler
from clause_parser.src.api.reviews import DecisionRequest, submit_decision_handler
from clause_parser.src.db.document_repository import DocumentRepository
from clause_parser.src.db.obligation_repository import ObligationRepository
from clause_parser.src.pipeline import run_parse_job
from compliance_graph.src.api.changesets import publish_changeset_handler, validate_changeset_handler
from compliance_graph.src.db.changeset_repository import ChangesetRepository
from compliance_graph.src.export.exporter import build_export
from compliance_graph.src.graph_mapping_agent.agent import propose_change_set
from compliance_graph.src.publisher.in_memory_store import InMemoryGraphStore
from compliance_graph.src.review.changeset_approval import approve_change_set
from shared_contracts.py.db import configure, get_session, get_engine_singleton
from shared_contracts.py.tables import create_all


def test_downgraded_obligation_excluded_from_export(tmp_path):
    configure("sqlite:///:memory:")
    create_all(get_engine_singleton())
    session = get_session()
    doc_repo = DocumentRepository(session)
    obl_repo = ObligationRepository(session)

    fixture_path = tmp_path / "doc.txt"
    fixture_path.write_text(
        "Article 21\n"
        "1. The operator shall notify the competent authority within 30 days.\n"
        "Article 22\n"
        "1. The manufacturer must maintain records for 5 years.\n"
    )
    doc_payload, _ = register_document_handler(
        DocumentRequest(instrument="NIS2", source_artifact_uri=str(fixture_path), source_version="v1"), session
    )
    full_doc = doc_repo.get(doc_payload["document_id"], doc_payload["source_version"])
    run_parse_job(full_doc, obligation_repository=obl_repo)

    clause_id_1 = f"{doc_payload['document_id']}:v1:article-21/paragraph-1"
    clause_id_2 = f"{doc_payload['document_id']}:v1:article-22/paragraph-1"

    revision_1 = obl_repo.list_revisions_for_clause(clause_id_1)[0]
    revision_2 = obl_repo.list_revisions_for_clause(clause_id_2)[0]

    accepted_1 = submit_decision_handler(
        revision_1["revision_id"],
        DecisionRequest(reviewer_id="r1", action="accept", rationale="Correct."),
        session=session,
    )
    accepted_2 = submit_decision_handler(
        revision_2["revision_id"],
        DecisionRequest(reviewer_id="r1", action="accept", rationale="Correct."),
        session=session,
    )

    changeset = propose_change_set(obligations=[accepted_1, accepted_2], base_snapshot_id=None)
    repo = ChangesetRepository(session)
    repo.create(changeset)
    validate_changeset_handler(changeset["changeset_id"], session=session)
    approve_change_set(changeset["changeset_id"], repository=repo)

    store = InMemoryGraphStore()
    publish_result = publish_changeset_handler(changeset["changeset_id"], session=session, graph_store=store)

    # A later, real review decision downgrades clause 2 after it was already mapped.
    submit_decision_handler(
        revision_2["revision_id"],
        DecisionRequest(reviewer_id="r2", action="escalate", rationale="Needs legal re-review."),
        session=session,
    )

    export_payload = build_export(
        publish_result["snapshot_id"],
        graph_store=store,
        changeset_repository=repo,
        document_repository=doc_repo,
        obligation_repository=obl_repo,
    )

    exported_clause_ids = {o["clause_id"] for o in export_payload["obligations"]}
    assert clause_id_1 in exported_clause_ids
    assert clause_id_2 not in exported_clause_ids
