# Quickstart: Clause Parser & Compliance Knowledge Graph

Validates the §9.4 completion condition end-to-end: pinned source → registered `CanonicalDocument` → parsed + validated proposals → reviewed `ObligationObject`s → approved `GraphChangeSet` → published snapshot → successful proof-path query → schema-valid `GraphSnapshotExport`.

## Prerequisites

- Python 3.11+ environment with project dependencies installed.
- A running Neo4j instance reachable by the graph module (local dev instance is sufficient; no external system integration required per §1.2).
- LLM gateway configured against at least one allow-listed provider (or a fixture/mock provider for offline runs — required for CI per the no-live-LLM-in-CI testing decision in `research.md` §7).
- One fixture source artifact (a small bounded excerpt of NIS2, CRA, or DORA text) available locally, representing the evaluation-corpus scope decided in `research.md` §8.

## 1. Register a pinned document

```
POST /v1/documents
{ "instrument": "NIS2", "source_artifact_uri": "<fixture-uri>", "source_version": "<pinned-version-id>" }
```

**Expect**: `201` with a `CanonicalDocument` (see `contracts/CanonicalDocument.schema.json`). Re-posting the identical bytes returns `200` with the same `document_id` (idempotency — §9.1 Ingestion scenario).

## 2. Run a parse job

```
POST /v1/parse-jobs
{ "document_id": "<document_id>", "source_version": "<pinned-version-id>" }
```

**Expect**: `202` with `{ "job_id", "status": "queued" }`. Poll `GET /v1/parse-jobs/{id}` until `status == "completed"`; `validation_summary` shows counts across pass/needs_review/fail.

## 3. Inspect a clause's parse revisions

```
GET /v1/clauses/{clause_id}/parse-revisions
```

**Expect**: array of `{ObligationObjectProposal, ValidationReport, revision_history}`, oldest-first. Confirm at least one proposal's `source_evidence.verbatim_text` is a substring of the canonical document text at its offsets, and `evidence_hash` matches its sha256 (§9.1 Parsing scenario).

## 4. Review and accept a clause

```
POST /v1/reviews/{revision}/decisions
{ "reviewer_id": "<reviewer>", "action": "accept", "rationale": "<non-empty justification>", "edits": null }
```

**Expect**: `200` with updated `ObligationObject`; `governance.review_status == "accepted"`; `revision_history` has a new entry (§9.1 Review scenario). Repeat for enough clauses to support a graph mapping proposal.

## 5. Propose a graph change set

Trigger the Graph Mapping Agent (internal call, not a REST endpoint per §4.4) against one or more accepted `ObligationObject`s. Confirm the resulting `GraphChangeSet` is `status: "draft"`.

## 6. Validate and approve the change set

```
POST /v1/graph/changesets/{id}/validate
```

**Expect**: `200` with a `ConstraintReport` showing zero failures for a well-formed proposal built entirely from allowed node/relationship types (§3.2). Approve the change set (internal reviewer action) so `status` becomes `"approved"`.

## 7. Publish

```
POST /v1/graph/changesets/{id}/publish
```

**Expect**: `200` with `{ "snapshot_id", "published_at" }`. A second publish attempt against a stale `base_snapshot_id` returns `409` and leaves the graph unchanged (§9.1 Graph mapping & publish scenario).

## 8. Query the proof path

```
POST /v1/graph/query
{ "snapshot_id": "<snapshot_id>", "pattern": "proof_path", "filters": {} }
```

**Expect**: `200` with `results` — each entry carries `clause_id`, `path`, `verbatim_text`, `review_status`, `graph_snapshot_id` (§3.3, §9.1 Query & export scenario). Querying a non-published snapshot id (e.g. one still `draft`/`validated`/`approved`) returns `404`.

## 9. Export

```
GET /v1/graph/snapshots/{snapshot_id}/export
```

**Expect**: `200` with a `GraphSnapshotExport` (schema in `contracts/GraphSnapshotExport.schema.json`) containing only obligations whose `review_status ∈ {accepted, edited}`.

## Success check

This run satisfies §9.4 if every step above completed without manual data patching and every response validated against its corresponding schema in `contracts/`.
