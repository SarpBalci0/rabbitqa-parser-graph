"""ObligationObject / ValidationReport repository.

Implements: create/update a proposal + its validation report as one record; list a
clause's parse-revisions oldest-first; atomically append a revision_history entry
alongside any review_status change (FR-014/FR-017 invariant: "no code path sets
review_status to accepted/edited without appending a revision_history entry in the
same transaction").
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared_contracts.py.tables import obligations_table
from shared_contracts.py.validation import validate
from shared_contracts.py.invariants import (
    assert_clause_id_derivation,
    assert_evidence_hash_matches,
    assert_reviewed_record_invariants,
)


class ObligationRepository:
    def __init__(self, session: Session):
        self._session = session

    def create_revision(
        self, proposal_payload: dict[str, Any], validation_report_payload: dict[str, Any]
    ) -> str:
        validate(proposal_payload, "ObligationObject.schema.json")
        validate(validation_report_payload, "ValidationReport.schema.json")
        assert_clause_id_derivation(proposal_payload)
        assert_evidence_hash_matches(proposal_payload)
        assert_reviewed_record_invariants(proposal_payload)
        revision_id = str(uuid.uuid4())
        self._session.execute(
            obligations_table.insert().values(
                revision_id=revision_id,
                clause_id=proposal_payload["identity"]["clause_id"],
                proposal_payload=proposal_payload,
                validation_report_payload=validation_report_payload,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        self._session.commit()
        return revision_id

    def get_revision(self, revision_id: str) -> dict[str, Any] | None:
        row = self._session.execute(
            select(
                obligations_table.c.proposal_payload,
                obligations_table.c.validation_report_payload,
            ).where(obligations_table.c.revision_id == revision_id)
        ).first()
        if row is None:
            return None
        proposal, report = row
        return {"revision_id": revision_id, "proposal": proposal, "validation_report": report}

    def list_revisions_for_clause(self, clause_id: str) -> list[dict[str, Any]]:
        rows = self._session.execute(
            select(
                obligations_table.c.revision_id,
                obligations_table.c.proposal_payload,
                obligations_table.c.validation_report_payload,
                obligations_table.c.created_at,
            )
            .where(obligations_table.c.clause_id == clause_id)
            .order_by(obligations_table.c.created_at.asc())
        ).all()
        return [
            {
                "revision_id": revision_id,
                "proposal": proposal,
                "validation_report": report,
                "created_at": created_at,
            }
            for revision_id, proposal, report, created_at in rows
        ]

    def apply_decision(
        self,
        revision_id: str,
        *,
        new_review_status: str,
        revision_history_entry: dict[str, Any],
        updated_proposal_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Appends revision_history_entry and sets governance.review_status in one
        atomic write — the only place review_status is ever mutated, guaranteeing
        FR-014's invariant.

        Append-only guarantee (§2.2 invariant 4 / FR-036 spirit): revision_history
        is ALWAYS read from the existing persisted record, never from
        updated_proposal_payload, so an edit payload that omits or truncates history
        can never drop a prior entry — only revision_history_entry is ever added.

        Schema-validated before persisting (§2 preamble, invariant 5): a payload with
        an empty rationale, or otherwise violating ObligationObject.schema.json, is
        rejected here rather than trusting an upstream caller to have checked it.
        """
        existing = self.get_revision(revision_id)
        if existing is None:
            raise ValueError(f"No such revision: {revision_id}")

        if not revision_history_entry.get("rationale"):
            raise ValueError("revision_history_entry.rationale MUST be non-empty (§2.2 invariant 5).")

        # Non-governance fields (e.g. edited legal_semantics) may come from the
        # caller's updated payload; governance/history never do.
        base = dict(updated_proposal_payload or existing["proposal"])
        existing_governance = dict(existing["proposal"].get("governance", {}))
        history = list(existing_governance.get("revision_history", []))
        history.append(revision_history_entry)

        governance = dict(base.get("governance", {}))
        governance["revision_history"] = history
        governance["review_status"] = new_review_status
        base["governance"] = governance

        validate(base, "ObligationObject.schema.json")
        assert_clause_id_derivation(base)
        assert_evidence_hash_matches(base)
        assert_reviewed_record_invariants(base)

        self._session.execute(
            obligations_table.update()
            .where(obligations_table.c.revision_id == revision_id)
            .values(proposal_payload=base)
        )
        self._session.commit()
        return base
