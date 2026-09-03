"""§5.11 contract: error responses from GET .../proof-path-view always use the
standard JSON envelope (never an HTML error page), per contracts/proof-path-view.md.
"""

from __future__ import annotations

import pytest

from clause_parser.src.api.errors import NotFoundError, SchemaValidationHttpError
from clause_parser.src.db.obligation_repository import ObligationRepository
from compliance_graph.src.api.visualization import render_proof_path_view_handler
from compliance_graph.src.publisher.in_memory_store import InMemoryGraphStore
from compliance_graph.tests.conftest import build_published_snapshot


def test_missing_clause_id_returns_400_schema_validation_failed(tmp_path):
    session, store, snapshot_id, _ = build_published_snapshot(tmp_path)
    obl_repo = ObligationRepository(session)

    with pytest.raises(SchemaValidationHttpError) as exc_info:
        render_proof_path_view_handler(
            snapshot_id, "", graph_store=store, obligation_repository=obl_repo
        )
    assert exc_info.value.code == "schema_validation_failed"
    assert exc_info.value.status_code == 400


def test_unpublished_snapshot_id_returns_404_not_found(tmp_path):
    store = InMemoryGraphStore()
    session, _accepted = _build_accepted_only(tmp_path)
    obl_repo = ObligationRepository(session)

    with pytest.raises(NotFoundError) as exc_info:
        render_proof_path_view_handler(
            "snap_never_published", "clause-does-not-matter", graph_store=store, obligation_repository=obl_repo
        )
    assert exc_info.value.code == "not_found"
    assert exc_info.value.status_code == 404


def test_published_snapshot_unknown_clause_id_returns_404_same_shape(tmp_path):
    session, store, snapshot_id, accepted = build_published_snapshot(tmp_path)
    obl_repo = ObligationRepository(session)

    with pytest.raises(NotFoundError) as exc_info:
        render_proof_path_view_handler(
            snapshot_id, "clause-that-does-not-exist", graph_store=store, obligation_repository=obl_repo
        )
    assert exc_info.value.code == "not_found"
    assert exc_info.value.status_code == 404


def _build_accepted_only(tmp_path):
    from compliance_graph.tests.conftest import build_accepted_obligation

    return build_accepted_obligation(tmp_path)
