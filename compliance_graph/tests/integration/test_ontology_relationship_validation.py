"""§9.1 Graph mapping Given/When/Then: a relationship type/pair not in the §3.2
table forces constraint_report failure and status == "rejected".

Uses a real accepted ObligationObject from the actual US1->US2 pipeline (per the
agreed approach), then proposes an intentionally invalid graph change set on top
of it.
"""

from compliance_graph.src.constraints.report import produce_constraint_report
from compliance_graph.src.constraints.engine import resolve_status_after_validation
from compliance_graph.src.db.changeset_repository import ChangesetRepository
from compliance_graph.tests.conftest import build_accepted_obligation


def test_disallowed_relationship_pair_forces_rejection(tmp_path):
    session, accepted = build_accepted_obligation(tmp_path)
    clause_id = accepted["identity"]["clause_id"]

    changeset = {
        "changeset_id": "cs_bad",
        "base_snapshot_id": None,
        "source_clause_ids": [clause_id],
        "ontology_version": "1.0.0",
        "proposed_nodes": [
            {
                "node_id": "obligation:1",
                "type": "Obligation",
                "properties": {"clause_id": clause_id, "norm_type": "obligation"},
                "provenance": {"clause_id": clause_id},
            },
            {
                "node_id": "asset:1",
                "type": "Asset",
                "properties": {"asset_id": "a1", "name": "Firewall", "asset_type": "network"},
                "provenance": {"clause_id": clause_id},
            },
        ],
        # DERIVED_FROM must point Obligation -> Provision, not Obligation -> Asset.
        "proposed_relationships": [
            {"from_node_id": "obligation:1", "to_node_id": "asset:1", "type": "DERIVED_FROM", "provenance": {}},
        ],
        "constraint_report": {"changeset_id": "cs_bad", "rules": [], "overall_status": "pass"},
        "status": "draft",
    }

    repo = ChangesetRepository(session)
    repo.create(changeset)

    report = produce_constraint_report(
        "cs_bad", changeset["proposed_nodes"], changeset["proposed_relationships"]
    )
    assert report["overall_status"] == "fail"
    pair_rule = next(r for r in report["rules"] if r["rule_name"] == "relationship_type_pair_allowed")
    assert pair_rule["status"] == "fail"

    new_status = resolve_status_after_validation(report["overall_status"], changeset["status"])
    assert new_status == "rejected"
