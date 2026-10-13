from app.services.browser.live_view import LiveViewProxy


class _Proxy(LiveViewProxy):
    def __init__(self):
        super().__init__(session=None)
        self.sent: list[tuple[str, dict]] = []

    async def send(self, method, params=None):
        self.sent.append((method, params or {}))
        return {}


async def test_wheel_is_forwarded_as_a_mouse_wheel_event():
    proxy = _Proxy()

    await proxy.dispatch_wheel(10, 20, 0, 120)

    method, params = proxy.sent[0]
    assert method == "Input.dispatchMouseEvent"
    assert params["type"] == "mouseWheel"
    assert (params["x"], params["y"], params["deltaY"]) == (10, 20, 120)


async def test_key_codes_and_modifiers_are_forwarded_for_editing_keys():
    proxy = _Proxy()

    await proxy.dispatch_key(
        "keyDown", None, "Backspace", code="Backspace", key_code=8, modifiers=2
    )

    _method, params = proxy.sent[0]
    assert params["windowsVirtualKeyCode"] == 8
    assert params["nativeVirtualKeyCode"] == 8
    assert params["code"] == "Backspace"
    assert params["modifiers"] == 2
    assert "text" not in params


async def test_plain_text_key_keeps_working_without_codes():
    proxy = _Proxy()

    await proxy.dispatch_key("keyDown", "a", "a")

    assert proxy.sent[0][1] == {"type": "keyDown", "text": "a", "key": "a"}
