# shared_contracts/schemas

These JSON Schema (draft 2020-12) files are the normative source of truth for RabbitQA's
Clause Parser & Compliance Knowledge Graph data contracts, per `rabbitqa_spec_v1.1.0.md` §0
and §2. They MUST be validated against, never hand-diverged from, and never regenerated
from code — code is generated/checked against them, not the other way around.

## Files

- `CanonicalDocument.schema.json` — §2.1, literal from the technical spec.
- `ObligationObject.schema.json` — §2.2, literal from the technical spec.
- `ValidationReport.schema.json` — §2.3, literal from the technical spec.
- `GraphChangeSet.schema.json` — §2.4, literal from the technical spec.
- `GraphSnapshotExport.schema.json` — §2.5, literal from the technical spec.
- `ConstraintReport.schema.json` — **INTERIM, NOT in the technical spec.** §2.4 and §5.6
  reference a `ConstraintReport.schema.json` for `GraphChangeSet.constraint_report` and the
  `POST /v1/graph/changesets/{id}/validate` response, but the technical spec never defines
  its fields. This file is derived by mirroring `ValidationReport.schema.json`'s
  `checks`/`overall_status` shape and enumerating exactly the six named cardinality/ontology
  rules stated in §2.4's prose (see the file's own `$comment`). It MUST be confirmed against
  a spec update (spec_version bump per §0's change policy) before being treated as final.
  Tracked as an open item in `specs/001-clause-parser-compliance-graph/plan.md`'s
  Complexity Tracking table.
