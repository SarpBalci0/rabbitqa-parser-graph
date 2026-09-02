# Data Model: Clause Parser & Compliance Knowledge Graph

Source of truth: `rabbitqa_spec_v1.0.0.md` §2 (Data Contracts) and §3 (Ontology). This document restates entities and relationships for implementation planning; the literal JSON Schemas live at `shared_contracts/schemas/*.json` and are authoritative over this summary.

## 1. CanonicalDocument

One pinned, registered version of a regulatory source.

| Field | Type | Notes |
|---|---|---|
| `document_id` | string, pattern `^doc_[a-z0-9]{12}$` | Required |
| `source_version` | string | Pinned identifier (OJ reference / publication date). Required |
| `instrument` | enum: NIS2, CRA, DORA | Required |
| `checksum_sha256` | string, 64 hex chars | Required, computed before parsing touches content |
| `language` | string, pattern `^[a-z]{2}(-[A-Z]{2})?$` | Required; v1 pipeline validated only for `en` |
| `jurisdiction` | const "EU" | Required |
| `structure` | array of `anchor_node` | Required |
| `raw_storage_uri` | string | Optional field; write-once storage pointer |
| `created_at` | date-time string | Required |
| `schema_version` | const "1.0.0" | Required |

**anchor_node** (nested):
| Field | Type | Notes |
|---|---|---|
| `anchor_id` | string | `{document_id}:{source_version}:{structural_path}`, pure function — no model/timestamp/random input |
| `type` | enum: article, paragraph, annex, table, footnote, recital | Required |
| `label` | string | e.g. "Article 21(2)(b)" |
| `char_start` / `char_end` | integer ≥ 0 | Offsets into canonicalized text |
| `parent_anchor_id` | string or null | |

**Invariants**: anchor_id generation is pure/deterministic and idempotent across identical re-ingestion; char offsets are into canonicalized text (formatting-only normalization, never content-altering); `raw_storage_uri` content is write-once (rewrite to existing key fails).

## 2. ObligationObject (and its unreviewed `ObligationObjectProposal` form)

Central entity — one atomic extracted legal requirement.

### 2.1 `identity`
`document_id`, `source_version`, `language`, `jurisdiction` (const "EU"), `instrument` (enum), `clause_id` (pattern `^[^:]+:[^:]+:.+$` — structural shape only; semantically MUST be derived from identity + structural anchor, never from model output, enforced as a cross-field code invariant since JSON Schema can't express it; corrected from the root spec's originally-unmatchable literal pattern, see `rabbitqa_spec_v1.0.0.md` §12 changelog v1.0.1), `schema_version` (const "1.0.0"). All required.

### 2.2 `source_evidence`
`anchor_id`, `char_start`, `char_end`, `verbatim_text` (exact substring of the CanonicalDocument at [char_start, char_end)), `evidence_hash` (sha256 of verbatim_text). All required.

### 2.3 `legal_semantics`
| Field | Type |
|---|---|
| `norm_type` | enum: obligation, prohibition, permission, definition_only |
| `actor` | array of string, min 1 |
| `modality` | enum: shall, must, may, should |
| `action` | string |
| `object` | string |
| `scope` | string |
| `trigger` | string or null |
| `deadline` | object or null: `{type: absolute_date\|relative_period\|recurring, value, normalized_iso}` |
| `frequency` | string or null |
| `conditions` | array of string |
| `exceptions` | array of string |

Required: norm_type, actor, modality, action, object, scope.

### 2.4 `references`
`definition_links`, `related_articles`, `annex_references`, `resolved_target_ids` — all arrays of string, optional group.

### 2.5 `governance`
| Field | Type |
|---|---|
| `field_confidence` | object, values 0–1 |
| `ambiguity_flag` | boolean, default false |
| `inference_flag` | boolean, default false |
| `model_version` | string |
| `prompt_version` | string |
| `review_status` | enum: pending, accepted, edited, rejected, escalated (required) |
| `revision_history` | array of `{reviewer_id, timestamp, action: accept\|edit\|reject\|escalate, rationale (non-empty), diff (object or null)}` (required) |

### 2.6 ObligationObject invariants (MUST hold when review_status ∈ {accepted, edited})
1. `evidence_hash == sha256(verbatim_text)`.
2. `verbatim_text == CanonicalDocument.text[char_start:char_end]` for the matching `document_id`+`source_version` ("evidence replay" — runs at validation time and again at publish time).
3. `clause_id` globally unique per `(document_id, source_version)`.
4. `revision_history` non-empty; no code path sets accepted/edited without appending a revision_history entry in the same transaction.
5. Every `rationale` non-empty.

## 3. ValidationReport

| Field | Type |
|---|---|
| `target_clause_id` | string, required |
| `run_id` | string, required |
| `checks` | array of `{check_name: enum[schema_validity, controlled_vocabulary, evidence_span_fidelity, date_normalization, quantity_normalization, reference_validity, cross_field_consistency], status: pass\|fail\|warn, message}`, required |
| `overall_status` | enum: pass, fail, needs_review, required |

**Rule**: any `fail` on `evidence_span_fidelity` or `schema_validity` → `overall_status = "fail"` → record routes to `escalated` automatically (not presentable for accept/edit). Any other single `fail` → `overall_status = "needs_review"` (presentable, flagged).

## 4. GraphChangeSet

| Field | Type |
|---|---|
| `changeset_id` | string, required |
| `base_snapshot_id` | string or null (null only for very first snapshot), required |
| `source_clause_ids` | array of string, min 1, required |
| `ontology_version` | string, required |
| `proposed_nodes` | array of `{node_id, type: enum(§3.1 node types), properties: object, provenance: {clause_id}}`, required |
| `proposed_relationships` | array of `{from_node_id, to_node_id, type: enum(§3.2 relationship types), valid_from (date), provenance}`, required |
| `superseded_assertions` | array of string, optional |
| `constraint_report` | ConstraintReport, required |
| `status` | enum: draft, validated, approved, rejected, published, required |

**Ontology cardinality constraints (constraint_report, MUST fail closed):**
- Every `Obligation` node MUST have exactly one outgoing `DERIVED_FROM` → `Provision`.
- Every `Obligation` node MUST have ≥1 outgoing `IMPOSES_ON` → `Actor`.
- `MAPS_TO_CONTROL` edges only from `Obligation`/`Risk`, only to `Control`.
- `EVIDENCED_BY` edges only terminate at `EvidenceRequirement`/`TestAsset`.
- No relationship may reference a `node_id` absent from `proposed_nodes` and not already published in `base_snapshot_id`.
- Any constraint_report failure forces `status = rejected` — not eligible for approval.

## 5. GraphSnapshotExport

| Field | Type |
|---|---|
| `snapshot_id` | string, required |
| `ontology_version` | string, required |
| `valid_from` | date, required |
| `superseded_snapshot_id` | string or null |
| `obligations` | array of `{clause_id, obligation_node_id, mapped_controls, mapped_assets, mapped_evidence, review_status, source_anchor, confidence (0–1)}`, required |
| `schema_version` | const "1.0.0", required |

**Rule**: only ever produced from a snapshot whose every included obligation has `review_status ∈ {accepted, edited}`. Non-compliant obligations are excluded, not a runtime toggle.

## 6. Ontology (Graph Schema)

### 6.1 Node types & required properties
Regulation(`instrument`, `source_version`) · Provision(`anchor_id`, `label`) · Definition(`term`, `anchor_id`) · Obligation(`clause_id`, `norm_type`) · Actor(`name`, `role_category`) · Action(`description`) · Condition(`description`) · Exception(`description`) · Deadline(`type`, `normalized_iso` nullable) · Control(`control_id`, `name`) · Risk(`risk_id`, `name`) · EvidenceRequirement(`evidence_id`, `description`) · Asset(`asset_id`, `name`, `asset_type`) · System(`system_id`, `name`) · API(`api_id`, `name`) · Dataset(`dataset_id`, `name`) · TestAsset(`test_id`, `name`) · Agent(`agent_id`, `role` — internal LLM agent provenance only, not a graph actor).

### 6.2 Relationship types & allowed (from → to) pairs — exhaustive for v1
DERIVED_FROM(Obligation→Provision) · IMPOSES_ON(Obligation→Actor) · REQUIRES(Obligation→Action) · CONDITIONED_BY(Obligation→Condition) · EXCEPTION_TO(Obligation→Exception) · REFERENCES(Provision→Provision, Provision→Definition) · DEFINES(Definition→any legal-meaning node) · AMENDS(Provision→Provision) · SUPERSEDES(Regulation→Regulation, snapshot-level only) · APPLIES_TO(Obligation→Actor) · MAPS_TO_CONTROL(Obligation→Control, Risk→Control) · AFFECTS_ASSET(Obligation→Asset, Control→Asset) · SATISFIED_BY(Control→EvidenceRequirement) · EVIDENCED_BY(EvidenceRequirement→TestAsset).

Any proposal outside this table fails `constraint_report`. Extending it requires a spec version bump — not a code-level decision.

### 6.3 Canonical proof-path (Cypher, per resolved graph-store decision)

```
(provision:Provision)<-[:DERIVED_FROM]-(o:Obligation)
  -[:MAPS_TO_CONTROL]->(c:Control)
  -[:AFFECTS_ASSET]->(a:Asset)
c-[:SATISFIED_BY]->(e:EvidenceRequirement)-[:EVIDENCED_BY]->(t:TestAsset)
```

Corrected from the root spec's originally-unsatisfiable `regulation:Regulation` first hop — see `rabbitqa_spec_v1.0.0.md` §12 changelog v1.0.4. The `Provision` node's regulation context (`instrument`, `source_version`) is carried on its `properties`, not via a graph edge (§3.2 defines no `Provision`→`Regulation` relationship).

Every response includes, per path: `clause_id`, `verbatim_text`, `review_status`, `graph_snapshot_id`.

## 7. Agent I/O contracts (§4.4)

| Agent | Context package | Output schema |
|---|---|---|
| Extraction Agent | one candidate span's text + immediate structural anchor + controlled vocabulary list | `ObligationObjectProposal` subset: `legal_semantics`, `source_evidence` |
| Reference Agent | resolved-definitions index for pinned source version + candidate reference mentions | `{candidates: [{mention, target_anchor_id, confidence}]}` |
| Critic Agent | full `ObligationObjectProposal` + source span | `{findings: [{field, issue_type: enum[unsupported, mismatch, contradiction, omission], detail}]}` |
| Graph Mapping Agent | one or more approved `ObligationObject`s + current ontology + fixture of controls/assets/evidence | `GraphChangeSet` (draft, pre-constraint-check) |

**Prompt-injection boundary**: document text is a clearly delimited untrusted block, separate from system/instruction prompt (never concatenated with document content). Agents have zero write-capable tools (no DB writes, graph writes, shell exec, unrestricted network) — enforced at the gateway's tool allow-list, not by prompt instruction alone.

## 8. Entity relationship summary (implementation-level, not ontology)

```
CanonicalDocument 1───* anchor_node (structure)
CanonicalDocument 1───* ObligationObject (via source_evidence.anchor_id → anchor_node)
ObligationObject 1───* ValidationReport (revisions, by run_id)
ObligationObject 1───* revision_history entry (governance)
ObligationObject(s) *───* GraphChangeSet (source_clause_ids → provenance.clause_id on proposed_nodes)
GraphChangeSet 1───1 ConstraintReport
GraphChangeSet *───1 GraphSnapshot (on publish)
GraphSnapshot 0..1───1 GraphSnapshot (superseded_snapshot_id lineage)
GraphSnapshot 1───1 GraphSnapshotExport (on export request)
```

## 9. State transitions

**ObligationObject.governance.review_status**: `pending → {accepted, edited, rejected, escalated}` (reviewer decision); validation `fail` on schema_validity/evidence_span_fidelity forces `pending → escalated` automatically before any reviewer sees it as ordinary pending work.

**GraphChangeSet.status**: `draft → validated → approved → published`, with `→ rejected` reachable from `draft`/`validated` on any constraint_report failure. `published` is terminal; no further mutation.

**GraphSnapshot**: created only via publish; immutable once created; superseded (not deleted) by the next publish.
