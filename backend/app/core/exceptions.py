"""
Domain-agnostic exceptions, framework-independent. Repositories/services
raise these; the API layer maps them to HTTP responses via exception
handlers registered in main.py (see NotFoundError -> 404, ConflictError ->
409). Keeping these out of `app.api` means domain/service/repository code
never has to import FastAPI just to signal an error.
"""


class NotFoundError(Exception):
    """Raised when a requested entity does not exist."""


class ConflictError(Exception):
    """Raised when a requested operation is invalid for the entity's current state."""
