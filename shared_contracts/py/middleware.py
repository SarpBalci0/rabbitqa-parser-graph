"""Request tracing middleware per rabbitqa_spec_v1.0.0.md §7 Workflow service zone:
- every mutating request carries an idempotency key
- rate limits enforced per client
- every request is trace-tagged; trace_id propagates into every downstream log line
  and provenance record
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from shared_contracts.py.errors import ApiError

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass
class _RateLimiterState:
    window_seconds: int = 60
    max_requests: int = 120
    hits: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))

    def check(self, client_id: str) -> bool:
        now = time.monotonic()
        window_start = now - self.window_seconds
        recent = [t for t in self.hits[client_id] if t >= window_start]
        recent.append(now)
        self.hits[client_id] = recent
        return len(recent) <= self.max_requests


class RateLimited(ApiError):
    status_code = 429
    code = "rate_limited"


class MissingIdempotencyKey(ApiError):
    status_code = 400
    code = "missing_idempotency_key"


class TracingMiddleware(BaseHTTPMiddleware):
    """Attaches trace_id to request.state, enforces idempotency-key presence on
    mutating requests, and applies a simple per-client rate limit.

    Bug fixed by a spec-code synchronization audit: this middleware sits OUTSIDE
    Starlette's ExceptionMiddleware layer in the ASGI stack (custom middleware added
    via app.add_middleware runs between ServerErrorMiddleware and ExceptionMiddleware,
    not inside it), so an ApiError raised here previously bypassed the
    @app.exception_handler(ApiError) registered in errors.py entirely and surfaced as
    a raw unhandled 500 instead of the standard error envelope. Fixed by catching
    ApiError locally and building the JSONResponse directly, rather than relying on
    FastAPI's exception_handler mechanism for errors raised at this layer.
    """

    def __init__(self, app, rate_limiter: _RateLimiterState | None = None):
        super().__init__(app)
        self._rate_limiter = rate_limiter or _RateLimiterState()

    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = request.headers.get("x-trace-id") or str(uuid.uuid4())
        request.state.trace_id = trace_id

        try:
            client_id = request.headers.get(
                "x-client-id", request.client.host if request.client else "unknown"
            )
            if not self._rate_limiter.check(client_id):
                raise RateLimited("Rate limit exceeded for client.", {"trace_id": trace_id})

            if request.method in MUTATING_METHODS:
                idempotency_key = request.headers.get("idempotency-key")
                if not idempotency_key:
                    raise MissingIdempotencyKey(
                        "Mutating requests must carry an Idempotency-Key header.",
                        {"trace_id": trace_id},
                    )
                request.state.idempotency_key = idempotency_key
        except ApiError as exc:
            response = JSONResponse(status_code=exc.status_code, content=exc.to_envelope())
            response.headers["x-trace-id"] = trace_id
            return response

        response = await call_next(request)
        response.headers["x-trace-id"] = trace_id
        return response
