"""§5.9: querying a snapshot_id that is not fully published (still draft/validated/
approved) MUST return 404, not partial data. This is the first hard gate the user
specifically asked to verify — tested across all three non-published statuses, not
just one, plus a nonexistent snapshot_id.
"""

import pytest

from clause_parser.src.api.errors import NotFoundError
from clause_parser.src.db.obligation_repository import ObligationRepository
from compliance_graph.src.api.changesets import validate_changeset_handler
from compliance_graph.src.api.query import GraphQueryRequest, run_query_handler
from compliance_graph.src.db.changeset_repository import ChangesetRepository
from compliance_graph.src.graph_mapping_agent.agent import propose_change_set
from compliance_graph.src.publisher.in_memory_store import InMemoryGraphStore
from compliance_graph.src.review.changeset_approval import approve_change_set
from compliance_graph.tests.conftest import build_accepted_obligation


def _query(store, obl_repo, fake_snapshot_id):
    request = GraphQueryRequest(snapshot_id=fake_snapshot_id, pattern="proof_path", filters={})
    return run_query_handler(request, graph_store=store, obligation_repository=obl_repo)


def test_querying_a_draft_changesets_id_returns_404(tmp_path):
    """A changeset's own changeset_id (not a snapshot_id) was never published —
    querying it must 404, never return partial/empty-but-200 results."""
    session, accepted = build_accepted_obligation(tmp_path)
    changeset = propose_change_set(obligations=[accepted], base_snapshot_id=None)
    ChangesetRepository(session).create(changeset)  # left at 'draft'

    store = InMemoryGraphStore()
    obl_repo = ObligationRepository(session)

    with pytest.raises(NotFoundError):
        _query(store, obl_repo, changeset["changeset_id"])


def test_querying_a_validated_but_not_approved_changesets_id_returns_404(tmp_path):
    session, accepted = build_accepted_obligation(tmp_path)
    changeset = propose_change_set(obligations=[accepted], base_snapshot_id=None)
    ChangesetRepository(session).create(changeset)
    validate_changeset_handler(changeset["changeset_id"], session=session)  # -> 'validated', not approved

    store = InMemoryGraphStore()
    obl_repo = ObligationRepository(session)

    with pytest.raises(NotFoundError):
        _query(store, obl_repo, changeset["changeset_id"])


def test_querying_an_approved_but_not_published_changesets_id_returns_404(tmp_path):
    session, accepted = build_accepted_obligation(tmp_path)
    changeset = propose_change_set(obligations=[accepted], base_snapshot_id=None)
    repo = ChangesetRepository(session)
    repo.create(changeset)
    validate_changeset_handler(changeset["changeset_id"], session=session)
    approve_change_set(changeset["changeset_id"], repository=repo)  # -> 'approved', never published

    store = InMemoryGraphStore()  # graph store has NOTHING published — approval alone never writes to it
    obl_repo = ObligationRepository(session)

    with pytest.raises(NotFoundError):
        _query(store, obl_repo, changeset["changeset_id"])

    # Confirm no partial data exists in the store at all for this id.
    assert store.is_published(changeset["changeset_id"]) is False
    assert store.get_snapshot(changeset["changeset_id"]) is None


def test_querying_a_completely_nonexistent_snapshot_id_returns_404(tmp_path):
    session, accepted = build_accepted_obligation(tmp_path)
    store = InMemoryGraphStore()
    obl_repo = ObligationRepository(session)

    with pytest.raises(NotFoundError):
        _query(store, obl_repo, "snap_does_not_exist_at_all")


def test_a_genuinely_published_snapshot_is_queryable_not_404(tmp_path):
    """Negative control: confirm the 404 gate isn't just always firing."""
    from compliance_graph.src.api.changesets import publish_changeset_handler

    session, accepted = build_accepted_obligation(tmp_path)
    changeset = propose_change_set(obligations=[accepted], base_snapshot_id=None)
    repo = ChangesetRepository(session)
    repo.create(changeset)
    validate_changeset_handler(changeset["changeset_id"], session=session)
    approve_change_set(changeset["changeset_id"], repository=repo)

    store = InMemoryGraphStore()
    result = publish_changeset_handler(changeset["changeset_id"], session=session, graph_store=store)

    obl_repo = ObligationRepository(session)
    response = _query(store, obl_repo, result["snapshot_id"])
    assert "results" in response  # did not raise
