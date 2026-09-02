"""Change-set approval action, per rabbitqa_spec_v1.0.0.md §4.3/§9.1:
explicit reviewer approval is required before a validated change set can be
published; no auto-publish path exists anywhere.
"""

from __future__ import annotations

from compliance_graph.src.db.changeset_repository import ChangesetRepository


class ChangesetNotValidatedError(Exception):
    """A changeset can only be approved from status == 'validated' (i.e. its most
    recent constraint_report passed) — not from 'draft' or 'rejected'."""


def approve_change_set(changeset_id: str, *, repository: ChangesetRepository) -> dict:
    changeset = repository.get(changeset_id)
    if changeset is None:
        raise ValueError(f"No such changeset: {changeset_id}")

    if changeset["status"] != "validated":
        raise ChangesetNotValidatedError(
            f"Changeset {changeset_id} has status '{changeset['status']}', not 'validated'; "
            "it must pass POST .../validate before it can be approved."
        )

    return repository.update_status(changeset_id, status="approved")
