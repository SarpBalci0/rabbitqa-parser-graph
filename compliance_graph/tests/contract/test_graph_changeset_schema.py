"""Contract test: a GraphChangeSet produced by the Graph Mapping Agent + constraints
engine (including its now-resolvable constraint_report) validates against
GraphChangeSet.schema.json."""

from shared_contracts.py.validation import validate
from compliance_graph.src.constraints.report import produce_constraint_report
from compliance_graph.src.graph_mapping_agent.agent import propose_change_set
from compliance_graph.tests.conftest import build_accepted_obligation


def test_change_set_with_computed_constraint_report_validates(tmp_path):
    _, accepted = build_accepted_obligation(tmp_path)
    changeset = propose_change_set(obligations=[accepted], base_snapshot_id=None)
    changeset["constraint_report"] = produce_constraint_report(
        changeset["changeset_id"], changeset["proposed_nodes"], changeset["proposed_relationships"]
    )
    validate(changeset, "GraphChangeSet.schema.json")
