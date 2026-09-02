"""GET /v1/clauses/{id}/parse-revisions, per rabbitqa_spec_v1.0.0.md §5.4:
"array of {ObligationObjectProposal, ValidationReport, revision_history} ordered
oldest-first."
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.orm import Session

from clause_parser.src.db.obligation_repository import ObligationRepository


def get_parse_revisions_handler(clause_id: str, *, session: Session) -> list[dict]:
    repo = ObligationRepository(session)
    revisions = repo.list_revisions_for_clause(clause_id)
    return [
        {
            # revision_id: not in §5.4's literal response shape
            # ({ObligationObjectProposal, ValidationReport, revision_history}),
            # but §5.5's POST /v1/reviews/{revision}/decisions has no other way
            # to discover its {revision} path parameter — found via a real
            # curl-based walkthrough that this endpoint's own response gave no
            # way to construct the next request. Added as an additive field.
            "revision_id": r["revision_id"],
            "ObligationObjectProposal": r["proposal"],
            "ValidationReport": r["validation_report"],
            "revision_history": r["proposal"].get("governance", {}).get("revision_history", []),
        }
        for r in revisions
    ]


def build_router(session_factory) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/clauses/{clause_id:path}/parse-revisions")
    def get_parse_revisions(clause_id: str):
        # clause_id legitimately contains '/' (e.g. "article-21/paragraph-1" as
        # its suffix), so the default FastAPI path converter — which stops at the
        # first '/' — would silently truncate it. The ':path' converter matches
        # the rest of the path including slashes. Found and fixed via a real
        # curl-based smoke test that returned a false 404 without this.
        session = session_factory()
        try:
            return get_parse_revisions_handler(clause_id, session=session)
        finally:
            session.close()

    return router
