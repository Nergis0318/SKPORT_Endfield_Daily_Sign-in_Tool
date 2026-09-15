from app import state


def test_state_shape():
    assert state.state["settings"] == {"telegram": True, "claimed_day": 0}
    assert state.state["last_status"] == "-"
    assert state.LOGIN_WINDOW_MINUTES == 10
    assert (state.VNC_HOST, state.VNC_PORT) == ("127.0.0.1", 5900)


def test_add_log_caps_at_20():
    state.state["log"] = []
    for i in range(25):
        state.add_log(f"m{i}")
    assert len(state.state["log"]) == 20
    assert state.state["log"][-1].endswith("m24")


def test_data_dir_env(monkeypatch):
    monkeypatch.setenv("SKPORT_DATA_DIR", "/tmp/x")
    assert state.get_settings_file() == "/tmp/x/settings.json"
