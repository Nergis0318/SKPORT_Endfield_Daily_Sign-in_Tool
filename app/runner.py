"""출석 실행기. manager.py:45-61,92-173 이식. sync Playwright는 이 모듈에서만,
반드시 executor(단일 워커) 경유로 호출된다."""
import datetime
import os
import time
from concurrent.futures import ThreadPoolExecutor

import checkin

from app import state
from app.notify import notify_sync
from app.settings import Settings, save_settings

executor = ThreadPoolExecutor(max_workers=1)


def check_hour_minute():
    """매일 실행 시각(UTC+8). SKPORT_CHECK_TIME="01:23" 로 변경 가능."""
    try:
        h, m = os.environ.get("SKPORT_CHECK_TIME", "01:23").split(":")
        return int(h), int(m)
    except ValueError:
        return 1, 23


def next_check_delay(now=None):
    """다음 실행시각(UTC+8)까지 남은 초 + 목표 시각. 순수함수(테스트 가능)."""
    h, m = check_hour_minute()
    now = now or datetime.datetime.now(state.UTC8)
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    return (target - now).total_seconds(), target


def _run_once():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = checkin.launch_browser(pw)
        try:
            ctx_kwargs = {"storage_state": checkin.STATE_FILE} if os.path.isfile(checkin.STATE_FILE) else {}
            ctx = browser.new_context(**ctx_kwargs)
            page = ctx.new_page()
            page.goto(checkin.SIGNIN_URL, timeout=checkin.TIMEOUT_MS)
            status, day = checkin.attempt_endfield(page)
            try:
                ctx.storage_state(path=checkin.STATE_FILE)
            except Exception as e:
                print(f"[warn] state save failed: {e}", flush=True)
            return status, day
        finally:
            browser.close()


def do_cycle(reason):
    """브라우저를 켜서 출석 1회 수행 후 종료. 당일 첫 출석·상태 변화·오류만 알림."""
    if state.login_open.is_set():
        state.add_log("로그인 창이 열려 있어 이번 출석을 건너뜁니다.")
        return
    try:
        status, day = _run_once()
        prev = state.state["last_status"]
        state.state["last_status"] = status
        state.state["last_run"] = f"{state.now()} ({reason})"
        if status == "success" or (status == "already" and state.state["settings"].get("claimed_day") != day):
            state.state["settings"]["claimed_day"] = day
            save_settings(Settings(**state.state["settings"]))
            msg = f"{checkin.MESSAGES['success']} [{reason}]"
            state.add_log(msg)
            notify_sync(msg)
        elif status != prev:
            msg = f"{checkin.MESSAGES.get(status, status)} [{reason}]"
            state.add_log(msg)
            notify_sync(msg)
        if status == "login_required":
            state.add_log("관리 UI의 '로그인용 브라우저 열기' 버튼 또는 VNC로 로그인하세요.")
            executor.submit(do_login_window, "세션 만료")
    except Exception as e:
        state.add_log(f"실행 오류: {type(e).__name__}: {e}")
        prev = state.state["last_status"]
        state.state["last_status"] = "error"
        state.state["last_run"] = f"{state.now()} ({reason})"
        if prev != "error":
            notify_sync(f"{checkin.MESSAGES['error']} [{reason}]")


def do_login_window(reason, minutes=state.LOGIN_WINDOW_MINUTES):
    """로그인용 브라우저를 minutes분간 열어둔다. 저장 세션이 없을 때 강제 실행용."""
    if state.login_open.is_set():
        state.add_log("로그인 창이 이미 열려 있습니다.")
        return
    state.login_open.set()
    try:
        from playwright.sync_api import sync_playwright

        state.add_log(f"{reason}: {minutes}분간 로그인용 브라우저를 엽니다. 화면/VNC(/vnc.html)에서 로그인하세요.")
        notify_sync("🔑 SKPORT 로그인 필요 — {minutes}분간 브라우저를 열어둡니다. 화면/VNC(/vnc.html)로 로그인하세요.".format(minutes=minutes))
        with sync_playwright() as pw:
            browser = checkin.launch_browser(pw)
            try:
                ctx_kwargs = {"storage_state": checkin.STATE_FILE} if os.path.isfile(checkin.STATE_FILE) else {}
                ctx = browser.new_context(**ctx_kwargs)
                page = ctx.new_page()
                page.goto(checkin.SIGNIN_URL, timeout=checkin.TIMEOUT_MS)
                state.state["last_run"] = f"{state.now()} ({reason})"
                time.sleep(minutes * 60)
                try:
                    ctx.storage_state(path=checkin.STATE_FILE)
                except Exception as e:
                    print(f"[warn] state save failed: {e}", flush=True)
            finally:
                browser.close()
        state.add_log("로그인 창을 닫았습니다.")
    except Exception as e:
        state.add_log(f"로그인 창 오류: {type(e).__name__}: {e}")
    finally:
        state.login_open.clear()
