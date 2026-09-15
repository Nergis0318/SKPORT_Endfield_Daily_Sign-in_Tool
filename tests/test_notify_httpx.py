import asyncio
import httpx

from app import notify, state


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=15)


def test_send_telegram_posts():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.read().decode()
        return httpx.Response(200)

    ok = asyncio.run(notify.send_telegram("TOKEN", "123", "hi", client=_client(handler)))
    assert ok is True
    assert seen["url"] == "https://api.telegram.org/botTOKEN/sendMessage"
    assert "chat_id=123" in seen["body"] and "text=hi" in seen["body"]


def test_send_telegram_false_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    assert asyncio.run(notify.send_telegram("T", "1", "x", client=_client(handler))) is False


def test_send_telegram_false_on_network_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    assert asyncio.run(notify.send_telegram("T", "1", "x", client=_client(handler))) is False


def test_send_telegram_missing_creds():
    assert asyncio.run(notify.send_telegram("", "", "x")) is False


def test_notify_gated_by_settings(monkeypatch):
    calls = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    state.state["settings"] = {"telegram": False, "claimed_day": 0}

    async def fake(bot, chat, text, client=None):
        calls.append(text)
        return True

    monkeypatch.setattr(notify, "send_telegram", fake)
    asyncio.run(notify.notify("hello"))
    assert calls == []


def test_owned_client_closed(monkeypatch):
    """client 미주입 시 자체 생성 AsyncClient는 aclose 되어야 한다."""
    closed = []
    real = httpx.AsyncClient

    class Tracking(real):
        def __init__(self, *a, **kw):
            kw["transport"] = httpx.MockTransport(lambda r: httpx.Response(200))
            super().__init__(*a, **kw)

        async def aclose(self):
            closed.append(True)
            await super().aclose()

    monkeypatch.setattr(httpx, "AsyncClient", Tracking)
    assert asyncio.run(notify.send_telegram("T", "1", "x")) is True
    assert closed == [True]


def test_injected_client_not_closed():
    """client 주입 시 소유자가 아니므로 aclose 하면 안 된다."""
    closed = []
    c = _client(lambda r: httpx.Response(200))
    orig = c.aclose

    async def tracking():
        closed.append(True)
        await orig()

    c.aclose = tracking
    assert asyncio.run(notify.send_telegram("T", "1", "x", client=c)) is True
    assert closed == []
    asyncio.run(c.aclose())  # 정리

