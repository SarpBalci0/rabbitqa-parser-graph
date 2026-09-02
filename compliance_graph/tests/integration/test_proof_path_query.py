"""§3.3/§5.9: every proof-path query result includes clause_id, verbatim_text,
review_status, graph_snapshot_id — using the spec_version 1.0.4 corrected pattern
(Provision as the first hop, not the originally-unsatisfiable Regulation)."""

from compliance_graph.src.api.changesets import publish_changeset_handler, validate_changeset_handler
from compliance_graph.src.api.query import GraphQueryRequest, run_query_handler
from compliance_graph.src.db.changeset_repository import ChangesetRepository
from clause_parser.src.db.obligation_repository import ObligationRepository
from compliance_graph.src.graph_mapping_agent.agent import propose_change_set
from compliance_graph.src.publisher.in_memory_store import InMemoryGraphStore
from compliance_graph.src.review.changeset_approval import approve_change_set
from compliance_graph.tests.conftest import build_accepted_obligation


def _publish_full_path_changeset(session, accepted):
    """Builds a changeset with the full §3.3 path by augmenting the agent's output
    with EvidenceRequirement/TestAsset nodes and SATISFIED_BY/EVIDENCED_BY edges —
    the Graph Mapping Agent's fixture support (control_mappings/asset_mappings)
    doesn't yet cover evidence/test-asset mapping, so this test constructs that part
    directly rather than claiming the agent produces it."""
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
    # §3.3's canonical path continues c-[:AFFECTS_ASSET]->(a:Asset) FROM Control (the
    # agent's asset_mappings wires Obligation->Asset instead — also valid per §3.2,
    # but a separate edge is needed here to complete this specific canonical path).
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

    session_repo = ChangesetRepository(session)
    session_repo.create(changeset)
    validate_changeset_handler(changeset["changeset_id"], session=session)
    approve_change_set(changeset["changeset_id"], repository=session_repo)

    store = InMemoryGraphStore()
    publish_result = publish_changeset_handler(changeset["changeset_id"], session=session, graph_store=store)
    return store, publish_result["snapshot_id"], clause_id


def test_proof_path_query_returns_required_fields(tmp_path):
    session, accepted = build_accepted_obligation(tmp_path)
    store, snapshot_id, clause_id = _publish_full_path_changeset(session, accepted)

    obl_repo = ObligationRepository(session)
    request = GraphQueryRequest(snapshot_id=snapshot_id, pattern="proof_path", filters={})
    response = run_query_handler(request, graph_store=store, obligation_repository=obl_repo)

    assert len(response["results"]) >= 1
    for result in response["results"]:
        assert result["clause_id"] == clause_id
        assert result["verbatim_text"]  # non-empty, sourced from the ObligationObject
        assert result["review_status"] == "accepted"
        assert result["graph_snapshot_id"] == snapshot_id
        assert isinstance(result["path"], list) and len(result["path"]) == 6
