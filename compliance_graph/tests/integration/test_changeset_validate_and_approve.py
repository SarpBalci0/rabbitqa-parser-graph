"""Integration test for the POST /v1/graph/changesets/{id}/validate endpoint and
the approval action: a well-formed change set validates to 'validated', then can
be explicitly approved; an invalid one is forced to 'rejected' and approval is
refused."""

import pytest

from compliance_graph.src.api.changesets import validate_changeset_handler
from compliance_graph.src.db.changeset_repository import ChangesetRepository
from compliance_graph.src.graph_mapping_agent.agent import propose_change_set
from compliance_graph.src.review.changeset_approval import (
    ChangesetNotValidatedError,
    approve_change_set,
)
from compliance_graph.tests.conftest import build_accepted_obligation


def test_valid_changeset_validates_and_can_be_approved(tmp_path):
    session, accepted = build_accepted_obligation(tmp_path)
    changeset = propose_change_set(obligations=[accepted], base_snapshot_id=None)

    repo = ChangesetRepository(session)
    repo.create(changeset)

    report = validate_changeset_handler(changeset["changeset_id"], session=session)
    assert report["overall_status"] == "pass"
    assert repo.get(changeset["changeset_id"])["status"] == "validated"

    approved = approve_change_set(changeset["changeset_id"], repository=repo)
    assert approved["status"] == "approved"


def test_invalid_changeset_is_rejected_and_cannot_be_approved(tmp_path):
    session, accepted = build_accepted_obligation(tmp_path)
    clause_id = accepted["identity"]["clause_id"]

    changeset = {
        "changeset_id": "cs_invalid",
        "base_snapshot_id": None,
        "source_clause_ids": [clause_id],
        "ontology_version": "1.0.0",
        "proposed_nodes": [
            {
                "node_id": "obligation:1",
                "type": "Obligation",
                "properties": {"clause_id": clause_id, "norm_type": "obligation"},
                "provenance": {"clause_id": clause_id},
            }
        ],
        "proposed_relationships": [],  # no DERIVED_FROM, no IMPOSES_ON
        "constraint_report": {"changeset_id": "cs_invalid", "rules": [], "overall_status": "pass"},
        "status": "draft",
    }
    repo = ChangesetRepository(session)
    repo.create(changeset)

    report = validate_changeset_handler("cs_invalid", session=session)
    assert report["overall_status"] == "fail"
    assert repo.get("cs_invalid")["status"] == "rejected"

    with pytest.raises(ChangesetNotValidatedError):
        approve_change_set("cs_invalid", repository=repo)
