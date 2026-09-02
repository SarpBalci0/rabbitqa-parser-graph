# CLAUDE.md

## Spec authority hierarchy (highest to lowest)

1. **`rabbitqa_spec_v1.1.0.md`** — the ORIGINAL normative technical spec. This is the ultimate source of truth for all schemas, invariants, endpoints, and acceptance criteria. Any conflict resolves in its favor.
2. **`specs/001-clause-parser-compliance-graph/spec.md`, `plan.md`, `data-model.md`, `contracts/`** — spec-kit's derived artifacts. These MUST be consistent with `rabbitqa_spec_v1.1.0.md` at all times. They exist to drive `/speckit-tasks` and `/speckit-implement`, not to introduce new authority.
3. **`tasks.md`** — derived from the above; a checklist, not a source of new requirements.

**Rule:** if `rabbitqa_spec_v1.1.0.md` and any spec-kit artifact disagree, `rabbitqa_spec_v1.1.0.md` wins. Fix the spec-kit artifact to match — do not silently follow the spec-kit artifact. If a divergence is found, fix `rabbitqa_spec_v1.1.0.md` first only if the ROOT spec itself was wrong (bump `spec_version`, §12 changelog); otherwise fix the spec-kit derived file to match the root spec, and note the correction.

Before implementing anything, if there is any doubt about which file governs a given detail, check `rabbitqa_spec_v1.1.0.md` first.

The root spec's filename tracks its major.minor line only (`v1.1.x`) — it is not renamed on every patch. The authoritative version for any given revision is the `spec_version` field in the document's own §0 Document Control table and §12 Changelog, not the filename.
