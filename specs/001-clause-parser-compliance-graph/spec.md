# Feature Specification: Clause Parser & Compliance Knowledge Graph

**Feature Branch**: `001-clause-parser-compliance-graph`

**Created**: 2026-09-01

**Status**: Draft

**Input**: User description: "Build the RabbitQA Clause Parser and Compliance Knowledge Graph standalone module pair, exactly as defined in rabbitqa_spec_v1.0.0.md in this repo. Read that file first and treat it as the normative source of truth: implement the CanonicalDocument, ObligationObject, ValidationReport, GraphChangeSet, and GraphSnapshotExport data contracts (section 2), the ontology (section 3), the clause parser processing sequence (section 4.1), the compliance graph module (section 4.3), the agent I/O contracts (section 4.4), the API endpoints (section 5), and the acceptance criteria (section 9) precisely as specified. Do not invent behavior not covered in the spec — flag gaps instead of guessing."

**Normative source**: `rabbitqa_spec_v1.0.0.md` (spec_version 1.0.3 as of this revision — see that document's own §0 Document Control table and §12 Changelog for the current authoritative version; this citation is not re-updated on every patch, so always defer to the root spec itself). Where this document and that spec appear to disagree, the technical spec wins; this document restates its intent for planning purposes and does not override it.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ingest and parse a pinned regulation into reviewable obligations (Priority: P1)

A compliance analyst registers one pinned version of a regulatory source (NIS2, CRA, or DORA) and runs it through parsing so that every legally binding clause becomes a discrete, source-traceable candidate obligation ready for human review.

**Why this priority**: Without ingestion and parsing there is nothing to review, map, or query — this is the foundation the rest of the system depends on.

**Independent Test**: Register a source document, trigger a parse job, and confirm every resulting obligation proposal carries verbatim evidence text that is an exact substring of the registered document at the stated offsets, with a validation outcome attached.

**Acceptance Scenarios**:

1. **Given** a source artifact and its declared instrument/source version, **When** it is registered twice with byte-identical content, **Then** both registrations resolve to the same document identity and the second attempt is reported as already-existing rather than a new record.
2. **Given** a registered document, **When** a parse job completes, **Then** every resulting obligation proposal's evidence text matches its recorded hash and is an exact substring of the canonical document at the stated character offsets.
3. **Given** a proposal whose evidence text does not actually appear in the source document, **When** it is validated, **Then** the validation fails and the record is automatically escalated rather than being offered to a reviewer as ordinary pending work.

---

### User Story 2 - Review and decide on extracted obligations (Priority: P1)

A compliance reviewer examines each candidate obligation alongside its source text and validation findings, then accepts, edits, rejects, or escalates it — with every decision recorded and justified.

**Why this priority**: No obligation may become authoritative without a recorded human decision; this is the mandatory gate between machine extraction and anything downstream (graph mapping, export) trusting the data.

**Independent Test**: Take a pending obligation proposal, submit each of the four possible reviewer decisions in separate cases, and confirm the resulting record's status and decision history match expectations, including rejection of decisions that lack justification or that break evidence integrity.

**Acceptance Scenarios**:

1. **Given** a reviewer submits an accept decision with a rationale, **When** the decision is persisted, **Then** the obligation's status becomes accepted and a new history entry recording who decided, when, and why is attached in the same operation.
2. **Given** a reviewer submits a decision with an empty rationale, **When** it is submitted, **Then** the decision is rejected and no record state changes.
3. **Given** a reviewer edits a field in a way that breaks the link between the evidence text and its source offsets, **When** the edit is submitted, **Then** the system rejects the edit and no persisted state changes — the edit is not silently accepted.
4. **Given** an obligation with a full decision history, **When** a reviewer opens it, **Then** they can see every past reviewer, timestamp, decision, and rationale for that obligation, and for prior versions of the source article if it was superseded.

---

### User Story 3 - Map approved obligations into the compliance knowledge graph (Priority: P2)

A compliance analyst or automated proposal process turns a batch of accepted/edited obligations into a proposed set of graph nodes and relationships (obligations, actors, controls, assets, evidence), which is checked against the ontology's structural rules before anyone can approve it.

**Why this priority**: The knowledge graph is the queryable, audit-ready product of this system; it depends on reviewed obligations existing first (Story 1–2) but is the primary value delivered to downstream consumers.

**Independent Test**: Supply one or more accepted obligations, generate a proposed change set, and confirm that a change set violating a structural rule (e.g., a relationship type/pair not defined in the ontology, or a missing required link) is automatically marked invalid and cannot proceed to approval, while a valid one can be validated and approved.

**Acceptance Scenarios**:

1. **Given** a proposed change set containing a relationship type/pair not defined in the ontology, **When** it is validated, **Then** the validation reports a failure and the change set's status is forced to rejected — it cannot be approved.
2. **Given** an obligation node in a proposal, **When** validated, **Then** the validation confirms it has exactly one derivation link back to its source provision and at least one link to an actor it is imposed on, failing otherwise.
3. **Given** a change set that passes validation, **When** a reviewer approves it, **Then** it becomes eligible for publishing.

---

### User Story 4 - Publish a graph snapshot and query proof paths (Priority: P2)

An analyst publishes an approved change set as a new, immutable graph snapshot, then runs a proof-path query to demonstrate — with source-backed evidence — that a given obligation traces through to a control, an affected asset, and supporting evidence.

**Why this priority**: Publishing and querying is how the system proves compliance claims are traceable end-to-end; it is the ultimate demonstration of value but requires Stories 1–3 to have produced approved graph content first.

**Independent Test**: Publish a validated, approved change set, confirm a new snapshot is created and the prior snapshot remains retrievable in its lineage, then run the reference proof-path query and confirm every result carries the clause identifier, verbatim source text, review status, and originating snapshot identifier.

**Acceptance Scenarios**:

1. **Given** an approved change set whose base snapshot no longer matches the graph's current published state, **When** publish is attempted, **Then** it is rejected as a conflict and the graph is left unchanged.
2. **Given** a successful publish, **When** the new snapshot is queried afterward, **Then** it is retrievable, and the snapshot it replaced remains retrievable via its lineage link.
3. **Given** a proof-path query against a published snapshot, **When** results are returned, **Then** every result includes the clause identifier, the verbatim source text, the review status, and the snapshot identifier it came from.
4. **Given** a query is issued against a snapshot that is not yet fully published, **When** it is queried, **Then** the system reports it as not found rather than returning partial or draft data.

---

### User Story 5 - Export a read-only, audit-ready snapshot (Priority: P3)

An external stakeholder or downstream system requests a read-only export of a published graph snapshot, containing only obligations that passed human review, each traceable back to its source evidence.

**Why this priority**: Export is the hand-off point to consumers outside this system's trust boundary; it depends on a published, queryable snapshot already existing (Story 4) and is lower priority than the internal review/publish loop because it adds no new compliance content, only exposes it.

**Independent Test**: Request an export of a published snapshot containing a mix of accepted, edited, and non-reviewed obligations, and confirm the exported payload includes only the accepted/edited ones and validates against the export contract.

**Acceptance Scenarios**:

1. **Given** a published snapshot containing an obligation whose review status is not accepted or edited, **When** the snapshot is exported, **Then** that obligation is silently excluded from the export payload rather than causing a failure or being included anyway.
2. **Given** any export request, **When** the export is produced, **Then** it conforms to the export contract before being returned to the requester.
3. **Given** an exported obligation, **When** its provenance is traced, **Then** every link in the chain — from source checksum through parse run, validation, reviewer decision, change set, and snapshot — can be resolved; if any link cannot be resolved, that obligation must not appear in the export at all.

---

### Edge Cases

- What happens when the same source document is registered under two different declared source versions? (Treated as distinct pinned versions — each gets its own identity; this is not a duplicate.)
- What happens when different content is registered under an instrument/source_version combination that's already registered with different content? (Rejected as a conflict — a pinned source_version is immutable once registered; revised content requires registering under a new source_version. Added in `rabbitqa_spec_v1.0.0.md` spec_version 1.0.2, §12 changelog.)
- How does the system handle a parse job for a document that contains no detectable normative passages? (Job completes with zero proposals rather than failing.)
- What happens when a reviewer attempts to accept a record without ever having viewed its validation findings in the same session? (The UI must prevent this, but the system independently re-validates on submission regardless of what was shown, so a bypassed UI check cannot result in an unvalidated acceptance.)
- How does the system handle a graph change-set proposal that references a node not present in either the proposal itself or the already-published graph? (Treated as a validation failure — the relationship is not created.)
- What happens if a publish operation fails partway through (e.g., a subset of nodes written, then an error)? (No partial state is retained — the operation either fully applies as one unit or leaves the graph exactly as it was.)
- What happens when an export is requested for a snapshot that has obligations with completely resolvable provenance mixed with ones that have a broken provenance link? (Only the fully-traceable obligations appear in the export; the others are excluded, not flagged as an error that blocks the whole export.)
- How are non-English source documents handled in this version? (The data model reserves space for other languages, but only English-language sources are supported by the actual parsing pipeline in this version.)

## Requirements *(mandatory)*

### Functional Requirements

**Ingestion**
- **FR-001**: System MUST allow registration of exactly one pinned source artifact per (instrument, source version) combination, computing a content checksum before any further processing touches it.
- **FR-002**: System MUST treat registration as idempotent by content: re-registering byte-identical content for an already-registered (instrument, source version) MUST return the existing record rather than creating a duplicate. Registering different content under an (instrument, source version) that is already registered with different content MUST be rejected as a conflict, since a pinned source_version is immutable once registered — revised content requires a new source_version.
- **FR-003**: System MUST preserve the untouched source artifact as immutable, write-once storage, separate from the canonicalized text used for parsing.
- **FR-004**: System MUST canonicalize source text (whitespace/encoding normalization only) without altering legal text content, and MUST record a structural map (articles, paragraphs, annexes, tables, footnotes, recitals) with stable, reproducible identifiers.
- **FR-005**: Structural identifiers MUST be derived purely from document identity and structural position — never from model output, run timestamp, or randomness — so re-ingesting identical source content always yields identical identifiers.

**Parsing**
- **FR-006**: System MUST run parsing as a fixed, ordered sequence — canonicalize, detect normative passages, decompose into atomic candidate obligations, extract structured fields, resolve references, then validate — with no step skipped or reordered.
- **FR-007**: System MUST run normative-passage detection through a deterministic baseline pass first (logged separately from any optional AI-assisted refinement layered on top).
- **FR-008**: System MUST retain the link between an atomic candidate obligation and any shared conditions/exceptions it was decomposed from.
- **FR-009**: Every extracted obligation candidate MUST carry verbatim source evidence text, its character offsets in the canonical document, and a content hash of that evidence text.
- **FR-010**: System MUST record, for every extracted candidate, whether decomposition/extraction/reference-resolution used a deterministic method or an AI-assisted one, and which model/prompt version if applicable.
- **FR-011**: Final validation of a candidate obligation MUST be performed entirely through deterministic checks with no AI involvement in that step.
- **FR-012**: System MUST run, as part of validation, at minimum: schema conformance, controlled-vocabulary conformance, evidence-span fidelity (evidence text truly appears at its stated offsets, and its hash matches), date/quantity normalization correctness, reference validity, and cross-field consistency.
- **FR-013**: A validation failure on evidence-span fidelity or schema conformance MUST force the overall validation outcome to fail and MUST automatically route the record to an escalated state rather than presenting it to a reviewer as ordinary pending work. Any other single check failure MUST route the record to a "needs review" state, still presentable but visibly flagged.

**Review**
- **FR-014**: System MUST require a recorded human decision — accept, edit, reject, or escalate — with a non-empty justification, before an obligation can be treated as accepted or edited; there MUST be no path to an accepted/edited status without this record being created in the same operation.
- **FR-015**: System MUST reject any reviewer decision submitted with an empty or missing justification.
- **FR-016**: An edit decision MUST re-run full validation on the edited content before persisting; if the edited version fails evidence-span fidelity, the edit MUST be rejected and no state may change.
- **FR-017**: System MUST preserve the complete decision history (reviewer, timestamp, decision, rationale, and what changed) for every obligation, including history from prior versions of the source article when it has since been superseded.
- **FR-018**: System MUST independently re-validate an obligation at the moment of decision submission, regardless of whether validation findings were shown to the reviewer beforehand.

**Graph mapping**
- **FR-019**: System MUST allow generating a proposed set of graph nodes and relationships from one or more accepted/edited obligations, without ever writing directly to the authoritative graph as part of generating the proposal.
- **FR-020**: System MUST validate every proposed change set against the fixed ontology rules (allowed node types and their required properties; allowed relationship types and their allowed endpoint types; required links, e.g. every obligation must derive from exactly one provision and impose on at least one actor) with no exemption for any change set regardless of its size.
- **FR-021**: A proposed change set with any structural validation failure MUST have its status forced to rejected and MUST NOT be eligible for approval.
- **FR-022**: System MUST reject any relationship proposal that references a node not present either in the same proposal or already published in the graph it is based on.
- **FR-023**: System MUST require an explicit reviewer approval step before a validated change set can be published; entity matches above a confidence threshold MUST NOT be auto-merged into the graph without a recorded reviewer decision.

**Publishing & query**
- **FR-024**: Publishing a change set MUST apply as a single all-or-nothing operation — on any failure partway through, all changes MUST be rolled back, leaving no partial state.
- **FR-025**: Publishing MUST only succeed if the change set's approval status holds, its most recent validation shows zero failures, and its declared base snapshot still matches the graph's current published state; if the graph has moved on since validation, publishing MUST be refused and the graph left unchanged.
- **FR-026**: Every successful publish MUST create a new, independently retrievable snapshot, and the snapshot it replaces MUST remain retrievable through a lineage reference.
- **FR-027**: System MUST support a proof-path query pattern that traces an obligation through its regulation, mapped control, affected asset, required evidence, and supporting test/evidence asset, returning for every result the clause identifier, the verbatim source text, the review status, and the originating snapshot identifier.
- **FR-028**: Querying a snapshot that is not fully published MUST return a not-found result rather than partial or draft data.

**Export**
- **FR-029**: An export of a graph snapshot MUST include only obligations whose review status is accepted or edited; any other obligation MUST be silently excluded from the export payload rather than causing a failed export or being included regardless.
- **FR-030**: Every exported record MUST have its full provenance chain resolvable — from source checksum, through parse run, validation outcome, reviewer decision, change set, and snapshot; if any link cannot be resolved, that record MUST be excluded from the export entirely rather than exported with a gap.
- **FR-031**: Every export payload MUST conform to the export data contract before being returned to the requester.

**Security & trust boundaries**
- **FR-032**: System MUST treat all source document text passed to any AI-assisted step as untrusted data, kept clearly separated from system instructions, which MUST never be built from or combined with document content.
- **FR-033**: AI-assisted steps MUST NOT be granted the ability to write to the database or graph, execute shell commands, or make unrestricted network calls; any tool access granted MUST be limited to read-only lookups against the pinned document and controlled vocabulary.
- **FR-034**: System MUST reject document uploads exceeding a configured size limit and MUST validate uploaded content type against an allow-list before persisting it.
- **FR-035**: System MUST log, for every AI-assisted step invocation, the model and prompt identifiers used along with hashes of its input and output, sufficient to reconstruct what was asked and returned.
- **FR-036**: Audit/decision-history records MUST be append-only — no capability to update or delete a past entry may exist.

### Key Entities

- **CanonicalDocument**: One pinned, registered version of a regulatory source (instrument, source version, checksum, language, jurisdiction) plus its structural map of articles/paragraphs/annexes/tables/footnotes/recitals, each with a stable identifier and character-offset span into the canonical text.
- **ObligationObject** (and its unreviewed proposal form): A single atomic legal requirement extracted from the source, comprising: an identity (which document/version/clause it belongs to), source evidence (verbatim text, offsets, hash), legal semantics (type of norm, who it applies to, the required action/object, scope, trigger, deadline, frequency, conditions, exceptions), references to related provisions/definitions, and governance metadata (confidence, flags, review status, and full decision history).
- **ValidationReport**: The deterministic outcome of running the fixed set of checks against a proposal, listing each check's name/status/message and an overall pass/fail/needs-review outcome.
- **GraphChangeSet**: A proposed batch of graph nodes and relationships derived from one or more accepted obligations, together with the ontology version it was checked against, its structural validation outcome, and its lifecycle status (draft/validated/approved/rejected/published).
- **Graph Snapshot**: An immutable, published version of the compliance graph, with a lineage reference to the snapshot it superseded.
- **GraphSnapshotExport**: A read-only, schema-conformant external representation of a published snapshot's fully-reviewed obligations and their mapped controls/assets/evidence.
- **Ontology node/relationship types**: The fixed vocabulary of graph entity types (Regulation, Provision, Definition, Obligation, Actor, Action, Condition, Exception, Deadline, Control, Risk, EvidenceRequirement, Asset, System, API, Dataset, TestAsset) and the fixed, exhaustive set of allowed relationships between them.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A single, reproducible run demonstrates the entire path — from registering a pinned source document to a schema-valid export of a published graph snapshot — without any manual data patching.
- **SC-002**: Re-registering byte-identical source content always resolves to the same document identity, and re-parsing identical source content always produces identical structural and evidence identifiers, 100% of the time.
- **SC-003**: 100% of obligations with an accepted or edited review status have verbatim evidence text that is an exact, hash-verified substring of their source document.
- **SC-004**: On the locked evaluation corpus, normative-clause detection reaches at least 90% precision and 93% recall.
- **SC-005**: On the locked evaluation corpus, extraction quality for core fields (who/what/object) reaches at least 90% F1, and for complex fields (conditions/deadlines/exceptions/references) at least 85% F1.
- **SC-006**: On accepted graph content, at least 85% macro F1 is achieved for graph node/relationship mapping quality, and 100% of accepted snapshots show full provenance and structural-constraint compliance.
- **SC-007**: At least 90% of reference proof-path queries return accurate, fully source-backed results (verbatim text, review status, snapshot identifier present).
- **SC-008**: At least 99% of end-to-end parser-to-graph transactions complete successfully without manual intervention.
- **SC-009**: 100% of graph snapshot exports validate against the export data contract before being returned.
- **SC-010**: No obligation ever reaches an accepted or edited state without a non-empty, attributable, timestamped reviewer justification on record.

## Assumptions

- The evaluation corpus (§9.3 of the technical spec) will be assembled separately and is treated as an external input to this feature, not something this feature builds.
- "Standard web/mobile app" defaults do not apply here; all data-handling and validation behaviors follow the technical spec's explicit rules rather than generic conventions, since the technical spec is the normative authority for this feature.
- Reviewer identity/authentication mechanics (how a reviewer logs in) are assumed to reuse whatever authentication approach the surrounding RabbitQA product already uses; this feature only requires that a reviewer identity be attached to every decision, not how that identity is established.
- Only one regulatory instrument's pinned version is processed at a time; cross-instrument correlation is explicitly out of scope for this feature (confirmed non-goal in the technical spec).
- Non-English source language support is limited to the data model reserving a field for it; the parsing pipeline itself is validated only against English-language sources.
- No automatic legal interpretation or auto-publication path exists anywhere in this feature; every state transition that matters (obligation acceptance, change-set approval, snapshot publish) requires an explicit recorded human decision.

## Resolved Clarifications

The technical spec (`rabbitqa_spec_v1.0.0.md`, §10) marked the following as blocking open questions. They have been resolved for this feature:

- **Graph storage/query technology**: Neo4j (Cypher-style property-graph traversal), matching the technical spec's §3.3 reference proof-path query as written — no restatement of that query needed.
- **Evaluation corpus scope**: A bounded, representative subset of NIS2/CRA/DORA articles (not the full instrument), including hard negatives, nested conditions, annex tables, long cross-references, and at least one amendment scenario per §9.3, rather than the entire regulation text.
- **Four-eyes review for edits**: Single-reviewer decisions are sufficient — an "edit" action does not require a second confirming reviewer before the record becomes authoritative.
