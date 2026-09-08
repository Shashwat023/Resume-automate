"""
Shared proxy-URL parsing for chrome_launcher.py (browser egress) and
solver.py (2captcha solve egress). Both MUST route through the same proxy
— see config.py's captcha_proxy_url docstring for why a mismatch is the
root cause of a real "Please complete the reCAPTCHA" rejection despite a
genuinely solved token: Google binds the token to the IP that solved it,
and rejects if the submitting IP differs.
"""

from dataclasses import dataclass
from urllib.parse import urlparse

_TWOCAPTCHA_TYPE_BY_SCHEME = {
    "http": "HTTP",
    "https": "HTTPS",
    "socks4": "SOCKS4",
    "socks5": "SOCKS5",
}


@dataclass
class ProxyConfig:
    scheme: str  # "http" | "https" | "socks4" | "socks5"
    host: str
    port: int
    username: str | None = None
    password: str | None = None

    @property
    def server_url(self) -> str:
        """For Stagehand's local_browser.launch(proxy_server=...)."""
        return f"{self.scheme}://{self.host}:{self.port}"

    @property
    def twocaptcha_proxy(self) -> dict[str, str]:
        """For 2captcha SDK's recaptcha(proxy={...}) kwarg."""
        proxy_type = _TWOCAPTCHA_TYPE_BY_SCHEME.get(self.scheme, "HTTP")
        uri = f"{self.host}:{self.port}"
        if self.username:
            auth = (
                self.username
                if not self.password
                else f"{self.username}:{self.password}"
            )
            uri = f"{auth}@{uri}"
        return {"type": proxy_type, "uri": uri}


def parse_proxy_url(url: str) -> ProxyConfig:
    parsed = urlparse(url)
    if not parsed.hostname or not parsed.port:
        raise ValueError(
            f"Invalid proxy URL {url!r} — expected 'scheme://[user:pass@]host:port'"
        )
    return ProxyConfig(
        scheme=(parsed.scheme or "http").lower(),
        host=parsed.hostname,
        port=parsed.port,
        username=parsed.username,
        password=parsed.password,
    )
