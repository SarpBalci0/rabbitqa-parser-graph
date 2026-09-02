"""GraphChangeSet repository.

Implements: create draft; persist status transitions
draft->validated->approved->rejected(->published); retrieve by id; list by
base_snapshot_id.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared_contracts.py.tables import changesets_table


class ChangesetRepository:
    def __init__(self, session: Session):
        self._session = session

    def create(self, changeset_payload: dict[str, Any]) -> None:
        self._session.execute(
            changesets_table.insert().values(
                changeset_id=changeset_payload["changeset_id"],
                base_snapshot_id=changeset_payload.get("base_snapshot_id"),
                payload=changeset_payload,
            )
        )
        self._session.commit()

    def get(self, changeset_id: str) -> dict[str, Any] | None:
        row = self._session.execute(
            select(changesets_table.c.payload).where(
                changesets_table.c.changeset_id == changeset_id
            )
        ).first()
        return row[0] if row else None

    def update_status(self, changeset_id: str, *, status: str, patch: dict[str, Any] | None = None) -> dict[str, Any]:
        existing = self.get(changeset_id)
        if existing is None:
            raise ValueError(f"No such changeset: {changeset_id}")
        updated = dict(existing)
        updated.update(patch or {})
        updated["status"] = status
        self._session.execute(
            changesets_table.update()
            .where(changesets_table.c.changeset_id == changeset_id)
            .values(payload=updated)
        )
        self._session.commit()
        return updated

    def list_by_base_snapshot(self, base_snapshot_id: str | None) -> list[dict[str, Any]]:
        rows = self._session.execute(
            select(changesets_table.c.payload).where(
                changesets_table.c.base_snapshot_id == base_snapshot_id
            )
        ).all()
        return [payload for (payload,) in rows]

    def list_published_by_snapshot(self, snapshot_id: str) -> list[dict[str, Any]]:
        rows = self._session.execute(select(changesets_table.c.payload)).all()
        return [
            payload
            for (payload,) in rows
            if payload.get("status") == "published" and payload.get("published_snapshot_id") == snapshot_id
        ]

    def find_published_by_clause_id(self, clause_id: str) -> dict[str, Any] | None:
        """§7 provenance chain lookup: the published changeset (if any) whose
        source_clause_ids includes clause_id. Returns the most recently published
        match if more than one changeset ever carried this clause_id."""
        rows = self._session.execute(select(changesets_table.c.payload)).all()
        candidates = [
            payload
            for (payload,) in rows
            if payload.get("status") == "published" and clause_id in payload.get("source_clause_ids", [])
        ]
        if not candidates:
            return None
        return candidates[-1]
