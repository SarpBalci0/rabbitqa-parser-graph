# API Contract: Clause Parser & Compliance Knowledge Graph

Source: `rabbitqa_spec_v1.1.0.md` §5. All endpoints return `application/json`. Errors follow:

```json
{ "error": { "code": "string", "message": "string", "details": {} } }
```

| HTTP status | Meaning |
|---|---|
| 400 | Schema validation failure on request body |
| 404 | Referenced entity (document/job/clause/changeset/snapshot) not found |
| 409 | State conflict (e.g. publishing a changeset not in `approved` status) |
| 422 | Business-rule violation (e.g. constraint_report has failures) |
| 500 | Unhandled — MUST still log full provenance chain before returning |

## POST /v1/documents
- Request: `{ "instrument": "NIS2"|"CRA"|"DORA", "source_artifact_uri": str, "source_version": str }`
- 201: `CanonicalDocument`
- 400: checksum cannot be computed
- 200: re-posting content whose checksum matches an already-registered `(instrument, source_version)` returns the existing `CanonicalDocument` — idempotent by content.
- 409: re-posting content whose checksum does NOT match an already-registered `(instrument, source_version)` — a pinned source_version is immutable once registered; register revised content under a new source_version instead. (Disambiguated in `rabbitqa_spec_v1.1.0.md` spec_version 1.0.2 — the original text stated both outcomes in one sentence without distinguishing the match/mismatch cases.)

## POST /v1/parse-jobs
- Request: `{ "document_id": str, "source_version": str }`
- 202: `{ "job_id": str, "status": "queued" }`
- Async; runs §4.1 steps 1–6 for every detected normative span.

## GET /v1/parse-jobs/{id}
- 200: `{ "job_id": str, "status": "queued"|"running"|"completed"|"failed", "trace_id": str, "validation_summary": { "total": int, "pass": int, "needs_review": int, "fail": int } }`

## GET /v1/clauses/{id}/parse-revisions
- 200: array of `{ ObligationObjectProposal, ValidationReport, revision_history }`, oldest-first.

## POST /v1/reviews/{revision}/decisions
- Request: `{ "reviewer_id": str, "action": "accept"|"edit"|"reject"|"escalate", "rationale": str, "edits": {}|null }`
- 200: updated `ObligationObject`
- Rules: `rationale` non-empty (else 400). `edit` requires non-null `edits` and re-runs `ValidationReport`; a failed evidence-span-fidelity re-check → 422, no persisted change.

## POST /v1/graph/changesets/{id}/validate
- 200: `ConstraintReport` (per §2.4). Does not mutate graph state.

## POST /v1/graph/changesets/{id}/publish
- Preconditions (all MUST hold, else 409):
  - `changeset.status == "approved"`
  - latest `validate` call's `constraint_report` has zero failures
  - `changeset.base_snapshot_id` equals graph's current head snapshot (optimistic concurrency)
- 200: `{ "snapshot_id": str, "published_at": str }`

## GET /v1/graph/snapshots/{id}
- 200: snapshot metadata + `ontology_version` + lineage (`superseded_snapshot_id` chain).

## POST /v1/graph/query
- Request: `{ "snapshot_id": str, "pattern": "proof_path"|"coverage", "filters": {} }`
- 200: `{ "results": [ { "clause_id", "path": [...], "verbatim_text", "review_status", "graph_snapshot_id" } ] }`
- Rule: querying a `snapshot_id` not fully published (`draft`/`validated`/`approved`) → 404, never partial data.

## GET /v1/graph/snapshots/{id}/export
- 200: `GraphSnapshotExport`, schema-validated before being returned (§2.5 rule).
