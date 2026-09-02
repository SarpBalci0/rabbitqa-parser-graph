"""Standard API error envelope and exception types, per rabbitqa_spec_v1.1.0.md §5.

Error body shape: {"error": {"code": str, "message": str, "details": {}}}
Reused by both clause_parser's and compliance_graph's FastAPI apps.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """Base class for the five HTTP-status-carrying error types in §5."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def to_envelope(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class SchemaValidationHttpError(ApiError):
    status_code = 400
    code = "schema_validation_failed"


class NotFoundError(ApiError):
    status_code = 404
    code = "not_found"


class ConflictError(ApiError):
    status_code = 409
    code = "conflict"


class BusinessRuleViolation(ApiError):
    status_code = 422
    code = "business_rule_violation"


def install_error_handlers(app: FastAPI) -> None:
    """Register handlers so every ApiError (and any uncaught exception) returns the
    standard envelope, and unhandled 500s still log a provenance chain before returning
    (per §5's 500 row)."""

    @app.exception_handler(ApiError)
    async def _handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_envelope())

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        trace_id = getattr(request.state, "trace_id", None)
        # Full provenance chain logging is implemented by the tracing middleware
        # (shared_contracts/py/middleware.py), which attaches trace_id to request.state
        # and to every downstream log line before this handler ever runs.
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected error occurred.",
                    "details": {"trace_id": trace_id} if trace_id else {},
                }
            },
        )
