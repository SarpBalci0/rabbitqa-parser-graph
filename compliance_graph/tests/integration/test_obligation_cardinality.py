"""§2.4: an Obligation node without exactly one DERIVED_FROM->Provision or without
>=1 IMPOSES_ON->Actor fails validation. Built from a real accepted ObligationObject
via the Graph Mapping Agent (the normal, well-formed path), then perturbed to
break each cardinality rule in isolation."""

from compliance_graph.src.constraints.report import produce_constraint_report
from compliance_graph.src.graph_mapping_agent.agent import propose_change_set
from compliance_graph.tests.conftest import build_accepted_obligation


def test_well_formed_change_set_passes_cardinality_rules(tmp_path):
    _, accepted = build_accepted_obligation(tmp_path)
    changeset = propose_change_set(obligations=[accepted], base_snapshot_id=None)

    report = produce_constraint_report(
        changeset["changeset_id"], changeset["proposed_nodes"], changeset["proposed_relationships"]
    )
    assert report["overall_status"] == "pass"


def test_missing_derived_from_fails_cardinality(tmp_path):
    _, accepted = build_accepted_obligation(tmp_path)
    changeset = propose_change_set(obligations=[accepted], base_snapshot_id=None)

    relationships_without_derived_from = [
        r for r in changeset["proposed_relationships"] if r["type"] != "DERIVED_FROM"
    ]

    report = produce_constraint_report(
        changeset["changeset_id"], changeset["proposed_nodes"], relationships_without_derived_from
    )
    assert report["overall_status"] == "fail"
    rule = next(r for r in report["rules"] if r["rule_name"] == "obligation_derived_from_provision")
    assert rule["status"] == "fail"


def test_missing_imposes_on_fails_cardinality(tmp_path):
    _, accepted = build_accepted_obligation(tmp_path)
    changeset = propose_change_set(obligations=[accepted], base_snapshot_id=None)

    relationships_without_imposes_on = [
        r for r in changeset["proposed_relationships"] if r["type"] != "IMPOSES_ON"
    ]

    report = produce_constraint_report(
        changeset["changeset_id"], changeset["proposed_nodes"], relationships_without_imposes_on
    )
    assert report["overall_status"] == "fail"
    rule = next(r for r in report["rules"] if r["rule_name"] == "obligation_imposes_on_actor")
    assert rule["status"] == "fail"
