"""Write-once raw artifact storage.

Per rabbitqa_spec_v1.0.0.md §2.1 invariant: "raw_storage_uri content MUST be
write-once. Any write attempt to an existing key MUST fail."
"""

from __future__ import annotations

import os
from pathlib import Path


class KeyAlreadyExistsError(Exception):
    pass


class RawStorage:
    """Filesystem-backed write-once store, appropriate for the single-tenant local
    deployment target (§1.2). Swappable for a real object store later without
    changing the write-once contract this class enforces."""

    def __init__(self, base_dir: str | os.PathLike | None = None):
        self._base_dir = Path(base_dir or "./raw_storage")
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, content: bytes) -> str:
        path = self._base_dir / key
        if path.exists():
            raise KeyAlreadyExistsError(f"raw_storage_uri key already exists: {key}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return f"file://{path.resolve()}"

    def get(self, key: str) -> bytes:
        path = self._base_dir / key
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return (self._base_dir / key).exists()
