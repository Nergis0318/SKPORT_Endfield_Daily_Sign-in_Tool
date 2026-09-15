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


def test_send_telegram_mention_prepended_html():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read().decode()
        return httpx.Response(200)

    ok = asyncio.run(notify.send_telegram("T", "1", "hello", mention_id="12345", client=_client(handler)))
    assert ok is True
    body = seen["body"]
    assert "parse_mode=HTML" in body
    assert "tg%3A%2F%2Fuser%3Fid%3D12345" in body  # URL 인코딩된 tg://user?id=12345
    assert "hello" in body


def test_send_telegram_no_mention_has_no_html():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read().decode()
        return httpx.Response(200)

    asyncio.run(notify.send_telegram("T", "1", "hello", mention_id="", client=_client(handler)))
    assert "tg%3A%2F%2Fuser" not in seen["body"]
    assert "hello" in seen["body"]


def test_send_telegram_escapes_text():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read().decode()
        return httpx.Response(200)

    asyncio.run(notify.send_telegram("T", "1", "<b>&x</b>", mention_id="1", client=_client(handler)))
    body = seen["body"]
    # parse_mode=HTML이라 본문은 이스케이프되어 전송된다: <b>&x</b> → &lt;b&gt;&amp;x&lt;/b&gt;
    assert "%26lt%3Bb%26gt%3B" in body
    assert "%26amp%3B" in body
    assert "%3Cb%3E" not in body


def test_notify_uses_settings_mention(monkeypatch):
    calls = []

    async def fake_tg(bot, chat, text, mention_id="", client=None):
        calls.append((bot, chat, mention_id, text))
        return True

    monkeypatch.setattr(notify, "send_telegram", fake_tg)
    state.state["settings"] = {
        "telegram": True,
        "discord": False,
        "claimed_day": 0,
        "telegram_bot_token": "BT",
        "telegram_chat_id": "CC",
        "telegram_mention_id": "999",
        "discord_webhook_url": "",
    }
    asyncio.run(notify.notify("hi"))
    assert calls == [("BT", "CC", "999", "hi")]


def test_send_discord_posts():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.read().decode()
        return httpx.Response(204)

    ok = asyncio.run(notify.send_discord("https://discord.com/api/webhooks/1/abc", "hi", client=_client(handler)))
    assert ok is True
    assert seen["url"] == "https://discord.com/api/webhooks/1/abc"
    assert "content" in seen["body"] and "hi" in seen["body"]


def test_send_discord_false_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    assert asyncio.run(notify.send_discord("https://d", "x", client=_client(handler))) is False


def test_send_discord_false_on_network_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    assert asyncio.run(notify.send_discord("https://d", "x", client=_client(handler))) is False


def test_send_discord_missing_webhook():
    assert asyncio.run(notify.send_discord("", "x")) is False


def test_notify_gated_by_settings(monkeypatch):
    calls = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://d")
    state.state["settings"] = {"telegram": False, "discord": False, "claimed_day": 0}

    async def fake_tg(bot, chat, text, client=None):
        calls.append(("tg", text))
        return True

    async def fake_dc(url, text, client=None):
        calls.append(("dc", text))
        return True

    monkeypatch.setattr(notify, "send_telegram", fake_tg)
    monkeypatch.setattr(notify, "send_discord", fake_dc)
    asyncio.run(notify.notify("hello"))
    assert calls == []

    state.state["settings"] = {"telegram": True, "discord": True, "claimed_day": 0}
    asyncio.run(notify.notify("hello"))
    assert calls == [("tg", "hello"), ("dc", "hello")]


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

