"""Schema-validation helper for the normative JSON Schema contracts.

Per rabbitqa_spec_v1.0.0.md §2 preamble: "Every object MUST include schema_version
and MUST be validated against its schema before being persisted or transmitted
across a module boundary." This module is the single place that validation happens
so no call site can silently skip it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
from referencing import Registry, Resource

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"

_SCHEMA_FILES = [
    "CanonicalDocument.schema.json",
    "ObligationObject.schema.json",
    "ValidationReport.schema.json",
    "GraphChangeSet.schema.json",
    "ConstraintReport.schema.json",
    "GraphSnapshotExport.schema.json",
]


class SchemaValidationError(Exception):
    """Raised when a payload fails validation against its named schema."""

    def __init__(self, schema_name: str, errors: list[str]):
        self.schema_name = schema_name
        self.errors = errors
        super().__init__(f"{schema_name}: {'; '.join(errors)}")


def _load_registry() -> Registry:
    resources = []
    for filename in _SCHEMA_FILES:
        data = json.loads((SCHEMAS_DIR / filename).read_text())
        resources.append((filename, Resource.from_contents(data)))
    return Registry().with_resources(resources)


_REGISTRY = _load_registry()
_SCHEMA_CACHE: dict[str, dict[str, Any]] = {}


def _load_schema(schema_name: str) -> dict[str, Any]:
    if schema_name not in _SCHEMA_CACHE:
        path = SCHEMAS_DIR / schema_name
        if not path.exists():
            raise FileNotFoundError(f"Unknown schema: {schema_name}")
        _SCHEMA_CACHE[schema_name] = json.loads(path.read_text())
    return _SCHEMA_CACHE[schema_name]


def validate(payload: dict[str, Any], schema_name: str) -> None:
    """Validate payload against the named schema file under shared_contracts/schemas/.

    Raises SchemaValidationError (collecting all violations) if invalid.
    """
    schema = _load_schema(schema_name)
    validator_cls = jsonschema.validators.validator_for(schema)
    validator = validator_cls(schema, registry=_REGISTRY)
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
    if errors:
        messages = [f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors]
        raise SchemaValidationError(schema_name, messages)


def is_valid(payload: dict[str, Any], schema_name: str) -> bool:
    try:
        validate(payload, schema_name)
        return True
    except SchemaValidationError:
        return False
