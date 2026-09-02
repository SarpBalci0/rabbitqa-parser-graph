"""Snapshot lineage modeling and the GraphStore interface.

Per rabbitqa_spec_v1.1.0.md §2.5, §4.3, §5.7, §5.8:
- Snapshots are immutable once published; a new publish creates a new snapshot and
  points its `superseded_snapshot_id` at the one it replaces (§5.8 lineage chain).
- Publish is a single all-or-nothing transaction (§4.3 Deterministic publisher).
- §5.7's optimistic-concurrency precondition compares a changeset's
  `base_snapshot_id` against the graph's CURRENT head snapshot.

GraphStore is implemented by two backends (see neo4j_store.py and
in_memory_store.py): the real production backend uses actual Cypher via the T014
Neo4jClient; the in-memory backend is a test-only double with an identical
contract, used because no live Neo4j instance is available in this development
environment. Both must satisfy the same precondition/atomicity/lineage semantics —
this module defines that shared contract precisely so neither backend can quietly
diverge from it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Protocol


@dataclass(frozen=True)
class SnapshotMetadata:
    snapshot_id: str
    ontology_version: str
    valid_from: str  # ISO date
    superseded_snapshot_id: str | None
    published_at: str  # ISO datetime


class GraphStore(Protocol):
    """The contract every publisher/query backend MUST satisfy identically."""

    def get_head_snapshot_id(self) -> str | None:
        """None if no snapshot has ever been published."""
        ...

    def publish(
        self,
        *,
        nodes: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        ontology_version: str,
    ) -> SnapshotMetadata:
        """Publishes nodes+relationships as a new snapshot in a single all-or-
        nothing transaction. MUST raise (leaving the store completely unchanged,
        including the head pointer) if anything inside fails — no partial commit."""
        ...

    def get_snapshot(self, snapshot_id: str) -> SnapshotMetadata | None:
        ...

    def is_published(self, snapshot_id: str) -> bool:
        """True only for a snapshot that completed a successful publish() call —
        never true for draft/validated/approved changeset state, since those never
        reach this store at all."""
        ...

    def query_proof_path(self, snapshot_id: str) -> list[dict[str, Any]]:
        """§3.3 canonical proof-path (spec_version 1.0.4 pattern, starting at
        Provision — see rabbitqa_spec_v1.1.0.md §12 changelog). Returns raw graph
        results only: {clause_id, path, graph_snapshot_id} — verbatim_text and
        review_status are NOT graph properties (the Obligation node only carries
        clause_id+norm_type per §3.1); enrichment from the ObligationObject store
        happens one layer up, in query/proof_path.py. Returns [] if the snapshot
        doesn't exist or has no matching paths — callers are responsible for the
        404-on-unpublished gate (this method assumes snapshot_id IS published; see
        is_published)."""
        ...

    def find_latest_regulation(self, instrument: str) -> dict[str, Any] | None:
        """Searches across ALL published snapshot history (each snapshot's content
        is self-contained per the immutable-versioned-subgraph model — see
        research.md §4 — so a Regulation node from an older snapshot is not
        automatically present in a newer one) for the most recently published
        Regulation node with this instrument. Returns
        {node_id, snapshot_id, source_version} or None if this instrument has
        never been published. Used by graph_mapping_agent to detect that a newly
        mapped source_version supersedes an earlier one (§3.2 SUPERSEDES,
        Regulation->Regulation, snapshot-level only)."""
        ...

    def find_regulation_supersedes_target(self, instrument: str, source_version: str) -> dict[str, Any] | None:
        """Given a published (instrument, source_version)'s Regulation node,
        returns the properties {instrument, source_version} of the Regulation node
        it SUPERSEDES, if any, by searching that Regulation node's own snapshot for
        an outgoing SUPERSEDES relationship. Returns None if no such node was ever
        published, or it supersedes nothing. Used to walk the supersession chain in
        compliance_graph/src/query/article_history.py."""
        ...


class StaleBaseSnapshotError(Exception):
    """§5.7: changeset.base_snapshot_id no longer matches the graph's current head."""


def new_snapshot_id() -> str:
    import uuid

    return f"snap_{uuid.uuid4().hex[:12]}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_iso() -> str:
    return date.today().isoformat()
