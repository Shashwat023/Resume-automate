from app.domain import status as st


def test_terminal_set_contains_exactly_the_finished_statuses():
    assert st.TERMINAL == {st.COMPLETED, st.FAILED, st.CANCELLED}


def test_active_statuses_are_not_terminal():
    assert st.QUEUED not in st.TERMINAL
    assert st.RUNNING not in st.TERMINAL
    assert st.NEEDS_INPUT not in st.TERMINAL
    assert st.PAUSED not in st.TERMINAL
