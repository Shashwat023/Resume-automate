import pytest

from app.services.captcha.proxy import parse_proxy_url


def test_parses_scheme_host_port_and_credentials():
    proxy = parse_proxy_url("http://user:pass@proxy.example.com:8080")

    assert proxy.scheme == "http"
    assert proxy.host == "proxy.example.com"
    assert proxy.port == 8080
    assert proxy.username == "user"
    assert proxy.password == "pass"


def test_parses_proxy_without_credentials():
    proxy = parse_proxy_url("socks5://proxy.example.com:1080")

    assert proxy.username is None
    assert proxy.password is None


def test_server_url_is_scheme_host_port_only_no_credentials():
    # For Stagehand's local_browser.launch(proxy_server=...) — credentials
    # are passed as separate proxy_username/proxy_password kwargs, not
    # embedded in the server URL.
    proxy = parse_proxy_url("http://user:pass@proxy.example.com:8080")

    assert proxy.server_url == "http://proxy.example.com:8080"


def test_twocaptcha_proxy_dict_includes_credentials_in_uri():
    proxy = parse_proxy_url("https://user:pass@proxy.example.com:8080")

    assert proxy.twocaptcha_proxy == {
        "type": "HTTPS",
        "uri": "user:pass@proxy.example.com:8080",
    }


def test_twocaptcha_proxy_dict_without_credentials():
    proxy = parse_proxy_url("http://proxy.example.com:3128")

    assert proxy.twocaptcha_proxy == {"type": "HTTP", "uri": "proxy.example.com:3128"}


def test_invalid_proxy_url_raises_clear_error():
    with pytest.raises(ValueError, match="Invalid proxy URL"):
        parse_proxy_url("not-a-valid-url")


def test_missing_port_raises_clear_error():
    with pytest.raises(ValueError, match="Invalid proxy URL"):
        parse_proxy_url("http://proxy.example.com")
