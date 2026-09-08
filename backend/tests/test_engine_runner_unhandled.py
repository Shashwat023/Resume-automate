from app.services.engine.runner import FillCascadeResult, _unhandled_labels
from app.services.engine.tier0_harvest import FormField, HarvestResult
from app.services.engine.tier1_map import Tier1Result
from app.services.engine.tier2_resolve import Tier2Result


def _cascade(
    fields,
    tier0_filled=(),
    tier1_filled=(),
    from_library=(),
    tier2_resolved=(),
    tier2_errored=(),
):
    return FillCascadeResult(
        fields=fields,
        tier0=HarvestResult(filled=list(tier0_filled), unmatched=[], errored=[]),
        tier1=Tier1Result(
            filled=list(tier1_filled),
            from_library=list(from_library),
            for_tier2=[],
            low_confidence_filled=[],
            unanswered=[],
            errored=[],
            usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        ),
        tier2=Tier2Result(resolved=list(tier2_resolved), errored=list(tier2_errored)),
    )


def test_a_field_tier1_decided_but_tier2_never_clicked_is_still_unhandled():
    # Real bug found live (FLAGGED.md): tier1_map.py's map_fields appends
    # to `from_library` the moment a cached ANSWER exists for a label —
    # unconditionally, before it's known whether that field is a direct
    # fill or a for_tier2 custom widget. Treating `from_library` as
    # "handled" here previously let a field Tier 2 explicitly FAILED to
    # click (still logged in tier2.errored) count as complete, which
    # skipped both the pre-submit and post-validation-error repair passes
    # entirely. This is the exact real shape: 'Country' had a cached
    # answer (from_library) but Tier 2's click failed (tier2.errored).
    field = FormField(node_id="1", role="combobox", label="Country", xpath="//x")
    cascade = _cascade(
        fields=[field],
        from_library=[("Country", "India")],
        tier2_errored=[
            ("Country", "Failed to perform act: -32602 Invalid mouse button")
        ],
    )

    assert _unhandled_labels(cascade) == {"Country"}


def test_a_field_tier2_actually_resolved_is_handled():
    field = FormField(node_id="1", role="combobox", label="Country", xpath="//x")
    cascade = _cascade(
        fields=[field],
        from_library=[("Country", "India")],
        tier2_resolved=[("Country", "Selected India")],
    )

    assert _unhandled_labels(cascade) == set()


def test_a_directly_filled_textbox_is_handled_without_tier2():
    field = FormField(node_id="1", role="textbox", label="First Name", xpath="//x")
    cascade = _cascade(fields=[field], tier1_filled=[("First Name", "Jordan")])

    assert _unhandled_labels(cascade) == set()


def test_a_field_with_no_result_anywhere_is_unhandled():
    field = FormField(node_id="1", role="checkbox", label="I agree", xpath="//x")
    cascade = _cascade(fields=[field])

    assert _unhandled_labels(cascade) == {"I agree"}


async def test_required_unhandled_field_pauses_for_manual_input(
    async_session, monkeypatch
):
    # Real gap reported live: fields like 'Please read the arbitration
    # agreement below' ask the applicant to read an embedded document, not
    # just pick from options a model can infer — no amount of retrying
    # observe()/act() fixes that. This is the fallback: pause and hand the
    # page to the user, the same pattern already used for CAPTCHA/2FA.
    from app.services.engine import runner
    from app.models.db_models import Application, Job, Profile
    from app.domain import status as st

    profile = Profile(full_name="Jordan Smith", email="j@example.com", phone="123")
    async_session.add(profile)
    await async_session.commit()
    await async_session.refresh(profile)

    job = Job(
        title="Engineer",
        company_name="Acme",
        location="Remote",
        status="active",
        apply_url="https://example.com/apply",
    )
    async_session.add(job)
    await async_session.commit()
    await async_session.refresh(job)

    application = Application(profile_id=profile.id, job_id=job.id, status=st.RUNNING)
    async_session.add(application)
    await async_session.commit()
    await async_session.refresh(application)

    async def _fake_session_factory():
        yield async_session

    class _CtxWrapper:
        def __aiter__(self):
            return _fake_session_factory()

        async def __aenter__(self):
            return async_session

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(runner, "async_session_factory", lambda: _CtxWrapper())

    resume_calls = []

    async def _fake_wait_for_resume_or_cancel(app_id):
        resume_calls.append(app_id)
        return "resumed"

    monkeypatch.setattr(
        runner, "wait_for_resume_or_cancel", _fake_wait_for_resume_or_cancel
    )

    required_field = FormField(
        node_id="1",
        role="combobox",
        label="Please read the arbitration agreement below",
        xpath="//x",
        required=True,
    )
    optional_field = FormField(
        node_id="2",
        role="textbox",
        label="Publications URL",
        xpath="//y",
        required=False,
    )
    cascade = _cascade(fields=[required_field, optional_field])

    await runner._escalate_unhandled_fields_if_any(application.id, cascade)

    assert resume_calls == [application.id]
    await async_session.refresh(application)
    # Resumed and cleared by the end of the call — a real live-view pause
    # happened in between (status was set to NEEDS_INPUT before the wait).
    assert application.status == st.RUNNING
    assert application.pause_reason is None


async def test_only_optional_fields_unhandled_does_not_pause(
    async_session, monkeypatch
):
    from app.services.engine import runner
    from app.models.db_models import Application, Job, Profile
    from app.domain import status as st

    profile = Profile(full_name="Jordan Smith", email="j@example.com", phone="123")
    async_session.add(profile)
    await async_session.commit()
    await async_session.refresh(profile)

    job = Job(
        title="Engineer",
        company_name="Acme",
        location="Remote",
        status="active",
        apply_url="https://example.com/apply",
    )
    async_session.add(job)
    await async_session.commit()
    await async_session.refresh(job)

    application = Application(profile_id=profile.id, job_id=job.id, status=st.RUNNING)
    async_session.add(application)
    await async_session.commit()
    await async_session.refresh(application)

    async def _boom(app_id):
        raise AssertionError("must not pause when nothing unhandled is required")

    monkeypatch.setattr(runner, "wait_for_resume_or_cancel", _boom)

    optional_field = FormField(
        node_id="2",
        role="textbox",
        label="Publications URL",
        xpath="//y",
        required=False,
    )
    cascade = _cascade(fields=[optional_field])

    await runner._escalate_unhandled_fields_if_any(application.id, cascade)

    await async_session.refresh(application)
    assert application.status == st.RUNNING
    assert application.pause_reason is None
