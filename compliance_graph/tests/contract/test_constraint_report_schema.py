"""Contract test: produce_constraint_report's output validates against
shared_contracts/schemas/ConstraintReport.schema.json (produce_constraint_report
already calls validate() internally, so a passing call is itself the test; this
file exists for 1:1 traceability to tasks.md T057)."""

from compliance_graph.src.constraints.report import produce_constraint_report
from compliance_graph.src.graph_mapping_agent.agent import propose_change_set
from compliance_graph.tests.conftest import build_accepted_obligation


def test_constraint_report_is_schema_valid(tmp_path):
    _, accepted = build_accepted_obligation(tmp_path)
    changeset = propose_change_set(obligations=[accepted], base_snapshot_id=None)
    report = produce_constraint_report(
        changeset["changeset_id"], changeset["proposed_nodes"], changeset["proposed_relationships"]
    )
    assert report["overall_status"] == "pass"
