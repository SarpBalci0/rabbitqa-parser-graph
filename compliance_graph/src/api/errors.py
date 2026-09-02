"""Re-exports the shared error envelope (see shared_contracts/py/errors.py) so
compliance_graph's API layer imports from its own module path per tasks.md T008."""

from shared_contracts.py.errors import (  # noqa: F401
    ApiError,
    BusinessRuleViolation,
    ConflictError,
    NotFoundError,
    SchemaValidationHttpError,
    install_error_handlers,
)
