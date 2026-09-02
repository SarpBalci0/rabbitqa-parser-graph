"""§9.1 Validation Given/When/Then: a proposal with a fabricated (non-substring)
verbatim_text forces overall_status == "fail" and review_status auto-routes to
"escalated" — it MUST NOT be presentable as "pending"."""

from clause_parser.src.validate.routing import route_review_status
from clause_parser.src.validate.validator import validate_proposal


def _proposal(verbatim_text: str, evidence_hash: str, char_start=0, char_end=10):
    return {
        "identity": {
            "document_id": "doc_abc123456789",
            "source_version": "v1",
            "language": "en",
            "jurisdiction": "EU",
            "instrument": "NIS2",
            "clause_id": "doc_abc123456789:v1:article-1/paragraph-1",
            "schema_version": "1.0.0",
        },
        "source_evidence": {
            "anchor_id": "doc_abc123456789:v1:article-1/paragraph-1",
            "char_start": char_start,
            "char_end": char_end,
            "verbatim_text": verbatim_text,
            "evidence_hash": evidence_hash,
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
        "governance": {"review_status": "pending", "revision_history": []},
    }


def test_fabricated_verbatim_text_forces_fail_and_auto_escalation():
    canonical_text = "1. Real obligation text goes here.\n"
    fake_evidence = "This text does not appear in the document at all."
    import hashlib

    proposal = _proposal(
        fake_evidence,
        hashlib.sha256(fake_evidence.encode("utf-8")).hexdigest(),
        char_start=0,
        char_end=len(fake_evidence),
    )

    report = validate_proposal(
        proposal, canonical_text=canonical_text, valid_anchor_ids={proposal["source_evidence"]["anchor_id"]}
    )

    assert report["overall_status"] == "fail"
    evidence_check = next(c for c in report["checks"] if c["check_name"] == "evidence_span_fidelity")
    assert evidence_check["status"] == "fail"

    review_status = route_review_status(report["overall_status"])
    assert review_status == "escalated"
    assert review_status != "pending"
