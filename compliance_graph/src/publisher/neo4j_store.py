"""Real GraphStore backend using Cypher via the T014 Neo4jClient.

NOT covered by an automated test in this development pass — no live Neo4j instance
is available here (no local server, Docker daemon not running). The `in_memory_store.
InMemoryGraphStore` implements the identical GraphStore contract and is what the
test suite actually exercises for publish/query business logic (preconditions,
atomicity, 404 gating). This file implements the literal §4.1/§4.3 requirement
("Neo4j... Cypher-style traversal" per research.md §4) for production use; its
Cypher statements should be verified against a real instance before deployment.
"""

from __future__ import annotations

from typing import Any

from compliance_graph.src.db.neo4j_client import Neo4jClient
from compliance_graph.src.publisher.snapshot import SnapshotMetadata, new_snapshot_id, now_iso, today_iso

_HEAD_POINTER_LABEL = "GraphHead"


class Neo4jGraphStore:
    def __init__(self, client: Neo4jClient):
        self._client = client

    def get_head_snapshot_id(self) -> str | None:
        self._client.connect()
        with self._client.all_or_nothing_transaction() as tx:
            result = tx.run(f"MATCH (h:{_HEAD_POINTER_LABEL}) RETURN h.snapshot_id AS snapshot_id LIMIT 1")
            record = result.single()
            return record["snapshot_id"] if record else None

    def publish(
        self, *, nodes: list[dict[str, Any]], relationships: list[dict[str, Any]], ontology_version: str
    ) -> SnapshotMetadata:
        snapshot_id = new_snapshot_id()
        published_at = now_iso()
        valid_from = today_iso()

        with self._client.all_or_nothing_transaction() as tx:
            current_head = tx.run(
                f"MATCH (h:{_HEAD_POINTER_LABEL}) RETURN h.snapshot_id AS snapshot_id LIMIT 1"
            ).single()
            superseded_snapshot_id = current_head["snapshot_id"] if current_head else None

            for node in nodes:
                tx.run(
                    "MERGE (n {node_id: $node_id, snapshot_id: $snapshot_id}) "
                    "SET n += $properties SET n:`" + node["type"] + "`",
                    node_id=node["node_id"],
                    snapshot_id=snapshot_id,
                    properties=node.get("properties", {}),
                )

            for rel in relationships:
                tx.run(
                    "MATCH (a {node_id: $from_id, snapshot_id: $snapshot_id}), "
                    "(b {node_id: $to_id, snapshot_id: $snapshot_id}) "
                    "MERGE (a)-[r:`" + rel["type"] + "`]->(b)",
                    from_id=rel["from_node_id"],
                    to_id=rel["to_node_id"],
                    snapshot_id=snapshot_id,
                )

            tx.run(
                "MERGE (s:SnapshotMetadata {snapshot_id: $snapshot_id}) "
                "SET s.ontology_version = $ontology_version, s.valid_from = $valid_from, "
                "s.superseded_snapshot_id = $superseded_snapshot_id, s.published_at = $published_at",
                snapshot_id=snapshot_id,
                ontology_version=ontology_version,
                valid_from=valid_from,
                superseded_snapshot_id=superseded_snapshot_id,
                published_at=published_at,
            )

            tx.run(f"MATCH (h:{_HEAD_POINTER_LABEL}) DETACH DELETE h")
            tx.run(f"CREATE (h:{_HEAD_POINTER_LABEL} {{snapshot_id: $snapshot_id}})", snapshot_id=snapshot_id)

        return SnapshotMetadata(
            snapshot_id=snapshot_id,
            ontology_version=ontology_version,
            valid_from=valid_from,
            superseded_snapshot_id=superseded_snapshot_id,
            published_at=published_at,
        )

    def get_snapshot(self, snapshot_id: str) -> SnapshotMetadata | None:
        with self._client.all_or_nothing_transaction() as tx:
            record = tx.run(
                "MATCH (s:SnapshotMetadata {snapshot_id: $snapshot_id}) RETURN s", snapshot_id=snapshot_id
            ).single()
            if record is None:
                return None
            s = record["s"]
            return SnapshotMetadata(
                snapshot_id=s["snapshot_id"],
                ontology_version=s["ontology_version"],
                valid_from=s["valid_from"],
                superseded_snapshot_id=s.get("superseded_snapshot_id"),
                published_at=s["published_at"],
            )

    def is_published(self, snapshot_id: str) -> bool:
        return self.get_snapshot(snapshot_id) is not None

    def query_proof_path(self, snapshot_id: str) -> list[dict[str, Any]]:
        """§3.3 (spec_version 1.0.4 pattern, starting at Provision)."""
        cypher = (
            "MATCH (provision:Provision {snapshot_id: $snapshot_id})"
            "<-[:DERIVED_FROM]-(o:Obligation {snapshot_id: $snapshot_id})"
            "-[:MAPS_TO_CONTROL]->(c:Control {snapshot_id: $snapshot_id})"
            "-[:AFFECTS_ASSET]->(a:Asset {snapshot_id: $snapshot_id}) "
            "MATCH (c)-[:SATISFIED_BY]->(e:EvidenceRequirement {snapshot_id: $snapshot_id})"
            "-[:EVIDENCED_BY]->(t:TestAsset {snapshot_id: $snapshot_id}) "
            "RETURN o.clause_id AS clause_id, "
            "[provision.node_id, o.node_id, c.node_id, a.node_id, e.node_id, t.node_id] AS path"
        )
        with self._client.all_or_nothing_transaction() as tx:
            results = tx.run(cypher, snapshot_id=snapshot_id)
            return [
                {"clause_id": r["clause_id"], "path": r["path"], "graph_snapshot_id": snapshot_id}
                for r in results
            ]

    def find_latest_regulation(self, instrument: str) -> dict[str, Any] | None:
        """Most recently published Regulation node for this instrument, across all
        snapshot history (Regulation nodes are per-snapshot, not carried forward
        automatically — see the in-memory backend's docstring for the same note).
        Ordered by SnapshotMetadata.published_at, the most reliable ordering signal
        available (node creation order is not otherwise recoverable from Cypher)."""
        cypher = (
            "MATCH (r:Regulation {instrument: $instrument}) "
            "MATCH (s:SnapshotMetadata {snapshot_id: r.snapshot_id}) "
            "RETURN r.node_id AS node_id, r.snapshot_id AS snapshot_id, r.source_version AS source_version "
            "ORDER BY s.published_at DESC LIMIT 1"
        )
        with self._client.all_or_nothing_transaction() as tx:
            record = tx.run(cypher, instrument=instrument).single()
            if record is None:
                return None
            return {
                "node_id": record["node_id"],
                "snapshot_id": record["snapshot_id"],
                "source_version": record["source_version"],
            }

    def find_regulation_supersedes_target(self, instrument: str, source_version: str) -> dict[str, Any] | None:
        cypher = (
            "MATCH (r:Regulation {instrument: $instrument, source_version: $source_version})"
            "-[:SUPERSEDES]->(target:Regulation {snapshot_id: r.snapshot_id}) "
            "RETURN target.instrument AS instrument, target.source_version AS source_version LIMIT 1"
        )
        with self._client.all_or_nothing_transaction() as tx:
            record = tx.run(cypher, instrument=instrument, source_version=source_version).single()
            if record is None:
                return None
            return {"instrument": record["instrument"], "source_version": record["source_version"]}
