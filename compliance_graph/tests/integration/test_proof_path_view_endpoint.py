"""§4.5/§5.11/§7 integration tests for GET .../proof-path-view: full render, the
branching Control->Asset / Control->EvidenceRequirement edge topology (per
research.md "Edge-label derivation" and tasks.md T006 — NOT a linear 6-box chain),
determinism, the review-gate/incomplete-chain 404s, and escaping.
"""

from __future__ import annotations

import pytest

from clause_parser.src.api.errors import NotFoundError
from clause_parser.src.db.obligation_repository import ObligationRepository
from compliance_graph.src.api.changesets import publish_changeset_handler, validate_changeset_handler
from compliance_graph.src.api.visualization import render_proof_path_view_handler
from compliance_graph.src.db.changeset_repository import ChangesetRepository
from compliance_graph.src.graph_mapping_agent.agent import propose_change_set
from compliance_graph.src.publisher.in_memory_store import InMemoryGraphStore
from compliance_graph.src.review.changeset_approval import approve_change_set
from compliance_graph.tests.conftest import build_accepted_obligation


def _publish_full_path_changeset(session, accepted):
    """Same fixture-building approach as test_proof_path_query.py's
    _publish_full_path_changeset: the Graph Mapping Agent doesn't yet cover
    evidence/test-asset mapping, so EvidenceRequirement/TestAsset nodes and their
    relationships are constructed directly."""
    clause_id = accepted["identity"]["clause_id"]
    changeset = propose_change_set(
        obligations=[accepted],
        base_snapshot_id=None,
        controls_assets_evidence_fixture={
            "control_mappings": {clause_id: [{"control_id": "c1", "name": "Incident notification control"}]},
            "asset_mappings": {clause_id: [{"asset_id": "a1", "name": "Reporting system", "asset_type": "system"}]},
        },
    )
    control_id = "control:c1"
    changeset["proposed_nodes"].append(
        {
            "node_id": "evidence:e1",
            "type": "EvidenceRequirement",
            "properties": {"evidence_id": "e1", "description": "Notification log"},
            "provenance": {"clause_id": clause_id},
        }
    )
    changeset["proposed_nodes"].append(
        {
            "node_id": "testasset:t1",
            "type": "TestAsset",
            "properties": {"test_id": "t1", "name": "Notification log sample"},
            "provenance": {"clause_id": clause_id},
        }
    )
    asset_id = "asset:a1"
    changeset["proposed_relationships"].append(
        {"from_node_id": control_id, "to_node_id": asset_id, "type": "AFFECTS_ASSET", "provenance": {}}
    )
    changeset["proposed_relationships"].append(
        {"from_node_id": control_id, "to_node_id": "evidence:e1", "type": "SATISFIED_BY", "provenance": {}}
    )
    changeset["proposed_relationships"].append(
        {"from_node_id": "evidence:e1", "to_node_id": "testasset:t1", "type": "EVIDENCED_BY", "provenance": {}}
    )

    repo = ChangesetRepository(session)
    repo.create(changeset)
    validate_changeset_handler(changeset["changeset_id"], session=session)
    approve_change_set(changeset["changeset_id"], repository=repo)

    store = InMemoryGraphStore()
    publish_result = publish_changeset_handler(changeset["changeset_id"], session=session, graph_store=store)
    return store, publish_result["snapshot_id"], clause_id


def test_full_render_shows_all_nodes_and_correctly_branched_edges(tmp_path):
    session, accepted = build_accepted_obligation(tmp_path)
    store, snapshot_id, clause_id = _publish_full_path_changeset(session, accepted)
    obl_repo = ObligationRepository(session)

    body = render_proof_path_view_handler(
        snapshot_id, clause_id, graph_store=store, obligation_repository=obl_repo
    )

    assert "<svg" in body
    for label in ("provision", "obligation", "control", "asset", "evidence", "testasset"):
        assert label in body.lower()

    for edge_label in ("DERIVED_FROM", "MAPS_TO_CONTROL", "AFFECTS_ASSET", "SATISFIED_BY", "EVIDENCED_BY"):
        assert edge_label in body

    verbatim_text = accepted["source_evidence"]["verbatim_text"]
    assert verbatim_text in body


def test_full_render_control_branches_to_asset_and_evidence_not_asset_to_evidence(tmp_path):
    """Regression test for the F1 fix: the diagram MUST wire Control->Asset
    (AFFECTS_ASSET) and Control->EvidenceRequirement (SATISFIED_BY) as two separate
    edges sourced from Control -- a naive positional/index-adjacent implementation
    would instead draw a nonexistent Asset->EvidenceRequirement edge labeled
    SATISFIED_BY. We can't rely on string search alone to prove wiring, so this
    inspects the renderer's own edge list directly."""
    session, accepted = build_accepted_obligation(tmp_path)
    store, snapshot_id, clause_id = _publish_full_path_changeset(session, accepted)
    obl_repo = ObligationRepository(session)

    from compliance_graph.src.query.proof_path import run_proof_path_query
    from compliance_graph.src.visualization.proof_path_renderer import build_renderable_proof_path

    results = run_proof_path_query(snapshot_id, graph_store=store, obligation_repository=obl_repo)
    result = next(r for r in results if r["clause_id"] == clause_id)
    renderable = build_renderable_proof_path(result)

    assert renderable is not None
    edge_pairs = {(e["from_node_type"], e["to_node_type"], e["relationship_name"]) for e in renderable["edges"]}

    assert ("control", "asset", "AFFECTS_ASSET") in edge_pairs
    assert ("control", "evidence", "SATISFIED_BY") in edge_pairs
    assert ("asset", "evidence", "SATISFIED_BY") not in edge_pairs
    assert not any(frm == "asset" for frm, _, _ in edge_pairs)


def test_two_identical_requests_return_byte_identical_bodies(tmp_path):
    session, accepted = build_accepted_obligation(tmp_path)
    store, snapshot_id, clause_id = _publish_full_path_changeset(session, accepted)
    obl_repo = ObligationRepository(session)

    body1 = render_proof_path_view_handler(
        snapshot_id, clause_id, graph_store=store, obligation_repository=obl_repo
    )
    body2 = render_proof_path_view_handler(
        snapshot_id, clause_id, graph_store=store, obligation_repository=obl_repo
    )
    assert body1 == body2


def test_non_accepted_obligation_returns_404(tmp_path):
    from clause_parser.src.api.reviews import DecisionRequest, submit_decision_handler
    from clause_parser.src.api.documents import DocumentRequest, register_document_handler
    from clause_parser.src.db.document_repository import DocumentRepository
    from clause_parser.src.pipeline import run_parse_job
    from shared_contracts.py.db import configure, get_engine_singleton, get_session
    from shared_contracts.py.tables import create_all

    configure("sqlite:///:memory:")
    create_all(get_engine_singleton())
    session = get_session()
    doc_repo = DocumentRepository(session)
    obl_repo = ObligationRepository(session)

    fixture_path = tmp_path / "doc.txt"
    fixture_path.write_text("Article 21\n1. The operator shall notify the competent authority within 30 days.\n")
    doc_payload, _ = register_document_handler(
        DocumentRequest(instrument="NIS2", source_artifact_uri=str(fixture_path), source_version="v1"), session
    )
    full_doc = doc_repo.get(doc_payload["document_id"], doc_payload["source_version"])
    run_parse_job(full_doc, obligation_repository=obl_repo)

    clause_id = f"{doc_payload['document_id']}:v1:article-21/paragraph-1"
    revision = obl_repo.list_revisions_for_clause(clause_id)[0]
    rejected = submit_decision_handler(
        revision["revision_id"],
        DecisionRequest(reviewer_id="reviewer-1", action="reject", rationale="Not a real obligation."),
        session=session,
    )

    changeset = propose_change_set(obligations=[], base_snapshot_id=None)
    repo = ChangesetRepository(session)
    repo.create(changeset)
    validate_changeset_handler(changeset["changeset_id"], session=session)
    approve_change_set(changeset["changeset_id"], repository=repo)
    store = InMemoryGraphStore()
    publish_result = publish_changeset_handler(changeset["changeset_id"], session=session, graph_store=store)

    with pytest.raises(NotFoundError):
        render_proof_path_view_handler(
            publish_result["snapshot_id"], clause_id, graph_store=store, obligation_repository=obl_repo
        )
    assert rejected["governance"]["review_status"] == "rejected"


def test_accepted_obligation_with_incomplete_chain_returns_404_never_partial(tmp_path):
    session, accepted = build_accepted_obligation(tmp_path)
    clause_id = accepted["identity"]["clause_id"]

    changeset = propose_change_set(obligations=[accepted], base_snapshot_id=None)
    repo = ChangesetRepository(session)
    repo.create(changeset)
    validate_changeset_handler(changeset["changeset_id"], session=session)
    approve_change_set(changeset["changeset_id"], repository=repo)

    store = InMemoryGraphStore()
    publish_result = publish_changeset_handler(changeset["changeset_id"], session=session, graph_store=store)
    obl_repo = ObligationRepository(session)

    with pytest.raises(NotFoundError):
        render_proof_path_view_handler(
            publish_result["snapshot_id"], clause_id, graph_store=store, obligation_repository=obl_repo
        )


def test_verbatim_text_with_special_characters_is_escaped(tmp_path):
    session, accepted = build_accepted_obligation(
        tmp_path,
        text="Article 21\n1. The operator shall notify <the & 'competent' authority> within 30 days.\n",
    )
    store, snapshot_id, clause_id = _publish_full_path_changeset(session, accepted)
    obl_repo = ObligationRepository(session)

    body = render_proof_path_view_handler(
        snapshot_id, clause_id, graph_store=store, obligation_repository=obl_repo
    )

    assert "<the & 'competent' authority>" not in body
    assert "&lt;the" in body
    assert "&amp;" in body
    assert "<script" not in body.lower()
    assert "onerror" not in body.lower()
    assert "foreignobject" not in body.lower()
