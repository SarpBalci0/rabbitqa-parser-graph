---

description: "Task list for the visual proof-path viewer feature"
---

# Tasks: Visual Proof-Path Viewer

**Input**: Design documents from `/specs/002-visual-proof-path-viewer/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/proof-path-view.md, quickstart.md — all present.

**Tests**: Included. This codebase's existing convention (every endpoint in `compliance_graph/tests/{contract,integration}/`) already pairs each endpoint with a contract test and an integration test; this feature follows that established pattern rather than inventing a new one.

**Organization**: This feature has exactly one user story (US1 — no P2/P3 exist in spec.md), so all implementation tasks live in one phase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 (the only user story in spec.md)

## Path Conventions

Single project (existing `compliance_graph` service). Paths match plan.md's Project Structure section exactly.

---

## Phase 1: Setup

**Purpose**: Directory/module scaffolding for the new submodule. No new dependencies to install (research.md: stdlib-only).

- [ ] T001 Create `compliance_graph/src/visualization/__init__.py` (empty package init, matching the existing `export/`, `query/` submodule pattern)
- [ ] T002 Create empty `compliance_graph/tests/contract/test_proof_path_view_errors.py` and `compliance_graph/tests/integration/test_proof_path_view_endpoint.py` files (test scaffolding, matching existing test-directory layout)

**Checkpoint**: Directories/files exist; nothing functional yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: This feature reuses 100% of its data-access infrastructure (`run_proof_path_query`, `GraphStore`, `ObligationRepository`, the shared `ApiError`/`NotFoundError` envelope, the existing `compliance_graph` FastAPI `app.py`) — all of it already exists and is unchanged (data-model.md, research.md). There is no new foundational/blocking infrastructure to build before US1 can start.

**Checkpoint**: N/A — proceed directly to US1.

---

## Phase 3: User Story 1 - Reviewer inspects an obligation's compliance chain visually (Priority: P1) 🎯 MVP

**Goal**: A reviewer who knows an obligation's `clause_id` and its snapshot's `snapshot_id` can request a static HTML+SVG page showing the full proof-path chain and the obligation's verbatim source text.

**Independent Test**: Publish a snapshot containing one obligation with a complete proof-path (per `evaluation/run_full_e2e_demo.py`'s existing fixture pattern), request `GET /v1/graph/snapshots/{snapshot_id}/proof-path-view?clause_id={clause_id}`, and confirm the response renders all 6 nodes and 5 labeled edges with the obligation's exact source text alongside.

### Tests for User Story 1 ⚠️

> Write these tests FIRST; confirm they FAIL before implementation (no renderer/route exists yet).

- [ ] T003 [P] [US1] Contract test: missing `clause_id` → `400` JSON envelope (`code: "schema_validation_failed"`) in `compliance_graph/tests/contract/test_proof_path_view_errors.py` (contracts/proof-path-view.md)
- [ ] T004 [P] [US1] Contract test: unpublished `snapshot_id` → `404` JSON envelope (`code: "not_found"`) in `compliance_graph/tests/contract/test_proof_path_view_errors.py` (contracts/proof-path-view.md; reuses the existing unpublished-snapshot fixture pattern from `compliance_graph/tests/integration/test_query_unpublished_snapshot.py`)
- [ ] T005 [P] [US1] Contract test: published snapshot but unknown/absent `clause_id` → `404` JSON envelope, same shape as T004 (indistinguishable per contracts/proof-path-view.md) in `compliance_graph/tests/contract/test_proof_path_view_errors.py`
- [ ] T006 [P] [US1] Integration test: full render — published snapshot + complete proof-path + accepted obligation → `200`, `text/html`, body contains 6 node boxes + 5 correctly-labeled edges (`DERIVED_FROM`, `MAPS_TO_CONTROL`, `AFFECTS_ASSET`, `SATISFIED_BY`, `EVIDENCED_BY`) + the obligation's exact `verbatim_text`, in `compliance_graph/tests/integration/test_proof_path_view_endpoint.py` (quickstart.md scenario 1; reuses `compliance_graph/tests/integration/test_proof_path_query.py`'s fixture-building pattern). **The fixture and assertions MUST reflect the branching topology, not a linear chain**: assert `Control->Asset` is labeled `AFFECTS_ASSET` AND `Control->EvidenceRequirement` is labeled `SATISFIED_BY` (both edges sourced from the Control box), and explicitly assert there is NO edge rendered directly between `Asset` and `EvidenceRequirement` — a naive positional/index-adjacent implementation would produce exactly that wrong edge, so this test must be able to catch it (data-model.md "Existing entities read", research.md "Edge-label derivation")
- [ ] T007 [P] [US1] Integration test: determinism — two identical requests return byte-identical response bodies, in `compliance_graph/tests/integration/test_proof_path_view_endpoint.py` (quickstart.md scenario 2)
- [ ] T008 [P] [US1] Integration test: non-`accepted` obligation (rejected/escalated) → `404`, same shape as the unpublished-snapshot case, in `compliance_graph/tests/integration/test_proof_path_view_endpoint.py` (quickstart.md scenario 4)
- [ ] T009 [P] [US1] Integration test: accepted obligation with an incomplete proof-path (published but not fully graph-mapped) → `404`, never a partial diagram, in `compliance_graph/tests/integration/test_proof_path_view_endpoint.py` (quickstart.md scenario 5)
- [ ] T010 [P] [US1] Integration test: escaping — an obligation whose `verbatim_text` contains `<`, `&`, `"` renders those characters as literal text (e.g. `<` appears as `&lt;` in the raw response body, never as an unescaped `<`) inside both the `<svg>` and the surrounding HTML, in `compliance_graph/tests/integration/test_proof_path_view_endpoint.py` (quickstart.md scenario 7; this is the test proving root spec §7's escaping requirement)

### Implementation for User Story 1

- [ ] T011 [US1] Implement the escaping helper and SVG/HTML renderer in `compliance_graph/src/visualization/proof_path_renderer.py`: a `render(proof_path_result: dict) -> str` function that (a) splits each `path` entry into `node_type`/`node_id`, (b) validates the node sequence is exactly the 6-entry §3.3 canonical shape — returning a sentinel/raising an internal "incomplete chain" signal otherwise (data-model.md's `RenderableProofPath` validation rule) — (c) derives edge labels via the fixed **type-keyed** lookup from research.md's "Edge-label derivation" decision, **not** by pairing adjacent array indices: `Control` is the source of two edges (`AFFECTS_ASSET` to `Asset`, `SATISFIED_BY` to `EvidenceRequirement`) and `Asset` has no outgoing edge, so the lookup must locate each node by its `node_type` and wire the fixed 5-edge tree directly, never read from `path` data itself, (d) lays the diagram out to show `Control`'s branch (e.g. two lines fanning out from the `Control` box to `Asset` and to `EvidenceRequirement`), not a single row of 6 boxes, (e) escapes every interpolated value (node `display_label`s, `verbatim_text`) via a single dedicated escaping function per research.md's "Escaping mechanism" decision, (f) returns a complete, self-contained HTML string with one inline `<svg>` — no `<script>`/`<foreignObject>`/event-handler attributes/external references anywhere in the output (depends on T001)
- [ ] T012 [US1] Implement the route handler in `compliance_graph/src/api/visualization.py`: a `render_proof_path_view_handler(snapshot_id: str, clause_id: str, *, graph_store, obligation_repository) -> str` function (kept as a plain function per this codebase's existing handler pattern, e.g. `compliance_graph/src/api/query.py`'s `run_query_handler`) that (a) calls `run_proof_path_query` unchanged (no new traversal — root spec §4.5/§5.11), (b) selects the entry matching `clause_id`, raising `NotFoundError` (imported from `compliance_graph/src/api/errors.py`) if the snapshot isn't published, the `clause_id` isn't present in the results, or its `review_status != "accepted"` — one uniform `404` pathway per research.md's "Not-found semantics" decision, (c) raises `SchemaValidationHttpError` if `clause_id` is missing from the request before any lookup, (d) calls `proof_path_renderer.render(...)`, mapping an "incomplete chain" signal from T011 to the same `NotFoundError` path, (e) exposes a `build_router(graph_store_factory, obligation_repository_factory) -> APIRouter` with the `GET /v1/graph/snapshots/{snapshot_id}/proof-path-view` route returning an HTML response (`fastapi.responses.HTMLResponse`) (depends on T011)
- [ ] T013 [US1] Wire the new router into the existing app in `compliance_graph/src/api/app.py`: import and mount `visualization.build_router(...)` alongside the existing routers (query, export, changesets, snapshots), passing the same `graph_store_factory`/`obligation_repository_factory` already used by the existing query router (depends on T012)

**Checkpoint**: US1 fully functional and independently testable — this is the entire feature (T001–T013 constitute the whole MVP; there is no US2/US3).

---

## Phase 4: Polish & Cross-Cutting Concerns

**Purpose**: Final validation against the spec's success criteria; no cross-cutting concerns beyond US1 since this is a single-story feature.

- [ ] T014 Run the full existing test suite (`python -m pytest --ignore=compliance_graph/tests/live_neo4j`) and confirm all prior tests still pass alongside the new T003–T010 tests (no regressions to `compliance_graph/src/api/app.py`'s existing routers from the T013 wiring change)
- [ ] T015 Walk through every scenario in `specs/002-visual-proof-path-viewer/quickstart.md` manually (or via a small demo script following `evaluation/run_full_e2e_demo.py`'s pattern) and confirm each expected outcome, closing the loop on spec.md's SC-001 through SC-005

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: N/A — nothing to build, all infrastructure reused as-is
- **User Story 1 (Phase 3)**: Depends on Setup (T001) completing first; this is the only user story
- **Polish (Phase 4)**: Depends on Phase 3 completing

### Within User Story 1

- Tests (T003–T010) MUST be written and confirmed failing before implementation (T011–T013)
- T011 (renderer) before T012 (route handler, calls the renderer)
- T012 before T013 (app wiring needs the router `build_router` produces)
- T003–T010 are mutually parallel (different assertions, but note T003–T005 share one file and T006–T010 share another — parallel here means "no logical dependency between the test cases," not "safe to literally run concurrent edits to the same file"; sequence writes to each shared file, but there is no ordering dependency between the test *cases* themselves)

### Parallel Opportunities

- T001 and T002 (Setup) — different files, no dependency
- T003, T004, T005 — same file (`test_proof_path_view_errors.py`), independent test cases; write sequentially but in any order
- T006, T007, T008, T009, T010 — same file (`test_proof_path_view_endpoint.py`), independent test cases; write sequentially but in any order
- No parallelism within T011 → T012 → T013 (strict dependency chain)

---

## Parallel Example: User Story 1

```bash
# All error-path test cases (same file, independent cases):
Task: "Contract test: missing clause_id -> 400 in compliance_graph/tests/contract/test_proof_path_view_errors.py"
Task: "Contract test: unpublished snapshot -> 404 in compliance_graph/tests/contract/test_proof_path_view_errors.py"
Task: "Contract test: unknown clause_id -> 404 in compliance_graph/tests/contract/test_proof_path_view_errors.py"

# All integration test cases (same file, independent cases):
Task: "Integration test: full render in compliance_graph/tests/integration/test_proof_path_view_endpoint.py"
Task: "Integration test: determinism in compliance_graph/tests/integration/test_proof_path_view_endpoint.py"
Task: "Integration test: non-accepted obligation -> 404 in compliance_graph/tests/integration/test_proof_path_view_endpoint.py"
Task: "Integration test: incomplete chain -> 404 in compliance_graph/tests/integration/test_proof_path_view_endpoint.py"
Task: "Integration test: escaping in compliance_graph/tests/integration/test_proof_path_view_endpoint.py"
```

---

## Implementation Strategy

### MVP First (and only)

This feature has a single user story — there is no incremental multi-story delivery to plan. Sequence:

1. Complete Phase 1: Setup (T001–T002)
2. Skip Phase 2: nothing to do
3. Complete Phase 3: US1 tests (T003–T010) → confirm failing → implementation (T011–T013)
4. Complete Phase 4: full regression run + quickstart walkthrough (T014–T015)
5. **STOP and VALIDATE** against spec.md's Success Criteria, then this feature is done

---

## Notes

- [P] tasks = different files or independent test cases within a shared file, no ordering dependency
- Every implementation task cites the root spec section it satisfies (§4.5 for T011, §5.11 for T012, module-placement note for T013) — consult `rabbitqa_spec_v1.1.0.md` directly on any ambiguity, per this project's spec authority hierarchy (CLAUDE.md)
- Commit after each task or logical group, consistent with this project's existing commit-message conventions (see recent git log for style/detail level expected)
