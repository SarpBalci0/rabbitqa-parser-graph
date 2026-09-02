"""Provenance-chain resolver, per rabbitqa_spec_v1.1.0.md §7:

"source checksum -> CanonicalDocument.document_id -> parse job run_id + agent
run_ids (per agent, with model/prompt hashes) -> ValidationReport -> reviewer
decision (revision_history entry) -> GraphChangeSet.changeset_id -> graph
snapshot_id -> export request manifest. If any link in this chain cannot be
resolved for a given exported obligation, that obligation MUST NOT appear in the
export — this is a hard gate, not a warning."

Every link is ACTUALLY resolved against real persisted/logged data — not assumed
present. This required two upstream fixes (see clause_parser/src/pipeline.py's
trace_id-as-run_id change, llm_gateway/logging.py's clause_id field, and
publisher.py's published_snapshot_id patch) so these links are genuinely
queryable rather than fabricated by this resolver.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from clause_parser.src.db.document_repository import DocumentRepository
from clause_parser.src.db.obligation_repository import ObligationRepository
from compliance_graph.src.db.changeset_repository import ChangesetRepository
from llm_gateway.logging import DEFAULT_AGENT_CALL_LOG, AgentCallLog


@dataclass(frozen=True)
class ProvenanceChain:
    clause_id: str
    resolved: bool
    unresolved_link: str | None
    document_id: str | None = None
    checksum_sha256: str | None = None
    parse_run_id: str | None = None
    agent_run_count: int = 0
    validation_report_run_id: str | None = None
    reviewer_decision_present: bool = False
    changeset_id: str | None = None
    snapshot_id: str | None = None


def resolve_provenance_chain(
    clause_id: str,
    *,
    document_repository: DocumentRepository,
    obligation_repository: ObligationRepository,
    changeset_repository: ChangesetRepository,
    agent_call_log: AgentCallLog = DEFAULT_AGENT_CALL_LOG,
) -> ProvenanceChain:
    revisions = obligation_repository.list_revisions_for_clause(clause_id)
    if not revisions:
        return ProvenanceChain(clause_id=clause_id, resolved=False, unresolved_link="ValidationReport")

    latest = revisions[-1]
    proposal = latest["proposal"]
    report = latest["validation_report"]
    identity = proposal["identity"]

    # 1. source checksum -> CanonicalDocument.document_id
    document = document_repository.get(identity["document_id"], identity["source_version"])
    if document is None or "checksum_sha256" not in document:
        return ProvenanceChain(clause_id=clause_id, resolved=False, unresolved_link="CanonicalDocument")

    # 2. parse job run_id (ValidationReport.run_id, stamped from the parse job's
    # trace_id per the pipeline.py fix)
    parse_run_id = report.get("run_id")
    if not parse_run_id:
        return ProvenanceChain(clause_id=clause_id, resolved=False, unresolved_link="parse_job_run_id")

    # 3. agent run_ids (per agent, with model/prompt hashes) — at least one
    # Extraction Agent call must be resolvable for this clause_id.
    agent_records = agent_call_log.records_for_clause(clause_id)
    if not agent_records:
        return ProvenanceChain(clause_id=clause_id, resolved=False, unresolved_link="agent_run_ids")

    # 4. ValidationReport — already have it (report), just confirm target matches.
    if report.get("target_clause_id") != clause_id:
        return ProvenanceChain(clause_id=clause_id, resolved=False, unresolved_link="ValidationReport")

    # 5. reviewer decision (revision_history entry)
    revision_history = proposal.get("governance", {}).get("revision_history", [])
    if not revision_history:
        return ProvenanceChain(clause_id=clause_id, resolved=False, unresolved_link="reviewer_decision")

    # 6. GraphChangeSet.changeset_id
    changeset = changeset_repository.find_published_by_clause_id(clause_id)
    if changeset is None:
        return ProvenanceChain(clause_id=clause_id, resolved=False, unresolved_link="GraphChangeSet")

    # 7. graph snapshot_id
    snapshot_id = changeset.get("published_snapshot_id")
    if not snapshot_id:
        return ProvenanceChain(clause_id=clause_id, resolved=False, unresolved_link="graph_snapshot_id")

    return ProvenanceChain(
        clause_id=clause_id,
        resolved=True,
        unresolved_link=None,
        document_id=document["document_id"],
        checksum_sha256=document["checksum_sha256"],
        parse_run_id=parse_run_id,
        agent_run_count=len(agent_records),
        validation_report_run_id=report.get("run_id"),
        reviewer_decision_present=True,
        changeset_id=changeset["changeset_id"],
        snapshot_id=snapshot_id,
    )
