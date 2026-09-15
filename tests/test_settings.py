import json
import os

from app import settings, state

_NOTIFICATION_ENV = (
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_MENTION_ID",
    "DISCORD_WEBHOOK_URL",
)

_FULL_DEFAULTS = {
    "telegram": True,
    "discord": True,
    "claimed_day": 0,
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "telegram_mention_id": "",
    "discord_webhook_url": "",
}


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def _clear_env(monkeypatch):
    for key in _NOTIFICATION_ENV:
        monkeypatch.delenv(key, raising=False)


def test_load_ignores_unknown_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("SKPORT_DATA_DIR", str(tmp_path))
    _clear_env(monkeypatch)
    _write(str(tmp_path / "settings.json"), {"telegram": True, "claimed_day": 15, "refresh_minutes": 60})
    settings.load_settings()
    assert state.state["settings"] == {**_FULL_DEFAULTS, "claimed_day": 15}


def test_load_missing_file_uses_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("SKPORT_DATA_DIR", str(tmp_path))
    _clear_env(monkeypatch)
    settings.load_settings()
    assert state.state["settings"] == _FULL_DEFAULTS


def test_load_broken_file_uses_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("SKPORT_DATA_DIR", str(tmp_path))
    _clear_env(monkeypatch)
    p = tmp_path / "settings.json"
    p.write_text("{broken", encoding="utf-8")
    settings.load_settings()
    assert state.state["settings"]["telegram"] is True


def test_load_validation_error_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("SKPORT_DATA_DIR", str(tmp_path))
    _clear_env(monkeypatch)
    _write(str(tmp_path / "settings.json"), {"telegram": "yes-please", "claimed_day": "many"})
    settings.load_settings()
    assert state.state["settings"] == _FULL_DEFAULTS


def test_save_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("SKPORT_DATA_DIR", str(tmp_path))
    settings.save_settings(settings.Settings(
        telegram=False,
        discord=False,
        claimed_day=15,
        telegram_bot_token="T",
        telegram_chat_id="C",
        telegram_mention_id="M",
        discord_webhook_url="https://d",
    ))
    with open(tmp_path / "settings.json", encoding="utf-8") as f:
        assert json.load(f) == {
            "telegram": False,
            "discord": False,
            "claimed_day": 15,
            "telegram_bot_token": "T",
            "telegram_chat_id": "C",
            "telegram_mention_id": "M",
            "discord_webhook_url": "https://d",
        }


def test_load_seeds_notification_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SKPORT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "ENVTOK")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    monkeypatch.setenv("TELEGRAM_MENTION_ID", "7")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://env/hook")
    settings.load_settings()
    s = state.state["settings"]
    assert s["telegram_bot_token"] == "ENVTOK"
    assert s["telegram_chat_id"] == "42"
    assert s["telegram_mention_id"] == "7"
    assert s["discord_webhook_url"] == "https://env/hook"


def test_saved_notification_fields_win_over_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SKPORT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "ENVTOK")
    _write(str(tmp_path / "settings.json"), {"telegram_bot_token": "FILETOK"})
    settings.load_settings()
    assert state.state["settings"]["telegram_bot_token"] == "FILETOK"
