# Feature Specification: Visual Proof-Path Viewer

**Feature Branch**: `002-visual-proof-path-viewer`

**Created**: 2026-09-03

**Status**: Draft

**Input**: User description: "Visual proof-path viewer for RabbitQA. The root normative spec (rabbitqa_spec_v1.1.0.md) already covers this feature at spec_version 1.2.0, in new sections §4.5 (Proof-Path Visualization renderer) and §5.11 (GET /v1/graph/snapshots/{snapshot_id}/proof-path-view endpoint), plus a new §7 trust-zone row ("Visualization rendering") and a new §1.2 non-goal (no interactivity in v1)."

**Spec authority note**: This document is derived from, and MUST remain consistent with, `rabbitqa_spec_v1.1.0.md` §4.5, §5.11, §7 ("Visualization rendering"), and §1.2 (spec_version 1.2.0) — per this project's `CLAUDE.md` spec authority hierarchy, the root spec is the source of truth; this file exists to drive `/speckit-plan` and `/speckit-tasks`, not to introduce requirements the root spec doesn't already state. Any apparent conflict between this file and the root spec resolves in the root spec's favor.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reviewer inspects an obligation's compliance chain visually (Priority: P1)

A compliance reviewer or auditor already knows the `clause_id` of an obligation they care about (e.g. from the review workspace, an export, or an audit finding) and the `snapshot_id` of the published graph snapshot it was published into. They want to see, at a glance, the full chain connecting that obligation's source legal text to the control, asset, and evidence that satisfy it — without querying the graph API directly or reading raw JSON.

**Why this priority**: This is the entire feature — a single-purpose visual aid for one already-published obligation's proof path. There is no viable smaller slice.

**Independent Test**: Can be fully tested by publishing a snapshot containing one obligation with a complete proof-path (obligation → control → asset → evidence → test asset), requesting the viewer with that obligation's `clause_id` and the snapshot's `snapshot_id`, and confirming the returned page renders one diagram showing all five nodes connected by correctly labeled edges, with the obligation's exact source text displayed alongside.

**Acceptance Scenarios**:

1. **Given** a published, approved snapshot containing an accepted obligation with a complete proof-path, **When** the reviewer requests the viewer for that obligation's `clause_id` and the snapshot's `snapshot_id`, **Then** the page renders a diagram with one labeled box per node in the chain, each connecting edge labeled with its relationship name, and the obligation's exact verbatim source text shown alongside the diagram.
2. **Given** the same published snapshot, **When** the reviewer requests the viewer twice for the same `clause_id`/`snapshot_id`, **Then** both responses are identical (the rendering is deterministic — no randomness, no timestamps embedded in the diagram itself).
3. **Given** a snapshot that has not yet been published (still in `draft`, `validated`, or `approved`-but-not-published status), **When** the reviewer requests the viewer for a `clause_id` within it, **Then** the request is refused as not found — no partial or draft diagram is ever rendered.
4. **Given** a published snapshot, **When** the reviewer requests the viewer for a `clause_id` whose obligation was reviewed but not accepted (e.g. rejected or escalated), **Then** the request is refused as not found — only accepted obligations are ever rendered.
5. **Given** a published snapshot and a valid `clause_id` within it that has no complete proof-path (e.g. mapped to a control but no evidence chain exists yet), **When** the reviewer requests the viewer, **Then** the request is refused as not found — the viewer never renders a partial chain.
6. **Given** an obligation whose source text contains characters with special meaning in the output format (e.g. `<`, `&`, quotation marks), **When** the reviewer requests the viewer, **Then** those characters are displayed correctly as plain text and never interpreted as part of the diagram's own markup.

### Edge Cases

- What happens when the requested `clause_id` doesn't exist at all, anywhere, in any snapshot? → Same "not found" outcome as any other unresolvable reference in this system — no distinction is surfaced between "wrong clause_id" and "clause_id exists but isn't in this snapshot's proof-path results," since neither case has a diagram to show.
- What happens when the requested `snapshot_id` doesn't exist at all? → Same "not found" outcome as requesting any other operation against a nonexistent snapshot.
- What happens when the `clause_id` query parameter is omitted entirely? → The request is rejected as malformed before any lookup is attempted.
- What happens if an obligation's source text is unusually long? → The full verbatim text is always shown in full — this feature never truncates or summarizes source-backed legal text, since doing so would misrepresent the source (consistent with this system's content-fidelity principle elsewhere).
- What happens if a viewer tries to interact with the diagram (click a node, zoom, drag)? → Nothing happens; the output has no interactive behavior by design (see Assumptions).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a way to request a visual rendering of one obligation's proof-path chain, identified by a `clause_id` and the `snapshot_id` of the published snapshot it belongs to.
- **FR-002**: The rendered output MUST show every node in the obligation's proof-path chain (the source provision, the obligation itself, the control it maps to, the asset the control affects, the evidence requirement that satisfies the control, and the test asset that evidences it) as a distinct, labeled visual element, each labeled with its type and a short identifier.
- **FR-003**: The rendered output MUST show each connection between consecutive nodes labeled with the name of the relationship it represents (the same relationship names used elsewhere in this system's compliance ontology).
- **FR-004**: The rendered output MUST display the obligation's exact source (verbatim) text alongside the diagram, unaltered in meaning.
- **FR-005**: System MUST source all rendered data exclusively from the results of this system's existing proof-path query logic — this feature MUST NOT introduce or duplicate any independent graph-traversal logic of its own.
- **FR-006**: System MUST only render data belonging to a snapshot that has already been fully published — a snapshot still in draft, validated, or approved-but-unpublished status MUST be treated as not found, never rendered even partially.
- **FR-007**: System MUST only render an obligation whose review outcome was acceptance — an obligation that was rejected, escalated, or otherwise not accepted MUST be treated as not found.
- **FR-008**: System MUST only render a complete proof-path chain — if the requested obligation exists in the published snapshot but its chain is incomplete (e.g. not yet mapped through to evidence), the request MUST be treated as not found rather than rendering a partial diagram.
- **FR-009**: System MUST reject a request that omits the required `clause_id` identifier before attempting any lookup.
- **FR-010**: The rendered output MUST contain no interactive behavior — no scripted behavior, no click/drag/zoom handling, and no references to external resources. The output is static, self-contained, read-only visual content.
- **FR-011**: Every value drawn from the source document or from user/system-supplied identifiers and displayed inside the diagram (node labels, the verbatim source text, the clause identifier) MUST be rendered as inert, literal display text — never interpretable as diagram markup or executable content — regardless of what characters that value contains.
- **FR-012**: Rendering MUST be fully deterministic: requesting the same obligation from the same published snapshot twice MUST produce identical output both times.
- **FR-013**: A request for a nonexistent identifier (unknown `snapshot_id`, or a `clause_id` not present in that snapshot's results) MUST be treated as not found, consistently with how this system already treats other not-found references.

### Key Entities *(include if feature involves data)*

- **Proof-path chain**: The ordered sequence of compliance-ontology nodes (provision, obligation, control, asset, evidence requirement, test asset) and the named relationships connecting them, that together demonstrate how one obligation is satisfied. Already exists as this system's existing proof-path query result — this feature only renders it, it does not define or compute it.
- **Rendered view**: The visual (diagram + source text) representation of one proof-path chain, for one obligation, as it existed in one published snapshot at request time. Not a stored artifact — generated fresh from query results on each request.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reviewer who already knows an obligation's `clause_id` and its snapshot's `snapshot_id` can view its complete compliance chain — from source obligation through to evidence — without querying the graph API or reading raw JSON results themselves.
- **SC-002**: 100% of rendered diagrams for a complete, published, accepted proof-path show every node in the chain and every connecting relationship, with no missing or mislabeled elements.
- **SC-003**: 0% of requests for unpublished, non-accepted, or incomplete-chain obligations return any diagram content — such requests are indistinguishable, from the caller's perspective, from a request for a genuinely nonexistent obligation.
- **SC-004**: 100% of source-document-derived content shown in a rendered view displays as literal, correctly-read text, with 0% of it ever altering the structure of the surrounding output, regardless of what characters that source content contains.
- **SC-005**: Requesting the same obligation from the same published snapshot repeatedly always produces byte-identical output.

## Assumptions

- This is a read-only inspection aid for humans (reviewers/auditors), not a data-entry or editing surface — no functional requirement here implies any write capability.
- v1 is intentionally non-interactive: no pan/zoom/click-through, no diagram-editing capability, and no client-side scripting framework. This matches `rabbitqa_spec_v1.1.0.md` §1.2's explicit non-goal for this feature; a future, richer viewer would be a separate, later feature with its own spec addition.
- The caller already knows or can obtain the target obligation's `clause_id` and its snapshot's `snapshot_id` through existing means (the review workspace, an export, direct API knowledge) — this feature does not add a new discovery/search mechanism for finding either.
- This feature covers exactly one canonical proof-path shape (provision → obligation → control → asset → evidence → test asset, per this system's existing ontology). It is not a general-purpose graph visualizer for arbitrary query results or arbitrary node/relationship combinations.
- "Not found" is the uniform outcome for every case where a complete, published, accepted chain isn't available to show (unknown identifiers, unpublished snapshots, non-accepted obligations, incomplete chains) — the feature does not attempt to give the caller a more specific reason in these cases, consistent with how this system already treats querying anything not fully published elsewhere.
