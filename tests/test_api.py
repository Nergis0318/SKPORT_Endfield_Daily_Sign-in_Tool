import json

from fastapi.testclient import TestClient

import app.main as main
from app import scheduler, state

_DEFAULTS = {
    "telegram": True,
    "discord": True,
    "claimed_day": 0,
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "telegram_mention_id": "",
    "discord_webhook_url": "",
}


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("SKPORT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SKPORT_DISABLE_BOOT", "1")
    for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TELEGRAM_MENTION_ID", "DISCORD_WEBHOOK_URL"):
        monkeypatch.delenv(key, raising=False)
    state.state.update({"last_status": "-", "last_run": "-", "next_run": "-", "log": []})
    state.state["settings"] = dict(_DEFAULTS)
    return TestClient(main.app)


def test_index_html(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        r = c.get("/")
        assert r.status_code == 200
        assert "SKPORT 에이전트" in r.text


def test_index_has_notification_inputs(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        html = c.get("/").text
        for field_id in ("botToken", "chatId", "mentionId", "discordUrl", "tg", "dc"):
            assert f'id="{field_id}"' in html


def test_status_shape(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        r = c.get("/api/status")
        assert r.status_code == 200
        data = r.json()
        assert data["settings"] == {**_DEFAULTS, "telegram_configured": False, "discord_configured": False}
        assert data["last_status"] == "-"
        assert data["has_session"] in (True, False)


def test_status_masks_secrets(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        state.state["settings"].update({
            "telegram_bot_token": "SECRETTOKEN",
            "discord_webhook_url": "https://secret/hook",
        })
        s = c.get("/api/status").json()["settings"]
        assert s["telegram_bot_token"] == ""
        assert s["discord_webhook_url"] == ""
        # 토큰 보유 여부는 플래그로 노출
        assert s["telegram_configured"] is True
        assert s["discord_configured"] is True


def test_settings_json_roundtrip(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        r = c.post("/api/settings", json={"telegram": False})
        assert r.status_code == 200
        assert r.json()["settings"]["telegram"] is False
        saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert saved["telegram"] is False


def test_settings_form_compat(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        r = c.post("/api/settings", content="telegram=on",
                   headers={"Content-Type": "application/x-www-form-urlencoded"})
        assert r.status_code == 200
        assert r.json()["settings"]["telegram"] is True


def test_settings_json_string_bool(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        r = c.post("/api/settings", json={"telegram": "false"})
        assert r.status_code == 200
        assert r.json()["settings"]["telegram"] is False


def test_settings_json_non_object_body_keeps_telegram(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        r = c.post("/api/settings", json=["telegram"])
        assert r.status_code == 200
        assert r.json()["settings"]["telegram"] is True


def test_settings_saves_notification_fields(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        r = c.post("/api/settings", json={
            "telegram": True,
            "discord": True,
            "telegram_bot_token": "TOK",
            "telegram_chat_id": "CHAT",
            "telegram_mention_id": "USER1",
            "discord_webhook_url": "https://d/hook",
        })
        assert r.status_code == 200
        saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert saved["telegram_bot_token"] == "TOK"
        assert saved["telegram_chat_id"] == "CHAT"
        assert saved["telegram_mention_id"] == "USER1"
        assert saved["discord_webhook_url"] == "https://d/hook"
        # 응답은 마스킹되고, 값 자체는 상태에 유지
        assert r.json()["settings"]["telegram_bot_token"] == ""
        assert state.state["settings"]["telegram_bot_token"] == "TOK"


def test_settings_blank_clears_to_env_fallback(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "ENVTOK")
        c.post("/api/settings", json={"telegram_bot_token": "USERTOK"})
        assert state.state["settings"]["telegram_bot_token"] == "USERTOK"
        # 빈 문자열 → 저장값 제거, env 폴백
        r = c.post("/api/settings", json={"telegram_bot_token": ""})
        assert r.status_code == 200
        assert state.state["settings"]["telegram_bot_token"] == "ENVTOK"
        saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert saved["telegram_bot_token"] == ""


def test_settings_omitted_fields_keep_values(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        c.post("/api/settings", json={"telegram_bot_token": "KEEP", "telegram_chat_id": "C1"})
        c.post("/api/settings", json={"telegram": False})
        assert state.state["settings"]["telegram_bot_token"] == "KEEP"
        assert state.state["settings"]["telegram_chat_id"] == "C1"


def test_cycle_and_login_queue(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(scheduler, "request_cycle", lambda: calls.append("cycle") or True)
    monkeypatch.setattr(scheduler, "request_login", lambda *a: calls.append("login") or True)
    with _client(tmp_path, monkeypatch) as c:
        assert c.post("/api/cycle").status_code == 202
        assert c.post("/api/login").status_code == 202
    assert calls == ["cycle", "login"]


def test_preview_503(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        assert c.get("/preview.png").status_code == 503
