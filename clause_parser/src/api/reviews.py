"""POST /v1/reviews/{revision}/decisions, per rabbitqa_spec_v1.1.0.md §5.5.

Rules: rationale MUST be non-empty (400 otherwise). edit action REQUIRES non-null
edits and MUST re-run ValidationReport on the edited version before persisting — an
edit that fails evidence-span fidelity is rejected with 422, not silently accepted.

T055 (server-side independent re-validation-on-submit guarantee): the server never
trusts a client's claim that validation findings were shown — decision_service.py
re-runs Step 6 validation on every edit unconditionally, and blocks accept/edit
entirely on any record whose current status is 'escalated' (§2.3), regardless of
what any UI displayed.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.orm import Session

from clause_parser.src.api.errors import BusinessRuleViolation, NotFoundError, SchemaValidationHttpError
from clause_parser.src.db.document_repository import DocumentRepository
from clause_parser.src.db.obligation_repository import ObligationRepository
from clause_parser.src.review.decision_service import (
    EditBreaksEvidenceFidelityError,
    EditRequiresEditsError,
    EmptyRationaleError,
    EscalatedRecordNotPresentableError,
    apply_review_decision,
)


class EvidenceFidelityViolation(BusinessRuleViolation):
    status_code = 422
    code = "evidence_span_fidelity_violation"


class DecisionRequest(BaseModel):
    reviewer_id: str
    action: str
    rationale: str
    edits: dict | None = None


def submit_decision_handler(revision_id: str, request: DecisionRequest, *, session: Session) -> dict:
    obl_repo = ObligationRepository(session)
    doc_repo = DocumentRepository(session)

    revision = obl_repo.get_revision(revision_id)
    if revision is None:
        raise NotFoundError(f"No such revision: {revision_id}")

    identity = revision["proposal"]["identity"]
    document_payload = doc_repo.get(identity["document_id"], identity["source_version"])
    if document_payload is None:
        raise NotFoundError(
            f"No such document: {identity['document_id']}/{identity['source_version']}"
        )
    canonical_text = document_payload["_canonical_text"]
    valid_anchor_ids = {a["anchor_id"] for a in document_payload["structure"]}

    try:
        updated_proposal = apply_review_decision(
            revision_id,
            reviewer_id=request.reviewer_id,
            action=request.action,
            rationale=request.rationale,
            edits=request.edits,
            canonical_text=canonical_text,
            valid_anchor_ids=valid_anchor_ids,
            obligation_repository=obl_repo,
        )
    except EmptyRationaleError as exc:
        raise SchemaValidationHttpError(str(exc)) from exc
    except EditRequiresEditsError as exc:
        raise SchemaValidationHttpError(str(exc)) from exc
    except EditBreaksEvidenceFidelityError as exc:
        raise EvidenceFidelityViolation(str(exc), {"validation_report": exc.validation_report}) from exc
    except EscalatedRecordNotPresentableError as exc:
        raise EvidenceFidelityViolation(str(exc)) from exc

    return updated_proposal


def build_router(session_factory) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/reviews/{revision_id}/decisions")
    def post_decision(revision_id: str, request: DecisionRequest):
        session = session_factory()
        try:
            return submit_decision_handler(revision_id, request, session=session)
        finally:
            session.close()

    return router
