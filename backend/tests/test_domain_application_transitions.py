import pytest

from app.core.exceptions import ConflictError
from app.domain import application_transitions as transitions
from app.domain import status as st


def test_can_pause_from_running():
    transitions.ensure_can_pause(st.RUNNING)  # does not raise


def test_can_pause_from_needs_input():
    transitions.ensure_can_pause(st.NEEDS_INPUT)  # does not raise


@pytest.mark.parametrize("terminal_status", [st.COMPLETED, st.FAILED, st.CANCELLED])
def test_cannot_pause_terminal_application(terminal_status):
    with pytest.raises(ConflictError, match="already finished"):
        transitions.ensure_can_pause(terminal_status)


def test_can_resume_from_needs_input():
    transitions.ensure_can_resume(st.NEEDS_INPUT)  # does not raise


def test_can_resume_from_paused():
    transitions.ensure_can_resume(st.PAUSED)  # does not raise


@pytest.mark.parametrize(
    "other_status", ["queued", "running", "completed", "failed", "cancelled"]
)
def test_cannot_resume_when_not_paused(other_status):
    with pytest.raises(ConflictError, match="not paused"):
        transitions.ensure_can_resume(other_status)


def test_can_pause_from_paused_is_a_noop_conflict_free_call():
    # Not disallowed — pausing an already-paused application is harmless
    # (ensure_can_pause only rejects TERMINAL statuses).
    transitions.ensure_can_pause(st.PAUSED)  # does not raise


def test_can_cancel_from_running():
    transitions.ensure_can_cancel(st.RUNNING)  # does not raise


@pytest.mark.parametrize("terminal_status", [st.COMPLETED, st.FAILED, st.CANCELLED])
def test_cannot_cancel_terminal_application(terminal_status):
    with pytest.raises(ConflictError, match="already finished"):
        transitions.ensure_can_cancel(terminal_status)
