# Quickstart: Visual Proof-Path Viewer

Validates the feature end-to-end once implemented. This mirrors the existing pattern used by `evaluation/run_full_e2e_demo.py` / `evaluation/run_pdf_demo.py` (already in this repo) — get a real obligation through to a published snapshot, then request its view.

## Prerequisites

- `.venv` activated (`source .venv/bin/activate`), repo dependencies installed (`pip install -e ".[dev]"`)
- No live Neo4j needed — `InMemoryGraphStore` is sufficient, as used throughout the existing test suite and demo scripts

## Setup

Get one obligation through to a published snapshot with a complete proof-path chain — reuse the exact sequence `evaluation/run_full_e2e_demo.py` already demonstrates (register → parse → review/accept → graph-map with a controls/assets/evidence fixture → validate → approve → publish), stopping once you have a `snapshot_id` and the accepted obligation's `clause_id`.

## Validation scenarios

### 1. Full render, correct shape (FR-002, FR-003, FR-004; SC-002)

```bash
curl -s "http://localhost:8000/v1/graph/snapshots/{snapshot_id}/proof-path-view?clause_id={clause_id}"
```

Expected: `200`, `Content-Type: text/html`, body contains one `<svg>` with 6 node boxes and 5 labeled edges (`DERIVED_FROM`, `MAPS_TO_CONTROL`, `AFFECTS_ASSET`, `SATISFIED_BY`, `EVIDENCED_BY`), plus the obligation's exact `verbatim_text` rendered as plain text.

### 2. Determinism (FR-012; SC-005)

Run the same `curl` command twice. Expected: byte-identical response bodies.

### 3. Unpublished snapshot → 404 (FR-006; SC-003)

Request the view using a `snapshot_id` still at `draft`/`validated`/`approved` (not yet published). Expected: `404`, JSON envelope `{"error": {"code": "not_found", ...}}` — never partial HTML.

### 4. Non-accepted obligation → 404 (FR-007; SC-003)

Request the view for a `clause_id` whose obligation was rejected/escalated rather than accepted. Expected: `404`, same JSON envelope shape as scenario 3 — indistinguishable from it.

### 5. Incomplete chain → 404 (FR-008; SC-003)

Request the view for an accepted obligation that was published but never graph-mapped through to evidence (a partial `path`). Expected: `404` — never a partial diagram.

### 6. Missing `clause_id` → 400 (FR-009)

```bash
curl -s "http://localhost:8000/v1/graph/snapshots/{snapshot_id}/proof-path-view"
```

Expected: `400`, JSON envelope with `code: "schema_validation_failed"`.

### 7. Injection-safe escaping (FR-011; SC-004)

Using a source document whose obligation text contains `<`, `&`, and `"` characters (e.g. an obligation quoting a clause like `the entity shall notify <competent authority> & document "immediately"`), request the view. Expected: those characters appear as literal, correctly-displayed text in the rendered page; view the raw response body and confirm no unescaped `<`/`&`/`"` from the source text appears un-entity-encoded inside the `<svg>` or surrounding HTML — i.e. `<` from source text must appear as `&lt;` in the response body, not as a literal `<`.

## Expected outcome

All 7 scenarios pass → feature satisfies spec.md's SC-001 through SC-005 and the corresponding functional requirements, consistent with root spec §4.5/§5.11/§7.
