"""§5.7 publish preconditions: non-approved status, stale base_snapshot_id, or
non-zero constraint failures each return a conflict, with the graph left
COMPLETELY unchanged — not partially committed. This is the second hard gate the
user specifically asked to verify.
"""

import pytest

from compliance_graph.src.api.changesets import publish_changeset_handler
from compliance_graph.src.api.errors import ConflictError
from compliance_graph.src.db.changeset_repository import ChangesetRepository
from compliance_graph.src.graph_mapping_agent.agent import propose_change_set
from compliance_graph.src.publisher.in_memory_store import InMemoryGraphStore
from compliance_graph.src.review.changeset_approval import approve_change_set
from compliance_graph.tests.conftest import build_accepted_obligation


def _validated_and_approved_changeset(session, accepted, *, base_snapshot_id=None):
    changeset = propose_change_set(obligations=[accepted], base_snapshot_id=base_snapshot_id)
    repo = ChangesetRepository(session)
    repo.create(changeset)

    from compliance_graph.src.api.changesets import validate_changeset_handler

    validate_changeset_handler(changeset["changeset_id"], session=session)
    approve_change_set(changeset["changeset_id"], repository=repo)
    return changeset["changeset_id"], repo


def test_publishing_a_non_approved_changeset_returns_409_and_graph_unchanged(tmp_path):
    session, accepted = build_accepted_obligation(tmp_path)
    changeset = propose_change_set(obligations=[accepted], base_snapshot_id=None)
    repo = ChangesetRepository(session)
    repo.create(changeset)  # left at 'draft' — never validated or approved

    store = InMemoryGraphStore()
    assert store.get_head_snapshot_id() is None

    with pytest.raises(ConflictError):
        publish_changeset_handler(changeset["changeset_id"], session=session, graph_store=store)

    # Graph is completely untouched: no head, no snapshots at all.
    assert store.get_head_snapshot_id() is None
    assert store._snapshots == {}
    assert store._snapshot_content == {}
    assert repo.get(changeset["changeset_id"])["status"] == "draft"


def test_publishing_with_stale_base_snapshot_returns_409_and_graph_unchanged(tmp_path):
    session, accepted = build_accepted_obligation(tmp_path)
    store = InMemoryGraphStore()

    # Publish once so the graph has a real head snapshot.
    changeset_id_1, repo = _validated_and_approved_changeset(session, accepted, base_snapshot_id=None)
    first_result = publish_changeset_handler(changeset_id_1, session=session, graph_store=store)
    real_head = store.get_head_snapshot_id()
    assert real_head == first_result["snapshot_id"]

    # Second changeset is built against a STALE base_snapshot_id (None, from before
    # the first publish), simulating "the graph moved since validation".
    changeset_id_2, repo2 = _validated_and_approved_changeset(session, accepted, base_snapshot_id=None)
    assert repo2.get(changeset_id_2)["base_snapshot_id"] != real_head

    snapshots_before = dict(store._snapshots)
    content_before = {k: dict(v) for k, v in store._snapshot_content.items()}

    with pytest.raises(ConflictError):
        publish_changeset_handler(changeset_id_2, session=session, graph_store=store)

    # Graph state is byte-for-byte identical to before the failed attempt — not
    # partially committed, and the head pointer did not move.
    assert store.get_head_snapshot_id() == real_head
    assert store._snapshots == snapshots_before
    assert store._snapshot_content == content_before
    assert repo2.get(changeset_id_2)["status"] == "approved"  # not silently marked published


def test_publishing_with_constraint_failures_present_returns_409(tmp_path):
    session, accepted = build_accepted_obligation(tmp_path)
    clause_id = accepted["identity"]["clause_id"]

    # Hand-build a GENUINELY invalid changeset (an Obligation node with no
    # DERIVED_FROM/IMPOSES_ON edges at all — a real §2.4 cardinality violation),
    # directly at 'approved' status, with a stale stored constraint_report that
    # falsely claims "pass" — bypassing the /validate step entirely.
    #
    # This specifically tests the T100 security-review fix: publish must not trust
    # a stale/falsified stored constraint_report — it re-checks the actual
    # proposed_nodes/relationships fresh, immediately before writing. A changeset
    # this invalid must be rejected regardless of what its stored report claims.
    changeset = {
        "changeset_id": "cs_bad_but_approved",
        "base_snapshot_id": None,
        "source_clause_ids": [clause_id],
        "ontology_version": "1.0.0",
        "proposed_nodes": [
            {
                "node_id": "obligation:orphan",
                "type": "Obligation",
                "properties": {"clause_id": clause_id, "norm_type": "obligation"},
                "provenance": {"clause_id": clause_id},
            }
        ],
        "proposed_relationships": [],  # no DERIVED_FROM, no IMPOSES_ON — genuinely invalid
        "constraint_report": {
            "changeset_id": "cs_bad_but_approved",
            "rules": [],
            "overall_status": "pass",  # stale/falsified — the fresh re-check must catch this anyway
        },
        "status": "approved",
    }
    repo = ChangesetRepository(session)
    repo.create(changeset)

    store = InMemoryGraphStore()
    with pytest.raises(ConflictError):
        publish_changeset_handler("cs_bad_but_approved", session=session, graph_store=store)

    # Confirm nothing was published despite the stale report claiming "pass".
    assert store.get_head_snapshot_id() is None

    assert store.get_head_snapshot_id() is None
