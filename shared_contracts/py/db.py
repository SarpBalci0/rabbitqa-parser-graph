"""Pre-graph record store: connection/session management.

Resolves the storage-layer gap flagged in plan.md's Technical Context ("Storage")
and Complexity Tracking table — CanonicalDocument, ObligationObject, ValidationReport,
and GraphChangeSet need somewhere to live before graph publish. Single-tenant, local
deployment (rabbitqa_spec_v1.1.0.md §1.2) makes SQLite-via-SQLAlchemy a reasonable
default; RABBITQA_DB_URL can point at PostgreSQL for a non-local deployment without
changing any repository code.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_DEFAULT_URL = "sqlite:///./rabbitqa.db"


def get_engine(url: str | None = None):
    resolved = url or os.environ.get("RABBITQA_DB_URL", _DEFAULT_URL)
    connect_args = {"check_same_thread": False} if resolved.startswith("sqlite") else {}
    return create_engine(resolved, connect_args=connect_args)


_ENGINE = None
_SESSION_FACTORY: sessionmaker | None = None


def configure(url: str | None = None) -> None:
    global _ENGINE, _SESSION_FACTORY
    _ENGINE = get_engine(url)
    _SESSION_FACTORY = sessionmaker(bind=_ENGINE, expire_on_commit=False)


def get_session() -> Session:
    global _SESSION_FACTORY
    if _SESSION_FACTORY is None:
        configure()
    assert _SESSION_FACTORY is not None
    return _SESSION_FACTORY()


def get_engine_singleton():
    global _ENGINE
    if _ENGINE is None:
        configure()
    return _ENGINE
