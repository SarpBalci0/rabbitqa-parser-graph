"""Tests for clause_parser.src.canonicalize.document_registry, per §5.1
(spec_version 1.0.2): idempotent-by-content registration, and 409 conflict when
different content is registered under an already-used (instrument, source_version).
"""

import pytest

from shared_contracts.py.db import configure, get_session, get_engine_singleton
from shared_contracts.py.tables import create_all
from clause_parser.src.canonicalize.document_registry import (
    DocumentVersionConflictError,
    register_document,
)
from clause_parser.src.canonicalize.raw_storage import RawStorage
from clause_parser.src.db.document_repository import DocumentRepository


def _fresh_deps(tmp_path):
    configure("sqlite:///:memory:")
    create_all(get_engine_singleton())
    repo = DocumentRepository(get_session())
    storage = RawStorage(tmp_path / "raw")
    return repo, storage


def test_identical_content_reregistration_returns_existing_not_created(tmp_path):
    repo, storage = _fresh_deps(tmp_path)
    content = b"Article 1\n1. The operator shall notify within 30 days.\n"

    first = register_document(
        raw_bytes=content, instrument="NIS2", source_version="v1", repository=repo, raw_storage=storage
    )
    assert first.created is True

    second = register_document(
        raw_bytes=content, instrument="NIS2", source_version="v1", repository=repo, raw_storage=storage
    )
    assert second.created is False
    assert second.document_payload["document_id"] == first.document_payload["document_id"]


def test_different_content_same_source_version_conflicts(tmp_path):
    repo, storage = _fresh_deps(tmp_path)
    register_document(
        raw_bytes=b"Article 1\n1. The operator shall notify within 30 days.\n",
        instrument="NIS2",
        source_version="v1",
        repository=repo,
        raw_storage=storage,
    )

    with pytest.raises(DocumentVersionConflictError):
        register_document(
            raw_bytes=b"Article 1\n1. Completely different text.\n",
            instrument="NIS2",
            source_version="v1",
            repository=repo,
            raw_storage=storage,
        )


def test_different_source_version_is_not_a_conflict(tmp_path):
    repo, storage = _fresh_deps(tmp_path)
    register_document(
        raw_bytes=b"Article 1\n1. The operator shall notify within 30 days.\n",
        instrument="NIS2",
        source_version="v1",
        repository=repo,
        raw_storage=storage,
    )

    result = register_document(
        raw_bytes=b"Article 1\n1. Revised text for a new pinned version.\n",
        instrument="NIS2",
        source_version="v2",
        repository=repo,
        raw_storage=storage,
    )
    assert result.created is True
