"""§9.1 Graph mapping & publish: a successful publish creates a new snapshot_id
that's queryable, and the prior snapshot remains retrievable via
superseded_snapshot_id lineage."""

from compliance_graph.src.api.changesets import publish_changeset_handler, validate_changeset_handler
from compliance_graph.src.api.snapshots import get_snapshot_handler
from compliance_graph.src.db.changeset_repository import ChangesetRepository
from compliance_graph.src.graph_mapping_agent.agent import propose_change_set
from compliance_graph.src.publisher.in_memory_store import InMemoryGraphStore
from compliance_graph.src.review.changeset_approval import approve_change_set
from compliance_graph.tests.conftest import build_accepted_obligation


def _publish(session, repo, accepted, store, base_snapshot_id):
    changeset = propose_change_set(obligations=[accepted], base_snapshot_id=base_snapshot_id)
    repo.create(changeset)
    validate_changeset_handler(changeset["changeset_id"], session=session)
    approve_change_set(changeset["changeset_id"], repository=repo)
    return publish_changeset_handler(changeset["changeset_id"], session=session, graph_store=store)


def test_second_publish_supersedes_first_and_both_remain_retrievable(tmp_path):
    session, accepted = build_accepted_obligation(tmp_path)
    store = InMemoryGraphStore()
    repo = ChangesetRepository(session)

    first_result = _publish(session, repo, accepted, store, base_snapshot_id=None)
    first_snapshot_id = first_result["snapshot_id"]

    second_result = _publish(session, repo, accepted, store, base_snapshot_id=first_snapshot_id)
    second_snapshot_id = second_result["snapshot_id"]

    assert second_snapshot_id != first_snapshot_id
    assert store.get_head_snapshot_id() == second_snapshot_id

    second_metadata = get_snapshot_handler(second_snapshot_id, graph_store=store)
    assert second_metadata["superseded_snapshot_id"] == first_snapshot_id
    assert second_metadata["lineage"] == [second_snapshot_id, first_snapshot_id]

    first_metadata = get_snapshot_handler(first_snapshot_id, graph_store=store)
    assert first_metadata["snapshot_id"] == first_snapshot_id  # still retrievable
