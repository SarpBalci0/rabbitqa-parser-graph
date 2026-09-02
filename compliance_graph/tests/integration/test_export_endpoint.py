"""Integration test for the GET /v1/graph/snapshots/{id}/export handler (T086)."""

import pytest

from clause_parser.src.api.errors import NotFoundError
from compliance_graph.src.api.export import export_snapshot_handler
from compliance_graph.src.publisher.in_memory_store import InMemoryGraphStore
from compliance_graph.tests.conftest import build_published_snapshot


def test_export_endpoint_returns_schema_valid_payload(tmp_path):
    session, store, snapshot_id, accepted = build_published_snapshot(tmp_path)
    payload = export_snapshot_handler(snapshot_id, session=session, graph_store=store)
    assert payload["snapshot_id"] == snapshot_id
    assert len(payload["obligations"]) == 1


def test_export_endpoint_404s_for_unpublished_snapshot(tmp_path):
    session, store, snapshot_id, accepted = build_published_snapshot(tmp_path)
    fresh_store = InMemoryGraphStore()  # nothing published in this one
    with pytest.raises(NotFoundError):
        export_snapshot_handler(snapshot_id, session=session, graph_store=fresh_store)
