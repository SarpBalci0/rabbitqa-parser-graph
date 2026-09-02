"""Append-only audit/decision-history persistence primitive.

Per rabbitqa_spec_v1.1.0.md §7 (Graph & registries zone: "audit events are
append-only (no update/delete grants on the audit table)") and FR-036.

This module intentionally exposes no update/delete method at all — not "update
disabled by a flag" but structurally absent, so there is no code path that could
mutate or remove a past entry.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class AuditEntry:
    entry_id: str
    subject_type: str
    subject_id: str
    action: str
    actor_id: str
    rationale: str | None
    payload: dict[str, Any]
    recorded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AppendOnlyAuditLog:
    """No `update`, `delete`, or `clear` method exists on this class by design."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def append(
        self,
        *,
        subject_type: str,
        subject_id: str,
        action: str,
        actor_id: str,
        rationale: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            entry_id=str(uuid.uuid4()),
            subject_type=subject_type,
            subject_id=subject_id,
            action=action,
            actor_id=actor_id,
            rationale=rationale,
            payload=payload or {},
        )
        self._entries.append(entry)
        return entry

    def entries_for(self, subject_type: str, subject_id: str) -> list[AuditEntry]:
        return [e for e in self._entries if e.subject_type == subject_type and e.subject_id == subject_id]

    def all_entries(self) -> list[AuditEntry]:
        return list(self._entries)


DEFAULT_AUDIT_LOG = AppendOnlyAuditLog()
