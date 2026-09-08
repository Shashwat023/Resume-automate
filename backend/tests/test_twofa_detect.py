from app.services.engine.twofa_detect import detect_2fa


def test_detects_verification_code_textbox():
    tree = "            [1-1] textbox: Verification Code\n"
    assert detect_2fa(tree) is True


def test_detects_one_time_passcode_variants():
    assert detect_2fa("[1] textbox: Enter your one-time passcode\n") is True
    assert detect_2fa("[1] textbox: One-time code\n") is True


def test_detects_otp_abbreviation():
    assert detect_2fa("[1] textbox: Enter OTP\n") is True


def test_detects_authenticator_app_heading():
    tree = "[1] heading: Open your authenticator app and enter the code\n"
    assert detect_2fa(tree) is True


def test_detects_two_factor_heading():
    assert detect_2fa("[1] heading: Two-Factor Authentication Required\n") is True
    assert detect_2fa("[1] heading: 2FA Required\n") is True


def test_body_prose_alone_does_not_trigger_a_pause():
    # Deliberate behavior change. A match here PAUSES the application and
    # waits for a human indefinitely, which is indistinguishable from a
    # freeze — so prose is not enough evidence. Previously EVERY line of
    # the whole page tree was scanned, so a security-role job description,
    # a privacy footer, or a cookie banner mentioning these words would
    # strand the run (and, via the per-profile lock, every later
    # application for that profile too).
    assert (
        detect_2fa("[1] StaticText: We sent a security code to your email\n") is False
    )
    assert (
        detect_2fa(
            "[7] StaticText: You will help us build two-factor authentication "
            "and one-time passcode flows for millions of users.\n"
        )
        is False
    )


def test_real_challenge_still_detected_when_prose_accompanies_it():
    # The prose above is safe to ignore precisely BECAUSE a genuine
    # challenge always also renders the input the code goes into.
    tree = (
        "[1] StaticText: We sent a security code to your email\n"
        "  [2] textbox: Security code\n"
    )
    assert detect_2fa(tree) is True


def test_ordinary_form_returns_false():
    tree = "[1] textbox: First Name\n[2] textbox: Email\n[3] combobox: Country\n"
    assert detect_2fa(tree) is False


def test_empty_tree_returns_false():
    assert detect_2fa("") is False


def test_case_insensitive():
    assert detect_2fa("[1] textbox: VERIFICATION CODE\n") is True
