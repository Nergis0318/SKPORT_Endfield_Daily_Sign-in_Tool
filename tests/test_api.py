import json

from fastapi.testclient import TestClient

import app.main as main
from app import scheduler, state


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("SKPORT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SKPORT_DISABLE_BOOT", "1")
    state.state.update({"last_status": "-", "last_run": "-", "next_run": "-", "log": []})
    state.state["settings"] = {"telegram": True, "claimed_day": 0}
    return TestClient(main.app)


def test_index_html(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        r = c.get("/")
        assert r.status_code == 200
        assert "SKPORT 에이전트" in r.text


def test_status_shape(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        r = c.get("/api/status")
        assert r.status_code == 200
        data = r.json()
        assert data["settings"] == {"telegram": True, "claimed_day": 0}
        assert data["last_status"] == "-"
        assert data["has_session"] in (True, False)


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