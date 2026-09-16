import asyncio
import concurrent.futures
import datetime
import json
import threading

import pytest

import checkin
from app import runner, scheduler, settings, state


class _Recorder:
    """runner.executor 대역. submit 호출을 기록하고 완료된 Future를 반환."""

    def __init__(self, calls):
        self.calls = calls

    def submit(self, fn, *args):
        self.calls.append((fn.__name__, args))
        fut = concurrent.futures.Future()
        fut.set_result(None)
        return fut


def _reset():
    state.state.update(
        {"last_status": "-", "last_run": "-", "next_run": "-", "log": []}
    )
    state.state["settings"] = {"telegram": True, "claimed_day": 0}
    state.login_open.clear()
    state.close_requested.clear()


class _FakeBrowser:
    """sync_playwright()/launch_browser() 대역. 브라우저 없이 대기 로직만 검증."""

    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def new_context(self, **kwargs):
        return self

    def new_page(self):
        return self

    def goto(self, url, timeout=None):
        self.log.append(("goto", url))

    def storage_state(self, path=None):
        self.log.append(("storage_state", path))

    def close(self):
        self.log.append(("close",))


def _fake_playwright(monkeypatch, log):
    monkeypatch.setattr(
        "playwright.sync_api.sync_playwright", lambda: _FakeBrowser(log)
    )
    monkeypatch.setattr(checkin, "launch_browser", lambda pw: _FakeBrowser(log))


def test_next_check_before_target(monkeypatch):
    monkeypatch.setenv("SKPORT_CHECK_TIME", "01:23")
    now = datetime.datetime(2026, 9, 15, 0, 0, tzinfo=state.UTC8)
    delay, target = runner.next_check_delay(now)
    assert delay == 83 * 60  # 00:00 → 01:23 = 83분
    assert (target.hour, target.minute, target.day) == (1, 23, 15)


def test_next_check_after_target_rolls_next_day(monkeypatch):
    monkeypatch.setenv("SKPORT_CHECK_TIME", "01:23")
    now = datetime.datetime(2026, 9, 15, 2, 0, tzinfo=state.UTC8)
    delay, target = runner.next_check_delay(now)
    assert (target.hour, target.minute, target.day) == (1, 23, 16)
    assert delay == pytest.approx(23 * 3600 + 23 * 60)


def test_check_hour_minute_invalid(monkeypatch):
    monkeypatch.setenv("SKPORT_CHECK_TIME", "junk")
    assert runner.check_hour_minute() == (1, 23)


def test_do_cycle_success_saves_and_notifies(monkeypatch, tmp_path):
    _reset()
    monkeypatch.setenv("SKPORT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(runner, "_run_once", lambda: ("success", 15))
    sent = []
    monkeypatch.setattr("app.runner.notify_sync", lambda t: sent.append(t))
    runner.do_cycle("테스트")
    assert state.state["settings"]["claimed_day"] == 15
    assert state.state["last_status"] == "success"
    assert any("출석 완료" in m for m in sent)


def test_do_cycle_does_not_persist_env_secrets(monkeypatch, tmp_path):
    """claimed_day 저장이 env로만 준 자격증명을 settings.json에 굳히면 안 된다."""
    _reset()
    monkeypatch.setenv("SKPORT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "ENVTOK")
    state.state["settings"] = {
        "telegram": True,
        "discord": True,
        "claimed_day": 0,
        "telegram_bot_token": "ENVTOK",
        "telegram_chat_id": "",
        "telegram_mention_id": "",
        "discord_webhook_url": "",
    }
    monkeypatch.setattr(runner, "_run_once", lambda: ("success", 15))
    monkeypatch.setattr("app.runner.notify_sync", lambda t: None)
    runner.do_cycle("test")
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved["claimed_day"] == 15
    assert saved.get("telegram_bot_token", "") == ""


def test_do_cycle_duplicate_already_no_notify(monkeypatch, tmp_path):
    _reset()
    monkeypatch.setenv("SKPORT_DATA_DIR", str(tmp_path))
    state.state["settings"] = {"telegram": True, "claimed_day": 15}
    state.state["last_status"] = (
        "already"  # 진짜 중복: 이전 상태도 already여야 조용함 (manager.py elif status != prev 규칙 유지)
    )
    monkeypatch.setattr(runner, "_run_once", lambda: ("already", 15))
    sent = []
    monkeypatch.setattr("app.runner.notify_sync", lambda t: sent.append(t))
    runner.do_cycle("테스트")
    assert sent == []


def test_do_cycle_notify_follows_language(monkeypatch, tmp_path):
    """알림 문구와 사유가 설정 언어를 따른다 (en이면 한국어가 남지 않아야 한다).

    언어는 UI와 같은 경로(settings.json)로 저장한다 — claimed_day 저장이 state를
    파일 기준으로 다시 만들기 때문에 메모리 값만 바꾸면 사라진다.
    """
    _reset()
    monkeypatch.setenv("SKPORT_DATA_DIR", str(tmp_path))
    settings.save_settings(settings.Settings(language="en"))
    settings.load_settings()
    monkeypatch.setattr(runner, "_run_once", lambda: ("success", 15))
    sent = []
    monkeypatch.setattr("app.runner.notify_sync", lambda t: sent.append(t))
    runner.do_cycle("수동 실행")
    assert len(sent) == 1
    assert "check-in complete" in sent[0]
    assert "출석 완료" not in sent[0]
    assert "[Manual run]" in sent[0]


def test_do_cycle_skipped_while_login_open(monkeypatch):
    _reset()
    state.login_open.set()
    called = []
    monkeypatch.setattr(runner, "_run_once", lambda: called.append(1) or ("success", 1))
    runner.do_cycle("테스트")
    assert called == []
    state.login_open.clear()


def test_do_cycle_login_required_queues_login_window(monkeypatch, tmp_path):
    _reset()
    monkeypatch.setenv("SKPORT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(runner, "_run_once", lambda: ("login_required", 15))
    monkeypatch.setattr("app.runner.notify_sync", lambda t: None)
    queued = []
    monkeypatch.setattr(
        runner.executor, "submit", lambda fn, *a: queued.append((fn.__name__, a))
    )
    runner.do_cycle("테스트")
    assert queued == [("do_login_window", ("세션 만료",))]


def test_login_window_closes_immediately_on_request(monkeypatch, tmp_path):
    """즉시 종료 요청이 오면 10분 대기 중이라도 브라우저를 닫고 세션을 저장해야 한다."""
    _reset()
    monkeypatch.setenv("SKPORT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("app.runner.notify_sync", lambda t: None)
    log = []
    _fake_playwright(monkeypatch, log)

    def _click_close():  # API 스레드가 이벤트를 set하는 상황
        state.login_open.wait(5)
        state.close_requested.set()

    threading.Thread(target=_click_close, daemon=True).start()
    done = threading.Event()

    def _run():
        runner.do_login_window("테스트", minutes=10)
        done.set()

    threading.Thread(target=_run, daemon=True).start()
    assert done.wait(5), "즉시 종료 요청 후에도 로그인 창이 닫히지 않음"
    assert ("storage_state", checkin.STATE_FILE) in log  # 종료 직전 세션 저장은 유지
    assert ("close",) in log
    assert not state.login_open.is_set()
    assert not state.close_requested.is_set()  # 다음 창을 위해 초기화


def test_request_close_noop_without_open_window():
    _reset()
    assert runner.request_close() is False
    assert not state.close_requested.is_set()


def test_request_close_signals_open_window():
    _reset()
    state.login_open.set()
    assert runner.request_close() is True
    assert state.close_requested.is_set()


def test_daily_cron_registers(monkeypatch):
    monkeypatch.setenv("SKPORT_CHECK_TIME", "01:23")
    monkeypatch.setenv("SKPORT_DISABLE_BOOT", "1")

    async def go():
        scheduler.start()
        try:
            job = scheduler.scheduler.get_job("daily")
            assert job is not None
            trig = str(job.trigger)
            assert "hour='1'" in trig and "minute='23'" in trig
            assert job.args == ("01:23 정기 실행",)
            nxt = job.next_run_time
            assert (nxt.hour, nxt.minute) == (1, 23)
            return nxt
        finally:
            scheduler.shutdown()

    nxt = asyncio.run(go())
    _, target = runner.next_check_delay()
    assert nxt.strftime("%Y-%m-%d %H:%M") == target.strftime("%Y-%m-%d %H:%M")


def test_boot_disabled_registers_only_daily(monkeypatch):
    monkeypatch.setenv("SKPORT_DISABLE_BOOT", "1")

    async def go():
        scheduler.start()
        try:
            return sorted(j.id for j in scheduler.scheduler.get_jobs())
        finally:
            scheduler.shutdown()

    assert asyncio.run(go()) == ["daily"]


def test_request_cycle_queues_job(monkeypatch):
    monkeypatch.setenv("SKPORT_DISABLE_BOOT", "1")

    async def go():
        scheduler.start()
        try:
            assert scheduler.request_cycle() is True
            return scheduler.scheduler.get_job("once-cycle") is not None
        finally:
            scheduler.shutdown()

    assert asyncio.run(go()) is True


def test_boot_login_run_date_is_tz_aware_now(monkeypatch, tmp_path):
    """B1 회귀: naive datetime.now()면 UTC8 기준 8h(또는 호스트 로컬 오프셋)만큼 벌어진다."""
    monkeypatch.delenv("SKPORT_DISABLE_BOOT", raising=False)
    monkeypatch.setattr(checkin, "STATE_FILE", str(tmp_path / "absent.json"))
    monkeypatch.setattr(runner, "executor", _Recorder([]))

    async def go():
        scheduler.start()
        try:
            job = scheduler.scheduler.get_job("boot-login")
            assert job is not None
            nxt = job.next_run_time
            assert nxt.utcoffset() == datetime.timedelta(
                hours=8
            )  # naive면 8h 오프셋이 아니거나 8h 벌어짐
            delta = abs((nxt - datetime.datetime.now(state.UTC8)).total_seconds())
            assert delta < 10
        finally:
            scheduler.shutdown()

    asyncio.run(go())


def test_boot_cycle_when_unclaimed(monkeypatch, tmp_path):
    monkeypatch.delenv("SKPORT_DISABLE_BOOT", raising=False)
    session = tmp_path / "session.json"
    session.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(checkin, "STATE_FILE", str(session))
    monkeypatch.setattr(runner, "executor", _Recorder([]))
    state.state["settings"] = {"telegram": True, "claimed_day": 0}

    async def go():
        scheduler.start()
        try:
            return sorted(j.id for j in scheduler.scheduler.get_jobs())
        finally:
            scheduler.shutdown()

    ids = asyncio.run(go())
    assert "boot-cycle" in ids
    assert "boot-login" not in ids


def test_no_boot_jobs_when_claimed_today(monkeypatch, tmp_path):
    monkeypatch.delenv("SKPORT_DISABLE_BOOT", raising=False)
    session = tmp_path / "session.json"
    session.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(checkin, "STATE_FILE", str(session))
    monkeypatch.setattr(runner, "executor", _Recorder([]))
    state.state["settings"] = {
        "telegram": True,
        "claimed_day": datetime.datetime.now(state.UTC8).day,
    }

    async def go():
        scheduler.start()
        try:
            return sorted(j.id for j in scheduler.scheduler.get_jobs())
        finally:
            scheduler.shutdown()

    ids = asyncio.run(go())
    assert "boot-cycle" not in ids
    assert "boot-login" not in ids


def test_cycle_job_routes_through_executor(monkeypatch):
    calls = []
    monkeypatch.setattr(runner, "executor", _Recorder(calls))
    asyncio.run(scheduler._cycle_job("수동 실행"))
    assert calls == [("do_cycle", ("수동 실행",))]


def test_login_job_routes_through_executor(monkeypatch):
    calls = []
    monkeypatch.setattr(runner, "executor", _Recorder(calls))
    asyncio.run(scheduler._login_job("세션 만료", 10))
    assert calls == [("do_login_window", ("세션 만료", 10))]
