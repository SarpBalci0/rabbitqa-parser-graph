---

description: "Task list for Clause Parser & Compliance Knowledge Graph"
---

# Tasks: Clause Parser & Compliance Knowledge Graph

**Input**: Design documents from `/specs/001-clause-parser-compliance-graph/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included. The technical spec (`rabbitqa_spec_v1.0.0.md`, "How to use this spec during implementation") states: "§9's Given/When/Then blocks are the literal test names to write first (TDD-friendly by design)" — so contract and integration tests are mandatory, not optional, for this feature.

**Organization**: Tasks are grouped by user story (spec.md priorities) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 (Ingest & Parse), US2 (Review), US3 (Graph Mapping), US4 (Publish & Query), US5 (Export)
- File paths follow the module layout in `plan.md` → Project Structure

## Path Conventions

Per `plan.md`: `shared_contracts/`, `clause_parser/`, `compliance_graph/`, `llm_gateway/`, `reviewer_ui/`, `evaluation/` at repository root, each with `src/` and `tests/{contract,integration,unit}/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Create repository directories per plan.md: `shared_contracts/{schemas,py}`, `clause_parser/{src,tests/{contract,integration,unit}}`, `compliance_graph/{src,tests/{contract,integration,unit}}`, `llm_gateway/`, `reviewer_ui/`, `evaluation/{corpus,metrics}`
- [X] T002 Initialize Python 3.11+ project with `pyproject.toml` declaring dependencies: `fastapi`, `pydantic`, `jsonschema`, `neo4j`, a SQL toolkit for the pre-graph record store (e.g. `sqlalchemy` + a driver), `pytest`, `pytest-asyncio`, `httpx` (test client)
- [X] T003 [P] Configure linting/formatting (ruff + black config) in `pyproject.toml`
- [X] T004 [P] Copy the five literal JSON Schemas from `specs/001-clause-parser-compliance-graph/contracts/*.schema.json` into `shared_contracts/schemas/` as the checked-in source of truth (CanonicalDocument, ObligationObject, ValidationReport, GraphChangeSet, GraphSnapshotExport)
- [X] T005 [P] Copy `specs/001-clause-parser-compliance-graph/contracts/ConstraintReport.schema.json` into `shared_contracts/schemas/` — this is an INTERIM contract (see its `$comment`), derived by mirroring `ValidationReport.schema.json`'s shape and enumerating the six named rules from §2.4, since the technical spec references `ConstraintReport.schema.json` without ever defining it. Add a `shared_contracts/schemas/README.md` note that this file MUST be confirmed against a spec update (spec_version bump per §0) before being treated as final, and that `GraphChangeSet.schema.json`'s `constraint_report` field resolves against it

**Checkpoint**: Directory layout and schema files exist; dependencies installable; the `GraphChangeSet` → `ConstraintReport` schema reference resolves to a concrete (if interim) file.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T006 Implement schema-validation helper in `shared_contracts/py/validation.py` that validates any dict against a named schema file under `shared_contracts/schemas/` using `jsonschema` (draft 2020-12), raising a typed `SchemaValidationError`; confirm it correctly resolves the `GraphChangeSet` → `ConstraintReport` `$ref` from T005
- [X] T007 [P] Implement Pydantic models mirroring the five contracts plus `ConstraintReport` in `shared_contracts/py/models.py` (`CanonicalDocument`, `ObligationObject`, `ValidationReport`, `GraphChangeSet`, `ConstraintReport`, `GraphSnapshotExport`), used for API (de)serialization; validation against the literal schemas (T006) remains authoritative
- [X] T008 Implement the standard API error envelope (`{"error": {"code","message","details"}}`) and FastAPI exception handlers for 400/404/409/422/500 in `clause_parser/src/api/errors.py` and reused by `compliance_graph/src/api/errors.py`
- [X] T009 Implement request tracing middleware (idempotency key on mutating requests, per-client rate limiting, `trace_id` generation propagated into every log line) in a shared `shared_contracts/py/middleware.py`, per §7 Workflow service zone
- [X] T010 [P] Implement `llm_gateway/allow_list.py`: explicit, configuration-driven model-provider allow-list (no arbitrary endpoint), per research.md §5
- [X] T011 [P] Implement `llm_gateway/tool_policy.py`: enforces zero write-capable tools for any agent call (no DB writes, graph writes, shell exec, unrestricted network — only read-only lookups against the pinned document and controlled vocabulary), enforced at the gateway level per §4.4/§7
- [X] T012 [P] Implement `llm_gateway/logging.py`: logs `{model_version, prompt_version, input_hash, output_hash, context_hash}` for every agent call, per §7 LLM gateway zone
- [X] T013 Implement the untrusted-data wrapping helper in `llm_gateway/context_package.py` that assembles an agent context package with document text in a clearly delimited untrusted block, kept separate from the system/instruction prompt, per §4.4 prompt-injection boundary
- [X] T014 Set up Neo4j connection/session management in `compliance_graph/src/db/neo4j_client.py` (driver init, transaction helper enforcing all-or-nothing commit/rollback)
- [X] T015 Set up append-only audit/decision-history persistence primitive (no update/delete grants) in `shared_contracts/py/audit_log.py`, per §7 Graph & registries zone and FR-036
- [X] T016 Select and implement the pre-graph record store technology (a relational/document store, e.g. PostgreSQL/SQLite via SQLAlchemy) and connection/session management in `shared_contracts/py/db.py` — resolves the storage-layer gap flagged in plan.md's Technical Context ("Storage") and Complexity Tracking table; without this, `CanonicalDocument`/`ObligationObject`/`ValidationReport`/`GraphChangeSet` have nowhere to be persisted before graph publish
- [X] T017 [P] Implement `CanonicalDocument` repository (create; get-by-checksum for idempotent registration lookup per FR-002; get-by-id+source_version) in `clause_parser/src/db/document_repository.py` (depends on T016)
- [X] T018 [P] Implement `ObligationObject`/`ValidationReport` repository (create/update a proposal + its validation report as one record; list a clause's parse-revisions oldest-first; atomically append a `revision_history` entry alongside any `review_status` change, per FR-014/FR-017 invariant) in `clause_parser/src/db/obligation_repository.py` (depends on T016)
- [X] T019 [P] Implement `GraphChangeSet` repository (create draft; persist `status` transitions draft→validated→approved→rejected; retrieve by id; list by `base_snapshot_id`) in `compliance_graph/src/db/changeset_repository.py` (depends on T016)

**Checkpoint**: Foundation ready — user story implementation can now begin, including a concrete place to persist and retrieve every pre-graph record type.

---

## Phase 3: User Story 1 - Ingest and parse a pinned regulation into reviewable obligations (Priority: P1) 🎯 MVP

**Goal**: Register one pinned source document and run it through the fixed six-step parsing pipeline (§4.1) to produce validated, source-traceable obligation proposals.

**Independent Test**: Register a source document, trigger a parse job, and confirm every resulting obligation proposal's evidence text is an exact, hash-verified substring of the registered document, with a validation outcome attached.

### Tests for User Story 1

- [X] T020 [P] [US1] Contract test: `CanonicalDocument` payload validates against `shared_contracts/schemas/CanonicalDocument.schema.json` in `clause_parser/tests/contract/test_canonical_document_schema.py`
- [X] T021 [P] [US1] Contract test: `ObligationObjectProposal` (subset) and `ValidationReport` payloads validate against their schemas in `clause_parser/tests/contract/test_obligation_validation_schemas.py`
- [X] T022 [P] [US1] Integration test — Ingestion Given/When/Then: registering byte-identical content twice returns the same `document_id`, second call is `200` not `201`, in `clause_parser/tests/integration/test_ingestion_idempotency.py`
- [X] T023 [P] [US1] Integration test — Parsing Given/When/Then: every proposal's `evidence_hash == sha256(verbatim_text)` and `verbatim_text` is an exact substring at its offsets, in `clause_parser/tests/integration/test_parsing_evidence_fidelity.py`
- [X] T024 [P] [US1] Integration test — Validation Given/When/Then: a proposal with fabricated (non-substring) `verbatim_text` forces `overall_status == "fail"` and `review_status` auto-routes to `"escalated"`, in `clause_parser/tests/integration/test_validation_escalation.py`
- [X] T025 [P] [US1] Integration test: re-ingesting identical source content yields byte-identical `anchor_id`s (replay idempotency), in `clause_parser/tests/integration/test_anchor_id_idempotency.py`

### Implementation for User Story 1

- [X] T026 [US1] Implement Step 1 Canonicalize (deterministic, no LLM): whitespace/encoding normalization + structural anchor extraction producing `CanonicalDocument.structure` with pure-function `anchor_id`s in `clause_parser/src/canonicalize/canonicalizer.py`
- [X] T027 [US1] Implement write-once raw artifact storage (reject rewrite to existing key) in `clause_parser/src/canonicalize/raw_storage.py`
- [X] T028 [US1] Implement checksum computation (sha256 of raw artifact) and content-based idempotent document registration, backed by the T017 repository, in `clause_parser/src/canonicalize/document_registry.py`
- [X] T029 [US1] Implement Step 2 Detect: deterministic normative-passage/hard-negative classifier baseline (logged separately) in `clause_parser/src/detect/deterministic_detector.py`
- [X] T030 [US1] Implement optional LLM-assisted detection refinement layered on top of T029's output (never replacing it) in `clause_parser/src/detect/llm_refinement.py`
- [X] T031 [US1] Implement Step 3 Decompose: split normative spans into atomic candidate obligation spans, retaining shared conditions/exceptions via `parent_span_id`, recording deterministic-vs-LLM method in governance metadata, in `clause_parser/src/decompose/decomposer.py`
- [X] T032 [US1] Implement Extraction Agent client (context package: one span's text + immediate structural anchor + controlled vocabulary list; output: `legal_semantics` + `source_evidence` subset) using `llm_gateway` in `clause_parser/src/agents/extraction_agent.py`
- [X] T033 [US1] Implement Step 4 Extract orchestration calling the Extraction Agent and assembling an `ObligationObjectProposal` in `clause_parser/src/extract/extractor.py`
- [X] T034 [US1] Implement Reference Agent client (context: resolved-definitions index + candidate reference mentions; output: `{candidates:[{mention,target_anchor_id,confidence}]}`) in `clause_parser/src/agents/reference_agent.py`
- [X] T035 [US1] Implement Step 5 Resolve: deterministic date/quantity normalizers plus Reference Agent-backed reference resolution populating `references` block in `clause_parser/src/resolve/resolver.py`
- [X] T036 [US1] Implement Step 6 Validate (deterministic only, no LLM): schema_validity, controlled_vocabulary, evidence_span_fidelity, date_normalization, quantity_normalization, reference_validity, cross_field_consistency checks producing `ValidationReport` in `clause_parser/src/validate/validator.py`
- [X] T037 [US1] Implement the fail/needs_review routing rule (evidence_span_fidelity or schema_validity fail → overall fail → auto-escalated; other single fail → needs_review) in `clause_parser/src/validate/routing.py`
- [X] T038 [US1] Implement `clause_parser/src/pipeline.py` orchestrating steps 1–6 in fixed order with no step skippable/reorderable, persisting each proposal + its `ValidationReport` via the T018 repository
- [X] T039 [US1] Implement `POST /v1/documents` endpoint (checksum-based idempotent registration via T028/T017, 201/200/400) in `clause_parser/src/api/documents.py`
- [X] T040 [US1] Implement `POST /v1/parse-jobs` (async, 202 + job_id/status) and background job runner invoking the T038 pipeline for every detected normative span in `clause_parser/src/api/parse_jobs.py`
- [X] T041 [US1] Implement `GET /v1/parse-jobs/{id}` (status + trace_id + validation_summary) in `clause_parser/src/api/parse_jobs.py`
- [X] T042 [US1] Implement `GET /v1/clauses/{id}/parse-revisions` (oldest-first array of proposal+report+history, read via the T018 repository) in `clause_parser/src/api/clauses.py`
- [X] T043 [US1] Wire document-ingress security controls (size limit rejection, content-type allow-list, malware scan hook, checksum-before-parse ordering) in `clause_parser/src/api/documents.py`, per §7 Document ingress zone and FR-034

**Checkpoint**: User Story 1 fully functional — documents can be registered and parsed into validated, persisted proposals independently of review/graph/export.

---

## Phase 4: User Story 2 - Review and decide on extracted obligations (Priority: P1)

**Goal**: A reviewer accepts, edits, rejects, or escalates a proposal, with every decision recorded and justified, and edits re-validated before persisting.

**Independent Test**: Submit each of the four reviewer decisions against a pending proposal and confirm resulting status/history, including rejection of empty-rationale or evidence-breaking edits.

### Tests for User Story 2

- [X] T044 [P] [US2] Contract test: decision request/response and updated `ObligationObject` validate against `ObligationObject.schema.json` in `clause_parser/tests/contract/test_review_decision_schema.py`
- [X] T045 [P] [US2] Integration test — Review Given/When/Then: accept decision persists `revision_history` entry + `review_status == "accepted"` in `clause_parser/tests/integration/test_review_accept.py`
- [X] T046 [P] [US2] Integration test: empty-rationale decision is rejected (400), no state change, in `clause_parser/tests/integration/test_review_empty_rationale.py`
- [X] T047 [P] [US2] Integration test — edit breaking evidence-span fidelity returns 422 and no persisted state changes, in `clause_parser/tests/integration/test_review_edit_evidence_break.py`
- [X] T048 [P] [US2] Integration test: full decision history (reviewer, timestamp, decision, rationale) is retrievable for a clause and its superseded prior article versions, in `clause_parser/tests/integration/test_review_history.py`

### Implementation for User Story 2

- [X] T049 [US2] Implement decision-application logic (accept/edit/reject/escalate) appending a `revision_history` entry in the same transaction as any status change, persisted via the T018 repository, in `clause_parser/src/review/decision_service.py`
- [X] T050 [US2] Implement mandatory non-empty-rationale validation (400 on empty) in `clause_parser/src/review/decision_service.py`
- [X] T051 [US2] Implement edit-path re-validation: re-run Step 6 validator (T036) on edited content before persisting; reject with 422 on evidence-span-fidelity failure, no partial writes, in `clause_parser/src/review/decision_service.py`
- [X] T052 [US2] Implement `diff` capture for free-text field edits attached to the `revision_history` entry in `clause_parser/src/review/diff.py`
- [X] T053 [US2] **RESOLVED** (originally deferred pending US4 graph publish — see prior note below, kept for history): prior-article-version history linkage. Supersession is tracked via the real `SUPERSEDES` (Regulation→Regulation, §3.2) relationship, inferred from graph *publish order* (never guessed from `clause_parser` data alone, which genuinely has no supersession field per §2.1) — `compliance_graph/src/graph_mapping_agent/agent.py`'s new `latest_published_regulation` parameter creates the edge when a caller-supplied, read-only `GraphStore.find_latest_regulation(instrument)` lookup finds a prior version. Resolver: `compliance_graph/src/query/article_history.py:resolve_superseded_article_history` — walks the chain via `GraphStore.find_regulation_supersedes_target`, stopping (not erroring) at the first unresolvable link. **Moved from the originally-planned `clause_parser/src/review/article_history.py`** to `compliance_graph/src/query/article_history.py`, since the data it needs (`GraphStore`) only exists in `compliance_graph`. Tested end-to-end in `compliance_graph/tests/integration/test_article_history.py` (real two-version register→accept→map→publish→resolve flow, not a hand-built graph), including a direct constraint-validation check that the created `SUPERSEDES` edges pass the real engine. Wired into `reviewer_ui/src/history_view.py` (§6.5's second half, previously stubbed with a "deferred" note). **Building this surfaced and fixed a real, separate pre-existing bug**: `DocumentRepository.get_by_checksum` was scoped to `(instrument, checksum)` only, ignoring `source_version` — so re-registering byte-identical content under a genuinely different `source_version` silently returned the OLD document instead of registering a new one, violating spec.md's own documented edge case ("distinct pinned versions — each gets its own identity"). Fixed: now scoped to `(instrument, source_version, checksum)` per §5.1 spec_version 1.0.2's literal wording ("matches the already-registered (instrument, source_version)"). Original deferral note: DEFERRED to US4 (user-confirmed during implementation): prior-article-version history linkage can't be correctly implemented until `compliance_graph`'s `SUPERSEDES` relationship (Regulation→Regulation, §3.2) exists and is queryable — the root spec has no supersession field on `CanonicalDocument` (§2.1) or elsewhere that `clause_parser` alone can consult, and guessing a same-instrument heuristic would invent behavior the spec never states.
- [X] T054 [US2] Implement `POST /v1/reviews/{revision}/decisions` endpoint wiring T049–T052 (T053 deferred, see above) in `clause_parser/src/api/reviews.py`
- [X] T055 [US2] Implement server-side independent re-validation-on-submit guarantee (server never trusts UI-side "validation shown" state) in `clause_parser/src/api/reviews.py`

**Checkpoint**: User Stories 1 and 2 together deliver a complete ingest→parse→review loop, independently testable.

---

## Phase 5: User Story 3 - Map approved obligations into the compliance knowledge graph (Priority: P2)

**Goal**: Turn accepted/edited obligations into a proposed, ontology-validated `GraphChangeSet` that cannot be approved unless structurally valid.

**Independent Test**: Generate a change set from accepted obligations; confirm an ontology-violating proposal is auto-rejected and cannot be approved, while a valid one validates and can be approved.

### Tests for User Story 3

- [X] T056 [P] [US3] Contract test: `GraphChangeSet` payload (including its now-resolvable `constraint_report`) validates against `GraphChangeSet.schema.json` in `compliance_graph/tests/contract/test_graph_changeset_schema.py`
- [X] T057 [P] [US3] Contract test: `ConstraintReport` payload validates against `shared_contracts/schemas/ConstraintReport.schema.json` in `compliance_graph/tests/contract/test_constraint_report_schema.py`
- [X] T058 [P] [US3] Integration test — Graph mapping Given/When/Then: relationship type/pair not in §3.2 table forces `constraint_report` failure and `status == "rejected"`, in `compliance_graph/tests/integration/test_ontology_relationship_validation.py`
- [X] T059 [P] [US3] Integration test: `Obligation` node without exactly one `DERIVED_FROM`→`Provision` or without ≥1 `IMPOSES_ON`→`Actor` fails validation, in `compliance_graph/tests/integration/test_obligation_cardinality.py`
- [X] T060 [P] [US3] Integration test: relationship referencing a `node_id` absent from both the proposal and the published base snapshot fails validation, in `compliance_graph/tests/integration/test_dangling_reference.py`

### Implementation for User Story 3

- [X] T061 [US3] Implement entity resolution (fuzzy+exact actor/asset matching with confidence score, no auto-merge above threshold without a recorded reviewer decision) in `compliance_graph/src/entity_resolution/matcher.py`
- [X] T062 [US3] Implement Graph Mapping Agent client (context: approved `ObligationObject`(s) + ontology + controls/assets/evidence fixture; output: draft `GraphChangeSet`, proposal-only, never writes to graph) using `llm_gateway` in `compliance_graph/src/graph_mapping_agent/agent.py`, persisting the draft via the T019 repository
- [X] T063 [US3] Implement ontology reference tables (node types + required properties, relationship types + allowed from/to pairs) as a versioned constant module in `compliance_graph/src/constraints/ontology.py`, mirroring data-model.md §6.1–§6.2 exactly
- [X] T064 [US3] Implement the constraints engine: ontology conformance, cardinality rules (Obligation→exactly one DERIVED_FROM, ≥1 IMPOSES_ON; MAPS_TO_CONTROL/EVIDENCED_BY endpoint restrictions), dangling-reference checks, run identically for every change set regardless of size, in `compliance_graph/src/constraints/engine.py`
- [X] T065 [US3] Implement `ConstraintReport` production against the resolved `shared_contracts/schemas/ConstraintReport.schema.json` (T005/T007) — one `rules[]` entry per named rule in the schema's enum — in `compliance_graph/src/constraints/report.py`
- [X] T066 [US3] Implement forced-rejection rule: any constraint failure sets `GraphChangeSet.status = "rejected"` (persisted via T019), ineligible for approval, in `compliance_graph/src/constraints/engine.py`
- [X] T067 [US3] Implement change-set approval action (explicit reviewer decision required; no auto-publish path; status transition persisted via T019) in `compliance_graph/src/review/changeset_approval.py`
- [X] T068 [US3] Implement `POST /v1/graph/changesets/{id}/validate` endpoint (non-mutating) in `compliance_graph/src/api/changesets.py`

**Checkpoint**: Accepted obligations can be proposed and validated into graph change sets, independently of publish/query/export.

---

## Phase 6: User Story 4 - Publish a graph snapshot and query proof paths (Priority: P2)

**Goal**: Publish an approved, validated change set as an immutable, versioned graph snapshot and run source-backed proof-path queries against it.

**Independent Test**: Publish a validated/approved change set, confirm a new snapshot exists and the prior one remains retrievable via lineage, then run the §3.3 proof-path query and confirm every result carries clause_id/verbatim_text/review_status/graph_snapshot_id.

### Tests for User Story 4

- [X] T069 [P] [US4] Integration test — publish preconditions: non-approved status, stale `base_snapshot_id`, or non-zero constraint failures each return 409/422 with graph unchanged, in `compliance_graph/tests/integration/test_publish_preconditions.py`
- [X] T070 [P] [US4] Integration test — successful publish: new `snapshot_id` queryable, prior snapshot retrievable via `superseded_snapshot_id`, in `compliance_graph/tests/integration/test_publish_lineage.py`
- [X] T071 [P] [US4] Integration test — proof-path query: every result includes `clause_id`, `verbatim_text`, `review_status`, `graph_snapshot_id`, in `compliance_graph/tests/integration/test_proof_path_query.py`
- [X] T072 [P] [US4] Integration test: querying a non-fully-published snapshot returns 404, never partial data, in `compliance_graph/tests/integration/test_query_unpublished_snapshot.py`

### Implementation for User Story 4

- [X] T073 [US4] Implement transactional publisher (single all-or-nothing Neo4j transaction; full rollback on any failure; no partial-success state) in `compliance_graph/src/publisher/publisher.py`, using T014's transaction helper and reading the approved changeset via T019
- [X] T074 [US4] Implement optimistic-concurrency check (`base_snapshot_id` must equal current head) in `compliance_graph/src/publisher/publisher.py`
- [X] T075 [US4] Implement snapshot lineage modeling (`superseded_snapshot_id` chain, immutable-versioned-subgraph approach per research.md §4) in `compliance_graph/src/publisher/snapshot.py`
- [X] T076 [US4] Implement `POST /v1/graph/changesets/{id}/publish` endpoint enforcing all three preconditions in `compliance_graph/src/api/changesets.py`
- [X] T077 [US4] Implement `GET /v1/graph/snapshots/{id}` (metadata + ontology_version + lineage) in `compliance_graph/src/api/snapshots.py`
- [X] T078 [US4] Implement the §3.3 proof-path Cypher query and a `coverage` pattern query in `compliance_graph/src/query/proof_path.py`
- [X] T079 [US4] Implement `POST /v1/graph/query` endpoint enforcing the not-fully-published → 404 rule in `compliance_graph/src/api/query.py`

**Checkpoint**: Approved graph content can be published and queried end-to-end, independently of export.

---

## Phase 7: User Story 5 - Export a read-only, audit-ready snapshot (Priority: P3)

**Goal**: Produce a schema-valid, review-gated, provenance-gated export of a published snapshot.

**Independent Test**: Export a snapshot with mixed review statuses and confirm only accepted/edited obligations with a fully resolvable provenance chain appear, validated against the export schema.

### Tests for User Story 5

- [X] T080 [P] [US5] Contract test: export payload validates against `GraphSnapshotExport.schema.json` in `compliance_graph/tests/contract/test_export_schema.py`
- [X] T081 [P] [US5] Integration test — Query & export Given/When/Then: obligation with review_status not in {accepted, edited} is excluded from export payload, in `compliance_graph/tests/integration/test_export_review_gate.py`
- [X] T082 [P] [US5] Integration test: obligation with any unresolvable provenance-chain link is excluded from export, in `compliance_graph/tests/integration/test_export_provenance_gate.py`

### Implementation for User Story 5

- [X] T083 [US5] Implement provenance-chain resolver (source checksum → document_id → parse run_id + agent run_ids → ValidationReport → reviewer decision → changeset_id → snapshot_id → export manifest), reading pre-graph records via T017/T018 and change-set records via T019, in `compliance_graph/src/export/provenance.py`, per §7 Provenance chain
- [X] T084 [US5] Implement export builder: include only accepted/edited obligations with a fully resolvable provenance chain, silently excluding all others, in `compliance_graph/src/export/exporter.py`
- [X] T085 [US5] Implement export-boundary logging (signed request manifest) per §7 Export boundary zone in `compliance_graph/src/export/manifest.py`
- [X] T086 [US5] Implement `GET /v1/graph/snapshots/{id}/export` endpoint validating the payload against `GraphSnapshotExport.schema.json` before returning, in `compliance_graph/src/api/export.py`

**Checkpoint**: All five user stories independently functional; full ingest→parse→review→map→publish→query→export path exists.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Reviewer UI, evaluation harness, security-control test coverage, and end-to-end validation spanning all stories

- [X] T087 [P] Implement reviewer workspace source pane (verbatim text + highlighted evidence span + anchor label) per §6.1 in `reviewer_ui/src/source_pane.*`
- [X] T088 [P] Implement reviewer workspace structured field editor capturing free-text edits as `diff` objects per §6.2 in `reviewer_ui/src/field_editor.*`
- [X] T089 [P] Implement reviewer workspace validator-findings/confidence display gating decision submission in the UI (client-side only; server independently re-validates per T055) per §6.3 in `reviewer_ui/src/validation_panel.*`
- [X] T090 [P] Implement reviewer workspace graph-diff/proof-path preview for a pending `GraphChangeSet` (calls §5.6 validate before enabling approval) per §6.4 in `reviewer_ui/src/graph_diff_preview.*`
- [X] T091 [P] Implement reviewer workspace prior-revision history view (including T053's article-history linkage) per §6.5 in `reviewer_ui/src/history_view.*`
- [X] T092 [P] Assemble the locked, regulation-stratified evaluation corpus (bounded NIS2/CRA/DORA article subset per research.md §8; hard negatives, nested conditions, annex table, long cross-reference, one amendment scenario) in `evaluation/corpus/`
- [X] T093 [P] Implement the §4.2/§9.2 metrics harness (detection precision/recall, core/complex field F1, evidence-span exact-overlap rate, source-anchor validity rate, graph mapping macro F1, competency query accuracy, transaction success rate, replay idempotency, export schema validity) in `evaluation/metrics/harness.py`
- [X] T094 [P] Integration test: agent context packages wrap document text in a clearly delimited untrusted block, never concatenated into the system/instruction prompt (FR-032), in `llm_gateway/tests/test_prompt_injection_boundary.py`
- [X] T095 [P] Integration test: every agent client's tool allow-list is empty except read-only document/vocabulary lookups — no DB write, graph write, shell, or unrestricted network tool is reachable (FR-033), in `llm_gateway/tests/test_tool_policy_enforcement.py`
- [X] T096 [P] Integration test: uploads exceeding the configured size limit or failing the content-type allow-list are rejected before checksum/parsing (FR-034), in `clause_parser/tests/integration/test_document_ingress_controls.py`
- [X] T097 [P] Integration test: every agent call logs `{model_version, prompt_version, input_hash, output_hash, context_hash}` (FR-035), in `llm_gateway/tests/test_agent_call_logging.py`
- [X] T098 [P] Integration test: the audit/decision-history store exposes no update or delete operation, only append (FR-036), in `shared_contracts/tests/test_audit_log_append_only.py`
- [X] T099 Run the full `quickstart.md` validation scenario end-to-end and record results (satisfies §9.4 completion condition) — see `evaluation/run_full_e2e_demo.py`, run twice to confirm reproducibility (exit code 0 both times)
- [X] T100 [P] Security review pass against the §7 trust-zone table (document ingress, workflow service, LLM gateway, graph & registries, export boundary) confirming each MUST is enforced in code — cross-check against T094–T098's automated coverage rather than re-verifying manually. **Two real findings, both fixed**: (1) Graph & registries zone — `publish_change_set` trusted only the STORED `constraint_report` from an earlier, separate `/validate` call ("before-and-hope", exactly what §7 prohibits); fixed by re-running constraints fresh in `publisher.py` immediately before the graph write, regardless of what the stored report claims (`compliance_graph/tests/integration/test_publish_preconditions.py`'s constraint-failure test rewritten to prove a stale/falsified "pass" report no longer bypasses this). (2) LLM gateway zone — `llm_gateway/allow_list.py` (T010) had zero test coverage; added `llm_gateway/tests/test_allow_list.py`.
- [X] T101 [P] Add unit tests for canonicalization idempotency, checksum computation, and anchor_id purity in `clause_parser/tests/unit/`
- [X] T102 [P] Add unit tests for constraint-engine rule coverage (every node type, every relationship pair) in `compliance_graph/tests/unit/` — already satisfied by `compliance_graph/tests/unit/test_ontology_exhaustive.py`, built during User Story 3's verification pass (exhaustive 14x18x18 combination check, not spot-checks)
- [X] T103 Documentation: record the resolved and open items from plan.md's Complexity Tracking table (ConstraintReport interim schema now resolved per T005/contracts/ConstraintReport.schema.json; storage-layer choice now resolved per T016; LLM provider and corpus article list still open) in a project README or tracking doc — see `README.md`
- [X] T104 **RESOLVED** (2026-09-01, once Docker Desktop was started): ran a real smoke test against `Neo4jGraphStore` — `compliance_graph/tests/live_neo4j/test_neo4j_store_smoke.py`, 5/5 PASSED against a live `neo4j:5` container (`docker run -d --name rabbitqa-neo4j -p 7687:7687 -p 7474:7474 -e NEO4J_AUTH=none neo4j:5`), covering exactly the named risk areas: (1) transactional publish commit path AND rollback-on-failure (a genuine mid-transaction `KeyError` from a malformed node leaves node count, snapshot count, and head pointer completely unchanged — verified by direct Cypher `count()` queries before/after, not inferred); (2) `MERGE`/`DETACH DELETE` head-pointer sequencing — after 3 publishes, exactly one `:GraphHead` node exists, pointing at the latest snapshot; (3) cross-snapshot property matching — two snapshots with colliding `clause_id` property values on their Obligation nodes remain correctly isolated by the `{snapshot_id: $snapshot_id}` filter (each snapshot's query returns exactly 1, not 2). A bonus check not in the original three risk areas but directly relevant to "label injection via f-string": a relationship type string containing Cypher-breaking characters (`` REL`}) DETACH DELETE n // ``) was submitted, and the driver raised a syntax error rather than silently executing the injected fragment — confirmed by the test asserting an exception occurred (`pytest.fail` would have fired otherwise) and that the graph was left in the expected node count. Re-verified reproducibility: 5/5 pass with the container up, all 5 cleanly SKIP (not error) via a connectivity-check `skipif` when it's down (confirmed by stopping/restarting the container mid-session). Test file is NOT in `pyproject.toml`'s default `testpaths` list as a live-server dependency, but lives under `compliance_graph/tests/` so it auto-discovers and self-skips safely in any environment without a live Neo4j reachable at `bolt://localhost:7687`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **User Story 1 (Phase 3, P1)**: Depends on Foundational only (including the T016–T019 persistence layer)
- **User Story 2 (Phase 4, P1)**: Depends on Foundational; consumes proposals produced by US1's pipeline (T038) and validator (T036), persisted via T018 — in practice sequenced after US1, though its own tests/endpoints are a separable slice
- **User Story 3 (Phase 5, P2)**: Depends on Foundational; consumes accepted `ObligationObject`s from US2, persisted change sets via T019 — sequenced after US2
- **User Story 4 (Phase 6, P2)**: Depends on Foundational; consumes approved `GraphChangeSet`s from US3 — sequenced after US3
- **User Story 5 (Phase 7, P3)**: Depends on Foundational; consumes published snapshots from US4 — sequenced after US4
- **Polish (Phase 8)**: Depends on all desired user stories being complete

### User Story Dependencies

Unlike a typical spec-kit feature where stories are independently orderable, this feature's stories form the literal pipeline stages of one system (§9.4 completion condition is end-to-end), so:
- US1 → US2 → US3 → US4 → US5 is the natural build/demo order (each stage's output is the next stage's input).
- Each story is still **independently testable** using fixture data that stands in for the upstream stage's output (e.g., US3's tests can use a hand-built accepted `ObligationObject` fixture without running US1/US2's endpoints), so implementation teams are not blocked from working stories in parallel once Foundational is done — only the *end-to-end* demo requires the full chain.

### Parallel Opportunities

- All Setup tasks marked [P] (T003–T005) run in parallel.
- Within Foundational, T007, T010–T012 are independent files and run in parallel; T017–T019 are independent files and run in parallel once T016 (shared connection/session setup) is complete.
- All contract/integration test tasks marked [P] within a story run in parallel (different files).
- Reviewer UI tasks (T087–T091), evaluation tasks (T092–T093), and the security-control test tasks (T094–T098) in Phase 8 are independent of each other and can run in parallel.

---

## Parallel Example: User Story 1

```bash
# Launch all US1 tests together:
Task: "Contract test CanonicalDocument schema in clause_parser/tests/contract/test_canonical_document_schema.py"
Task: "Contract test ObligationObjectProposal/ValidationReport schemas in clause_parser/tests/contract/test_obligation_validation_schemas.py"
Task: "Integration test ingestion idempotency in clause_parser/tests/integration/test_ingestion_idempotency.py"
Task: "Integration test parsing evidence fidelity in clause_parser/tests/integration/test_parsing_evidence_fidelity.py"
Task: "Integration test validation escalation in clause_parser/tests/integration/test_validation_escalation.py"
Task: "Integration test anchor_id idempotency in clause_parser/tests/integration/test_anchor_id_idempotency.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories; includes the persistence layer, T016–T019)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: registration + parse job + evidence-fidelity/escalation tests all pass independently
5. Demo: register a fixture document, run a parse job, inspect resulting proposals

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US1 (ingest/parse) → validate independently → demo
3. US2 (review) → validate independently → demo full ingest→review loop
4. US3 (graph mapping) → validate independently → demo change-set validation/rejection behavior
5. US4 (publish/query) → validate independently → demo published, queryable snapshot
6. US5 (export) → validate independently → demo full §9.4 end-to-end run via quickstart.md
7. Polish (reviewer UI, evaluation harness, security-control tests)

---

## Notes

- [P] tasks = different files, no dependencies.
- [Story] label maps task to specific user story for traceability.
- This feature's stories are pipeline-sequential by nature (§9.4 is one end-to-end condition), but each story remains independently testable via fixtures per the Dependencies section above.
- Verify tests fail before implementing (TDD, per the technical spec's explicit instruction).
- Commit after each task or logical group.
- T005/T065 (and the `contracts/ConstraintReport.schema.json` file) carry forward the `ConstraintReport` schema gap flagged in plan.md — it is now a concrete, resolvable interim contract rather than an unresolved `$ref`, but still MUST be confirmed against a spec update before being treated as final.
- T016–T019 close a gap identified during `/speckit-analyze`: the pre-graph record store (for `CanonicalDocument`/`ObligationObject`/`ValidationReport`/`GraphChangeSet`) was previously unaddressed by any task despite several endpoints depending on it.
- T094–T098 close a second `/speckit-analyze` gap: FR-032–FR-036 (trust-boundary requirements) previously had implementation tasks but no dedicated automated tests.
