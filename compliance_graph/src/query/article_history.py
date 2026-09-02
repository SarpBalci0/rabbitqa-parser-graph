"""Prior-article-version history resolution, per rabbitqa_spec_v1.0.0.md §6.5:
"Prior-revision history: ... and, separately, for prior versions of the source
regulation article if superseded."

This is tasks.md T053, DEFERRED during User Story 2 because clause_parser alone
has no supersession data to consult (§2.1's CanonicalDocument has no supersession
field, and no other relationship links different source_versions of the same
instrument at the document level). It is implemented here, in compliance_graph,
once User Story 4 (publish) made the graph's own SUPERSEDES relationship
(§3.2: Regulation->Regulation, snapshot-level only) real and queryable —
supersession is tracked by graph publish order (see
graph_mapping_agent/agent.py's `latest_published_regulation` parameter), which is
genuine information, not a guessed heuristic.

Originally planned at clause_parser/src/review/article_history.py per T053's
literal text; moved here because the data it needs (GraphStore) only exists in
compliance_graph, and clause_parser has no dependency on compliance_graph
elsewhere in this codebase — introducing one just for this function would invert
the module boundary for no benefit.
"""

from __future__ import annotations

from typing import Any

from clause_parser.src.db.document_repository import DocumentRepository
from clause_parser.src.db.obligation_repository import ObligationRepository
from compliance_graph.src.publisher.snapshot import GraphStore


def _structural_path(clause_id: str) -> tuple[str, str, str]:
    """clause_id is f'{document_id}:{source_version}:{structural_path}' per §2.2 —
    document_id/source_version themselves never contain ':' (document_id matches
    ^doc_[a-z0-9]{12}$; source_version is caller-supplied but every registration
    path in this codebase produces colon-free values), so a maxsplit=2 split is
    unambiguous here, matching build_clause_id's own construction in
    clause_parser/src/extract/extractor.py."""
    document_id, source_version, structural_path = clause_id.split(":", 2)
    return document_id, source_version, structural_path


def resolve_superseded_article_history(
    clause_id: str,
    *,
    graph_store: GraphStore,
    document_repository: DocumentRepository,
    obligation_repository: ObligationRepository,
) -> list[dict[str, Any]]:
    """Walks the SUPERSEDES chain backward from clause_id's own (instrument,
    source_version), returning one entry per prior version actually resolvable:
    {source_version, clause_id, revision_history}, most-recent-prior first.

    Stops (returns the partial chain gathered so far, never raises) at the first
    unresolvable link: no SUPERSEDES edge found, the prior document was never
    registered, the prior document has no anchor at the same structural_path, or a
    cycle is detected. This mirrors §7's export provenance gate philosophy (a
    broken link excludes/stops rather than fails the whole request) even though
    §6.5 itself states no explicit MUST about partial-chain handling."""
    document_id, source_version, structural_path = _structural_path(clause_id)
    document = document_repository.get(document_id, source_version)
    if document is None:
        return []
    instrument = document["instrument"]

    history: list[dict[str, Any]] = []
    current_source_version = source_version
    visited = {source_version}

    while True:
        target = graph_store.find_regulation_supersedes_target(instrument, current_source_version)
        if target is None:
            break
        target_source_version = target.get("source_version")
        if not target_source_version or target_source_version in visited:
            break
        visited.add(target_source_version)

        prior_document = document_repository.get_by_instrument_and_source_version(
            instrument, target_source_version
        )
        if prior_document is None:
            break

        matching_anchor = next(
            (
                a
                for a in prior_document["structure"]
                if a["anchor_id"].endswith(f":{structural_path}")
            ),
            None,
        )
        if matching_anchor is None:
            break

        prior_clause_id = f"{prior_document['document_id']}:{target_source_version}:{structural_path}"
        revisions = obligation_repository.list_revisions_for_clause(prior_clause_id)
        revision_history = (
            revisions[-1]["proposal"]["governance"]["revision_history"] if revisions else []
        )
        history.append(
            {
                "source_version": target_source_version,
                "clause_id": prior_clause_id,
                "revision_history": revision_history,
            }
        )
        current_source_version = target_source_version

    return history
