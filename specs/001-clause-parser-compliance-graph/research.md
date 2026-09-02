# Research: Clause Parser & Compliance Knowledge Graph

All decisions below are constrained by `rabbitqa_spec_v1.1.0.md` (normative) and `spec.md`'s resolved clarifications. Where the technical spec dictates a choice, that choice is not re-litigated here — only genuinely open implementation questions are researched.

## 1. Language & runtime

- **Decision**: Python 3.11+.
- **Rationale**: The repo's Spec Kit config (`.specify/init-options.json`) already targets Python tooling (`"script": "py"`); Python has mature libraries for JSON Schema 2020-12 validation (the spec's schema draft, §2), Neo4j drivers, and async API frameworks needed for the async parse-job flow (§5.2/5.3).
- **Alternatives considered**: TypeScript/Node — rejected, no existing project convention and weaker native JSON Schema 2020-12 tooling maturity for this draft version; Go — rejected, slower to iterate on LLM-agent orchestration code and no project precedent.

## 2. API framework

- **Decision**: FastAPI.
- **Rationale**: Native async support for the async parse-job endpoint (§5.2), automatic request/response validation via Pydantic which maps well onto the normative JSON Schemas, and straightforward error-model customization to match the spec's fixed error envelope (§5).
- **Alternatives considered**: Flask — lacks native async and built-in schema validation, would require more glue code; Django REST Framework — too much unused ORM/admin surface for a single-tenant module pair (§1.2 explicitly excludes multi-tenant SaaS concerns).

## 3. Schema validation

- **Decision**: Author the five contracts (`CanonicalDocument`, `ObligationObject`, `ValidationReport`, `GraphChangeSet`, `GraphSnapshotExport`) as literal JSON Schema draft 2020-12 documents under `shared_contracts/schemas/*.json`, exactly as titled in the spec (§0, "source of truth for schemas"), and validate against them with the `jsonschema` library at every module boundary (§2 preamble: "must be validated against its schema before being persisted or transmitted across a module boundary").
- **Rationale**: The spec is explicit that schemas are the source of truth and code must be generated from them, not hand-diverged. Keeping schemas as standalone JSON files (rather than only as Pydantic models) satisfies that literally and lets both Python code and any future non-Python consumer validate against the same artifact.
- **Alternatives considered**: Pydantic-model-only (no standalone JSON Schema files) — rejected because the spec requires schemas as the checked-in source of truth, not an implementation-derived artifact.

## 4. Graph database

- **Decision**: Neo4j (per spec.md resolved clarification), accessed via the official `neo4j` Python driver, with the reference proof-path query (technical spec §3.3) implemented directly in Cypher.
- **Rationale**: Matches the technical spec's own query pattern style, requiring no restatement; Neo4j natively supports the ontology's cardinality/constraint model (§2.4) via application-level checks run inside the same transaction as the write (§7, Graph & registries zone).
- **Transaction/versioning approach**: Snapshots are modeled as immutable, versioned subgraphs — every node/relationship carries a `valid_from` / snapshot-lineage property rather than being physically deleted on supersession, so `superseded_snapshot_id` chains (§2.5, §5.8) remain queryable. Publish (§5.7) runs as a single Neo4j transaction; any failure triggers a full transaction rollback with no partial commit (§4.3, Deterministic publisher).
- **Alternatives considered**: A relational store with a recursive-CTE emulation of graph traversal — rejected per the resolved clarification and because it would require re-deriving the §3.3 query pattern in SQL, adding risk of behavioral drift from the spec's literal traversal description.

## 5. LLM gateway & provider allow-list

- **Decision**: A single internal "LLM gateway" module mediates all agent calls (Extraction, Reference, Critic, Graph Mapping agents per §4.4); the concrete provider(s) behind the allow-list are configured, not hardcoded, defaulting to one commercial provider for the prototype with the allow-list mechanism itself built so a second provider can be added by configuration only.
- **Rationale**: Technical spec §7 requires "Model provider is selected from an explicit allow-list (no arbitrary endpoint)" but leaves the specific provider(s) to Engineering per §10 Q2 — an open question not resolved by the user during specification and not structurally blocking (unlike the three resolved in spec.md, this one does not change the data model or acceptance criteria, only which provider string appears in the allow-list config). Building the allow-list as configuration rather than a hardcoded branch means the actual provider choice can be finalized without re-touching this plan.
- **Constraint carried forward**: every agent call MUST be tool-restricted to read-only lookups against the pinned document and controlled vocabulary, enforced at the gateway level (§4.4, §7) — this is a hard architectural requirement regardless of which provider is configured.
- **Flag**: This remains an open configuration decision for Engineering before the gateway can point at a live provider in a non-fixture environment; it does not block building the gateway's interface, the agent I/O contracts, or fixture-based tests.

## 6. Async job execution

- **Decision**: In-process background task queue (e.g., FastAPI `BackgroundTasks` backed by an internal worker abstraction) for parse jobs (§5.2/5.3), designed so the worker abstraction can be swapped for a distributed queue later without changing the `POST /v1/parse-jobs` / `GET /v1/parse-jobs/{id}` contract.
- **Rationale**: Spec's non-goals (§1.2) exclude "real external system integration" and multi-tenant SaaS concerns, and the deployment target is single-tenant local (§1.2) — a full distributed job queue (Celery/Redis) would be scope creep for a prototype-scale module pair. The job status contract (`queued`/`running`/`completed`/`failed` + `trace_id` + `validation_summary`) is what's normative, not the execution substrate.
- **Alternatives considered**: Celery + Redis — rejected as unnecessary infrastructure for the stated single-tenant, non-SaaS scope; a synchronous endpoint — rejected because §5.2 explicitly specifies `202 Accepted` async semantics.

## 7. Testing strategy

- **Decision**: `pytest`, with the §9.1 Given/When/Then acceptance scenarios written as the literal first test names (per the technical spec's closing instruction: "§9's Given/When/Then blocks are the literal test names to write first"), contract tests validating every payload against its JSON Schema, and fixture-based agent tests (no live LLM calls in CI) per the non-goal excluding "real external system integration."
- **Rationale**: Directly follows the technical spec's own TDD guidance and non-goals.
- **Alternatives considered**: None — this is dictated by the spec's explicit "How to use this spec during implementation" section.

## 8. Evaluation corpus

- **Decision**: A bounded, curated subset of NIS2/CRA/DORA articles (per spec.md's resolved clarification), stored as versioned fixture documents under an evaluation-corpus directory, stratified by regulation with a locked train/eval split (§9.3), including deliberately: hard negatives, nested conditions, an annex table, a long cross-reference, and one amendment scenario.
- **Rationale**: Directly implements §9.3's stated corpus requirements at the smallest scope consistent with exercising every measured capability in §9.2.
- **Open point carried to Engineering**: the exact article list is not specified anywhere in the technical spec or the resolved clarification (only "bounded subset" was decided) — Engineering/Regulatory SME must enumerate the specific articles before the corpus can be finalized. This does not block building the ingestion/parsing/evaluation *machinery*, only populating it with final content.

## Summary of remaining non-blocking flags

Two items are explicitly *not* resolved by this research phase because the technical spec assigns them to a later owner (Engineering / Regulatory SME) rather than treating them as scope-defining product decisions:
1. Concrete LLM provider identity for the gateway allow-list (§10 Q2).
2. The literal enumerated article list for the v1 evaluation corpus (bounded-subset decision made; specific articles not enumerated).

Both are implementation-detail/content decisions that do not change any data contract, endpoint, or acceptance criterion, so they do not block Phase 1 design — they are called out again in `plan.md`'s Complexity Tracking / open-items area for visibility.
