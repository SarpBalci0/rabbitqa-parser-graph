"""§2.4: a relationship referencing a node_id absent from both proposed_nodes and
any published base snapshot fails validation."""

from compliance_graph.src.constraints.report import produce_constraint_report
from compliance_graph.src.graph_mapping_agent.agent import propose_change_set
from compliance_graph.tests.conftest import build_accepted_obligation


def test_dangling_relationship_reference_fails(tmp_path):
    _, accepted = build_accepted_obligation(tmp_path)
    changeset = propose_change_set(obligations=[accepted], base_snapshot_id=None)

    obligation_node_id = next(
        n["node_id"] for n in changeset["proposed_nodes"] if n["type"] == "Obligation"
    )
    dangling_relationships = changeset["proposed_relationships"] + [
        {
            "from_node_id": obligation_node_id,
            "to_node_id": "control:does-not-exist",
            "type": "MAPS_TO_CONTROL",
            "provenance": {},
        }
    ]

    report = produce_constraint_report(
        changeset["changeset_id"], changeset["proposed_nodes"], dangling_relationships
    )
    assert report["overall_status"] == "fail"
    rule = next(r for r in report["rules"] if r["rule_name"] == "no_dangling_node_reference")
    assert rule["status"] == "fail"


def test_reference_to_already_published_node_is_not_dangling(tmp_path):
    _, accepted = build_accepted_obligation(tmp_path)
    changeset = propose_change_set(obligations=[accepted], base_snapshot_id="snap1")

    obligation_node_id = next(
        n["node_id"] for n in changeset["proposed_nodes"] if n["type"] == "Obligation"
    )
    relationships_referencing_published = changeset["proposed_relationships"] + [
        {
            "from_node_id": obligation_node_id,
            "to_node_id": "control:already-published",
            "type": "MAPS_TO_CONTROL",
            "provenance": {},
        }
    ]

    report = produce_constraint_report(
        changeset["changeset_id"],
        changeset["proposed_nodes"],
        relationships_referencing_published,
        published_node_ids=frozenset({"control:already-published"}),
    )
    rule = next(r for r in report["rules"] if r["rule_name"] == "no_dangling_node_reference")
    assert rule["status"] == "pass"
