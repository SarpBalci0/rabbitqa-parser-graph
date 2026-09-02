"""Agent-call logging per rabbitqa_spec_v1.0.0.md §7 LLM gateway zone:
"every agent call logs {model_version, prompt_version, input_hash, output_hash,
context_hash}"."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("rabbitqa.llm_gateway")


def _hash(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True)
class AgentCallRecord:
    agent_role: str
    model_version: str
    prompt_version: str
    input_hash: str
    output_hash: str
    context_hash: str
    trace_id: str | None = None
    # clause_id is not part of §7's required logged fields, but is needed to make
    # the "agent run_ids" link of the §7 provenance chain actually resolvable per
    # obligation (compliance_graph/src/export/provenance.py) — without it, agent
    # call records exist but can never be tied back to the clause they were for.
    clause_id: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AgentCallLog:
    """In-memory sink by default; call `records` to retrieve, or subclass/override
    `_emit` to ship to a real log backend.

    persist_to_db=True additionally best-effort persists every call to the shared
    pre-graph SQLite store (shared_contracts/py/tables.py:agent_call_log_table) and
    has records_for_clause() query it too — found necessary when clause_parser and
    compliance_graph run as SEPARATE PROCESSES (the real deployment topology,
    exercised by a live curl walkthrough): an in-memory-only log is invisible
    across processes, so the §7 provenance gate would incorrectly, silently
    exclude every obligation from export whenever extraction happened in a
    different process than the one handling the export request. Persistence is
    best-effort (wrapped in try/except) so a misconfigured/absent DB never breaks
    the in-memory behavior single-process callers and existing tests rely on."""

    def __init__(self, persist_to_db: bool = False) -> None:
        self._records: list[AgentCallRecord] = []
        self._persist_to_db = persist_to_db

    def log_call(
        self,
        *,
        agent_role: str,
        model_version: str,
        prompt_version: str,
        context_package: Any,
        raw_output: Any,
        trace_id: str | None = None,
        clause_id: str | None = None,
    ) -> AgentCallRecord:
        record = AgentCallRecord(
            agent_role=agent_role,
            model_version=model_version,
            prompt_version=prompt_version,
            input_hash=_hash(context_package),
            output_hash=_hash(raw_output),
            context_hash=_hash(context_package),
            trace_id=trace_id,
            clause_id=clause_id,
        )
        self._records.append(record)
        self._emit(record)
        if self._persist_to_db:
            self._try_persist(record)
        return record

    def _emit(self, record: AgentCallRecord) -> None:
        logger.info("agent_call", extra={"agent_call": asdict(record)})

    def _try_persist(self, record: AgentCallRecord) -> None:
        try:
            from shared_contracts.py.db import get_session
            from shared_contracts.py.tables import agent_call_log_table

            session = get_session()
            try:
                session.execute(
                    agent_call_log_table.insert().values(
                        id=str(uuid.uuid4()),
                        agent_role=record.agent_role,
                        model_version=record.model_version,
                        prompt_version=record.prompt_version,
                        input_hash=record.input_hash,
                        output_hash=record.output_hash,
                        context_hash=record.context_hash,
                        trace_id=record.trace_id,
                        clause_id=record.clause_id,
                        timestamp=record.timestamp,
                    )
                )
                session.commit()
            finally:
                session.close()
        except Exception:
            # Best-effort only: the in-memory record (self._records) remains
            # authoritative for same-process callers regardless of DB state.
            pass

    @property
    def records(self) -> list[AgentCallRecord]:
        return list(self._records)

    def records_for_clause(self, clause_id: str) -> list[AgentCallRecord]:
        in_memory = [r for r in self._records if r.clause_id == clause_id]
        if not self._persist_to_db:
            return in_memory
        return in_memory + self._query_db_for_clause(clause_id)

    def _query_db_for_clause(self, clause_id: str) -> list[AgentCallRecord]:
        try:
            from sqlalchemy import select

            from shared_contracts.py.db import get_session
            from shared_contracts.py.tables import agent_call_log_table

            session = get_session()
            try:
                rows = session.execute(
                    select(agent_call_log_table).where(agent_call_log_table.c.clause_id == clause_id)
                ).all()
            finally:
                session.close()
            return [
                AgentCallRecord(
                    agent_role=row.agent_role,
                    model_version=row.model_version,
                    prompt_version=row.prompt_version,
                    input_hash=row.input_hash,
                    output_hash=row.output_hash,
                    context_hash=row.context_hash,
                    trace_id=row.trace_id,
                    clause_id=row.clause_id,
                    timestamp=row.timestamp,
                )
                for row in rows
            ]
        except Exception:
            return []


DEFAULT_AGENT_CALL_LOG = AgentCallLog(persist_to_db=True)
