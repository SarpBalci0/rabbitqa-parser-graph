"""ConstraintReport production, against the resolved (interim)
shared_contracts/schemas/ConstraintReport.schema.json — one rules[] entry per named
rule from that schema's enum, per rabbitqa_spec_v1.0.0.md §2.4.
"""

from __future__ import annotations

from typing import Any

from compliance_graph.src.constraints.engine import run_all_checks
from shared_contracts.py.validation import validate


def produce_constraint_report(
    changeset_id: str,
    proposed_nodes: list[dict[str, Any]],
    proposed_relationships: list[dict[str, Any]],
    *,
    published_node_ids: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    rules = run_all_checks(
        proposed_nodes, proposed_relationships, published_node_ids=published_node_ids
    )
    overall_status = "fail" if any(r["status"] == "fail" for r in rules) else "pass"

    report = {"changeset_id": changeset_id, "rules": rules, "overall_status": overall_status}
    validate(report, "ConstraintReport.schema.json")
    return report
