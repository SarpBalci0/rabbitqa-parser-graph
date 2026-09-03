# Phase 1 Data Model: Visual Proof-Path Viewer

This feature introduces no new persisted entities and no new database tables/schemas. It is a pure rendering layer over data that already exists (§4.5: "no new graph traversal, no new data source"). The entities below describe the *shapes this feature reads and produces*, not new storage.

## Existing entities read (unchanged)

### Proof-path query result (from `run_proof_path_query`, unchanged)

Already defined by `rabbitqa_spec_v1.1.0.md` §5.9 and implemented in `compliance_graph/src/query/proof_path.py`. One entry per obligation:

| Field | Type | Notes |
|---|---|---|
| `clause_id` | string | The obligation's identifier — the request's `clause_id` is matched against this field |
| `path` | array of strings | Ordered node list, each entry shaped `"{node_type}:{id}"` (e.g. `"control:ctrl-mfa-remote-access"`). Node-type prefixes confirmed against `compliance_graph/src/graph_mapping_agent/agent.py`: `provision`, `obligation`, `control`, `asset`. **Unverified assumption**: `evidence` and `testasset` are this document's guess for the `EvidenceRequirement`/`TestAsset` prefixes, following the same lowercase-type convention — no production code in this repo currently constructs an `EvidenceRequirement` or `TestAsset` node (there is no agent code path that creates `SATISFIED_BY`/`EVIDENCED_BY` relationships or their endpoint nodes), so these two prefixes are not confirmed by any existing implementation and MUST be verified (or the renderer's node-type parsing adjusted) once real Evidence/TestAsset node creation exists |
| `verbatim_text` | string | The obligation's exact source text — untrusted, originates from the ingested document |
| `review_status` | string | This feature only renders entries where this is `"accepted"` (root spec §5.11) |
| `graph_snapshot_id` | string | Must match the requested `snapshot_id` |

This feature adds no fields to this shape and performs no mutation of it.

## New (derived, request-scoped, non-persisted) shapes

### `ProofPathViewRequest` (parsed from the HTTP request, not stored)

| Field | Type | Source | Notes |
|---|---|---|---|
| `snapshot_id` | string | URL path segment | Required |
| `clause_id` | string | query parameter `clause_id` | Required — a missing value is a `400` before any lookup (FR-009) |

### `RenderableProofPath` (in-memory only, passed from the route handler to the renderer; never serialized/returned directly — the HTTP response is HTML, not this shape as JSON)

Derived by taking one `run_proof_path_query` result entry (filtered by `clause_id` and `review_status == "accepted"`) and splitting each `path` entry into its type/id parts for display:

| Field | Type | Derived from |
|---|---|---|
| `clause_id` | string | query result `clause_id` |
| `nodes` | array of `{node_type: string, node_id: string, display_label: string}` | each `path` entry, split on the first `:` |
| `edges` | array of `{from_node_type: string, to_node_type: string, relationship_name: string}`, exactly 5 entries | **type-keyed** lookup against the fixed §3.3 shape (research.md "Edge-label derivation"), never read from `path` data itself and never positional/index-adjacent over `nodes` — `Control` is the source of two edges (`AFFECTS_ASSET` to `Asset`, `SATISFIED_BY` to `EvidenceRequirement`), so the edge list is not "one fewer than `nodes`" via a linear chain, it is the fixed 5-edge tree: `Provision->Obligation` (`DERIVED_FROM`), `Obligation->Control` (`MAPS_TO_CONTROL`), `Control->Asset` (`AFFECTS_ASSET`), `Control->EvidenceRequirement` (`SATISFIED_BY`), `EvidenceRequirement->TestAsset` (`EVIDENCED_BY`) |
| `verbatim_text` | string | query result `verbatim_text`, unmodified |

**Validation rule**: if `nodes` does not have exactly the 6 entries §3.3's canonical shape requires (Provision, Obligation, Control, Asset, EvidenceRequirement, TestAsset, in that order), the renderer MUST treat this as "no complete proof-path" and the endpoint returns `404` (root spec §5.11: "never render a partial diagram for an obligation that doesn't have a complete, source-backed proof-path") — this is not a rendering-time crash, it's the same not-found pathway as every other incomplete-chain case. Note that this 6-entry ordering check validates *presence and node order* only; it MUST NOT be reused to derive edges by adjacent-index pairing (see `edges` row above) — `nodes[3]` (`Asset`) and `nodes[4]` (`EvidenceRequirement`) are siblings under `Control`, not directly connected.

## State transitions

None. This feature has no state of its own — it is read-only against already-finalized state (a published snapshot, an already-decided review outcome). No entity introduced here has a lifecycle.

## Relationships to existing entities

```
CanonicalDocument (clause_parser)
  └─ ObligationObject (clause_parser, review_status must be "accepted")
       └─ Obligation node (compliance_graph, via GraphChangeSet → publish)
            └─ [proof-path chain] (compliance_graph, via run_proof_path_query)
                 └─ RenderableProofPath (this feature, request-scoped, non-persisted)
                      └─ HTML+SVG response (this feature's only output)
```
