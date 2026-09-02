"""Unit test for compliance_graph.src.db.changeset_repository (T019) — previously
untested, found during a spec-code synchronization audit."""

from shared_contracts.py.db import configure, get_session, get_engine_singleton
from shared_contracts.py.tables import create_all
from compliance_graph.src.db.changeset_repository import ChangesetRepository


def _fresh_repo():
    configure("sqlite:///:memory:")
    create_all(get_engine_singleton())
    return ChangesetRepository(get_session())


def _changeset_payload(status="draft"):
    return {
        "changeset_id": "cs1",
        "base_snapshot_id": None,
        "source_clause_ids": ["c1"],
        "ontology_version": "1.0.0",
        "proposed_nodes": [],
        "proposed_relationships": [],
        "constraint_report": {"changeset_id": "cs1", "rules": [], "overall_status": "pass"},
        "status": status,
    }


def test_create_and_get_roundtrip():
    repo = _fresh_repo()
    repo.create(_changeset_payload())
    fetched = repo.get("cs1")
    assert fetched["status"] == "draft"


def test_update_status_transition():
    repo = _fresh_repo()
    repo.create(_changeset_payload())
    updated = repo.update_status("cs1", status="validated")
    assert updated["status"] == "validated"
    assert repo.get("cs1")["status"] == "validated"


def test_update_status_on_missing_changeset_raises():
    repo = _fresh_repo()
    try:
        repo.update_status("does-not-exist", status="validated")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_list_by_base_snapshot():
    repo = _fresh_repo()
    repo.create(_changeset_payload())
    payload2 = _changeset_payload()
    payload2["changeset_id"] = "cs2"
    payload2["base_snapshot_id"] = "snap1"
    repo.create(payload2)

    assert [c["changeset_id"] for c in repo.list_by_base_snapshot(None)] == ["cs1"]
    assert [c["changeset_id"] for c in repo.list_by_base_snapshot("snap1")] == ["cs2"]
