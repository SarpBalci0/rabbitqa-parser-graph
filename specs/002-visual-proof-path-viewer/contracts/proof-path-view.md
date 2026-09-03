# Contract: `GET /v1/graph/snapshots/{snapshot_id}/proof-path-view`

Normative source: `rabbitqa_spec_v1.1.0.md` §5.11 (spec_version 1.2.0). This file restates that contract in spec-kit's format for `/speckit-tasks` — the root spec section governs on any discrepancy.

## Request

```
GET /v1/graph/snapshots/{snapshot_id}/proof-path-view?clause_id={clause_id}
```

| Parameter | Location | Type | Required | Notes |
|---|---|---|---|---|
| `snapshot_id` | path | string | yes | Identifies the published graph snapshot |
| `clause_id` | query | string | yes | Identifies the obligation within that snapshot |

## Success response

`200 OK`, `Content-Type: text/html`

Body: a minimal, self-contained HTML page (no external `<link>`/`<script src>` references) containing:
- One inline `<svg>` element rendering the §3.3 canonical proof-path: 6 labeled node boxes (Provision, Obligation, Control, Asset, EvidenceRequirement, TestAsset). This is a **branching** shape, not a single row of 6 boxes in a line: `Control` has two outgoing edges — `Provision -[DERIVED_FROM]-> Obligation -[MAPS_TO_CONTROL]-> Control`, then from `Control` separately, `Control -[AFFECTS_ASSET]-> Asset` **and** `Control -[SATISFIED_BY]-> EvidenceRequirement -[EVIDENCED_BY]-> TestAsset` (per §3.3's own Cypher pattern, which restarts its second clause at `Control`, not at `Asset`; §3.2 confirms `SATISFIED_BY` is `Control -> EvidenceRequirement` only — there is no `Asset -> EvidenceRequirement` relationship in this ontology). 5 labeled edges total (`DERIVED_FROM`, `MAPS_TO_CONTROL`, `AFFECTS_ASSET`, `SATISFIED_BY`, `EVIDENCED_BY`, per §3.2); `Asset` has no outgoing edge.
- The obligation's `verbatim_text`, displayed as plain text alongside the diagram, unmodified in meaning.

No `<script>` element, no `on*` event-handler attribute, no `<foreignObject>`, no `javascript:`/`data:` URI, and no external resource reference anywhere in the response body.

Every value drawn from `verbatim_text` or from any node's derived `display_label` is escaped for the SVG/XML text context before being written into the response (see `research.md`, "Escaping mechanism").

Two identical requests (same `snapshot_id` + `clause_id`, snapshot unchanged) MUST return byte-identical bodies.

## Error responses

All error responses use the standard envelope shared by every endpoint in this spec (§5 preamble), as `application/json` — never an HTML error page, even though the success response is HTML:

```json
{ "error": { "code": "string", "message": "string", "details": {} } }
```

| Status | `error.code` | Condition |
|---|---|---|
| `400` | `schema_validation_failed` | `clause_id` query parameter is missing |
| `404` | `not_found` | `snapshot_id` does not exist, or is not yet fully published (still `draft`/`validated`/`approved`-but-unpublished) |
| `404` | `not_found` | `snapshot_id` is published, but no proof-path result exists in it for the given `clause_id` (obligation absent, review status not `accepted`, or the chain is incomplete) |
| `500` | `internal_error` | An untrusted value could not be safely escaped for the output context — a hard gate (root spec §7); the response body is still logged with full provenance per §7's provenance-chain requirement, it is just never returned to the caller unescaped |

Note: the two `404` cases are intentionally indistinguishable to the caller — same status, same `error.code`, no case-specific `error.details` key that would let a caller tell them apart — per `research.md`'s "Not-found semantics" decision and feature-spec FR-013.

## Example

Request:
```
GET /v1/graph/snapshots/snap_96e04c71f55d/proof-path-view?clause_id=doc_bmasuj3nma9d:v1-pdf-2026-09-03:article-21/paragraph-1
```

Success (`200`, abbreviated):
```html
<!doctype html>
<html>
<body>
  <svg viewBox="0 0 1200 200" xmlns="http://www.w3.org/2000/svg">
    <!-- 6 <rect>+<text> node boxes, 5 labeled <line>/<text> edges -->
  </svg>
  <pre>1. The essential entity shall implement multi-factor authentication...</pre>
</body>
</html>
```

Not found (`404`):
```json
{ "error": { "code": "not_found", "message": "No published proof-path found for this clause_id in this snapshot.", "details": { "snapshot_id": "snap_96e04c71f55d", "clause_id": "doc_bmasuj3nma9d:v1-pdf-2026-09-03:article-21/paragraph-1" } } }
```
