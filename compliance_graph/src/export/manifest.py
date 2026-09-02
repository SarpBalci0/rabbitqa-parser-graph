"""Export-boundary logging: signed request manifest, per rabbitqa_spec_v1.1.0.md §7
Export boundary zone: "export requests are logged with a signed request manifest."
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("rabbitqa.export_boundary")

_SIGNING_KEY_ENV = "RABBITQA_EXPORT_MANIFEST_SIGNING_KEY"
_DEV_FALLBACK_KEY = "rabbitqa-dev-only-signing-key"  # never used if the env var is set


def _signing_key() -> bytes:
    return os.environ.get(_SIGNING_KEY_ENV, _DEV_FALLBACK_KEY).encode("utf-8")


@dataclass(frozen=True)
class ExportManifest:
    manifest_id: str
    snapshot_id: str
    requested_at: str
    included_clause_ids: tuple[str, ...]
    excluded_clause_ids: tuple[str, ...]
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sign(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hmac.new(_signing_key(), canonical, hashlib.sha256).hexdigest()


def build_and_log_manifest(
    *, snapshot_id: str, included_clause_ids: list[str], excluded_clause_ids: list[str]
) -> ExportManifest:
    manifest_id = str(uuid.uuid4())
    requested_at = datetime.now(timezone.utc).isoformat()
    unsigned = {
        "manifest_id": manifest_id,
        "snapshot_id": snapshot_id,
        "requested_at": requested_at,
        "included_clause_ids": sorted(included_clause_ids),
        "excluded_clause_ids": sorted(excluded_clause_ids),
    }
    signature = _sign(unsigned)

    manifest = ExportManifest(
        manifest_id=manifest_id,
        snapshot_id=snapshot_id,
        requested_at=requested_at,
        included_clause_ids=tuple(sorted(included_clause_ids)),
        excluded_clause_ids=tuple(sorted(excluded_clause_ids)),
        signature=signature,
    )
    logger.info("export_request_manifest", extra={"manifest": manifest.to_dict()})
    return manifest


def verify_manifest_signature(manifest: ExportManifest) -> bool:
    unsigned = {
        "manifest_id": manifest.manifest_id,
        "snapshot_id": manifest.snapshot_id,
        "requested_at": manifest.requested_at,
        "included_clause_ids": list(manifest.included_clause_ids),
        "excluded_clause_ids": list(manifest.excluded_clause_ids),
    }
    return hmac.compare_digest(_sign(unsigned), manifest.signature)
