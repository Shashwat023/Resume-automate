"""
Application lifecycle state-machine rules. Pure validation functions, zero
I/O — extracted from what was previously inline logic in api/apply.py
(the `_require_active` helper and the ad-hoc status checks in each of
pause/resume/cancel). Behavior is copied verbatim: same conditions, same
error messages, just named and testable independent of FastAPI/SQLAlchemy.

Raises app.core.exceptions.ConflictError on an invalid transition; the API
layer maps that to HTTP 409 via a registered exception handler (see main.py).
"""

from app.core.exceptions import ConflictError
from app.domain import status as st


def ensure_can_pause(current_status: str) -> None:
    if current_status in st.TERMINAL:
        raise ConflictError("Application already finished")


def ensure_can_resume(current_status: str) -> None:
    if current_status not in (st.NEEDS_INPUT, st.PAUSED):
        raise ConflictError("Application is not paused")


def ensure_can_cancel(current_status: str) -> None:
    if current_status in st.TERMINAL:
        raise ConflictError("Application already finished")
