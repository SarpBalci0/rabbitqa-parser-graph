"""POST /v1/graph/changesets/{id}/validate and POST .../publish, per
rabbitqa_spec_v1.1.0.md §5.6/§5.7.

§5.6: "Response 200: ConstraintReport (embedded per §2.4). Does not mutate graph
state." Note: this endpoint DOES mutate the changeset's own status (draft->
validated or ->rejected) via the T019 repository — "does not mutate graph state"
refers to the graph store (Neo4j), which this endpoint never touches, consistent
with §4.3's rule that the constraints engine and Graph Mapping Agent never write to
the graph.

§5.7 publish preconditions (all MUST hold or 409): status == "approved"; most
recent constraint_report is a clean pass; base_snapshot_id matches the graph's
current head (optimistic concurrency).
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.orm import Session

from clause_parser.src.api.errors import ConflictError, NotFoundError
from compliance_graph.src.constraints.engine import resolve_status_after_validation
from compliance_graph.src.constraints.report import produce_constraint_report
from compliance_graph.src.db.changeset_repository import ChangesetRepository
from compliance_graph.src.publisher.publisher import (
    ChangesetNotApprovedError,
    ConstraintFailuresPresentError,
    publish_change_set,
)
from compliance_graph.src.publisher.snapshot import GraphStore, StaleBaseSnapshotError


def validate_changeset_handler(changeset_id: str, *, session: Session) -> dict:
    repo = ChangesetRepository(session)
    changeset = repo.get(changeset_id)
    if changeset is None:
        raise NotFoundError(f"No such changeset: {changeset_id}")

    report = produce_constraint_report(
        changeset_id,
        changeset["proposed_nodes"],
        changeset["proposed_relationships"],
    )

    new_status = resolve_status_after_validation(report["overall_status"], changeset["status"])
    repo.update_status(changeset_id, status=new_status, patch={"constraint_report": report})

    return report


def publish_changeset_handler(changeset_id: str, *, session: Session, graph_store: GraphStore) -> dict:
    repo = ChangesetRepository(session)
    try:
        return publish_change_set(changeset_id, changeset_repository=repo, graph_store=graph_store)
    except (ChangesetNotApprovedError, ConstraintFailuresPresentError, StaleBaseSnapshotError) as exc:
        raise ConflictError(str(exc)) from exc


def build_router(session_factory, graph_store_factory) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/graph/changesets/{changeset_id}/validate")
    def post_validate(changeset_id: str):
        session = session_factory()
        try:
            return validate_changeset_handler(changeset_id, session=session)
        finally:
            session.close()

    @router.post("/v1/graph/changesets/{changeset_id}/publish")
    def post_publish(changeset_id: str):
        session = session_factory()
        try:
            return publish_changeset_handler(
                changeset_id, session=session, graph_store=graph_store_factory()
            )
        finally:
            session.close()

    return router
