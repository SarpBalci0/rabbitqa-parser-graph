# Phase 0 Research: Visual Proof-Path Viewer

No `NEEDS CLARIFICATION` markers remained in the Technical Context — the root spec (`rabbitqa_spec_v1.1.0.md` §4.5, §5.11, §7, §1.2, spec_version 1.2.0) already made every technical decision this feature needs. This document records those decisions and their rationale for traceability, rather than resolving open unknowns.

## Decision: SVG generation approach

**Decision**: Hand-built SVG via plain Python string templates (f-strings/`.format()`-free string building with an explicit escaping step for every untrusted value), not a diagramming library.

**Rationale**: The diagram is always the same fixed 6-node, 5-edge shape (§3.3's canonical proof-path) rendered as simple boxes and lines — there's no variable layout complexity that would justify a layout engine. Root spec §4.5 requires full determinism (byte-identical output for identical input) and §7 requires that output be inert by construction (no `<script>`/`<foreignObject>`/event handlers/executable URIs) rather than filtered after the fact from an otherwise-general-purpose SVG surface. A minimal, auditable template with one explicit escaping call site per interpolated value is the most direct way to satisfy both — consistent with this codebase's existing precedent of intentionally simple, explicit deterministic modules (e.g. `clause_parser/src/canonicalize/pdf_extractor.py`, `clause_parser/src/agents/extraction_agent.py`).

**Alternatives considered**:
- A Python diagramming/graphing library (e.g. graphviz bindings) — rejected: adds an external binary dependency (Graphviz itself) for a fixed 6-node shape that doesn't need general graph layout, and makes the "no script, no foreignObject, output inert by construction" guarantee harder to audit (the library's own SVG output would need review, not just this codebase's escaping call sites).
- A general HTML templating engine (e.g. Jinja2) — rejected: not already a project dependency, and autoescaping defaults are HTML-context, not SVG-context; a purpose-built escaping helper for the exact contexts used here (SVG `<text>` content, HTML body text) is simpler to reason about and test than configuring a general templating engine's escaping modes correctly for two different embedded contexts.

## Decision: Escaping mechanism

**Decision**: Python's stdlib `xml.sax.saxutils.escape` (escapes `&`, `<`, `>`; extended with an explicit mapping for `"` and `'` since those matter inside quoted SVG attribute values, not just element text) as the single, dedicated escaping function all untrusted values pass through immediately before interpolation into the SVG/HTML template.

**Rationale**: Root spec §7 requires "a library or function whose only job is context-correct escaping — never manual string replacement." `xml.sax.saxutils.escape` is stdlib (no new dependency), is exactly that single-purpose function, and SVG is XML — so an XML-correct escaper is the correct tool for the SVG `<text>` element content this feature emits. The surrounding minimal HTML page body text uses the same escaper, since HTML's escaping requirements for plain text content are a subset of XML's (over-escaping in HTML text is harmless; under-escaping is the actual injection risk this must prevent).

**Alternatives considered**:
- `html.escape` (stdlib) — considered for the HTML page shell; not used for the SVG portion since it doesn't guarantee XML well-formedness the same way, and using one escaping function for both contexts (rather than two, applied inconsistently) is simpler to audit for "every untrusted value went through escaping."
- Manual `.replace()` chains — explicitly rejected by root spec §7 itself ("never manual string replacement").

## Decision: Edge-label derivation

**Decision**: A fixed, hardcoded lookup keyed by **node type**, not by array position, since §3.3's canonical shape is a tree, not a line: `Control` has two outgoing edges, not one. The `path` array's six entries are always, in order, `[Provision, Obligation, Control, Asset, EvidenceRequirement, TestAsset]`, but the five rendered edges are:

- `Provision -> Obligation`: `DERIVED_FROM`
- `Obligation -> Control`: `MAPS_TO_CONTROL`
- `Control -> Asset`: `AFFECTS_ASSET`
- `Control -> EvidenceRequirement`: `SATISFIED_BY` (branches from `Control` again — **not** from `Asset`)
- `EvidenceRequirement -> TestAsset`: `EVIDENCED_BY`

Note the `Control` node is the source of *two* edges (`AFFECTS_ASSET` and `SATISFIED_BY`); `Asset` is a dead end with no outgoing edge. This must NOT be implemented as "connect array index *i* to index *i+1*" — that naive positional-adjacency reading would draw a nonexistent `Asset -> EvidenceRequirement` edge (mislabeled `SATISFIED_BY`) and never draw `Control`'s real second edge. The renderer must locate the `Control`, `Asset`, and `EvidenceRequirement` entries by type and wire the fixed edge list above directly to them, then lay the diagram out to show the branch (e.g. `Control` with two lines fanning out to `Asset` and to `EvidenceRequirement`), not as a single row of six boxes.

**Rationale**: Root spec §3.3's own Cypher pattern makes the branch explicit — the second clause restarts at `c` (`Control`), not at `a` (`Asset`): `` (provision:Provision)<-[:DERIVED_FROM]-(o:Obligation)-[:MAPS_TO_CONTROL]->(c:Control)-[:AFFECTS_ASSET]->(a:Asset)`` then, separately, ``c-[:SATISFIED_BY]->(e:EvidenceRequirement)-[:EVIDENCED_BY]->(t:TestAsset)``. §3.2's relationship table confirms `SATISFIED_BY` is `Control -> EvidenceRequirement` only (no `Asset -> EvidenceRequirement` pair is permitted anywhere in §3.2). §4.5's own edge-rendering rule states the same branch with a semicolon separating the two chains from `Control`. A type-keyed lookup is therefore both correct and still the simplest implementation that matches the one fixed canonical shape — no relationship-type inference logic is needed or would be justified.

**Alternatives considered**: Positional (index-adjacent) lookup over the flat `path` array — rejected: an earlier draft of this decision used this approach and it silently mislabels the `Asset`/`EvidenceRequirement` boundary, producing a diagram that asserts a relationship §3.2 does not define. Any approach that infers or guesses edge types from data, or that generalizes beyond the one canonical shape in v1, remains out of scope per root spec §4.5.

## Decision: Not-found semantics (single 404 pathway)

**Decision**: A single `_ProofPathNotFoundError`-style internal signal covering all "nothing complete/published/accepted to show" cases (unknown `snapshot_id`, unpublished snapshot, `clause_id` absent from that snapshot's proof-path results, non-`accepted` review status), mapped uniformly to one `404` JSON-error response shape.

**Rationale**: Root spec §5.11 states two `404` cases explicitly and ties both to the same "404, not partial data" principle already established by §5.9. The feature spec's FR-013 and Assumptions section confirm the caller-facing outcome is deliberately undifferentiated across these cases. Reusing `run_proof_path_query`'s existing behavior (which already returns `404`-worthy "not found" for an unpublished/nonexistent snapshot per §5.9) and adding one additional filter-and-check step (does the result set contain this `clause_id`?) is the minimal correct implementation — no new query-layer error taxonomy is needed.

**Alternatives considered**: Distinguishing sub-cases with different error codes (e.g. `SNAPSHOT_NOT_PUBLISHED` vs `CLAUSE_NOT_IN_SNAPSHOT` vs `OBLIGATION_NOT_ACCEPTED`) — rejected: the root spec and derived feature spec both explicitly call for uniform "not found," and inventing a finer-grained error taxonomy would be introducing a requirement the root spec doesn't state (out of bounds per this project's spec authority hierarchy).
