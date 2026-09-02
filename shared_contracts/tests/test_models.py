"""Unit test for shared_contracts.py.models (T007) — previously untested, found
during a spec-code synchronization audit."""

from datetime import datetime

from shared_contracts.py.models import CanonicalDocument, ConstraintReport, GraphChangeSet


def test_canonical_document_model_constructs_from_valid_payload():
    doc = CanonicalDocument(
        document_id="doc_abc123456789",
        source_version="v1",
        instrument="NIS2",
        checksum_sha256="a" * 64,
        language="en",
        created_at=datetime.now(),
    )
    assert doc.jurisdiction == "EU"
    assert doc.schema_version == "1.0.0"


def test_graph_changeset_model_requires_constraint_report():
    changeset = GraphChangeSet(
        changeset_id="cs1",
        base_snapshot_id=None,
        source_clause_ids=["c1"],
        ontology_version="1.0.0",
        constraint_report=ConstraintReport(changeset_id="cs1", overall_status="pass"),
        status="draft",
    )
    assert changeset.constraint_report.overall_status == "pass"
