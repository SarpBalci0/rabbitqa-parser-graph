"""T104 smoke test: real Neo4jGraphStore against a live Neo4j instance, not
InMemoryGraphStore.

Requires a running Neo4j reachable at RABBITQA_NEO4J_URI (default
bolt://localhost:7687) with auth disabled (NEO4J_AUTH=none) or matching
RABBITQA_NEO4J_USER/PASSWORD. NOT included in pyproject.toml's default testpaths
(no live Neo4j is available in most environments this repo runs in — see
tasks.md T104) — run explicitly:

    pytest compliance_graph/tests/live_neo4j/ -v

Covers exactly the risk areas T104 named:
1. Transactional publish: commit path, and rollback-on-failure (a real exception
   mid-transaction leaves the graph completely unchanged).
2. MERGE/DETACH DELETE head-pointer sequencing: after N publishes, exactly ONE
   :GraphHead node exists, pointing at the latest snapshot.
3. Cross-snapshot property matching: two snapshots holding same-shaped nodes
   (same clause_id) are not confused by proof-path queries scoped via the
   {snapshot_id: $snapshot_id} property filter.

Also checks the "label injection via f-string" risk named in T104, since it's a
correctness/safety question this smoke test can answer directly rather than leave
purely theoretical.
"""

from __future__ import annotations

import pytest
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable

from compliance_graph.src.db.neo4j_client import Neo4jClient
from compliance_graph.src.publisher.neo4j_store import Neo4jGraphStore


def _live_neo4j_available() -> bool:
    try:
        driver = GraphDatabase.driver("bolt://localhost:7687", auth=None)
        driver.verify_connectivity()
        driver.close()
        return True
    except (ServiceUnavailable, Exception):
        return False


pytestmark = pytest.mark.skipif(
    not _live_neo4j_available(), reason="No live Neo4j reachable at bolt://localhost:7687"
)


@pytest.fixture()
def store():
    client = Neo4jClient(uri="bolt://localhost:7687", user="neo4j", password="")
    client.connect()
    # Wipe the database so this smoke test starts from a known-empty state.
    with client.all_or_nothing_transaction() as tx:
        tx.run("MATCH (n) DETACH DELETE n")
    yield Neo4jGraphStore(client)
    with client.all_or_nothing_transaction() as tx:
        tx.run("MATCH (n) DETACH DELETE n")
    client.close()


def _simple_graph(clause_id: str):
    nodes = [
        {
            "node_id": f"provision:{clause_id}",
            "type": "Provision",
            "properties": {"anchor_id": clause_id, "label": clause_id},
        },
        {
            "node_id": f"obligation:{clause_id}",
            "type": "Obligation",
            "properties": {"clause_id": clause_id, "norm_type": "obligation"},
        },
    ]
    relationships = [
        {
            "from_node_id": f"obligation:{clause_id}",
            "to_node_id": f"provision:{clause_id}",
            "type": "DERIVED_FROM",
        }
    ]
    return nodes, relationships


# --- 1. Transactional publish: commit path ----------------------------------


def test_publish_commits_and_is_queryable(store):
    nodes, relationships = _simple_graph("clause-A")
    metadata = store.publish(nodes=nodes, relationships=relationships, ontology_version="1.0.0")

    assert store.get_head_snapshot_id() == metadata.snapshot_id
    fetched = store.get_snapshot(metadata.snapshot_id)
    assert fetched is not None
    assert fetched.snapshot_id == metadata.snapshot_id
    assert store.is_published(metadata.snapshot_id)


# --- 1. Transactional publish: rollback-on-failure ---------------------------


def test_publish_rolls_back_completely_on_mid_transaction_failure(store):
    """First, a real successful publish to have a known-good baseline. Then force
    a genuine failure partway through a SECOND publish (a malformed node missing
    the required 'node_id' key — a realistic caller bug, not a contrived Cypher
    string) and confirm NOTHING from the failed attempt persisted: node count,
    head snapshot, and snapshot count are all unchanged from the baseline."""
    nodes, relationships = _simple_graph("clause-baseline")
    baseline = store.publish(nodes=nodes, relationships=relationships, ontology_version="1.0.0")

    node_count_before = _count_nodes(store)
    snapshot_count_before = _count_snapshot_metadata(store)
    head_before = store.get_head_snapshot_id()
    assert head_before == baseline.snapshot_id

    bad_nodes = [
        {"node_id": "ok-node", "type": "Provision", "properties": {"anchor_id": "x", "label": "x"}},
        {"type": "Obligation", "properties": {"clause_id": "x", "norm_type": "obligation"}},  # missing node_id
    ]

    with pytest.raises(KeyError):
        store.publish(nodes=bad_nodes, relationships=[], ontology_version="1.0.0")

    assert store.get_head_snapshot_id() == head_before
    assert _count_nodes(store) == node_count_before
    assert _count_snapshot_metadata(store) == snapshot_count_before
    # The half-written 'ok-node' from the failed attempt must not be visible.
    assert not _node_exists(store, "ok-node")


def _count_nodes(store: Neo4jGraphStore) -> int:
    with store._client.all_or_nothing_transaction() as tx:
        return tx.run("MATCH (n) RETURN count(n) AS c").single()["c"]


def _count_snapshot_metadata(store: Neo4jGraphStore) -> int:
    with store._client.all_or_nothing_transaction() as tx:
        return tx.run("MATCH (s:SnapshotMetadata) RETURN count(s) AS c").single()["c"]


def _node_exists(store: Neo4jGraphStore, node_id: str) -> bool:
    with store._client.all_or_nothing_transaction() as tx:
        record = tx.run("MATCH (n {node_id: $node_id}) RETURN n LIMIT 1", node_id=node_id).single()
        return record is not None


# --- 2. MERGE/DETACH DELETE head-pointer sequencing --------------------------


def test_head_pointer_sequencing_across_multiple_publishes(store):
    """After three publishes, exactly ONE :GraphHead node must exist (not zero,
    not stacking up duplicates), pointing at the LATEST snapshot — this is the
    exact 'MERGE/DETACH DELETE sequencing' risk T104 named."""
    ids = []
    for i in range(3):
        nodes, relationships = _simple_graph(f"clause-{i}")
        metadata = store.publish(nodes=nodes, relationships=relationships, ontology_version="1.0.0")
        ids.append(metadata.snapshot_id)

    with store._client.all_or_nothing_transaction() as tx:
        head_nodes = list(tx.run("MATCH (h:GraphHead) RETURN h.snapshot_id AS snapshot_id"))

    assert len(head_nodes) == 1, f"expected exactly 1 :GraphHead node, found {len(head_nodes)}"
    assert head_nodes[0]["snapshot_id"] == ids[-1]
    assert store.get_head_snapshot_id() == ids[-1]


# --- 3. Cross-snapshot property matching -------------------------------------


def test_cross_snapshot_property_matching_does_not_leak_between_snapshots(store):
    """Two snapshots each contain an Obligation node with the SAME clause_id
    property (a realistic case: re-mapping the same clause after an edit).
    Proof-path queries scoped to one snapshot_id must not match the other
    snapshot's nodes even though the clause_id property collides."""
    nodes_1, relationships_1 = _simple_graph("shared-clause-id")
    snap_1 = store.publish(nodes=nodes_1, relationships=relationships_1, ontology_version="1.0.0")

    nodes_2, relationships_2 = _simple_graph("shared-clause-id")
    snap_2 = store.publish(nodes=nodes_2, relationships=relationships_2, ontology_version="1.0.0")

    with store._client.all_or_nothing_transaction() as tx:
        count_in_snap_1 = tx.run(
            "MATCH (o:Obligation {snapshot_id: $sid, clause_id: 'shared-clause-id'}) RETURN count(o) AS c",
            sid=snap_1.snapshot_id,
        ).single()["c"]
        count_in_snap_2 = tx.run(
            "MATCH (o:Obligation {snapshot_id: $sid, clause_id: 'shared-clause-id'}) RETURN count(o) AS c",
            sid=snap_2.snapshot_id,
        ).single()["c"]
        total_obligation_nodes = tx.run("MATCH (o:Obligation) RETURN count(o) AS c").single()["c"]

    assert count_in_snap_1 == 1
    assert count_in_snap_2 == 1
    assert total_obligation_nodes == 2  # both exist; snapshot_id property keeps them distinct


# --- Bonus: label-injection risk, named explicitly in T104 -------------------


def test_relationship_type_with_backtick_does_not_silently_corrupt_the_graph():
    """T104 explicitly named 'label injection via f-string for dynamic node/
    relationship types' as an unverified risk. The constraints engine (§2.4)
    already restricts relationship types to a closed enum BEFORE anything reaches
    neo4j_store.py in the real pipeline, so this is defense-in-depth, not a path
    reachable through normal use — but the question of what actually happens if a
    malformed type ever got this far is answered here, not left theoretical."""
    from shared_contracts.py.db import configure, get_engine_singleton, get_session
    from shared_contracts.py.tables import create_all

    configure("sqlite:///:memory:")
    create_all(get_engine_singleton())

    client = Neo4jClient(uri="bolt://localhost:7687", user="neo4j", password="")
    client.connect()
    with client.all_or_nothing_transaction() as tx:
        tx.run("MATCH (n) DETACH DELETE n")
    store = Neo4jGraphStore(client)

    malicious_type = "REL`}) DETACH DELETE n //"
    nodes = [
        {"node_id": "n1", "type": "Provision", "properties": {"anchor_id": "a", "label": "a"}},
        {"node_id": "n2", "type": "Provision", "properties": {"anchor_id": "b", "label": "b"}},
    ]
    relationships = [{"from_node_id": "n1", "to_node_id": "n2", "type": malicious_type}]

    raised = False
    try:
        store.publish(nodes=nodes, relationships=relationships, ontology_version="1.0.0")
    except Exception:
        raised = True  # a Cypher syntax error is the SAFE outcome here

    with client.all_or_nothing_transaction() as tx:
        remaining = tx.run("MATCH (n) RETURN count(n) AS c").single()["c"]

    with client.all_or_nothing_transaction() as tx:
        tx.run("MATCH (n) DETACH DELETE n")
    client.close()

    if not raised:
        pytest.fail(
            "A relationship type containing Cypher-breaking characters was accepted "
            "WITHOUT error — this means dynamic label interpolation is not fail-safe "
            "and warrants a real fix (parameterized/allow-listed relationship types), "
            "not just upstream enum validation. Nodes remaining after the call: "
            f"{remaining}."
        )
