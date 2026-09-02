"""Transactional publisher, per rabbitqa_spec_v1.0.0.md §5.7/§4.3.

Preconditions (all MUST hold or 409):
- changeset.status == "approved"
- most recent validate call's constraint_report shows zero failures
- changeset.base_snapshot_id equals the graph's current head snapshot (optimistic
  concurrency — if the graph moved since validation, 409 and the caller must
  re-validate)

On any failure, the graph is left completely unchanged — GraphStore.publish() is
itself all-or-nothing (see snapshot.py's contract and both backends' "commit point"
comments), and this function never calls it unless every precondition already holds,
so there is no window where a partial write could occur.

§7 Graph & registries zone: "constraint checks run inside the same transaction as
the write, not before-and-hope." Found during a security review pass (tasks.md
T100) that trusting only the STORED constraint_report from an earlier, separate
/validate call (§5.6) was exactly "before-and-hope" — nothing re-checked the
proposal immediately before the write. Fixed: constraints are re-run fresh here,
immediately before graph_store.publish(), against the exact nodes/relationships
about to be written — not the possibly-stale stored report. The separate /validate
endpoint remains for reviewer-facing preview (§6.4), but publish never trusts it
alone.
"""

from __future__ import annotations

from compliance_graph.src.constraints.report import produce_constraint_report
from compliance_graph.src.db.changeset_repository import ChangesetRepository
from compliance_graph.src.publisher.snapshot import GraphStore, StaleBaseSnapshotError


class ChangesetNotApprovedError(Exception):
    pass


class ConstraintFailuresPresentError(Exception):
    pass


def publish_change_set(
    changeset_id: str, *, changeset_repository: ChangesetRepository, graph_store: GraphStore
) -> dict:
    changeset = changeset_repository.get(changeset_id)
    if changeset is None:
        raise ValueError(f"No such changeset: {changeset_id}")

    if changeset["status"] != "approved":
        raise ChangesetNotApprovedError(
            f"Changeset {changeset_id} has status '{changeset['status']}', not 'approved'."
        )

    # Re-check fresh, not the possibly-stale stored constraint_report from an
    # earlier /validate call — this is the fix for the before-and-hope gap.
    fresh_report = produce_constraint_report(
        changeset_id, changeset["proposed_nodes"], changeset["proposed_relationships"]
    )
    if fresh_report["overall_status"] != "pass":
        raise ConstraintFailuresPresentError(
            f"Changeset {changeset_id} fails a fresh constraint re-check immediately "
            f"before publish (stored constraint_report may be stale)."
        )

    current_head = graph_store.get_head_snapshot_id()
    if changeset.get("base_snapshot_id") != current_head:
        raise StaleBaseSnapshotError(
            f"Changeset {changeset_id}'s base_snapshot_id "
            f"({changeset.get('base_snapshot_id')!r}) no longer matches the graph's "
            f"current head ({current_head!r}); re-validate against the new head."
        )

    # All preconditions hold — the graph is guaranteed unchanged up to this line.
    # publish() itself is the single all-or-nothing write.
    metadata = graph_store.publish(
        nodes=changeset["proposed_nodes"],
        relationships=changeset["proposed_relationships"],
        ontology_version=changeset["ontology_version"],
    )

    # §7 provenance chain: "GraphChangeSet.changeset_id -> graph snapshot_id" — this
    # link must be persisted and queryable, not just returned to the immediate
    # caller, so compliance_graph/src/export/provenance.py can resolve it later.
    changeset_repository.update_status(
        changeset_id,
        status="published",
        patch={"published_snapshot_id": metadata.snapshot_id, "constraint_report": fresh_report},
    )

    return {"snapshot_id": metadata.snapshot_id, "published_at": metadata.published_at}
