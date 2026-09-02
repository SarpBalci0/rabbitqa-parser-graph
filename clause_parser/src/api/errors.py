"""Re-exports the shared error envelope (see shared_contracts/py/errors.py) so
clause_parser's API layer imports from its own module path per tasks.md T008,
while compliance_graph/src/api/errors.py reuses the same implementation."""

from shared_contracts.py.errors import (  # noqa: F401
    ApiError,
    BusinessRuleViolation,
    ConflictError,
    NotFoundError,
    SchemaValidationHttpError,
    install_error_handlers,
)
