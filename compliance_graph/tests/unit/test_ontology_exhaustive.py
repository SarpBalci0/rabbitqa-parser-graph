"""Exhaustive verification (not spot-checks) that the constraints engine rejects
every relationship type/pair not in §3.2's table, and accepts every one that is.

This iterates the full RELATIONSHIP_TYPES x NODE_TYPES x NODE_TYPES space (14 x 18
x 18 = 4536 combinations) and calls the actual engine function
(check_relationship_type_pair_allowed), not just the ontology lookup table it's
built on — so a bug in how the engine wires node_types into the lookup would be
caught here even if the table itself were correct.
"""

import itertools

from compliance_graph.src.constraints.engine import check_relationship_type_pair_allowed
from compliance_graph.src.constraints.ontology import (
    NODE_TYPES,
    RELATIONSHIP_ALLOWED_PAIRS,
    RELATIONSHIP_TYPES,
    is_pair_allowed,
)


def test_every_combination_matches_the_allow_list_exactly():
    total = 0
    checked_disallowed = 0
    checked_allowed = 0
    failures = []

    for rel_type, from_type, to_type in itertools.product(RELATIONSHIP_TYPES, NODE_TYPES, NODE_TYPES):
        total += 1
        should_be_allowed = (from_type, to_type) in RELATIONSHIP_ALLOWED_PAIRS[rel_type]

        node_types = {"n_from": from_type, "n_to": to_type}
        relationships = [{"from_node_id": "n_from", "to_node_id": "n_to", "type": rel_type}]
        result = check_relationship_type_pair_allowed(relationships, node_types)

        engine_says_allowed = result["status"] == "pass"

        if should_be_allowed:
            checked_allowed += 1
        else:
            checked_disallowed += 1

        if engine_says_allowed != should_be_allowed:
            failures.append((rel_type, from_type, to_type, "expected_allowed" if should_be_allowed else "expected_rejected"))

    assert total == len(RELATIONSHIP_TYPES) * len(NODE_TYPES) * len(NODE_TYPES)
    assert checked_allowed > 0, "sanity check: table should allow at least some pairs"
    assert checked_disallowed > checked_allowed, "sanity check: most combinations should be disallowed"
    assert failures == [], f"{len(failures)} mismatches between engine behavior and §3.2 allow-list: {failures[:10]}"


def test_unknown_relationship_type_is_always_rejected():
    """A relationship type not in RELATIONSHIP_TYPES at all (e.g. a typo, or a
    future/unversioned type) MUST fail closed, per §3.2: 'Any relationship proposal
    outside this table MUST fail constraint_report validation.'"""
    for from_type, to_type in itertools.product(NODE_TYPES, NODE_TYPES):
        assert is_pair_allowed("NOT_A_REAL_RELATIONSHIP_TYPE", from_type, to_type) is False


def test_every_node_type_pair_exhaustively_via_full_relationship_set():
    """Cross-check: for every relationship type, the set of pairs the engine
    accepts is EXACTLY the set in RELATIONSHIP_ALLOWED_PAIRS — no more, no fewer."""
    for rel_type in RELATIONSHIP_TYPES:
        accepted_by_engine = set()
        for from_type, to_type in itertools.product(NODE_TYPES, NODE_TYPES):
            node_types = {"a": from_type, "b": to_type}
            result = check_relationship_type_pair_allowed(
                [{"from_node_id": "a", "to_node_id": "b", "type": rel_type}], node_types
            )
            if result["status"] == "pass":
                accepted_by_engine.add((from_type, to_type))
        assert accepted_by_engine == RELATIONSHIP_ALLOWED_PAIRS[rel_type], (
            f"{rel_type}: engine accepts {accepted_by_engine}, "
            f"table says {RELATIONSHIP_ALLOWED_PAIRS[rel_type]}"
        )
