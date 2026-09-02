"""Regression tests for §2.2 invariants in ObligationRepository.apply_decision,
covering the append-only-history bug and the non-empty-rationale/schema-validation
gap found during a spec-conformance re-check."""

import pytest

from shared_contracts.py.db import configure, get_session, get_engine_singleton
from shared_contracts.py.tables import create_all
from clause_parser.src.db.obligation_repository import ObligationRepository


def _fresh_repo() -> ObligationRepository:
    configure("sqlite:///:memory:")
    create_all(get_engine_singleton())
    return ObligationRepository(get_session())


def _base_proposal(review_status="pending"):
    import hashlib

    verbatim_text = "1. Shall."
    return {
        "identity": {
            "document_id": "doc_abc123456789",
            "source_version": "v1",
            "language": "en",
            "jurisdiction": "EU",
            "instrument": "NIS2",
            "clause_id": "doc_abc123456789:v1:article-21/paragraph-1",
            "schema_version": "1.0.0",
        },
        "source_evidence": {
            "anchor_id": "doc_abc123456789:v1:article-21/paragraph-1",
            "char_start": 0,
            "char_end": len(verbatim_text),
            "verbatim_text": verbatim_text,
            "evidence_hash": hashlib.sha256(verbatim_text.encode("utf-8")).hexdigest(),
        },
        "legal_semantics": {
            "norm_type": "obligation",
            "actor": ["operator"],
            "modality": "shall",
            "action": "notify",
            "object": "authority",
            "scope": "EU",
        },
        "references": {},
        "governance": {"review_status": review_status, "revision_history": []},
    }


def _report():
    return {
        "target_clause_id": "doc_abc123456789:v1:article-21/paragraph-1",
        "run_id": "run1",
        "checks": [],
        "overall_status": "pass",
    }


def test_apply_decision_is_append_only_across_an_edit():
    repo = _fresh_repo()
    revision_id = repo.create_revision(_base_proposal(), _report())

    repo.apply_decision(
        revision_id,
        new_review_status="edited",
        revision_history_entry={
            "reviewer_id": "r1",
            "timestamp": "2026-01-01T00:00:00Z",
            "action": "edit",
            "rationale": "fixed typo",
        },
        updated_proposal_payload=_base_proposal(),  # caller omits governance entirely
    )

    result = repo.apply_decision(
        revision_id,
        new_review_status="accepted",
        revision_history_entry={
            "reviewer_id": "r2",
            "timestamp": "2026-01-02T00:00:00Z",
            "action": "accept",
            "rationale": "looks correct now",
        },
    )

    history = result["governance"]["revision_history"]
    assert len(history) == 2, "prior revision_history entry must survive an edit payload that omits it"
    assert history[0]["action"] == "edit"
    assert history[1]["action"] == "accept"


def test_apply_decision_rejects_empty_rationale():
    repo = _fresh_repo()
    revision_id = repo.create_revision(_base_proposal(), _report())
    with pytest.raises(ValueError):
        repo.apply_decision(
            revision_id,
            new_review_status="accepted",
            revision_history_entry={
                "reviewer_id": "r1",
                "timestamp": "2026-01-01T00:00:00Z",
                "action": "accept",
                "rationale": "",
            },
        )
