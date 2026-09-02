"""Neo4j connection/session management for the compliance graph.

Per rabbitqa_spec_v1.1.0.md §4.3 (Deterministic publisher: "Apply an approved
GraphChangeSet as a single transaction; on any failure, roll back completely...
there is no partial-success state") and §7 (Graph & registries zone: "All graph
mutations are transactional; constraint checks run inside the same transaction
as the write").
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from neo4j import Driver, GraphDatabase, Transaction


class Neo4jClient:
    def __init__(self, uri: str | None = None, user: str | None = None, password: str | None = None):
        self._uri = uri or os.environ.get("RABBITQA_NEO4J_URI", "bolt://localhost:7687")
        self._user = user or os.environ.get("RABBITQA_NEO4J_USER", "neo4j")
        self._password = password or os.environ.get("RABBITQA_NEO4J_PASSWORD", "")
        self._driver: Driver | None = None

    def connect(self) -> None:
        if self._driver is None:
            self._driver = GraphDatabase.driver(self._uri, auth=(self._user, self._password))

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    @contextmanager
    def all_or_nothing_transaction(self) -> Iterator[Transaction]:
        """A single Neo4j transaction; any exception inside the `with` block causes a
        full rollback via the driver's session.begin_transaction context management —
        there is no code path here that allows a partial commit."""
        self.connect()
        assert self._driver is not None
        with self._driver.session() as session:
            tx = session.begin_transaction()
            try:
                yield tx
                tx.commit()
            except Exception:
                tx.rollback()
                raise
            finally:
                if not tx.closed():
                    tx.close()
