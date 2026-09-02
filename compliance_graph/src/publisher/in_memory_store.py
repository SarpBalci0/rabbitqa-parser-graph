"""In-memory GraphStore test double.

Used exclusively by the test suite (never wired into the API's default
configuration — see api/changesets.py, api/query.py, api/snapshots.py, which
default to Neo4jGraphStore) because no live Neo4j instance is available in this
development environment. Implements the exact same GraphStore contract as
neo4j_store.py, including all-or-nothing publish semantics and the §3.3 proof-path
pattern, so the precondition/atomicity/lineage logic this backs is genuinely
exercised — only the storage substrate differs from production.
"""

from __future__ import annotations

import copy
from typing import Any

from compliance_graph.src.publisher.snapshot import SnapshotMetadata, new_snapshot_id, now_iso, today_iso


class InMemoryGraphStore:
    def __init__(self):
        self._head_snapshot_id: str | None = None
        self._snapshots: dict[str, SnapshotMetadata] = {}
        # snapshot_id -> {"nodes": {node_id: node}, "relationships": [rel, ...]}
        self._snapshot_content: dict[str, dict[str, Any]] = {}

    def get_head_snapshot_id(self) -> str | None:
        return self._head_snapshot_id

    def publish(
        self, *, nodes: list[dict[str, Any]], relationships: list[dict[str, Any]], ontology_version: str
    ) -> SnapshotMetadata:
        # Simulate an all-or-nothing transaction: stage everything locally, only
        # commit (mutate self._... ) at the very end. Any exception before that
        # point leaves self completely untouched.
        staged_snapshot_id = new_snapshot_id()
        staged_content = {
            "nodes": {n["node_id"]: copy.deepcopy(n) for n in nodes},
            "relationships": copy.deepcopy(relationships),
        }
        staged_metadata = SnapshotMetadata(
            snapshot_id=staged_snapshot_id,
            ontology_version=ontology_version,
            valid_from=today_iso(),
            superseded_snapshot_id=self._head_snapshot_id,
            published_at=now_iso(),
        )

        # --- commit point: everything below is the only code that mutates state ---
        self._snapshots[staged_snapshot_id] = staged_metadata
        self._snapshot_content[staged_snapshot_id] = staged_content
        self._head_snapshot_id = staged_snapshot_id
        return staged_metadata

    def get_snapshot(self, snapshot_id: str) -> SnapshotMetadata | None:
        return self._snapshots.get(snapshot_id)

    def is_published(self, snapshot_id: str) -> bool:
        return snapshot_id in self._snapshots

    def query_proof_path(self, snapshot_id: str) -> list[dict[str, Any]]:
        """Returns raw graph-only path results: {clause_id, path, graph_snapshot_id}.
        verbatim_text/review_status are NOT graph properties (the Obligation node
        only carries clause_id+norm_type per §3.1) — enrichment from the
        ObligationObject store happens one layer up, in query/proof_path.py."""
        content = self._snapshot_content.get(snapshot_id)
        if content is None:
            return []
        nodes = content["nodes"]
        relationships = content["relationships"]

        def edges_from(node_id: str, rel_type: str) -> list[str]:
            return [r["to_node_id"] for r in relationships if r["from_node_id"] == node_id and r["type"] == rel_type]

        results: list[dict[str, Any]] = []
        for node_id, node in nodes.items():
            if node["type"] != "Obligation":
                continue
            clause_id = node["properties"]["clause_id"]

            provision_ids = edges_from(node_id, "DERIVED_FROM")
            control_ids = edges_from(node_id, "MAPS_TO_CONTROL")
            for provision_id in provision_ids:
                if provision_id not in nodes or nodes[provision_id]["type"] != "Provision":
                    continue
                for control_id in control_ids:
                    if control_id not in nodes or nodes[control_id]["type"] != "Control":
                        continue
                    asset_ids = edges_from(control_id, "AFFECTS_ASSET")
                    evidence_ids = edges_from(control_id, "SATISFIED_BY")
                    for asset_id in asset_ids or [None]:
                        for evidence_id in evidence_ids or [None]:
                            test_asset_ids = (
                                edges_from(evidence_id, "EVIDENCED_BY") if evidence_id else []
                            )
                            for test_asset_id in test_asset_ids or [None]:
                                path = [
                                    provision_id,
                                    node_id,
                                    control_id,
                                    asset_id,
                                    evidence_id,
                                    test_asset_id,
                                ]
                                results.append(
                                    {
                                        "clause_id": clause_id,
                                        "path": [p for p in path if p is not None],
                                        "graph_snapshot_id": snapshot_id,
                                    }
                                )
        return results

    def find_latest_regulation(self, instrument: str) -> dict[str, Any] | None:
        """Scans snapshots in publish order (Python dicts preserve insertion
        order); the LAST matching Regulation node found is the most recently
        published one, since each publish() call is a new dict entry appended at
        the end."""
        latest: dict[str, Any] | None = None
        for snapshot_id, content in self._snapshot_content.items():
            for node_id, node in content["nodes"].items():
                if node["type"] == "Regulation" and node["properties"].get("instrument") == instrument:
                    latest = {
                        "node_id": node_id,
                        "snapshot_id": snapshot_id,
                        "source_version": node["properties"].get("source_version"),
                    }
        return latest

    def find_regulation_supersedes_target(self, instrument: str, source_version: str) -> dict[str, Any] | None:
        for snapshot_id, content in self._snapshot_content.items():
            for node_id, node in content["nodes"].items():
                if (
                    node["type"] == "Regulation"
                    and node["properties"].get("instrument") == instrument
                    and node["properties"].get("source_version") == source_version
                ):
                    for rel in content["relationships"]:
                        if rel["from_node_id"] == node_id and rel["type"] == "SUPERSEDES":
                            target = content["nodes"].get(rel["to_node_id"])
                            if target is not None:
                                return {
                                    "instrument": target["properties"].get("instrument"),
                                    "source_version": target["properties"].get("source_version"),
                                }
        return None
