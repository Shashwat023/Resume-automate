import asyncio

import pytest

from app.services.engine import runner
from app.services.engine.tier0_harvest import FormField, HarvestResult
from app.services.engine.tier1_map import Tier1Result
from app.services.engine.tier2_resolve import Tier2Result
from app.worker import queue_runner


def _cascade(fields):
    return runner.FillCascadeResult(
        fields=fields,
        tier0=HarvestResult(filled=[], unmatched=[], errored=[]),
        tier1=Tier1Result(
            filled=[],
            from_library=[],
            for_tier2=[],
            low_confidence_filled=[],
            unanswered=[],
            errored=[],
            usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        ),
        tier2=Tier2Result(resolved=[], errored=[]),
    )


@pytest.fixture(autouse=True)
def _clear_queue_events():
    yield
    queue_runner._cancel_events.clear()
    queue_runner._resume_events.clear()
    queue_runner._pause_events.clear()


async def test_check_paused_and_wait_raises_when_cancelled():
    application_id = "cancel-at-checkpoint"
    queue_runner._cancel_events[application_id] = asyncio.Event()
    queue_runner._cancel_events[application_id].set()

    with pytest.raises(runner.ApplicationCancelled):
        await runner._check_paused_and_wait(application_id)


async def test_cancel_while_waiting_for_profile_lock_never_acquires_the_lock():
    application_id = "lock-cancel"
    key = "profile-lock-cancel"
    queue_runner._cancel_events[application_id] = asyncio.Event()
    lock = queue_runner.get_profile_lock(key)
    await lock.acquire()
    try:
        waiter = asyncio.create_task(
            queue_runner.profile_session(key, application_id).__aenter__()
        )
        await asyncio.sleep(0)
        await queue_runner.signal_cancel(application_id)
        with pytest.raises(queue_runner.ApplicationCancelled):
            await waiter
        assert lock.locked()
    finally:
        lock.release()
        queue_runner._profile_locks.pop(key, None)


def test_file_field_is_excluded_from_repairable_labels():
    cascade = _cascade(
        [
            FormField(
                node_id="1",
                role="file",
                label="Cover Letter",
                xpath="//file",
                required=True,
            ),
            FormField(node_id="2", role="textbox", label="Website", xpath="//text"),
        ]
    )

    assert runner._repairable_unhandled_labels(cascade) == {"Website"}


def test_required_file_field_remains_escalatable():
    field = FormField(
        node_id="1", role="file", label="Cover Letter", xpath="//file", required=True
    )
    cascade = _cascade([field])

    assert runner._unhandled_labels(cascade) == {"Cover Letter"}
    assert runner._repairable_unhandled_labels(cascade) == set()


async def test_tier2_checkpoint_runs_before_each_field_and_can_abort():
    from app.services.engine import tier2_resolve

    fields = [
        (FormField("1", "checkbox", "First", "//first"), "yes"),
        (FormField("2", "checkbox", "Second", "//second"), "yes"),
    ]
    calls = 0
    observed = []

    async def checkpoint():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise runner.ApplicationCancelled

    class Stagehand:
        async def observe(self, instruction, page=None):
            observed.append(instruction)
            return type("Result", (), {"data": []})()

    with pytest.raises(runner.ApplicationCancelled):
        await tier2_resolve.resolve_and_execute(
            Stagehand(), object(), fields, checkpoint
        )

    assert len(observed) == 1
