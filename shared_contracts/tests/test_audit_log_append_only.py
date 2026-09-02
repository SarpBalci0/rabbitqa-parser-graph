"""FR-036/§7 Graph & registries zone: audit events are append-only (no
update/delete grants on the audit table)."""

import inspect

from shared_contracts.py.audit_log import AppendOnlyAuditLog


def test_append_and_retrieve():
    log = AppendOnlyAuditLog()
    entry = log.append(
        subject_type="ObligationObject",
        subject_id="clause-1",
        action="accept",
        actor_id="reviewer-1",
        rationale="Looks correct.",
    )
    assert entry.action == "accept"
    assert log.entries_for("ObligationObject", "clause-1") == [entry]


def test_no_update_or_delete_method_exists():
    """Structural check, not a runtime permission flag: the class exposes no
    method whose name suggests mutation or removal of an existing entry at all."""
    public_methods = {
        name for name, _ in inspect.getmembers(AppendOnlyAuditLog, predicate=inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_methods == {"append", "entries_for", "all_entries"}
    forbidden = {"update", "delete", "remove", "clear", "edit", "modify", "set"}
    assert public_methods.isdisjoint(forbidden)


def test_appending_more_entries_never_removes_earlier_ones():
    log = AppendOnlyAuditLog()
    log.append(subject_type="X", subject_id="1", action="a", actor_id="r1", rationale="first")
    log.append(subject_type="X", subject_id="1", action="b", actor_id="r1", rationale="second")
    log.append(subject_type="X", subject_id="1", action="c", actor_id="r1", rationale="third")

    entries = log.entries_for("X", "1")
    assert [e.action for e in entries] == ["a", "b", "c"]
    assert len(log.all_entries()) == 3
