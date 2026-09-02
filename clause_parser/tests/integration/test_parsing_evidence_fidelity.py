"""§9.1 Parsing Given/When/Then: every resulting ObligationObjectProposal's
evidence_hash matches sha256(verbatim_text), and verbatim_text is an exact
substring of the canonical text at its stated offsets."""

import hashlib

from shared_contracts.py.db import configure, get_session, get_engine_singleton
from shared_contracts.py.tables import create_all
from clause_parser.src.api.documents import DocumentRequest, register_document_handler
from clause_parser.src.db.document_repository import DocumentRepository
from clause_parser.src.db.obligation_repository import ObligationRepository
from clause_parser.src.pipeline import run_parse_job


def _setup(tmp_path):
    configure("sqlite:///:memory:")
    create_all(get_engine_singleton())
    session = get_session()
    doc_repo = DocumentRepository(session)
    obl_repo = ObligationRepository(session)

    fixture_path = tmp_path / "nis2_excerpt.txt"
    fixture_path.write_text(
        "Article 21\n"
        "1. The operator shall notify the competent authority within 30 days of an incident.\n"
        "2. This paragraph contains no modal verb and should not be detected.\n"
        "Article 22\n"
        "1. The manufacturer must maintain records for 5 years.\n"
    )
    request = DocumentRequest(instrument="NIS2", source_artifact_uri=str(fixture_path), source_version="v1")
    payload, _ = register_document_handler(request, session)

    # register_document_handler strips leading-underscore fields for the API response;
    # re-fetch the full stored record (including _canonical_text) for the pipeline.
    full_payload = doc_repo.get(payload["document_id"], payload["source_version"])
    return full_payload, obl_repo


def test_every_proposal_evidence_is_hash_verified_and_offset_accurate(tmp_path):
    document_payload, obl_repo = _setup(tmp_path)
    summary = run_parse_job(document_payload, obligation_repository=obl_repo)

    assert summary["total"] >= 2  # two modal-bearing paragraphs in the fixture

    canonical_text = document_payload["_canonical_text"]
    # Re-query every persisted revision by scanning the in-memory table directly.
    from shared_contracts.py.tables import obligations_table
    from sqlalchemy import select

    rows = obl_repo._session.execute(select(obligations_table.c.proposal_payload)).all()
    assert len(rows) == summary["total"]

    for (proposal,) in rows:
        evidence = proposal["source_evidence"]
        verbatim_text = evidence["verbatim_text"]
        assert evidence["evidence_hash"] == hashlib.sha256(verbatim_text.encode("utf-8")).hexdigest()
        assert canonical_text[evidence["char_start"] : evidence["char_end"]] == verbatim_text
