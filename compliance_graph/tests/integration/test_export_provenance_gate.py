"""§7 provenance chain: an obligation with any unresolvable provenance-chain link
is excluded from the export.

Uses a real published snapshot (all links genuinely resolvable via the normal
DEFAULT_AGENT_CALL_LOG), then re-runs the export with a FRESH, empty AgentCallLog
injected in place of the default — simulating the "agent run_ids" link being
unresolvable (e.g. logs not retained/queryable) without hand-faking any other part
of the chain.
"""

from clause_parser.src.db.document_repository import DocumentRepository
from clause_parser.src.db.obligation_repository import ObligationRepository
from compliance_graph.src.db.changeset_repository import ChangesetRepository
from compliance_graph.src.export.exporter import build_export
from compliance_graph.src.export.provenance import resolve_provenance_chain
from compliance_graph.tests.conftest import build_published_snapshot
from llm_gateway.logging import AgentCallLog


def test_resolvable_chain_included_with_real_agent_log(tmp_path):
    session, store, snapshot_id, accepted = build_published_snapshot(tmp_path)
    clause_id = accepted["identity"]["clause_id"]

    doc_repo = DocumentRepository(session)
    obl_repo = ObligationRepository(session)
    changeset_repo = ChangesetRepository(session)

    chain = resolve_provenance_chain(
        clause_id,
        document_repository=doc_repo,
        obligation_repository=obl_repo,
        changeset_repository=changeset_repo,
    )
    assert chain.resolved is True
    assert chain.unresolved_link is None

    export_payload = build_export(
        snapshot_id,
        graph_store=store,
        changeset_repository=changeset_repo,
        document_repository=doc_repo,
        obligation_repository=obl_repo,
    )
    assert {o["clause_id"] for o in export_payload["obligations"]} == {clause_id}


def test_unresolvable_agent_run_link_excludes_obligation_from_export(tmp_path):
    session, store, snapshot_id, accepted = build_published_snapshot(tmp_path)
    clause_id = accepted["identity"]["clause_id"]

    doc_repo = DocumentRepository(session)
    obl_repo = ObligationRepository(session)
    changeset_repo = ChangesetRepository(session)

    # A fresh, empty log has no agent-call records at all for this clause_id, so the
    # "agent run_ids" link cannot resolve — confirmed directly first:
    empty_log = AgentCallLog()
    chain = resolve_provenance_chain(
        clause_id,
        document_repository=doc_repo,
        obligation_repository=obl_repo,
        changeset_repository=changeset_repo,
        agent_call_log=empty_log,
    )
    assert chain.resolved is False
    assert chain.unresolved_link == "agent_run_ids"

    # ...and confirmed to actually exclude the obligation from the export, not just
    # from the resolver's own return value:
    export_payload = build_export(
        snapshot_id,
        graph_store=store,
        changeset_repository=changeset_repo,
        document_repository=doc_repo,
        obligation_repository=obl_repo,
        agent_call_log=empty_log,
    )
    assert export_payload["obligations"] == []
