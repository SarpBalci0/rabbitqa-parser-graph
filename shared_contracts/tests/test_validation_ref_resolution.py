"""Regression test for the GraphChangeSet -> ConstraintReport $ref resolution.

This is the concrete fix for /speckit-analyze finding I1: the $ref used to point
at an undefined file. It must actually resolve, not just parse as valid JSON.
"""

import pytest

from shared_contracts.py.validation import SchemaValidationError, validate


def test_graph_changeset_with_embedded_constraint_report_validates():
    payload = {
        "changeset_id": "cs1",
        "base_snapshot_id": None,
        "source_clause_ids": ["c1"],
        "ontology_version": "1.0.0",
        "proposed_nodes": [],
        "proposed_relationships": [],
        "constraint_report": {"changeset_id": "cs1", "rules": [], "overall_status": "pass"},
        "status": "draft",
    }
    validate(payload, "GraphChangeSet.schema.json")


def test_graph_changeset_missing_required_field_fails():
    payload = {"changeset_id": "cs1"}
    with pytest.raises(SchemaValidationError):
        validate(payload, "GraphChangeSet.schema.json")


def test_constraint_report_validates_standalone():
    payload = {
        "changeset_id": "cs1",
        "rules": [
            {
                "rule_name": "obligation_derived_from_provision",
                "status": "fail",
                "message": "missing DERIVED_FROM edge",
            }
        ],
        "overall_status": "fail",
    }
    validate(payload, "ConstraintReport.schema.json")
