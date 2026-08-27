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


def test_detects_we_sent_a_code_via_security_code_phrasing():
    tree = "[1] StaticText: We sent a security code to your email\n"
    assert detect_2fa(tree) is True


def test_ordinary_form_returns_false():
    tree = (
        "[1] textbox: First Name\n"
        "[2] textbox: Email\n"
        "[3] combobox: Country\n"
    )
    assert detect_2fa(tree) is False


def test_empty_tree_returns_false():
    assert detect_2fa("") is False


def test_case_insensitive():
    assert detect_2fa("[1] textbox: VERIFICATION CODE\n") is True
