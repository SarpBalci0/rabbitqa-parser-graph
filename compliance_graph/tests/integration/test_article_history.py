"""T053: prior-article-version history linkage, per §6.5/§3.2 SUPERSEDES.

End-to-end: register and publish two pinned versions (v1, v2) of the same
instrument with the same structural article/paragraph, accept+map+publish both,
and confirm v2's clause resolves v1's revision_history as its superseded-article
history — via the real SUPERSEDES relationship created by the Graph Mapping
Agent, not a hand-built graph.
"""

from clause_parser.src.api.documents import DocumentRequest, register_document_handler
from clause_parser.src.api.reviews import DecisionRequest, submit_decision_handler
from clause_parser.src.db.document_repository import DocumentRepository
from clause_parser.src.db.obligation_repository import ObligationRepository
from clause_parser.src.pipeline import run_parse_job
from compliance_graph.src.api.changesets import publish_changeset_handler, validate_changeset_handler
from compliance_graph.src.db.changeset_repository import ChangesetRepository
from compliance_graph.src.graph_mapping_agent.agent import propose_change_set
from compliance_graph.src.publisher.in_memory_store import InMemoryGraphStore
from compliance_graph.src.query.article_history import resolve_superseded_article_history
from compliance_graph.src.review.changeset_approval import approve_change_set
from shared_contracts.py.db import configure, get_engine_singleton, get_session
from shared_contracts.py.tables import create_all


_TEXT = "Article 21\n1. The operator shall notify the competent authority within 30 days.\n"


def _register_accept_map_publish(session, doc_repo, obl_repo, changeset_repo, store, *, tmp_path, source_version, latest_published_regulation):
    fixture_path = tmp_path / f"doc_{source_version}.txt"
    fixture_path.write_text(_TEXT)
    doc_payload, _ = register_document_handler(
        DocumentRequest(instrument="NIS2", source_artifact_uri=str(fixture_path), source_version=source_version),
        session,
    )
    full_doc = doc_repo.get(doc_payload["document_id"], doc_payload["source_version"])
    run_parse_job(full_doc, obligation_repository=obl_repo)

    clause_id = f"{doc_payload['document_id']}:{source_version}:article-21/paragraph-1"
    revision = obl_repo.list_revisions_for_clause(clause_id)[0]
    accepted = submit_decision_handler(
        revision["revision_id"],
        DecisionRequest(reviewer_id=f"reviewer-{source_version}", action="accept", rationale=f"Accepted for {source_version}."),
        session=session,
    )

    changeset = propose_change_set(
        obligations=[accepted],
        base_snapshot_id=store.get_head_snapshot_id(),
        latest_published_regulation=latest_published_regulation,
    )
    changeset_repo.create(changeset)
    validate_changeset_handler(changeset["changeset_id"], session=session)
    approve_change_set(changeset["changeset_id"], repository=changeset_repo)
    publish_changeset_handler(changeset["changeset_id"], session=session, graph_store=store)

    return clause_id


def test_second_version_supersedes_first_and_history_resolves(tmp_path):
    configure("sqlite:///:memory:")
    create_all(get_engine_singleton())
    session = get_session()
    doc_repo = DocumentRepository(session)
    obl_repo = ObligationRepository(session)
    changeset_repo = ChangesetRepository(session)
    store = InMemoryGraphStore()

    clause_id_v1 = _register_accept_map_publish(
        session, doc_repo, obl_repo, changeset_repo, store,
        tmp_path=tmp_path, source_version="v1", latest_published_regulation=None,
    )

    # Before mapping v2, the caller queries the graph for the latest published
    # Regulation of this instrument — this is the read-only lookup §4.3 requires
    # (the agent itself never queries the graph).
    latest = store.find_latest_regulation("NIS2")
    assert latest is not None
    assert latest["source_version"] == "v1"

    clause_id_v2 = _register_accept_map_publish(
        session, doc_repo, obl_repo, changeset_repo, store,
        tmp_path=tmp_path, source_version="v2", latest_published_regulation=latest,
    )

    history = resolve_superseded_article_history(
        clause_id_v2, graph_store=store, document_repository=doc_repo, obligation_repository=obl_repo
    )

    assert len(history) == 1
    assert history[0]["source_version"] == "v1"
    assert history[0]["clause_id"] == clause_id_v1
    assert len(history[0]["revision_history"]) == 1
    assert history[0]["revision_history"][0]["reviewer_id"] == "reviewer-v1"
    assert history[0]["revision_history"][0]["action"] == "accept"


def test_first_version_has_no_superseded_history(tmp_path):
    configure("sqlite:///:memory:")
    create_all(get_engine_singleton())
    session = get_session()
    doc_repo = DocumentRepository(session)
    obl_repo = ObligationRepository(session)
    changeset_repo = ChangesetRepository(session)
    store = InMemoryGraphStore()

    clause_id_v1 = _register_accept_map_publish(
        session, doc_repo, obl_repo, changeset_repo, store,
        tmp_path=tmp_path, source_version="v1", latest_published_regulation=None,
    )

    history = resolve_superseded_article_history(
        clause_id_v1, graph_store=store, document_repository=doc_repo, obligation_repository=obl_repo
    )
    assert history == []


def test_supersedes_relationship_passes_constraint_validation(tmp_path):
    """Confirms the SUPERSEDES(Regulation->Regulation) edges the agent creates
    actually pass the real constraints engine — not just that the ontology table
    allows the pair in the abstract (already covered by
    test_ontology_exhaustive.py), but that a real changeset containing one
    validates cleanly end-to-end."""
    configure("sqlite:///:memory:")
    create_all(get_engine_singleton())
    session = get_session()
    doc_repo = DocumentRepository(session)
    obl_repo = ObligationRepository(session)
    changeset_repo = ChangesetRepository(session)
    store = InMemoryGraphStore()

    _register_accept_map_publish(
        session, doc_repo, obl_repo, changeset_repo, store,
        tmp_path=tmp_path, source_version="v1", latest_published_regulation=None,
    )
    latest = store.find_latest_regulation("NIS2")

    fixture_path = tmp_path / "doc_v2.txt"
    fixture_path.write_text(_TEXT)
    doc_payload, _ = register_document_handler(
        DocumentRequest(instrument="NIS2", source_artifact_uri=str(fixture_path), source_version="v2"), session
    )
    full_doc = doc_repo.get(doc_payload["document_id"], doc_payload["source_version"])
    run_parse_job(full_doc, obligation_repository=obl_repo)
    clause_id = f"{doc_payload['document_id']}:v2:article-21/paragraph-1"
    revision = obl_repo.list_revisions_for_clause(clause_id)[0]
    accepted = submit_decision_handler(
        revision["revision_id"],
        DecisionRequest(reviewer_id="r2", action="accept", rationale="ok"),
        session=session,
    )

    changeset = propose_change_set(obligations=[accepted], base_snapshot_id=None, latest_published_regulation=latest)
    supersedes_rels = [r for r in changeset["proposed_relationships"] if r["type"] == "SUPERSEDES"]
    assert len(supersedes_rels) == 1

    changeset_repo.create(changeset)
    report = validate_changeset_handler(changeset["changeset_id"], session=session)
    assert report["overall_status"] == "pass"
