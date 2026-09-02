"""Runnable FastAPI app for the clause_parser service.

Wires together documents.py/parse_jobs.py/clauses.py/reviews.py's routers
(§5.1-§5.5) with the shared middleware/error-envelope and the pre-graph SQLite
record store. Run with:

    uvicorn clause_parser.src.api.app:app --port 8001
"""

from __future__ import annotations

from fastapi import FastAPI

from clause_parser.src.api import clauses, documents, parse_jobs, reviews
from shared_contracts.py.db import configure, get_engine_singleton, get_session
from shared_contracts.py.errors import install_error_handlers
from shared_contracts.py.middleware import TracingMiddleware
from shared_contracts.py.tables import create_all

configure()  # RABBITQA_DB_URL env var, or sqlite:///./rabbitqa.db relative to cwd
create_all(get_engine_singleton())

app = FastAPI(title="RabbitQA Clause Parser")
app.add_middleware(TracingMiddleware)
install_error_handlers(app)

app.include_router(documents.build_router(get_session))
app.include_router(parse_jobs.build_router(get_session))
app.include_router(clauses.build_router(get_session))
app.include_router(reviews.build_router(get_session))
