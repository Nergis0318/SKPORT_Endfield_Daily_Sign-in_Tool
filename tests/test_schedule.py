import copy
import datetime

import pytest

import checkin
from app import runner, state


@pytest.fixture(autouse=True)
def _isolate_state():
    saved = copy.deepcopy(state.state)
    yield
    state.state.clear()
    state.state.update(saved)
    state.login_open.clear()


def _reset():
    state.state.update({"last_status": "-", "last_run": "-", "next_run": "-", "log": []})
    state.state["settings"] = {"telegram": True, "claimed_day": 0}
    state.login_open.clear()


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


def test_do_cycle_duplicate_already_no_notify(monkeypatch, tmp_path):
    _reset()
    monkeypatch.setenv("SKPORT_DATA_DIR", str(tmp_path))
    state.state["settings"] = {"telegram": True, "claimed_day": 15}
    state.state["last_status"] = "already"  # 진짜 중복: 이전 상태도 already여야 조용함 (manager.py elif status != prev 규칙 유지)
    monkeypatch.setattr(runner, "_run_once", lambda: ("already", 15))
    sent = []
    monkeypatch.setattr("app.runner.notify_sync", lambda t: sent.append(t))
    runner.do_cycle("테스트")
    assert sent == []


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
    monkeypatch.setattr(runner.executor, "submit", lambda fn, *a: queued.append((fn.__name__, a)))
    runner.do_cycle("테스트")
    assert queued == [("do_login_window", ("세션 만료",))]


import asyncio
import os

from app import runner, scheduler, state


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
