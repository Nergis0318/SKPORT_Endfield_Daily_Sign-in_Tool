import urllib.error

import checkin


class FakeResp:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_send_telegram_posts(monkeypatch):
    seen = {}

    def fake_urlopen(url, data, timeout):
        seen["url"] = url
        seen["data"] = data
        return FakeResp()

    monkeypatch.setattr(checkin.urllib.request, "urlopen", fake_urlopen)
    assert checkin.send_telegram("TOKEN", "123", "hi") is True
    assert seen["url"] == "https://api.telegram.org/botTOKEN/sendMessage"
    assert b"chat_id=123" in seen["data"]
    assert b"text=hi" in seen["data"]


def test_send_telegram_false_on_error(monkeypatch):
    def boom(url, data, timeout):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(checkin.urllib.request, "urlopen", boom)
    assert checkin.send_telegram("T", "1", "x") is False


def test_send_telegram_missing_creds():
    assert checkin.send_telegram("", "", "x") is False


def test_notify_disabled(monkeypatch):
    monkeypatch.setenv("TELEGRAM_NOTIFY", "false")
    assert checkin.notify_enabled() is False
