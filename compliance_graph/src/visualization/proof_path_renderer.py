"""§4.5 Proof-Path Visualization renderer: a read-only, deterministic, no-LLM
module that turns one `run_proof_path_query` result into a static SVG diagram
embedded in a minimal HTML page (§5.11). No graph traversal happens here -- the
caller (compliance_graph/src/api/visualization.py) supplies an already-computed
query result.

Edge topology (research.md "Edge-label derivation", data-model.md
"RenderableProofPath"): §3.3's canonical proof-path is a TREE, not a line --
Control has two outgoing edges (AFFECTS_ASSET to Asset, SATISFIED_BY to
EvidenceRequirement), and Asset is a dead end. Edges are therefore derived by
node TYPE, never by pairing adjacent entries in the `path` array -- a positional
reading would draw a nonexistent Asset->EvidenceRequirement edge.
"""

from __future__ import annotations

from typing import Any
from xml.sax.saxutils import escape as _xml_escape

CANONICAL_NODE_TYPES = ("provision", "obligation", "control", "asset", "evidence", "testasset")

# Fixed, type-keyed edge list per §3.3/§3.2 -- never derived from `path` order.
_CANONICAL_EDGES = (
    ("provision", "obligation", "DERIVED_FROM"),
    ("obligation", "control", "MAPS_TO_CONTROL"),
    ("control", "asset", "AFFECTS_ASSET"),
    ("control", "evidence", "SATISFIED_BY"),
    ("evidence", "testasset", "EVIDENCED_BY"),
)

_DISPLAY_LABEL_MAX_ID_LEN = 24


def _escape(value: str) -> str:
    """The single, dedicated escaping call site for every untrusted value (§7):
    XML/SVG-context escaping (&, <, >) plus quote escaping for use inside quoted
    attribute values, since this codebase's only escaping helper is used for both
    SVG <text> content and the surrounding HTML page body text."""
    return _xml_escape(value, {'"': "&quot;", "'": "&apos;"})


def _split_node_type_id(entry: str) -> tuple[str, str] | None:
    if ":" not in entry:
        return None
    node_type, node_id = entry.split(":", 1)
    if not node_type or not node_id:
        return None
    return node_type, node_id


def build_renderable_proof_path(proof_path_result: dict[str, Any]) -> dict[str, Any] | None:
    """Splits the raw query result's `path` entries into typed nodes and derives
    the fixed 5-edge tree by node type. Returns None if the path is not exactly
    the 6-entry §3.3 canonical shape, in Provision..TestAsset order -- callers
    MUST treat that as "no complete proof-path" (404), never a partial render."""
    path = proof_path_result.get("path") or []
    if len(path) != len(CANONICAL_NODE_TYPES):
        return None

    nodes: list[dict[str, str]] = []
    for entry in path:
        split = _split_node_type_id(entry)
        if split is None:
            return None
        node_type, node_id = split
        nodes.append(
            {
                "node_type": node_type,
                "node_id": node_id,
                "display_label": f"{node_type}: {node_id[:_DISPLAY_LABEL_MAX_ID_LEN]}",
            }
        )

    if tuple(n["node_type"] for n in nodes) != CANONICAL_NODE_TYPES:
        return None

    nodes_by_type = {n["node_type"]: n for n in nodes}
    edges = [
        {"from_node_type": frm, "to_node_type": to, "relationship_name": rel}
        for frm, to, rel in _CANONICAL_EDGES
    ]

    return {
        "clause_id": proof_path_result["clause_id"],
        "nodes": nodes,
        "nodes_by_type": nodes_by_type,
        "edges": edges,
        "verbatim_text": proof_path_result.get("verbatim_text", ""),
    }


def _node_box(node: dict[str, str], x: int, y: int) -> str:
    label = _escape(node["display_label"])
    return (
        f'<rect x="{x}" y="{y}" width="160" height="50" fill="#eef" stroke="#334" />'
        f'<text x="{x + 80}" y="{y + 30}" text-anchor="middle" font-size="12">{label}</text>'
    )


def _edge_line(x1: int, y1: int, x2: int, y2: int, label: str) -> str:
    escaped_label = _escape(label)
    mid_x, mid_y = (x1 + x2) // 2, (y1 + y2) // 2
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#334" marker-end="url(#arrow)" />'
        f'<text x="{mid_x}" y="{mid_y - 6}" text-anchor="middle" font-size="10">{escaped_label}</text>'
    )


def render(proof_path_result: dict[str, Any]) -> str | None:
    """Returns a complete, self-contained HTML string with one inline <svg>, or
    None if the proof-path is not the complete 6-node canonical shape (caller maps
    that to a 404, per §5.11 "never render a partial diagram"). Static output only:
    no <script>, no <foreignObject>, no event-handler attributes, no external
    resource references (§4.5 "Interactivity", §7)."""
    renderable = build_renderable_proof_path(proof_path_result)
    if renderable is None:
        return None

    # Fixed layout: Provision -> Obligation -> Control on the top row; Control
    # branches down-left to Asset and down-right to Evidence -> TestAsset, making
    # the two-child topology visually explicit rather than implying a single line.
    positions = {
        "provision": (20, 20),
        "obligation": (220, 20),
        "control": (420, 20),
        "asset": (320, 140),
        "evidence": (520, 140),
        "testasset": (720, 140),
    }

    boxes = "".join(
        _node_box(renderable["nodes_by_type"][node_type], x, y) for node_type, (x, y) in positions.items()
    )

    def _center(node_type: str) -> tuple[int, int]:
        x, y = positions[node_type]
        return x + 80, y + 25

    lines = ""
    for edge in renderable["edges"]:
        x1, y1 = _center(edge["from_node_type"])
        x2, y2 = _center(edge["to_node_type"])
        lines += _edge_line(x1, y1, x2, y2, edge["relationship_name"])

    escaped_clause_id = _escape(renderable["clause_id"])
    escaped_verbatim_text = _escape(renderable["verbatim_text"])

    return (
        "<!doctype html>\n"
        "<html>\n"
        "<body>\n"
        f'<h1>Proof path for {escaped_clause_id}</h1>\n'
        '<svg viewBox="0 0 900 220" xmlns="http://www.w3.org/2000/svg">\n'
        "<defs>"
        '<marker id="arrow" markerWidth="8" markerHeight="8" refX="8" refY="4" orient="auto">'
        '<path d="M0,0 L8,4 L0,8 z" fill="#334" />'
        "</marker>"
        "</defs>\n"
        f"{lines}{boxes}\n"
        "</svg>\n"
        f"<pre>{escaped_verbatim_text}</pre>\n"
        "</body>\n"
        "</html>\n"
    )
