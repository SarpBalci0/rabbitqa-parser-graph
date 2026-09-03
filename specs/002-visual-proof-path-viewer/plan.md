# Implementation Plan: Visual Proof-Path Viewer

**Branch**: `002-visual-proof-path-viewer` | **Date**: 2026-09-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-visual-proof-path-viewer/spec.md`

**Root spec authority**: `rabbitqa_spec_v1.1.0.md` §4.5, §5.11, §7 ("Visualization rendering"), §1.2 (spec_version 1.2.0) is the normative source for every technical decision below. This plan implements those sections; it does not introduce technical choices the root spec doesn't already make.

## Summary

Add a read-only `GET /v1/graph/snapshots/{snapshot_id}/proof-path-view?clause_id=...` endpoint that renders one obligation's §3.3 proof-path chain as a static SVG diagram embedded in a minimal HTML page. Implementation reuses the existing `run_proof_path_query` (`compliance_graph/src/query/proof_path.py`) for all data access — no new graph traversal — and adds a new, deterministic, dependency-free SVG/HTML renderer plus a thin FastAPI route wrapping it.

## Technical Context

**Language/Version**: Python 3.13 (matches the rest of the repo's `.venv`; `pyproject.toml` requires >=3.11)

**Primary Dependencies**: FastAPI (existing, `compliance_graph/src/api/app.py`) for the route; Python's stdlib `xml.sax.saxutils.escape` (or equivalent stdlib-only escaping) for SVG/HTML text escaping — no new third-party dependency is needed or justified for a static-boxes-and-lines diagram (root spec §4.5/§7 require deterministic, dependency-minimal rendering consistent with every other fixture/deterministic module in this codebase)

**Storage**: N/A — this feature reads only, from the existing published-snapshot query path (`compliance_graph/src/publisher/snapshot.py`'s `GraphStore` via `run_proof_path_query`) and the existing `ObligationRepository`; it introduces no new persisted state

**Testing**: pytest (existing `compliance_graph/tests/` — contract/integration split, matching the existing `export`/`query` test layout)

**Target Platform**: Same as the rest of `compliance_graph` — a FastAPI service, tested via `TestClient`/direct handler calls (no live Neo4j required for unit/contract/integration tests, per the existing `InMemoryGraphStore` pattern used throughout this codebase)

**Project Type**: Web service (existing `compliance_graph` FastAPI app gains one new endpoint + one new rendering submodule)

**Performance Goals**: Not a spec concern — this renders one small, fixed-shape (6-node) diagram per request from an already-computed query result; no performance target is stated in the root spec and none is implied by the feature's shape

**Constraints**: Static output only — no `<script>`, no `<foreignObject>`, no event-handler attributes, no external resource references (root spec §4.5 "Interactivity", §7 "Visualization rendering"). All untrusted content (node labels, `verbatim_text`) MUST be escaped via a dedicated escaping function before embedding (§7) — an unescapable value is a hard `500`, not unescaped output. Rendering MUST be fully deterministic (§4.5) — same input always produces byte-identical output.

**Scale/Scope**: One new endpoint, one new rendering submodule. Diagram is always exactly the §3.3 canonical 6-node shape (Provision, Obligation, Control, Asset, EvidenceRequirement, TestAsset) — this feature is explicitly scoped to that one shape only (root spec §4.5: "MUST NOT be used for any path shape other than §3.3's canonical proof-path").

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is an unfilled template in this repository (no project-specific principles have been ratified there) — there are no constitution gates to evaluate. This project's actual governing document is `rabbitqa_spec_v1.1.0.md` per `CLAUDE.md`'s spec authority hierarchy, and this plan is derived from and consistent with its §4.5/§5.11/§7/§1.2 (spec_version 1.2.0), as verified during `/speckit-specify`. No violations to justify; Complexity Tracking is not applicable.

## Project Structure

### Documentation (this feature)

```text
specs/002-visual-proof-path-viewer/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
compliance_graph/
├── src/
│   ├── visualization/                  # NEW submodule (root spec §4.5, §12 changelog module-placement note)
│   │   ├── __init__.py
│   │   └── proof_path_renderer.py      # Deterministic, no-LLM SVG+HTML renderer; escaping via a
│   │                                    # dedicated function (root spec §7); edge labels derived from
│   │                                    # §3.3's fixed canonical shape, not read from path data
│   ├── api/
│   │   └── visualization.py            # NEW thin route: GET .../proof-path-view — calls
│   │                                    # run_proof_path_query (query/proof_path.py, unchanged) +
│   │                                    # proof_path_renderer.render(...), no traversal of its own
│   │   └── app.py                      # MODIFIED: wire the new router in, alongside existing routers
│   └── query/
│       └── proof_path.py               # UNCHANGED — reused as-is per root spec §4.5/§5.11 "MUST reuse,
│                                        # MUST NOT duplicate"
└── tests/
    ├── contract/
    │   └── test_proof_path_view_errors.py   # NEW: 400/404 JSON-envelope contract (root spec §5.11)
    └── integration/
        └── test_proof_path_view_endpoint.py # NEW: full render + escaping + determinism + review-gate tests
```

**Structure Decision**: Follows the existing `compliance_graph/src/export/` precedent (rendering/business logic in its own submodule, a thin `api/` route wrapping it) — applied here as a new `visualization/` submodule alongside `export/`, `query/`, `publisher/`, etc., exactly as the root spec's §12 changelog entry for spec_version 1.2.0 specifies. No new top-level project or service is introduced; this is one endpoint added to the existing `compliance_graph` FastAPI app.

## Complexity Tracking

*No Constitution Check violations — not applicable.*
