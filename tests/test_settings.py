import json
import os

from app import settings, state


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def test_load_ignores_unknown_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("SKPORT_DATA_DIR", str(tmp_path))
    _write(str(tmp_path / "settings.json"), {"telegram": True, "claimed_day": 15, "refresh_minutes": 60})
    settings.load_settings()
    assert state.state["settings"] == {"telegram": True, "claimed_day": 15}


def test_load_missing_file_uses_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("SKPORT_DATA_DIR", str(tmp_path))
    settings.load_settings()
    assert state.state["settings"] == {"telegram": True, "claimed_day": 0}


def test_load_broken_file_uses_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("SKPORT_DATA_DIR", str(tmp_path))
    p = tmp_path / "settings.json"
    p.write_text("{broken", encoding="utf-8")
    settings.load_settings()
    assert state.state["settings"]["telegram"] is True


def test_load_validation_error_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("SKPORT_DATA_DIR", str(tmp_path))
    _write(str(tmp_path / "settings.json"), {"telegram": "yes-please", "claimed_day": "many"})
    settings.load_settings()
    assert state.state["settings"] == {"telegram": True, "claimed_day": 0}


def test_save_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("SKPORT_DATA_DIR", str(tmp_path))
    settings.save_settings(settings.Settings(telegram=False, claimed_day=15))
    with open(tmp_path / "settings.json", encoding="utf-8") as f:
        assert json.load(f) == {"telegram": False, "claimed_day": 15}
