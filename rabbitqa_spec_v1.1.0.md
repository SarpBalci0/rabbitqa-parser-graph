# RabbitQA — Clause Parser & Compliance Knowledge Graph
## Technical Specification v1.1.2

**Status:** DRAFT — pending sign-off
**Scope:** Standalone module pair only (`clause_parser`, `compliance_graph`, `shared_contracts`, `reviewer_ui`, `evaluation`)
**Spec authority:** This document is normative. Where code and spec disagree, the spec wins — either the code is wrong or this document must be versioned and updated first. No implicit behavior is permitted; if a case is not covered here, it MUST be added to this spec before being implemented.

**Conventions:** Keywords MUST / MUST NOT / SHOULD / SHOULD NOT / MAY follow RFC 2119. All schemas are JSON Schema draft 2020-12 unless stated otherwise.

---

## 0. Document Control

| Field | Value |
|---|---|
| spec_version | 1.1.2 |
| covers report | RabbitQA Standalone Implementation Report, Aug 2026 |
| change policy | Any schema, endpoint, or acceptance-criterion change bumps spec_version (semver) and requires a changelog entry in §12 |
| source of truth for schemas | `/shared_contracts/schemas/*.json` — MUST be generated from this spec, never hand-diverged |

---

## 1. System Boundary & Non-Goals

### 1.1 In scope
- Ingesting one pinned regulatory source version at a time (NIS2, CRA, or DORA).
- Parsing it into reviewed, source-traceable `ObligationObject`s.
- Mapping approved obligations into a versioned compliance graph.
- Exposing proof-path queries and a read-only export.

### 1.2 Explicit non-goals (v1)
| Non-goal | Rationale |
|---|---|
| Multi-regulation cross-referencing across NIS2/CRA/DORA simultaneously | Each pinned run is single-instrument; cross-instrument mapping is a v2 concern |
| Automated legal interpretation without human review | Reviewer approval is mandatory for every ObligationObject and GraphChangeSet — no auto-publish path exists |
| Real external system integration (ticketing, GRC tools, live asset inventories) | Represented only by opaque contract tests and fixtures |
| Multi-tenant SaaS concerns (billing, org management) | Out of scope; single-tenant local deployment only |
| Non-English source languages in v1 | `language` field exists in schema for forward-compatibility but pipeline is validated only against English source text in v1 |
| Model fine-tuning / training custom extraction models | v1 uses prompted LLMs behind the gateway only |
| OCR / scanned (image-only) PDF ingestion | v1 supports PDF ingestion only where a text layer is extractable (§2.1, §7). A PDF with no extractable text layer MUST be rejected at ingress, never processed via OCR — OCR introduces a new dependency and a new trust boundary and is deferred to a future spec version (added spec_version 1.1.0, §12 changelog) |

If an implementer wants to build any of the above, it requires a new spec section and version bump — not silent inclusion.

---

## 2. Data Contracts (Normative Schemas)

All contracts live under `shared_contracts/schemas/`. Every object MUST include `schema_version` and MUST be validated against its schema before being persisted or transmitted across a module boundary.

### 2.1 `CanonicalDocument`

```json
{
  "$id": "CanonicalDocument.schema.json",
  "type": "object",
  "required": ["document_id", "source_version", "instrument", "checksum_sha256",
               "language", "jurisdiction", "structure", "created_at", "schema_version"],
  "properties": {
    "document_id": { "type": "string", "pattern": "^doc_[a-z0-9]{12}$" },
    "source_version": { "type": "string", "description": "Pinned identifier, e.g. official OJ reference or publication date" },
    "instrument": { "type": "string", "enum": ["NIS2", "CRA", "DORA"] },
    "checksum_sha256": { "type": "string", "pattern": "^[a-f0-9]{64}$" },
    "language": { "type": "string", "pattern": "^[a-z]{2}(-[A-Z]{2})?$" },
    "jurisdiction": { "type": "string", "const": "EU" },
    "structure": {
      "type": "array",
      "items": { "$ref": "#/$defs/anchor_node" }
    },
    "raw_storage_uri": { "type": "string", "description": "Immutable object storage pointer to the untouched source artifact" },
    "source_format": { "type": "string", "enum": ["text", "pdf"], "default": "text", "description": "Format of the source artifact at raw_storage_uri. Optional; absent is equivalent to \"text\" for backward compatibility with documents registered before spec_version 1.1.0." },
    "extraction_metadata": {
      "type": ["object", "null"],
      "description": "Present only when source_format is \"pdf\". Records how canonical text was extracted, for provenance and auditability.",
      "properties": {
        "extraction_method": { "type": "string", "description": "e.g. the name/version of the deterministic PDF text-extraction library used" },
        "confidence": { "type": "number", "minimum": 0, "maximum": 1, "description": "Deterministic extraction-quality score computed by the extraction step, per §7's rejection threshold" },
        "warnings": { "type": "array", "items": { "type": "string" }, "description": "Non-fatal extraction artifacts detected, e.g. \"possible multi-column reordering\", \"hyphenation-break artifacts detected\", \"possible broken word (mid-word line break without hyphen)\". None of these MUST trigger automatic text correction (see §2.1 invariants) — a warning records that the artifact was detected, never that it was fixed." }
      }
    },
    "created_at": { "type": "string", "format": "date-time" },
    "schema_version": { "type": "string", "const": "1.1.0" }
  },
  "$defs": {
    "anchor_node": {
      "type": "object",
      "required": ["anchor_id", "type", "char_start", "char_end"],
      "properties": {
        "anchor_id": { "type": "string", "description": "Stable ID: {document_id}:{source_version}:{structural_path}" },
        "type": { "type": "string", "enum": ["article", "paragraph", "annex", "table", "footnote", "recital"] },
        "label": { "type": ["string", "null"], "description": "e.g. 'Article 21(2)(b)'. MAY be null when no recognized structural label applies (e.g. a whole-document fallback anchor produced when no structural heading pattern in the source text was recognized) — this is the same optionality pattern as parent_anchor_id, not a data-quality gap." },
        "char_start": { "type": "integer", "minimum": 0 },
        "char_end": { "type": "integer", "minimum": 0 },
        "parent_anchor_id": { "type": ["string", "null"] }
      }
    }
  }
}
```

**Invariants:**
- `anchor_id` generation MUST be a pure function of `(document_id, source_version, structural_path)`. It MUST NOT depend on model output, run timestamp, or random seed. Re-ingesting the identical source artifact MUST yield byte-identical anchor IDs (idempotency — testable, see §9).
- `char_start`/`char_end` are offsets into the canonicalized text, not the raw file bytes. Canonicalization (whitespace normalization, encoding fix) MUST NOT alter legal text content — only formatting. This holds identically regardless of `source_format`: for `source_format: "pdf"`, `char_start`/`char_end` are offsets into the canonicalized text produced *after* PDF text extraction, never into PDF byte offsets, page numbers, or on-page coordinate positions. No downstream consumer of `structure` (detection, extraction, validation, review, export) MAY interpret these offsets as anything other than positions in the canonicalized text string.
- `raw_storage_uri` content MUST be write-once. Any write attempt to an existing key MUST fail.
- **PDF extraction is a distinct, deterministic step that MUST run before canonicalization, never inside it.** When `source_format` is `"pdf"`, the pipeline MUST: (1) extract a text layer from the PDF using a deterministic extraction method (no LLM call — consistent with §4.1 step 1's "Fully deterministic, no LLM" rule, which this extension does not weaken); (2) compute an `extraction_metadata.confidence` score and any `warnings` (e.g. detected multi-column reordering, hyphenation-break artifacts, page-break noise) as part of that same deterministic step; (3) only then hand the extracted text to the existing canonicalization step (§4.1 step 1), which applies unchanged (whitespace/encoding normalization only, content MUST NOT be altered).
- **Mid-word hard-break detection (spec_version 1.1.2).** The confidence-scoring step MUST detect a lowercase letter immediately followed by a line break immediately followed by a lowercase letter, with no intervening space or hyphen (e.g. PDF layout wrapping "remote" as "remo" + line break + "te") — this pattern is a strong signal of a broken word, distinct from the already-required hyphenation-break case (`<letter>-\n<letter>`), since it carries no hyphen to key off. Detecting this pattern MUST lower `extraction_metadata.confidence` and add an entry to `extraction_metadata.warnings`, so it surfaces at the §7 ingress quality gate exactly as any other extraction-quality signal does. The extraction step MUST NOT attempt to automatically rejoin the split word (or any other detected artifact) — doing so would risk silently altering legal text content (e.g. wrongly rejoining a legitimately line-final word with the next line's first word), which conflicts with this section's `char_start`/`char_end`-and-content-fidelity invariant above. Flag, never silently correct.
- **Extraction-quality gate.** If the PDF has no extractable text layer (zero characters extracted — the scanned/image-only case) or `extraction_metadata.confidence` falls below a configured threshold, `CanonicalDocument` registration MUST fail (see §5.1's `422` cases) and no `CanonicalDocument` record MUST be created. A low-confidence or empty extraction MUST NOT be registered and silently offered to the parser pipeline as if it were reliable text — this is a hard gate, not a warning, mirroring the hard-gate language already used for the export provenance chain (§7).
- OCR MUST NOT be attempted at any point in this pipeline (§1.2 non-goal). A PDF with no extractable text layer is a rejection, not a trigger for an OCR fallback.

### 2.2 `ObligationObject`

This is the central contract. Every field group below is REQUIRED unless marked optional.

```json
{
  "$id": "ObligationObject.schema.json",
  "type": "object",
  "required": ["identity", "source_evidence", "legal_semantics", "references", "governance"],
  "properties": {
    "identity": {
      "type": "object",
      "required": ["document_id", "source_version", "language", "jurisdiction",
                   "instrument", "clause_id", "schema_version"],
      "properties": {
        "document_id": { "type": "string" },
        "source_version": { "type": "string" },
        "language": { "type": "string" },
        "jurisdiction": { "type": "string", "const": "EU" },
        "instrument": { "type": "string", "enum": ["NIS2", "CRA", "DORA"] },
        "clause_id": { "type": "string", "pattern": "^[^:]+:[^:]+:.+$",
                       "description": "MUST be derived from identity + structural anchor, never from model output. Syntactic shape only: two non-empty colon-delimited segments (document_id, source_version) followed by a structural-path suffix. JSON Schema's pattern keyword cannot reference a sibling property's value, so the semantic requirement — that the first two segments equal this record's own document_id and source_version — is a cross-field invariant, enforced in implementation code alongside this schema, analogous to the evidence-replay invariant in §2.2's numbered list below (also cross-field, also not expressible as a single-field pattern)." },
        "schema_version": { "type": "string", "const": "1.0.0" }
      }
    },
    "source_evidence": {
      "type": "object",
      "required": ["anchor_id", "char_start", "char_end", "verbatim_text", "evidence_hash"],
      "properties": {
        "anchor_id": { "type": "string" },
        "char_start": { "type": "integer" },
        "char_end": { "type": "integer" },
        "verbatim_text": { "type": "string", "description": "MUST be an exact substring of the CanonicalDocument at [char_start, char_end)" },
        "evidence_hash": { "type": "string", "pattern": "^[a-f0-9]{64}$", "description": "SHA-256 of verbatim_text" }
      }
    },
    "legal_semantics": {
      "type": "object",
      "required": ["norm_type", "actor", "modality", "action", "object", "scope"],
      "properties": {
        "norm_type": { "type": "string", "enum": ["obligation", "prohibition", "permission", "definition_only"] },
        "actor": { "type": "array", "items": { "type": "string" }, "minItems": 1 },
        "modality": { "type": "string", "enum": ["shall", "must", "may", "should"] },
        "action": { "type": "string" },
        "object": { "type": "string" },
        "scope": { "type": "string" },
        "trigger": { "type": ["string", "null"] },
        "deadline": {
          "type": ["object", "null"],
          "properties": {
            "type": { "type": "string", "enum": ["absolute_date", "relative_period", "recurring"] },
            "value": { "type": "string" },
            "normalized_iso": { "type": ["string", "null"] }
          }
        },
        "frequency": { "type": ["string", "null"] },
        "conditions": { "type": "array", "items": { "type": "string" } },
        "exceptions": { "type": "array", "items": { "type": "string" } }
      }
    },
    "references": {
      "type": "object",
      "properties": {
        "definition_links": { "type": "array", "items": { "type": "string" } },
        "related_articles": { "type": "array", "items": { "type": "string" } },
        "annex_references": { "type": "array", "items": { "type": "string" } },
        "resolved_target_ids": { "type": "array", "items": { "type": "string" } }
      }
    },
    "governance": {
      "type": "object",
      "required": ["review_status", "revision_history"],
      "properties": {
        "field_confidence": { "type": "object", "additionalProperties": { "type": "number", "minimum": 0, "maximum": 1 } },
        "ambiguity_flag": { "type": "boolean", "default": false },
        "inference_flag": { "type": "boolean", "default": false },
        "model_version": { "type": "string" },
        "prompt_version": { "type": "string" },
        "review_status": { "type": "string", "enum": ["pending", "accepted", "edited", "rejected", "escalated"] },
        "revision_history": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["reviewer_id", "timestamp", "action", "rationale"],
            "properties": {
              "reviewer_id": { "type": "string" },
              "timestamp": { "type": "string", "format": "date-time" },
              "action": { "type": "string", "enum": ["accept", "edit", "reject", "escalate"] },
              "rationale": { "type": "string", "minLength": 1 },
              "diff": { "type": ["object", "null"] }
            }
          }
        }
      }
    }
  }
}
```

**Invariants (MUST hold for every record with `review_status = "accepted"` or `"edited"`):**
1. `evidence_hash == sha256(verbatim_text)`.
2. `verbatim_text == CanonicalDocument.text[char_start:char_end]` for the referenced `document_id`+`source_version`. This check is called **evidence replay** and MUST run at validation time and again at publish time.
3. `clause_id` is globally unique per `(document_id, source_version)`.
4. `revision_history` MUST NOT be empty — every accepted record has at least one human decision recorded. There is no code path that sets `review_status` to `accepted` or `edited` without appending a `revision_history` entry in the same transaction.
5. Every `rationale` MUST be non-empty free text — empty-string rationales are a schema violation, not merely a lint warning.

### 2.3 `ValidationReport`

```json
{
  "$id": "ValidationReport.schema.json",
  "type": "object",
  "required": ["target_clause_id", "run_id", "checks", "overall_status"],
  "properties": {
    "target_clause_id": { "type": "string" },
    "run_id": { "type": "string" },
    "checks": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["check_name", "status", "message"],
        "properties": {
          "check_name": { "type": "string", "enum": [
            "schema_validity", "controlled_vocabulary", "evidence_span_fidelity",
            "date_normalization", "quantity_normalization", "reference_validity",
            "cross_field_consistency" ] },
          "status": { "type": "string", "enum": ["pass", "fail", "warn"] },
          "message": { "type": "string" }
        }
      }
    },
    "overall_status": { "type": "string", "enum": ["pass", "fail", "needs_review"] }
  }
}
```

**Rule:** any `fail` on `evidence_span_fidelity` or `schema_validity` forces `overall_status = "fail"` and the record MUST NOT be presentable to a reviewer for accept/edit — it routes to `escalated` automatically. All other single `fail`s force `overall_status = "needs_review"`, which is presentable but flagged.

### 2.4 `GraphChangeSet`

```json
{
  "$id": "GraphChangeSet.schema.json",
  "type": "object",
  "required": ["changeset_id", "base_snapshot_id", "source_clause_ids", "ontology_version",
               "proposed_nodes", "proposed_relationships", "constraint_report", "status"],
  "properties": {
    "changeset_id": { "type": "string" },
    "base_snapshot_id": { "type": ["string", "null"], "description": "null only for the very first snapshot" },
    "source_clause_ids": { "type": "array", "items": { "type": "string" }, "minItems": 1 },
    "ontology_version": { "type": "string" },
    "proposed_nodes": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["node_id", "type", "properties", "provenance"],
        "properties": {
          "node_id": { "type": "string" },
          "type": { "type": "string", "enum": ["Regulation","Provision","Definition","Obligation","Actor",
                     "Action","Condition","Exception","Deadline","Control","Risk","EvidenceRequirement",
                     "Asset","System","API","Dataset","TestAsset","Agent"] },
          "properties": { "type": "object" },
          "provenance": { "type": "object", "required": ["clause_id"], "properties": { "clause_id": { "type": "string" } } }
        }
      }
    },
    "proposed_relationships": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["from_node_id", "to_node_id", "type", "provenance"],
        "properties": {
          "from_node_id": { "type": "string" },
          "to_node_id": { "type": "string" },
          "type": { "type": "string", "enum": ["DERIVED_FROM","IMPOSES_ON","REQUIRES","CONDITIONED_BY",
                    "EXCEPTION_TO","REFERENCES","DEFINES","AMENDS","SUPERSEDES","APPLIES_TO",
                    "MAPS_TO_CONTROL","AFFECTS_ASSET","SATISFIED_BY","EVIDENCED_BY"] },
          "valid_from": { "type": "string", "format": "date" },
          "provenance": { "type": "object" }
        }
      }
    },
    "superseded_assertions": { "type": "array", "items": { "type": "string" } },
    "constraint_report": { "$ref": "ConstraintReport.schema.json" },
    "status": { "type": "string", "enum": ["draft", "validated", "approved", "rejected", "published"] }
  }
}
```

**Ontology cardinality constraints (enforced by `ConstraintReport`, MUST fail closed):**
- Every `Obligation` node MUST have exactly one outgoing `DERIVED_FROM` to a `Provision`.
- Every `Obligation` node MUST have at least one outgoing `IMPOSES_ON` to an `Actor`.
- `MAPS_TO_CONTROL` edges MUST only originate from `Obligation` or `Risk` nodes and terminate at `Control` nodes.
- `EVIDENCED_BY` edges MUST only terminate at `EvidenceRequirement` or `TestAsset` nodes.
- No relationship may reference a `node_id` not present in `proposed_nodes` or already published in `base_snapshot_id`.
- A `GraphChangeSet` with any `constraint_report` failure MUST have `status` forced to `rejected` — it is not eligible for the approval endpoint.

### 2.5 `GraphSnapshotExport`

```json
{
  "$id": "GraphSnapshotExport.schema.json",
  "type": "object",
  "required": ["snapshot_id", "ontology_version", "valid_from", "obligations", "schema_version"],
  "properties": {
    "snapshot_id": { "type": "string" },
    "ontology_version": { "type": "string" },
    "valid_from": { "type": "string", "format": "date" },
    "superseded_snapshot_id": { "type": ["string", "null"] },
    "obligations": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["clause_id", "obligation_node_id", "mapped_controls", "mapped_evidence",
                     "review_status", "source_anchor", "confidence"],
        "properties": {
          "clause_id": { "type": "string" },
          "obligation_node_id": { "type": "string" },
          "mapped_controls": { "type": "array", "items": { "type": "string" } },
          "mapped_assets": { "type": "array", "items": { "type": "string" } },
          "mapped_evidence": { "type": "array", "items": { "type": "string" } },
          "review_status": { "type": "string" },
          "source_anchor": { "type": "string" },
          "confidence": { "type": "number", "minimum": 0, "maximum": 1 }
        }
      }
    },
    "schema_version": { "type": "string", "const": "1.0.0" }
  }
}
```

**Rule:** `GraphSnapshotExport` MUST only ever be produced from a snapshot whose every included obligation has `review_status` in `{accepted, edited}`. Exporting from a `pending`/`escalated`/`rejected` obligation is a contract violation, not a runtime option to be toggled.

---

## 3. Ontology Reference (Normative)

### 3.1 Node types and required properties

| Node type | Required properties |
|---|---|
| Regulation | `instrument`, `source_version` |
| Provision | `anchor_id`, `label` |
| Definition | `term`, `anchor_id` |
| Obligation | `clause_id`, `norm_type` |
| Actor | `name`, `role_category` |
| Action | `description` |
| Condition | `description` |
| Exception | `description` |
| Deadline | `type`, `normalized_iso` (nullable) |
| Control | `control_id`, `name` |
| Risk | `risk_id`, `name` |
| EvidenceRequirement | `evidence_id`, `description` |
| Asset | `asset_id`, `name`, `asset_type` |
| System | `system_id`, `name` |
| API | `api_id`, `name` |
| Dataset | `dataset_id`, `name` |
| TestAsset | `test_id`, `name` |
| Agent | `agent_id`, `role` — reserved for describing an internal LLM agent's provenance, not a graph actor |

### 3.2 Relationship type → allowed (from, to) pairs

| Relationship | Allowed from → to |
|---|---|
| DERIVED_FROM | Obligation → Provision |
| IMPOSES_ON | Obligation → Actor |
| REQUIRES | Obligation → Action |
| CONDITIONED_BY | Obligation → Condition |
| EXCEPTION_TO | Obligation → Exception |
| REFERENCES | Provision → Provision, Provision → Definition |
| DEFINES | Definition → (any legal-meaning node) |
| AMENDS | Provision → Provision |
| SUPERSEDES | Regulation → Regulation, snapshot-level only |
| APPLIES_TO | Obligation → Actor |
| MAPS_TO_CONTROL | Obligation → Control, Risk → Control |
| AFFECTS_ASSET | Obligation → Asset, Control → Asset |
| SATISFIED_BY | Control → EvidenceRequirement |
| EVIDENCED_BY | EvidenceRequirement → TestAsset |

Any relationship proposal outside this table MUST fail `constraint_report` validation. This table is exhaustive for v1 — extending it requires a spec version bump.

### 3.3 Canonical proof-path

The reference query for competency testing (§9.4) is:

```
(provision:Provision)<-[:DERIVED_FROM]-(o:Obligation)
  -[:MAPS_TO_CONTROL]->(c:Control)
  -[:AFFECTS_ASSET]->(a:Asset)
c-[:SATISFIED_BY]->(e:EvidenceRequirement)-[:EVIDENCED_BY]->(t:TestAsset)
```

**Clarification (spec_version 1.0.4):** the first hop originally read `(regulation:Regulation)<-[:DERIVED_FROM]-(o:Obligation)`, but §3.2's relationship table has never allowed a `DERIVED_FROM` edge from `Obligation` to `Regulation` (only to `Provision`), and no other relationship type in §3.2 links `Provision` to `Regulation` either — so the original pattern was never actually satisfiable by any graph this ontology permits. Corrected to start the traversal at `Provision`, the node `Obligation` actually derives from per §3.2. The `Provision` node's regulation context (`instrument`, `source_version`) is carried on the `Provision` node's own `properties` (beyond its two required properties, `anchor_id` and `label`) rather than via a graph edge, since §3.2 defines no `Provision`→`Regulation` relationship. This is a query-pattern correction only — no §3.2 relationship-table rule changed, and `ontology_version` is unaffected (§8: it "bumps whenever §3.1/§3.2 tables change," which they did not here).

Every query response MUST include, per path: `clause_id`, `verbatim_text` (from evidence), `review_status`, `graph_snapshot_id`.

---

## 4. Module Specifications

### 4.1 Clause Parser — processing sequence (MUST run in this exact order; no step may be skipped or reordered)

| # | Step | Input | Output | Determinism |
|---|---|---|---|---|
| 1 | Canonicalize | raw source artifact | `CanonicalDocument` | Fully deterministic, no LLM |
| 2 | Detect | `CanonicalDocument` | list of normative-passage spans + hard-negative spans | Deterministic classifier baseline REQUIRED; LLM-assisted refinement MAY be layered on top but the deterministic pass MUST run first and its output MUST be logged separately |
| 3 | Decompose | normative spans | atomic candidate obligation spans (shared conditions/exceptions retained via a `parent_span_id` link) | Deterministic or LLM; whichever is used MUST be recorded in governance metadata |
| 4 | Extract | candidate spans | `ObligationObjectProposal` (unreviewed) | LLM (Extraction Agent) |
| 5 | Resolve | proposal + pinned document | populated `references` block, normalized dates/quantities | Deterministic normalizers + Reference Agent |
| 6 | Validate | proposal | `ValidationReport` | Fully deterministic, no LLM |

**Hard rule:** Step 6 (Validate) MUST NOT invoke any LLM call. All checks in `ValidationReport.checks[].check_name` are pure functions over the proposal and the `CanonicalDocument`.

### 4.2 Parser evaluation (what MUST be measured, separately, per instrument)

- Normative-clause detection: precision, recall (span-level, exact-match IoU ≥ 0.95 counts as true positive).
- Field extraction: precision/recall/F1 per field (`actor`, `action`, `object`, `condition`, `deadline`, `exception`, cross-reference), reported separately for "core" fields (actor/action/object) and "complex" fields (condition/deadline/exception/reference) — this split matters because §9 sets different targets for each group.
- Evidence-span exact-overlap rate.
- Source-anchor validity rate.
- Accepted-record source fidelity (must be 100%, see §2.2 invariant 2).

### 4.3 Compliance Knowledge Graph — module responsibilities

| Sub-component | Responsibility | MUST NOT |
|---|---|---|
| Entity resolution | Match extracted actors/objects to existing Actor/Asset nodes by fuzzy+exact match with a confidence score | Auto-merge nodes above a threshold without a reviewer decision recorded |
| Graph Mapping Agent | Propose `GraphChangeSet.proposed_nodes/relationships` from one or more approved `ObligationObject`s | Write directly to the graph store; output is a proposal object only |
| Graph constraints engine | Run ontology + cardinality + provenance checks (§2.4) | Skip validation for changesets flagged "small" or "obvious" — every changeset is validated identically |
| Deterministic publisher | Apply an `approved` `GraphChangeSet` as a single transaction; on any failure, roll back completely | Partially commit; there is no partial-success state for a publish operation |

### 4.4 Agent I/O contracts

Each agent MUST be invoked with a bounded context package and MUST return schema-validated structured output. Free-text-only responses are a contract violation.

| Agent | Context package (exactly) | Output schema |
|---|---|---|
| Extraction Agent | one candidate span's text + immediate structural anchor + controlled vocabulary list | `ObligationObjectProposal` (subset: `legal_semantics`, `source_evidence`) |
| Reference Agent | resolved-definitions index for the pinned source version + candidate reference mentions | `{ "candidates": [ { "mention": str, "target_anchor_id": str, "confidence": float } ] }` |
| Critic Agent | full `ObligationObjectProposal` + its source span | `{ "findings": [ { "field": str, "issue_type": enum[unsupported, mismatch, contradiction, omission], "detail": str } ] }` |
| Graph Mapping Agent | one or more approved `ObligationObject`s + current ontology + a fixture of controls/assets/evidence | `GraphChangeSet` (draft status, pre-constraint-check) |

**Prompt-injection boundary (MUST):** source document text passed to any agent MUST be wrapped as a clearly delimited untrusted data block in the context package (e.g. tagged content region), and the system/instruction prompt MUST be assembled separately and never derived from or concatenated with document content. Agents MUST NOT be given tool access to: database writes, graph writes, shell execution, or unrestricted network calls. This is enforced at the gateway level (the agent's tool allow-list is empty except for read-only lookups against the pinned document and controlled vocabulary), not merely instructed via prompt.

---

## 5. API Specification

All endpoints return `application/json`. Errors follow:

```json
{ "error": { "code": "string", "message": "string", "details": {} } }
```

| HTTP status | Meaning |
|---|---|
| 400 | Schema validation failure on request body |
| 404 | Referenced entity (document/job/clause/changeset/snapshot) not found |
| 409 | State conflict (e.g. publishing a changeset not in `approved` status) |
| 422 | Business-rule violation (e.g. constraint_report has failures) |
| 500 | Unhandled — MUST still log full provenance chain before returning |

### 5.1 `POST /v1/documents`
Request: `{ "instrument": "NIS2"|"CRA"|"DORA", "source_artifact_uri": str, "source_version": str, "source_format": "text"|"pdf" }`
`source_format` is OPTIONAL; if absent it MUST be treated as `"text"` (backward-compatible with callers written before spec_version 1.1.0). `source_artifact_uri` keeps the same shape (an opaque URI pointer) regardless of `source_format` — it always points at the untouched raw artifact; the bytes at that URI are interpreted as plain text or as a PDF according to `source_format`, and stored unmodified as `raw_storage_uri` either way (§7 malware-scan and checksum rules apply identically to both formats).

Response `201`: `CanonicalDocument`
Errors:
- `400` if checksum cannot be computed, or if `source_format` is present and is not one of `"text"`/`"pdf"`.
- `422` with `error.code: "PDF_NO_TEXT_LAYER"` if `source_format` is `"pdf"` and zero characters of text can be extracted (scanned/image-only PDF, no text layer). No `CanonicalDocument` is created.
- `422` with `error.code: "PDF_EXTRACTION_LOW_CONFIDENCE"` if `source_format` is `"pdf"`, text is extracted, but the deterministic extraction step's `extraction_metadata.confidence` (§2.1) falls below the configured threshold. `error.details` MUST include the computed `confidence` value and any `warnings`. No `CanonicalDocument` is created.

Registration is idempotent by content, scoped to `(instrument, source_version)` — this rule is unchanged by `source_format` and applies to the checksum of the raw artifact bytes, not the extracted text:
- Re-posting content whose checksum matches the already-registered `(instrument, source_version)` returns the existing `CanonicalDocument` with `200`, not a duplicate.
- Re-posting content whose checksum does NOT match an already-registered `(instrument, source_version)` is a genuine conflict — a pinned source_version MUST be immutable once registered (§1.1) — and returns `409`. The caller MUST register revised content under a new `source_version`, not overwrite the existing one.

### 5.2 `POST /v1/parse-jobs`
Request: `{ "document_id": str, "source_version": str }`
Response `202`: `{ "job_id": str, "status": "queued" }`
This is async. Job runs steps 1–6 of §4.1 for every detected normative span.

### 5.3 `GET /v1/parse-jobs/{id}`
Response `200`: `{ "job_id": str, "status": "queued"|"running"|"completed"|"failed", "trace_id": str, "validation_summary": { "total": int, "pass": int, "needs_review": int, "fail": int } }`

### 5.4 `GET /v1/clauses/{id}/parse-revisions`
Response `200`: array of `{ ObligationObjectProposal, ValidationReport, revision_history }` ordered oldest-first.

### 5.5 `POST /v1/reviews/{revision}/decisions`
Request: `{ "reviewer_id": str, "action": "accept"|"edit"|"reject"|"escalate", "rationale": str, "edits": {}|null }`
Response `200`: updated `ObligationObject`
Rules: `rationale` MUST be non-empty (400 otherwise). `edit` action REQUIRES non-null `edits` and MUST re-run `ValidationReport` on the edited version before persisting — an edit that fails evidence-span fidelity is rejected with `422`, not silently accepted.

### 5.6 `POST /v1/graph/changesets/{id}/validate`
Response `200`: `ConstraintReport` (embedded per §2.4). Does not mutate graph state.

### 5.7 `POST /v1/graph/changesets/{id}/publish`
Preconditions (all MUST hold or `409`):
- `changeset.status == "approved"`
- most recent `validate` call's `constraint_report` shows zero failures
- `changeset.base_snapshot_id` equals the graph's current head snapshot (optimistic concurrency — if the graph moved since validation, `409` and the caller must re-validate)

Response `200`: `{ "snapshot_id": str, "published_at": str }`

### 5.8 `GET /v1/graph/snapshots/{id}`
Response `200`: snapshot metadata + `ontology_version` + lineage (`superseded_snapshot_id` chain).

### 5.9 `POST /v1/graph/query`
Request: `{ "snapshot_id": str, "pattern": "proof_path"|"coverage", "filters": {} }`
Response `200`: `{ "results": [ { "clause_id", "path": [...], "verbatim_text", "review_status", "graph_snapshot_id" } ] }`
Rule: querying a `snapshot_id` that is not fully published (i.e. still `draft`/`validated`/`approved`) MUST return `404`, not partial data.

### 5.10 `GET /v1/graph/snapshots/{id}/export`
Response `200`: `GraphSnapshotExport`, schema-validated before being returned. Rule per §2.5.

---

## 6. Reviewer Workspace Requirements

The UI (however implemented — web form or CLI) MUST expose, at minimum, per §7.2 of the source report:

1. Source pane showing the verbatim source text with the current proposal's evidence span highlighted, and the stable anchor label visible.
2. A structured editor with one input per `legal_semantics` field — free-text edits MUST be captured as a `diff` object attached to the resulting `revision_history` entry.
3. Validator findings and per-field confidence displayed before the reviewer can submit a decision (MUST NOT allow "accept" to be submitted without the `ValidationReport` having been fetched and rendered in the same session — this is a UX-level MUST, not enforceable server-side, but the server MUST independently re-validate on submit regardless of what the UI showed).
4. A graph-diff / proof-path preview for any `GraphChangeSet` awaiting approval, generated by calling §5.6 before the approval action is enabled.
5. Prior-revision history: reviewer identity, timestamp, decision, and rationale for every past revision of the clause and, separately, for prior versions of the source regulation article if superseded.

---

## 7. Security & Trust Zones (Normative)

Each zone below maps to enforceable controls, not aspirations. A code review MUST reject a PR that violates a MUST in this table.

| Zone | Trust level | MUST |
|---|---|---|
| Document ingress | Untrusted | Reject uploads exceeding **25 MB**, a fixed limit for both `text` and `pdf` source formats (testable — not a configuration value); validate content-type against an allow-list explicitly including `text/plain` and `application/pdf` (no other content-type is accepted in v1); run malware scan before persisting; compute checksum before any parsing step touches the content; for `source_format: "pdf"`, run the deterministic PDF text-extraction step (§2.1) after the malware scan and before canonicalization, and reject at ingress (per §5.1's `422` cases) any PDF with no extractable text layer or with extraction confidence below a configured threshold (deliberately left as a configuration decision, consistent with the LLM provider allow-list in §10) — OCR MUST NOT be attempted as a fallback (§1.2) |
| Workflow service | Controlled | Every mutating request carries an idempotency key; rate limits enforced per client; every request is trace-tagged and the trace_id is propagated into every downstream log line and provenance record |
| LLM gateway | Isolated inference | Model provider is selected from an explicit allow-list (no arbitrary endpoint); every agent call logs `{model_version, prompt_version, input_hash, output_hash, context_hash}`; agents have zero write-capable tools (§4.4) |
| Graph & registries | Trusted | All graph mutations are transactional; constraint checks run inside the same transaction as the write, not before-and-hope; audit events are append-only (no update/delete grants on the audit table) |
| Export boundary | Opaque read-only consumer | Export only from published snapshots (§2.5 rule); every export response is validated against `GraphSnapshotExport.schema.json` before being returned to the caller; export requests are logged with a signed request manifest |

**Provenance chain (MUST be reconstructable for every exported record):**
```
source checksum → CanonicalDocument.document_id
  → parse job run_id + agent run_ids (per agent, with model/prompt hashes)
  → ValidationReport
  → reviewer decision (revision_history entry)
  → GraphChangeSet.changeset_id
  → graph snapshot_id
  → export request manifest
```
If any link in this chain cannot be resolved for a given exported obligation, that obligation MUST NOT appear in the export — this is a hard gate, not a warning.

---

## 8. Versioning Rules

- `schema_version` on every contract object follows semver. A breaking change (removed/retyped required field) is a major bump; additive optional fields are a minor bump.
- `ontology_version` is independent of `schema_version` and bumps whenever §3.1/§3.2 tables change.
- A `GraphChangeSet` records the `ontology_version` it was validated against; publishing against a stale `ontology_version` relative to the graph's current head MUST fail with `409`, forcing re-validation.
- Prompt versions (`prompt_version` per agent) are tracked independently per agent role and MUST NOT be reused across agents even if the text is coincidentally identical.

---

## 9. Acceptance Criteria (Normative — these are the definition of "done", not aspirational targets)

### 9.1 Per-capability Given/When/Then

**Ingestion**
- Given a source artifact and its declared `instrument`/`source_version`, when `POST /v1/documents` is called twice with byte-identical content, then both calls resolve to the same `document_id` and the second returns `200` not `201`.

**Parsing**
- Given a `CanonicalDocument`, when a parse job completes, then every resulting `ObligationObjectProposal` has a `source_evidence.evidence_hash` that matches `sha256(verbatim_text)` and `verbatim_text` is an exact substring of the canonical text at the stated offsets.

**Validation**
- Given a proposal with a fabricated (non-substring) `verbatim_text`, when validated, then `ValidationReport.overall_status == "fail"` and `review_status` is forced to `"escalated"` — it MUST NOT be presentable as `"pending"`.

**Review**
- Given a reviewer submits an `accept` decision, when the record is persisted, then `revision_history` has a new entry with non-empty `rationale`, and `review_status == "accepted"`.
- Given a reviewer submits an `edit` that breaks evidence-span fidelity, when submitted, then the API returns `422` and no persisted state changes.

**Graph mapping & publish**
- Given a `GraphChangeSet` with a relationship type/pair not in the §3.2 table, when validated, then `constraint_report` shows a failure and `status` is forced to `"rejected"`.
- Given an `approved` changeset whose `base_snapshot_id` no longer matches the graph head, when publish is called, then it returns `409` and the graph is unchanged.
- Given a successful publish, when queried again, then the new `snapshot_id` is queryable and the prior snapshot is retrievable via `superseded_snapshot_id` lineage.

**Query & export**
- Given a proof-path query against a published snapshot, when results are returned, then every result includes `clause_id`, `verbatim_text`, `review_status`, and `graph_snapshot_id`.
- Given an export request for a snapshot containing any obligation with `review_status` not in `{accepted, edited}`, when exported, then that obligation is excluded from the export payload — the export MUST NOT fail silently by including it anyway.

### 9.2 Quantitative targets (measured on the locked evaluation corpus per §9.3)

| Measure | Target |
|---|---|
| Normative clause detection | Precision ≥ 0.90; Recall ≥ 0.93 |
| Core fields (actor/action/object) F1 | ≥ 0.90 |
| Complex fields (condition/deadline/exception/reference) F1 | ≥ 0.85 |
| Accepted-record source fidelity | 100% |
| Graph mapping macro F1 (accepted nodes/edges) | ≥ 0.85 |
| Competency query accuracy | ≥ 0.90, with source-backed proof paths |
| Graph integrity (provenance + constraint pass rate on accepted snapshots) | 100% |
| Parser→graph transaction success rate | ≥ 99% |
| Replay idempotency | 100% (identical input → identical anchors/IDs) |
| Snapshot export schema validity | 100% |

### 9.3 Evaluation corpus requirements
- Regulation-stratified, locked train/eval split (no eval clause ever used in prompt few-shot examples).
- MUST include: hard negatives, nested conditions, annex tables, long cross-references, at least one amendment scenario, and — even though v1 pipeline targets English — reserved multilingual sample slots for forward compatibility testing of the schema (not the pipeline).

### 9.4 Completion condition (system-level, not per-module)
A single reproducible run MUST demonstrate, end-to-end, without manual data patching:
pinned source → registered `CanonicalDocument` → parsed + validated `ObligationObjectProposal`s → reviewed (accepted/edited) `ObligationObject`s → approved `GraphChangeSet` → published graph snapshot → at least one successful proof-path query (§3.3 pattern) returning source-backed results → schema-valid `GraphSnapshotExport`.

---

## 10. Open Questions (blocking before implementation starts)

| # | Question | Owner | Status |
|---|---|---|---|
| 1 | Confirm graph database choice (spec assumes Neo4j/Cypher-style traversal semantics for §3.3) — if a different store is chosen, §3.3 query pattern needs restating in that store's query language | Engineering | **RESOLVED** (spec_version 1.0.3): Neo4j, matching §3.3 as written — no restatement needed. See `specs/001-clause-parser-compliance-graph/spec.md` "Resolved Clarifications" and `research.md` §4. |
| 2 | Confirm LLM provider(s) for the gateway allow-list (§7) before WP4 starts | Engineering | **OPEN.** Not yet decided; `llm_gateway/allow_list.py` implements a configuration-driven allow-list mechanism with no provider hardcoded, so this remains a pure configuration decision, not a code blocker. |
| 3 | Confirm the exact NIS2/CRA/DORA article subset to pin for v1 corpus (full instrument vs. a bounded subset) | Regulatory SME | **PARTIALLY RESOLVED** (spec_version 1.0.3): scope resolved to "a bounded subset" — see `spec.md` "Resolved Clarifications" and `research.md` §8. The specific enumerated article list is still open (Regulatory SME owner, per `research.md` §8's "Open point carried to Engineering"). |
| 4 | Confirm whether `edit` actions in review require a second reviewer (four-eyes) or single-reviewer is acceptable for this prototype | Product/Compliance | **RESOLVED** (spec_version 1.0.3): single-reviewer is acceptable. See `spec.md` "Resolved Clarifications". Implemented in `clause_parser/src/review/decision_service.py` (no second-reviewer gate). |

#1, #3 (scope), and #4 were resolved during specification (via `/speckit-specify`'s clarification flow, before any code was written) but this resolution was not logged back into this document until spec_version 1.0.3 — a `/speckit-analyze`-equivalent spec-code synchronization audit caught that this section's own "MUST be resolved and logged in §12" requirement had not actually been fulfilled here, only in the derived `spec.md`. #2 and the exact article list under #3 remain genuinely open.

---

## 11. Traceability Matrix (spec section → source report section)

| Spec section | Report section |
|---|---|
| §2 Data Contracts | Report §05 |
| §3 Ontology | Report §04 |
| §4.1–4.2 Parser | Report §03 |
| §4.3 Graph module | Report §04 |
| §4.4 Agents | Report §06 |
| §5 API | Report §07.1 |
| §6 Reviewer UI | Report §07.2 |
| §7 Security | Report §08 |
| §9 Acceptance | Report §10 |

---

## 12. Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-09-01 | Initial normative spec derived from RabbitQA Standalone Implementation Report |
| 1.0.1 | 2026-09-01 | Bugfix: §2.2 `ObligationObject.identity.clause_id` schema `pattern` was `"^{document_id}:{source_version}:.+$"`, which JSON Schema treats as a literal, unmatchable string (pattern cannot interpolate a sibling property's value) — no clause_id correctly derived per this same field's own description could ever satisfy it. Discovered during implementation when schema-validating real, spec-compliant `ObligationObject` writes. Corrected to a structural pattern (`^[^:]+:[^:]+:.+$`); the semantic requirement that the first two segments equal the record's own `document_id`/`source_version` is now stated as a cross-field invariant (not expressible in JSON Schema alone), enforced in implementation code. No other field, endpoint, or acceptance criterion changed. |
| 1.0.2 | 2026-09-01 | Clarification: §5.1 `POST /v1/documents` stated both "409 if (document_id-equivalent, source_version) already registered" and "re-posting identical bytes returns 200" in the same sentence, without distinguishing the genuine-conflict case (same instrument+source_version, different content) from the idempotent-match case (same content). Discovered during implementation when no layer — spec.md, contracts/api.md, or the document-registration code — had a defined behavior for re-registering different content under an already-used source_version. Disambiguated: `200` on checksum match; `409` on checksum mismatch for an already-registered `(instrument, source_version)`, since a pinned source_version MUST be immutable once registered (§1.1) — revised content requires a new source_version. No schema or acceptance-criterion change; endpoint behavior only. |
| 1.0.3 | 2026-09-01 | Housekeeping, discovered by a full spec-code synchronization audit: §10 explicitly requires its open questions to be "resolved and logged in §12" before implementation begins, but questions #1 (graph store), #3 (corpus scope), and #4 (four-eyes review) had been resolved during specification (`/speckit-specify`, recorded in `specs/001-clause-parser-compliance-graph/spec.md`'s "Resolved Clarifications") without ever being logged back into this document, as §10 itself requires. §10's table now marks each question's status and points to where it was resolved. No schema, endpoint, or acceptance-criterion content changed — this entry exists to satisfy §10's own logging requirement, not to alter any rule. |
| 1.0.4 | 2026-09-01 | Clarification: §3.3's canonical proof-path query started with `(regulation:Regulation)<-[:DERIVED_FROM]-(o:Obligation)`, but §3.2's relationship table has never permitted a `DERIVED_FROM` edge from `Obligation` to `Regulation` (only to `Provision`), and no relationship type links `Provision` to `Regulation` either — so the original query was never satisfiable by any graph this ontology actually permits. Discovered during implementation of User Story 4's proof-path query. Corrected to start at `Provision` (the node `Obligation` actually `DERIVED_FROM`s); the `Provision` node's regulation context (`instrument`, `source_version`) is now carried in its own `properties` rather than via a graph edge. §3.2's relationship table itself is unchanged — this is a query-pattern correction, not an ontology rule change — so `ontology_version` (§8) is unaffected. |
| 1.1.2 | 2026-09-03 | Clarification + gap fix: §2.1's extraction-quality heuristic detected mid-word hard breaks only in the hyphenated form (`<letter>-\n<letter>`, via a fixed 0.15 confidence penalty); a non-hyphenated mid-word break (`<letter>\n<letter>`, e.g. a fixed-width PDF renderer wrapping "remote" as "remo" + line break + "te") went completely undetected — confidence scored 1.0 with zero warnings despite the extracted text containing a corrupted word. Discovered via a manual PDF ingestion test (a synthetic Article 21 fixture rendered to PDF via `cupsfilter`'s fixed-column text layout) run against `evaluation/run_pdf_demo.py`: the same broken-word artifact also silently emptied `legal_semantics.exceptions` for the affected clause (a downstream regex bug in `extraction_agent.py`, fixed in code only — no schema/endpoint impact — since `_EXCEPTION_RE` assumed single-line text and its `.+?` could not match across the embedded line break). §2.1 now explicitly requires detecting the non-hyphenated case identically to the hyphenated one (new invariant bullet, "Mid-word hard-break detection"), and explicitly states extraction MUST flag, never automatically rejoin, any detected artifact — since silent rejoining risks altering legal text content, which this section's existing content-fidelity invariant already forbids. This also corrects the `extraction_metadata.warnings` schema description, which previously gave "hyphenation-break rejoin applied" as an example warning string — implying rejoining was expected/performed, contradicting the flag-only behavior required here (and never actually implemented). No required field, endpoint, or acceptance criterion changed; `CanonicalDocument.schema_version` const is unchanged at `"1.1.0"` (same precedent as 1.1.1). |
| 1.1.1 | 2026-09-02 | Bugfix: §2.1 `anchor_node.label` was typed `{ "type": "string" }` — not in `required`, but if present, forbidding `null`. `clause_parser/src/canonicalize/canonicalizer.py`'s documented fallback path (when no structural heading pattern is recognized in the source text, the whole document becomes a single top-level anchor "so no content is ever dropped") has always intentionally set `label: null` for that anchor, since no structural label is available in that case. This mismatch went undetected because every existing test fixture happened to contain text matching the recognized `Article N` heading pattern, so the fallback path — and therefore a `label: null` value — was never exercised against schema validation until PDF ingestion test fixtures (added in 1.1.0) triggered it. Corrected `label`'s type to `["string", "null"]`, mirroring the existing `parent_anchor_id` field's identical optionality pattern (also nullable, also not required) rather than inventing a new convention. No required field, endpoint, or acceptance criterion changed; `CanonicalDocument.schema_version` const is unchanged at `"1.1.0"` (precedent: 1.0.1–1.0.4 similarly corrected schema/query bugs without bumping the affected object's own `schema_version` const). |
| 1.1.0 | 2026-09-02 | Feature addition: PDF ingestion support. Prior to this version the spec implicitly assumed plain-text source artifacts only; §2.1, §5.1, and §7 now explicitly cover `source_format: "pdf"`. Per §8, this is an additive/optional-field change (minor bump), not a breaking one: `source_format` defaults to `"text"` when absent, so documents and callers predating 1.1.0 remain valid. Changes: (1) §5.1 request body gains an optional `source_format` field (`"text"` \| `"pdf"`); `source_artifact_uri` keeps its existing shape in both cases. (2) §2.1 `CanonicalDocument` gains optional `source_format` and `extraction_metadata` ({`extraction_method`, `confidence`, `warnings`}) fields; `schema_version` const bumped to `"1.1.0"`. A new invariant states PDF text extraction is a distinct, deterministic, no-LLM step that MUST run before canonicalization (never inside it), and that a hard extraction-quality gate — zero extracted text, or confidence below a configured threshold — MUST block `CanonicalDocument` registration entirely rather than register low-quality text; `char_start`/`char_end` are explicitly confirmed to remain offsets into canonicalized text only, never PDF byte/page/coordinate positions, regardless of `source_format`. (3) §5.1 gains two new `422` error cases (`PDF_NO_TEXT_LAYER`, `PDF_EXTRACTION_LOW_CONFIDENCE`) enforcing that gate at the API boundary. (4) §7's Document ingress row now explicitly allow-lists `application/pdf` alongside `text/plain`, and states a fixed, testable 25 MB size limit for both formats (previously stated only as "a configured size limit" with no number at all) — the extraction-confidence threshold, by contrast, is deliberately left as a configuration decision, consistent with how the LLM provider allow-list is handled in §10, and requires the extraction-quality gate to be enforced at ingress. (5) §1.2 non-goals gains an explicit entry: OCR / scanned (image-only) PDF ingestion is out of scope for v1 — a PDF with no text layer is rejected, not OCR'd; introducing OCR would add a new dependency and a new trust boundary and requires its own future spec version. No existing required field, endpoint status code, or acceptance criterion (§9) was removed or retyped; `ontology_version` (§8) is unaffected. |

---

## How to use this spec during implementation

1. Every PR that touches a schema, endpoint, or acceptance criterion MUST cite the spec section it implements.
2. If implementation reveals the spec is wrong or underspecified, STOP — update this document first (bump version, log in §12), then write code. Do not let code and spec diverge silently.
3. §9's Given/When/Then blocks are the literal test names to write first (TDD-friendly by design).
4. §10's open questions are blocking — do not guess defaults for them mid-implementation.
