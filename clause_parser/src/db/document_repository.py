"""CanonicalDocument repository.

Implements: create; get-by-checksum (idempotent-registration lookup, FR-002);
get-by-id+source_version.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared_contracts.py.tables import documents_table


class DocumentRepository:
    def __init__(self, session: Session):
        self._session = session

    def create(self, document_payload: dict[str, Any]) -> None:
        self._session.execute(
            documents_table.insert().values(
                document_id=document_payload["document_id"],
                source_version=document_payload["source_version"],
                checksum_sha256=document_payload["checksum_sha256"],
                payload=document_payload,
            )
        )
        self._session.commit()

    def get_by_checksum(
        self, checksum_sha256: str, instrument: str, source_version: str
    ) -> dict[str, Any] | None:
        """Idempotent-registration lookup, scoped to (instrument, source_version,
        checksum) per §5.1 (spec_version 1.0.2): "Re-posting content whose checksum
        matches the already-registered (instrument, source_version)..." — note
        source_version is part of the match key, not just instrument. Found and
        fixed during T053 testing: this previously ignored source_version entirely,
        so identical bytes registered under a NEW source_version silently returned
        the OLD document instead of registering a new one — directly violating
        spec.md's own documented edge case ("distinct pinned versions — each gets
        its own identity; this is not a duplicate")."""
        row = self._session.execute(
            select(documents_table.c.payload).where(
                documents_table.c.checksum_sha256 == checksum_sha256,
                documents_table.c.source_version == source_version,
            )
        ).first()
        if row is None:
            return None
        payload = row[0]
        return payload if payload.get("instrument") == instrument else None

    def get_by_instrument_and_source_version(
        self, instrument: str, source_version: str
    ) -> dict[str, Any] | None:
        """Conflict-detection lookup (§5.1, spec_version 1.0.2): finds whatever is
        already registered under this (instrument, source_version) REGARDLESS of
        checksum, so the caller can distinguish 'identical content, return 200' from
        'different content under an already-pinned source_version, return 409'."""
        rows = self._session.execute(
            select(documents_table.c.payload).where(
                documents_table.c.source_version == source_version
            )
        ).all()
        for (payload,) in rows:
            if payload.get("instrument") == instrument:
                return payload
        return None

    def get(self, document_id: str, source_version: str) -> dict[str, Any] | None:
        row = self._session.execute(
            select(documents_table.c.payload).where(
                documents_table.c.document_id == document_id,
                documents_table.c.source_version == source_version,
            )
        ).first()
        return row[0] if row else None
