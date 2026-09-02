"""SQLAlchemy Core table definitions for the pre-graph record store.

Records are stored as validated JSON payloads (the JSON Schema files under
shared_contracts/schemas/ remain the authoritative shape) alongside indexed lookup
columns needed by the endpoints in rabbitqa_spec_v1.0.0.md §5.
"""

from __future__ import annotations

from sqlalchemy import Column, JSON, MetaData, String, Table

metadata = MetaData()

documents_table = Table(
    "canonical_documents",
    metadata,
    Column("document_id", String, primary_key=True),
    Column("source_version", String, primary_key=True),
    Column("checksum_sha256", String, index=True),
    Column("payload", JSON, nullable=False),
)

obligations_table = Table(
    "obligation_revisions",
    metadata,
    Column("revision_id", String, primary_key=True),
    Column("clause_id", String, index=True, nullable=False),
    Column("proposal_payload", JSON, nullable=False),
    Column("validation_report_payload", JSON, nullable=False),
    Column("created_at", String, nullable=False),
)

changesets_table = Table(
    "graph_changesets",
    metadata,
    Column("changeset_id", String, primary_key=True),
    Column("base_snapshot_id", String, nullable=True),
    Column("payload", JSON, nullable=False),
)

agent_call_log_table = Table(
    "agent_call_log",
    metadata,
    Column("id", String, primary_key=True),
    Column("agent_role", String, nullable=False),
    Column("model_version", String, nullable=False),
    Column("prompt_version", String, nullable=False),
    Column("input_hash", String, nullable=False),
    Column("output_hash", String, nullable=False),
    Column("context_hash", String, nullable=False),
    Column("trace_id", String, nullable=True),
    Column("clause_id", String, index=True, nullable=True),
    Column("timestamp", String, nullable=False),
)


def create_all(engine) -> None:
    metadata.create_all(engine)
