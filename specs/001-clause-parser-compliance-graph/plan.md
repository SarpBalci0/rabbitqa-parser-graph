# Implementation Plan: Clause Parser & Compliance Knowledge Graph

**Branch**: `001-clause-parser-compliance-graph` | **Date**: 2026-09-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-clause-parser-compliance-graph/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Build the standalone `clause_parser` / `compliance_graph` module pair (plus `shared_contracts`, `reviewer_ui`, `evaluation`) that turns one pinned regulatory source (NIS2, CRA, or DORA) into reviewer-approved, source-traceable `ObligationObject`s, maps approved obligations into a versioned Neo4j compliance graph under a fixed ontology, and exposes proof-path queries plus a schema-valid, review-gated read-only export — exactly per `rabbitqa_spec_v1.1.0.md` §2–§9. Technical approach: Python 3.11 + FastAPI service exposing the §5 endpoints, JSON Schema 2020-12 contracts checked in under `shared_contracts/schemas/` as the literal source of truth, a fixed six-step deterministic-then-LLM parsing pipeline (§4.1) with an isolated LLM gateway (agents have zero write-capable tools), and Neo4j for the graph with ontology cardinality constraints enforced inside the same transaction as every write.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: FastAPI (API layer), Pydantic + `jsonschema` (contract validation against the checked-in JSON Schema 2020-12 files), `neo4j` Python driver (graph store), an internal LLM gateway module (provider(s) configured, not hardcoded — see research.md §5)

**Storage**: Neo4j (compliance graph, versioned/immutable snapshots); an object store or filesystem for immutable `raw_storage_uri` source artifacts (write-once); a relational or document store for `CanonicalDocument`, `ObligationObject`, `ValidationReport`, and `GraphChangeSet` records prior to graph publish (concrete choice not specified by the technical spec — flagged as a gap below)

**Testing**: pytest — §9.1 Given/When/Then scenarios as literal first test names; contract tests validating every payload against its JSON Schema; fixture-based agent tests (no live LLM calls in CI)

**Target Platform**: Single-tenant local/server deployment (Linux-compatible), no multi-tenant SaaS concerns (§1.2 non-goal)

**Project Type**: Backend service (API + async job worker) with a thin reviewer UI (web form or CLI, per §6 — implementation form not mandated by the spec)

**Performance Goals**: Not numerically specified by the technical spec beyond the §9.2 accuracy/reliability targets (precision/recall/F1/transaction-success-rate); no latency SLA is stated — flagged as a gap below

**Constraints**: Step 6 (Validate) MUST run zero LLM calls (pure functions only); agents MUST have zero write-capable tools (no DB/graph writes, shell exec, unrestricted network); publish MUST be one all-or-nothing transaction; audit/decision-history MUST be append-only

**Scale/Scope**: Single pinned regulatory instrument version processed at a time (no cross-instrument correlation in v1); bounded evaluation-corpus article subset (per spec.md resolved clarification), not a full-instrument corpus

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` in this repository is an unfilled template (placeholder principle names only, no ratified content) — there is no ratified project constitution to check against. This gate is therefore **not applicable**: no principles exist yet to violate. If a constitution is ratified later, this plan MUST be re-checked against it before implementation proceeds.

## Project Structure

### Documentation (this feature)

```text
specs/001-clause-parser-compliance-graph/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── api.md
│   ├── CanonicalDocument.schema.json
│   ├── ObligationObject.schema.json
│   ├── ValidationReport.schema.json
│   ├── GraphChangeSet.schema.json
│   └── GraphSnapshotExport.schema.json
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
shared_contracts/
├── schemas/              # Checked-in JSON Schema 2020-12 files — source of truth per spec §0
│   ├── CanonicalDocument.schema.json
│   ├── ObligationObject.schema.json
│   ├── ValidationReport.schema.json
│   ├── GraphChangeSet.schema.json
│   ├── ConstraintReport.schema.json   # gap — see Complexity Tracking
│   └── GraphSnapshotExport.schema.json
└── py/                    # Generated/validated Python models over the schemas above

clause_parser/
├── src/
│   ├── canonicalize/      # Step 1 — deterministic, no LLM
│   ├── detect/             # Step 2 — deterministic baseline + optional LLM refinement
│   ├── decompose/          # Step 3 — deterministic or LLM, recorded in governance metadata
│   ├── extract/             # Step 4 — Extraction Agent
│   ├── resolve/              # Step 5 — deterministic normalizers + Reference Agent
│   ├── validate/              # Step 6 — deterministic only, no LLM
│   ├── agents/                 # Extraction / Reference / Critic agent clients (gateway-mediated)
│   └── api/                     # §5.1–5.5 endpoints
└── tests/
    ├── contract/                 # schema-validation tests per shared_contracts
    ├── integration/                # §9.1 Given/When/Then scenarios
    └── unit/

compliance_graph/
├── src/
│   ├── entity_resolution/    # fuzzy+exact actor/asset matching, reviewer-gated merge
│   ├── graph_mapping_agent/   # proposal-only, never writes to graph store
│   ├── constraints/            # ontology + cardinality + provenance checks (§2.4, §3.2)
│   ├── publisher/                # transactional, all-or-nothing publish
│   ├── query/                     # proof-path / coverage query patterns (§3.3)
│   ├── export/                     # review-gated, provenance-gated export (§2.5)
│   └── api/                         # §5.6–5.10 endpoints
└── tests/
    ├── contract/
    ├── integration/
    └── unit/

reviewer_ui/
└── (per §6 — form not mandated; a minimal web form or CLI satisfying the five §6 requirements)

evaluation/
├── corpus/                # locked, regulation-stratified train/eval split per §9.3
└── metrics/                 # §4.2 / §9.2 measurement harness

llm_gateway/                # shared by clause_parser and compliance_graph agents
├── allow_list.py           # explicit provider allow-list, no arbitrary endpoint
├── tool_policy.py          # zero write-capable tools enforced here, not by prompt
└── logging.py               # {model_version, prompt_version, input_hash, output_hash, context_hash}
```

**Structure Decision**: Five top-level modules exactly matching the spec's stated scope (§1: "Standalone module pair only (`clause_parser`, `compliance_graph`, `shared_contracts`, `reviewer_ui`, `evaluation`)"), plus a shared `llm_gateway` package used by both `clause_parser` and `compliance_graph` agent clients to centralize the §4.4/§7 tool-restriction and provider-allow-list enforcement in one place rather than duplicating it per module. `shared_contracts/schemas/*.json` are the literal, checked-in JSON Schema files (not regenerated from code), matching §0's "source of truth for schemas... MUST be generated from this spec, never hand-diverged."

## Complexity Tracking

> Gaps in the normative spec identified during planning — not constitution violations (no ratified constitution exists), but items that MUST be resolved or explicitly scoped before the affected code is written, per the technical spec's own instruction: "If implementation reveals the spec is wrong or underspecified, STOP — update this document first... Do not let code and spec diverge silently."

| Gap | Where it appears | Why it blocks a clean implementation | Proposed resolution path |
|---|---|---|---|
| `ConstraintReport.schema.json` is referenced (§2.4, `GraphChangeSet.constraint_report`) but its own field-level schema is never defined in the technical spec | §2.4, §5.6 | `GraphChangeSet` and the `/v1/graph/changesets/{id}/validate` endpoint cannot be built to a precise contract without knowing `ConstraintReport`'s required fields | Do not invent the schema. Raise with the spec owner to add a `ConstraintReport` schema section (versioned as a spec change per §0's change policy) before `compliance_graph`'s constraints engine is implemented. In the interim, implementation may treat it as an internal, non-exported detail (a list of `{rule, status, message}` mirroring `ValidationReport.checks` shape) but this MUST be confirmed against a spec update, not shipped as an assumption. |
| No storage technology is specified for `CanonicalDocument`/`ObligationObject`/`ValidationReport`/`GraphChangeSet` prior to graph publish (only the graph store is pinned to Neo4j via resolved clarification, and `raw_storage_uri` is described only as "immutable object storage") | §2 (no storage layer named), §7 (Document ingress zone) | Affects module structure and the concrete persistence code inside `clause_parser`/`compliance_graph`, though not the API/data contracts themselves | Not a blocking gap for this plan (contracts and endpoints are storage-agnostic); Engineering selects a concrete store during implementation, consistent with single-tenant/local deployment (§1.2) and write-once/append-only requirements (§7). |
| No numeric latency/throughput SLA is stated anywhere in the technical spec (only accuracy/reliability targets in §9.2) | §9.2 | Cannot set a "Performance Goals" Technical Context value without inventing one | Not treated as a blocker — §9.2's stated targets (precision/recall/F1/transaction success rate) are used as the complete acceptance bar; no latency target is asserted or assumed. |
| Concrete LLM provider(s) for the gateway allow-list (§10 Q2) and the exact enumerated NIS2/CRA/DORA article list for the v1 corpus (§10 Q3, partially resolved to "bounded subset" only) remain open per `research.md` §5/§8 | §7, §9.3 | Does not block building the gateway interface or corpus machinery, but blocks pointing either at final, non-fixture content | Carried forward to Engineering / Regulatory SME as stated in `research.md`; not resolved by this plan since the technical spec itself assigns these to a different owner, not to specification or planning. |
| ~~`ObligationObject.identity.clause_id`'s JSON Schema `pattern` was written in the technical spec as `"^{document_id}:{source_version}:.+$"` — literal regex syntax cannot interpolate a sibling property's value, so this pattern was unmatchable by any real, correctly-derived `clause_id`~~ | §2.2 | Blocked every write of an `ObligationObject` — discovered when `create_revision`/`apply_decision` began schema-validating before persist (per §2 preamble) and every test payload failed | **RESOLVED — normative spec itself updated**, not just the implementation copy: `rabbitqa_spec_v1.1.0.md` §2.2 was corrected in place, `spec_version` bumped 1.0.0 → 1.0.1, and a §12 changelog entry added, per §0's change policy ("Any schema... change bumps spec_version and requires a changelog entry"). `shared_contracts/schemas/ObligationObject.schema.json` and its `specs/.../contracts/` counterpart now match the corrected spec text: a structural pattern `^[^:]+:[^:]+:.+$`, with the semantic requirement (prefix must equal the record's own `document_id`/`source_version`) enforced in code via `shared_contracts/py/invariants.py:assert_clause_id_derivation` — the same treatment as the evidence-replay invariant, which the spec itself now cites as the analogous case. |
| ~~§5.1 `POST /v1/documents` conflated the idempotent-match case (200) and an unstated genuine-conflict case (re-registering different content under an already-used source_version) in one sentence, with no defined behavior for the latter~~ | §5.1 | `document_registry.py` had no branch for content mismatch under an already-registered `(instrument, source_version)` | **RESOLVED — normative spec itself updated**: `rabbitqa_spec_v1.1.0.md` §5.1 disambiguated, `spec_version` bumped 1.0.1 → 1.0.2, §12 entry added. Implemented: `DocumentRepository.get_by_instrument_and_source_version`, `document_registry.DocumentVersionConflictError`, and `api/documents.py`'s `ConflictHttpError` (409). Propagated to `spec.md` (FR-002, Edge Cases) and `contracts/api.md`. |
| ~~§10's own text required its open questions to be "resolved and logged in §12" before implementation begins; questions #1 (graph store), #3 (corpus scope), and #4 (four-eyes) were resolved during `/speckit-specify` but never logged back into the root spec~~ | §10 | Caught by a full spec-code synchronization audit — the root spec's own self-imposed requirement had gone unfulfilled even though the actual decisions were made and implemented correctly | **RESOLVED**: `rabbitqa_spec_v1.1.0.md` §10 table now shows each question's status with a pointer to its resolution; `spec_version` bumped 1.0.2 → 1.0.3, §12 entry added. No functional change — logging only. |
| ~~No live Neo4j instance was available in this development environment (confirmed 2026-09-01: Docker CLI present but daemon not running, no `docker.sock`; no local Neo4j server; port 7687 unreachable)~~ | §4.1 ("Neo4j" resolved graph-store choice), §5.7/§5.9/§5.10 (publish/query/export endpoints) | `compliance_graph/src/publisher/neo4j_store.py` — the real, production `GraphStore` backend using actual Cypher — had never been run against a real server. Its Cypher strings (dynamic label injection via f-string, `MERGE`/`DETACH DELETE` head-pointer sequencing, cross-snapshot property matching) were unverified. | **RESOLVED (2026-09-01, later the same day, once Docker Desktop was started)** — tasks.md T104: ran `compliance_graph/tests/live_neo4j/test_neo4j_store_smoke.py` against a live `neo4j:5` Docker container, 5/5 PASSED, covering transactional commit + rollback-on-failure, `MERGE`/`DETACH DELETE` head-pointer sequencing across multiple publishes, cross-snapshot property-matching isolation, and a bonus check confirming a Cypher-injection-shaped relationship type fails safely (raises, does not silently execute) rather than being purely theoretical. Reproducibility re-verified by stopping/restarting the container mid-session. All of User Story 4/5 (T073–T086) and the §9.4 end-to-end demo remain built against `InMemoryGraphStore` for routine test runs (fast, no external dependency); the live-Neo4j test exists specifically to close the gap between that test double and the real Cypher backend, and is excluded from `pyproject.toml`'s default `testpaths` but auto-discovers and self-skips safely when no live server is reachable. |

No other Constitution-style violations apply, since no ratified constitution exists to violate.
