"""End-to-end User Story 1 demonstration: register -> parse job -> parse-revisions,
matching quickstart.md steps 1-3 and tasks.md's US1 Independent Test."""

from shared_contracts.py.db import configure, get_session, get_engine_singleton
from shared_contracts.py.tables import create_all
from clause_parser.src.api.clauses import get_parse_revisions_handler
from clause_parser.src.api.documents import DocumentRequest, register_document_handler
from clause_parser.src.api.parse_jobs import (
    ParseJobRequest,
    ParseJobStore,
    create_parse_job_handler,
    get_parse_job_handler,
)


def test_register_parse_and_read_revisions(tmp_path):
    configure("sqlite:///:memory:")
    create_all(get_engine_singleton())
    session = get_session()

    fixture_path = tmp_path / "nis2_excerpt.txt"
    fixture_path.write_text(
        "Article 21\n"
        "1. The operator shall notify the competent authority within 30 days of an incident.\n"
        "Article 22\n"
        "1. The manufacturer must maintain records for 5 years.\n"
    )

    doc_payload, doc_status = register_document_handler(
        DocumentRequest(instrument="NIS2", source_artifact_uri=str(fixture_path), source_version="v1"),
        session,
    )
    assert doc_status == 201

    job_store = ParseJobStore()
    job_response = create_parse_job_handler(
        ParseJobRequest(document_id=doc_payload["document_id"], source_version="v1"),
        session=session,
        job_store=job_store,
    )
    assert job_response["status"] == "queued"

    job_status = get_parse_job_handler(job_response["job_id"], job_store=job_store)
    assert job_status["status"] == "completed"
    assert job_status["validation_summary"]["total"] >= 2
    assert job_status["trace_id"]

    # Read back revisions for one of the two produced clauses.
    document_id = doc_payload["document_id"]
    clause_id = f"{document_id}:v1:article-21/paragraph-1"
    revisions = get_parse_revisions_handler(clause_id, session=session)
    assert len(revisions) == 1
    revision = revisions[0]
    assert revision["ObligationObjectProposal"]["identity"]["clause_id"] == clause_id
    assert revision["ValidationReport"]["target_clause_id"] == clause_id
    assert revision["revision_history"] == []  # not yet reviewed
