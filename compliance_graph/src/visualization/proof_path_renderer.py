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

Layout: box sizes and canvas dimensions are computed from deterministic,
character-count-based text-width estimates (no font-metrics library, no
randomness -- §4.5 "Fully deterministic" still holds: the same input always
produces the same estimate and therefore byte-identical output). Connecting
lines are anchored to each box's boundary (not its center), and horizontal/
diagonal spacing is sized to fit each edge label's estimated width, so neither
node text nor edge labels are visually clipped by an adjacent box.
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

_DISPLAY_LABEL_MAX_ID_LEN = 20

# Deterministic text-width estimate: a fixed px-per-character constant for the
# font-size used, not a font-metrics lookup -- same string always yields the
# same estimate, so layout (and therefore the whole rendered document) stays
# byte-identical across runs/hosts, per §4.5's determinism requirement.
_NODE_FONT_SIZE = 12
_NODE_CHAR_WIDTH = 7.2
_EDGE_FONT_SIZE = 10
_EDGE_CHAR_WIDTH = 6.4

_BOX_HEIGHT = 50
_BOX_PADDING_X = 24
_MIN_BOX_WIDTH = 120
_MIN_EDGE_GAP = 90
_EDGE_LABEL_PADDING = 30


def _escape(value: str) -> str:
    """The single, dedicated escaping call site for every untrusted value (§7):
    XML/SVG-context escaping (&, <, >) plus quote escaping for use inside quoted
    attribute values, since this codebase's only escaping helper is used for both
    SVG <text> content and the surrounding HTML page body text."""
    return _xml_escape(value, {'"': "&quot;", "'": "&apos;"})


def _text_width(text: str, char_width: float) -> float:
    """Deterministic width estimate in px: character count times a fixed
    per-character constant. Intentionally not exact font-metric measurement --
    exact glyph widths depend on the rendering host's font stack, which would
    make output non-deterministic across hosts (§4.5)."""
    return len(text) * char_width


def _split_node_type_id(entry: str) -> tuple[str, str] | None:
    if ":" not in entry:
        return None
    node_type, node_id = entry.split(":", 1)
    if not node_type or not node_id:
        return None
    return node_type, node_id


def _truncate_node_id(node_id: str) -> tuple[str, bool]:
    if len(node_id) <= _DISPLAY_LABEL_MAX_ID_LEN:
        return node_id, False
    return node_id[: _DISPLAY_LABEL_MAX_ID_LEN - 1] + "…", True


def build_renderable_proof_path(proof_path_result: dict[str, Any]) -> dict[str, Any] | None:
    """Splits the raw query result's `path` entries into typed nodes and derives
    the fixed 5-edge tree by node type. Returns None if the path is not exactly
    the 6-entry §3.3 canonical shape, in Provision..TestAsset order -- callers
    MUST treat that as "no complete proof-path" (404), never a partial render."""
    path = proof_path_result.get("path") or []
    if len(path) != len(CANONICAL_NODE_TYPES):
        return None

    nodes: list[dict[str, Any]] = []
    for entry in path:
        split = _split_node_type_id(entry)
        if split is None:
            return None
        node_type, node_id = split
        shown_id, truncated = _truncate_node_id(node_id)
        nodes.append(
            {
                "node_type": node_type,
                "node_id": node_id,
                "display_label": f"{node_type}: {shown_id}",
                "truncated": truncated,
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


def _box_width(display_label: str) -> float:
    return max(_MIN_BOX_WIDTH, _text_width(display_label, _NODE_CHAR_WIDTH) + _BOX_PADDING_X)


def _edge_gap(relationship_name: str) -> float:
    return max(_MIN_EDGE_GAP, _text_width(relationship_name, _EDGE_CHAR_WIDTH) + _EDGE_LABEL_PADDING)


def _compute_layout(renderable: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Computes a box (x, y, width, height) per node type. Deterministic: every
    input is either a fixed constant or derived from the node/edge label text via
    _text_width, so identical `renderable` input always yields identical
    positions."""
    nodes_by_type = renderable["nodes_by_type"]
    widths = {t: _box_width(nodes_by_type[t]["display_label"]) for t in CANONICAL_NODE_TYPES}

    top_row_y = 40.0
    boxes: dict[str, dict[str, float]] = {}

    x = 20.0
    boxes["provision"] = {"x": x, "y": top_row_y, "width": widths["provision"], "height": _BOX_HEIGHT}
    x += widths["provision"] + _edge_gap("DERIVED_FROM")
    boxes["obligation"] = {"x": x, "y": top_row_y, "width": widths["obligation"], "height": _BOX_HEIGHT}
    x += widths["obligation"] + _edge_gap("MAPS_TO_CONTROL")
    boxes["control"] = {"x": x, "y": top_row_y, "width": widths["control"], "height": _BOX_HEIGHT}

    control_center_x = boxes["control"]["x"] + boxes["control"]["width"] / 2
    bottom_row_y = top_row_y + 170.0
    branch_offset = max(180.0, widths["asset"] / 2 + widths["evidence"] / 2 + 60.0)

    boxes["asset"] = {
        "x": control_center_x - branch_offset - widths["asset"] / 2,
        "y": bottom_row_y,
        "width": widths["asset"],
        "height": _BOX_HEIGHT,
    }
    boxes["evidence"] = {
        "x": control_center_x + branch_offset - widths["evidence"] / 2,
        "y": bottom_row_y,
        "width": widths["evidence"],
        "height": _BOX_HEIGHT,
    }
    boxes["testasset"] = {
        "x": boxes["evidence"]["x"] + boxes["evidence"]["width"] + _edge_gap("EVIDENCED_BY"),
        "y": bottom_row_y,
        "width": widths["testasset"],
        "height": _BOX_HEIGHT,
    }

    # Asset's box may start left of the canvas origin for a very wide asset/
    # evidence pair -- shift every box right so nothing renders off-canvas.
    min_x = min(box["x"] for box in boxes.values())
    if min_x < 20.0:
        shift = 20.0 - min_x
        for box in boxes.values():
            box["x"] += shift

    return boxes


def _box_center(box: dict[str, float]) -> tuple[float, float]:
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def _anchor_on_boundary(box: dict[str, float], toward_x: float, toward_y: float) -> tuple[float, float]:
    """Returns the point where a ray from `box`'s center toward (toward_x,
    toward_y) crosses `box`'s rectangular boundary -- so a connecting line stops
    at the box edge instead of running into its interior."""
    cx, cy = _box_center(box)
    dx, dy = toward_x - cx, toward_y - cy
    if dx == 0 and dy == 0:
        return cx, cy
    half_w, half_h = box["width"] / 2, box["height"] / 2
    scale_candidates = []
    if dx != 0:
        scale_candidates.append(half_w / abs(dx))
    if dy != 0:
        scale_candidates.append(half_h / abs(dy))
    scale = min(scale_candidates)
    return cx + dx * scale, cy + dy * scale


def _node_box(node: dict[str, Any], box: dict[str, float]) -> str:
    label = _escape(node["display_label"])
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    title = f"<title>{_escape(node['node_type'] + ':' + node['node_id'])}</title>" if node["truncated"] else ""
    return (
        f'<g>{title}'
        f'<rect x="{box["x"]:.1f}" y="{box["y"]:.1f}" width="{box["width"]:.1f}" height="{box["height"]:.1f}" '
        f'fill="#eef" stroke="#334" />'
        f'<text x="{cx:.1f}" y="{cy + 4:.1f}" text-anchor="middle" font-size="{_NODE_FONT_SIZE}">{label}</text>'
        "</g>"
    )


def _edge_line(x1: float, y1: float, x2: float, y2: float, label: str) -> str:
    escaped_label = _escape(label)
    mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2
    return (
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#334" marker-end="url(#arrow)" />'
        f'<text x="{mid_x:.1f}" y="{mid_y - 6:.1f}" text-anchor="middle" '
        f'font-size="{_EDGE_FONT_SIZE}">{escaped_label}</text>'
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

    boxes = _compute_layout(renderable)

    lines = ""
    for edge in renderable["edges"]:
        from_box = boxes[edge["from_node_type"]]
        to_box = boxes[edge["to_node_type"]]
        to_cx, to_cy = _box_center(to_box)
        from_cx, from_cy = _box_center(from_box)
        x1, y1 = _anchor_on_boundary(from_box, to_cx, to_cy)
        x2, y2 = _anchor_on_boundary(to_box, from_cx, from_cy)
        lines += _edge_line(x1, y1, x2, y2, edge["relationship_name"])

    boxes_svg = "".join(_node_box(renderable["nodes_by_type"][t], boxes[t]) for t in CANONICAL_NODE_TYPES)

    canvas_width = max(box["x"] + box["width"] for box in boxes.values()) + 20.0
    canvas_height = max(box["y"] + box["height"] for box in boxes.values()) + 20.0

    escaped_clause_id = _escape(renderable["clause_id"])
    escaped_verbatim_text = _escape(renderable["verbatim_text"])

    return (
        "<!doctype html>\n"
        "<html>\n"
        '<head><meta charset="utf-8"></head>\n'
        "<body>\n"
        f'<h1>Proof path for {escaped_clause_id}</h1>\n'
        f'<svg viewBox="0 0 {canvas_width:.1f} {canvas_height:.1f}" xmlns="http://www.w3.org/2000/svg">\n'
        "<defs>"
        '<marker id="arrow" markerWidth="8" markerHeight="8" refX="8" refY="4" orient="auto">'
        '<path d="M0,0 L8,4 L0,8 z" fill="#334" />'
        "</marker>"
        "</defs>\n"
        f"{lines}{boxes_svg}\n"
        "</svg>\n"
        f"<pre>{escaped_verbatim_text}</pre>\n"
        "</body>\n"
        "</html>\n"
    )
