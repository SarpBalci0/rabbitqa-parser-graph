"""Runnable FastAPI app for the compliance_graph service.

Wires together changesets.py/snapshots.py/query.py/export.py's routers
(§5.6-§5.10) with a Neo4jGraphStore (requires a live Neo4j reachable at
RABBITQA_NEO4J_URI, default bolt://localhost:7687) and the SAME pre-graph SQLite
record store clause_parser's app uses (both default to sqlite:///./rabbitqa.db
relative to the current working directory — run both processes from the repo
root so they share data). Run with:

    uvicorn compliance_graph.src.api.app:app --port 8002

Note: there is no REST endpoint for CREATING a GraphChangeSet — the root spec's
§5 never defines one (the Graph Mapping Agent is invoked directly, not exposed
over HTTP; see rabbitqa_spec_v1.0.0.md §4.4). Propose a change set with a short
Python snippet (see the walkthrough), then use this service's
POST .../validate and POST .../publish endpoints on the resulting changeset_id.
"""

from __future__ import annotations

from fastapi import FastAPI

from clause_parser.src.db.obligation_repository import ObligationRepository
from compliance_graph.src.api import changesets, export, query, snapshots
from compliance_graph.src.db.neo4j_client import Neo4jClient
from compliance_graph.src.publisher.neo4j_store import Neo4jGraphStore
from shared_contracts.py.db import configure, get_engine_singleton, get_session
from shared_contracts.py.errors import install_error_handlers
from shared_contracts.py.middleware import TracingMiddleware
from shared_contracts.py.tables import create_all

configure()  # same default/env resolution as clause_parser's app.py
create_all(get_engine_singleton())

_neo4j_client = Neo4jClient()


def _graph_store_factory() -> Neo4jGraphStore:
    return Neo4jGraphStore(_neo4j_client)


def _obligation_repository_factory() -> ObligationRepository:
    return ObligationRepository(get_session())


app = FastAPI(title="RabbitQA Compliance Graph")
app.add_middleware(TracingMiddleware)
install_error_handlers(app)

app.include_router(changesets.build_router(get_session, _graph_store_factory))
app.include_router(snapshots.build_router(_graph_store_factory))
app.include_router(query.build_router(_graph_store_factory, _obligation_repository_factory))
app.include_router(export.build_router(get_session, _graph_store_factory))
