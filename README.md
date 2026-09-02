# RabbitQA — Clause Parser & Compliance Knowledge Graph

Standalone module pair implementing `rabbitqa_spec_v1.0.0.md` (spec_version 1.0.4).
See `CLAUDE.md` for the spec authority hierarchy governing this repository.

## Modules

- `shared_contracts/` — the five normative JSON Schema contracts (§2) plus the
  interim `ConstraintReport` contract, Pydantic models, schema validation,
  cross-field invariants, the pre-graph SQLite/SQLAlchemy record store, tracing
  middleware, and the append-only audit log.
- `clause_parser/` — ingestion, the six-step parsing pipeline (§4.1), review
  workflow (§5.5), and the Extraction/Reference agent clients.
- `compliance_graph/` — entity resolution, the Graph Mapping Agent, the
  constraints engine (§2.4/§3.2), transactional publisher, proof-path query
  (§3.3), and export (§2.5/§7).
- `llm_gateway/` — shared agent-call plumbing: provider allow-list, zero-write
  tool policy, prompt-injection boundary, call logging.
- `reviewer_ui/` — CLI reviewer workspace satisfying §6's five requirements.
- `evaluation/` — the §4.2/§9.2 metrics harness, a synthetic (not real
  regulatory text) corpus, and `run_full_e2e_demo.py`, the §9.4 completion-
  condition demonstration.

## Running

```
pip install -e ".[dev]"
python -m pytest                        # full test suite
python -m evaluation.run_full_e2e_demo   # §9.4 end-to-end demonstration
python -m evaluation.metrics.harness     # §4.2/§9.2 metrics against the synthetic corpus

uvicorn clause_parser.src.api.app:app --port 8001      # POST /v1/documents, /v1/parse-jobs, /v1/reviews/...
uvicorn compliance_graph.src.api.app:app --port 8002   # /v1/graph/... (requires a live Neo4j)
python -m reviewer_ui.cli <clause_id> --show-only      # CLI reviewer workspace (§6)
```

`clause_parser/src/api/app.py` and `compliance_graph/src/api/app.py` are the
runnable FastAPI entrypoints assembling the router factories each endpoint
module exports; `reviewer_ui/cli.py` is the runnable §6 CLI. None of these
existed until a real curl/CLI walkthrough was run end-to-end — building and
verifying them surfaced three further real bugs beyond the four already listed
below: a path-routing bug (`clause_id` contains `/`, so FastAPI's default path
converter silently truncated it), a missing `revision_id` field in
`GET /v1/clauses/{id}/parse-revisions`'s response (§5.4's literal response
shape gives no way to construct the request §5.5 needs), and an in-memory-only
agent-call log that made the §7 provenance-gated export always empty when
`clause_parser` and `compliance_graph` run as separate processes (the real
deployment topology) — fixed by persisting agent-call records to the shared
SQLite store both processes already use.

## Status (as of spec_version 1.0.4)

104 of 104 tasks in `specs/001-clause-parser-compliance-graph/tasks.md`
complete. All five user stories (Ingest & Parse, Review, Graph Mapping, Publish
& Query, Export) are built and tested, including prior-article-version history
(T053, §6.5's second half — supersession tracked via a real graph `SUPERSEDES`
relationship, inferred from publish order) and a real smoke test of the
production `Neo4jGraphStore` backend against a live Neo4j instance (T104, once
Docker Desktop became available — see `compliance_graph/tests/live_neo4j/`).
Routine test runs still use `InMemoryGraphStore` (fast, no external
dependency); the live-Neo4j test exists specifically to close the gap between
that test double and real Cypher execution, and self-skips safely when no live
server is reachable.

## Resolved spec issues (see `rabbitqa_spec_v1.0.0.md` §12 for full detail)

Four real defects/gaps were found in the root spec during implementation and
corrected there first, per this repo's rule that the root spec is fixed before
any derived artifact, with a version bump and changelog entry each time:

| Version | Issue |
|---|---|
| 1.0.1 | `ObligationObject.identity.clause_id`'s JSON Schema `pattern` was literal, unmatchable regex text (`"^{document_id}:{source_version}:.+$"`) — corrected to a structural pattern, with the semantic requirement enforced as a code-level cross-field invariant. |
| 1.0.2 | §5.1 conflated the idempotent-match (200) and genuine-conflict (409) cases for `POST /v1/documents` in one sentence with no defined behavior for re-registering different content under an already-used `source_version`. |
| 1.0.3 | §10's open questions (#1 graph store, #3 corpus scope, #4 four-eyes review) were resolved during specification but never logged back into the root spec's own §12, despite §10 explicitly requiring this. |
| 1.0.4 | §3.3's canonical proof-path query started at a `Regulation` node via a `DERIVED_FROM` edge that §3.2's own relationship table never permitted — the query was never satisfiable by any graph the ontology allows. Corrected to start at `Provision`. |

## Other known, explicitly-tracked gaps

- `ConstraintReport.schema.json` is an **interim contract** — §2.4/§5.6 reference
  it but the root spec never defines its fields. See
  `shared_contracts/schemas/README.md` and that schema file's own `$comment`.
- Concrete LLM provider identity (§10 Q2) and the exact enumerated NIS2/CRA/DORA
  article list (§10 Q3, scope resolved to "bounded subset," specific articles
  not yet chosen) remain open, assigned to Engineering / Regulatory SME per the
  root spec itself — not resolved by this implementation.
- Agent clients (`clause_parser/src/agents/`, `compliance_graph/src/graph_mapping_agent/`)
  use a fixture, rule-based stand-in (`model_version="fixture-rule-based-v1"`),
  not a live LLM — no live LLM calls run in this pass (see `research.md` §7).

See `specs/001-clause-parser-compliance-graph/plan.md`'s Complexity Tracking
table for the full history of every gap found and how each was resolved.
