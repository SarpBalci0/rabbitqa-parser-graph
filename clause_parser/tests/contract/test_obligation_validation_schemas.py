"""Contract test: extracted ObligationObjectProposal and its ValidationReport
validate against their respective schema files."""

from shared_contracts.py.db import configure, get_session, get_engine_singleton
from shared_contracts.py.tables import create_all
from shared_contracts.py.validation import validate
from clause_parser.src.api.documents import DocumentRequest, register_document_handler
from clause_parser.src.db.document_repository import DocumentRepository
from clause_parser.src.db.obligation_repository import ObligationRepository
from clause_parser.src.pipeline import run_parse_job
from shared_contracts.py.tables import obligations_table
from sqlalchemy import select


def test_proposal_and_report_validate_against_schemas(tmp_path):
    configure("sqlite:///:memory:")
    create_all(get_engine_singleton())
    session = get_session()
    doc_repo = DocumentRepository(session)
    obl_repo = ObligationRepository(session)

    fixture_path = tmp_path / "doc.txt"
    fixture_path.write_text("Article 1\n1. The operator shall act within 10 days.\n")

    payload, _ = register_document_handler(
        DocumentRequest(instrument="NIS2", source_artifact_uri=str(fixture_path), source_version="v1"),
        session,
    )
    full_payload = doc_repo.get(payload["document_id"], payload["source_version"])
    run_parse_job(full_payload, obligation_repository=obl_repo)

    rows = session.execute(
        select(obligations_table.c.proposal_payload, obligations_table.c.validation_report_payload)
    ).all()
    assert len(rows) >= 1
    for proposal, report in rows:
        validate(proposal, "ObligationObject.schema.json")
        validate(report, "ValidationReport.schema.json")
