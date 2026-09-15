"""APScheduler 스케줄러. manager.worker()의 부팅·정기 로직을 Cron+1회성 잡으로 이식."""
import asyncio
import datetime
import os

import checkin
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app import runner, state

TZ = "Asia/Shanghai"
scheduler = AsyncIOScheduler(timezone=TZ)


async def _cycle_job():
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(runner.executor, runner.do_cycle, "01:23 정기 실행")
    _refresh_next_run()


async def _login_job(reason, minutes):
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(runner.executor, runner.do_login_window, reason, minutes)


def _refresh_next_run():
    job = scheduler.get_job("daily")
    if job is not None and job.next_run_time is not None:
        state.state["next_run"] = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S") + " (UTC+8)"


def request_cycle() -> bool:
    """수동 출석 1회. 즉시 202 반환, 실행은 executor에서 직렬 처리."""
    scheduler.add_job(_cycle_job, trigger="date", run_date=datetime.datetime.now(),
                      id="once-cycle", replace_existing=True)
    return True


def request_login(minutes=state.LOGIN_WINDOW_MINUTES) -> bool:
    scheduler.add_job(_login_job, trigger="date", run_date=datetime.datetime.now(),
                      args=("수동 로그인", minutes), id="once-login", replace_existing=True)
    return True


def start_boot_jobs():
    if os.environ.get("SKPORT_DISABLE_BOOT") == "1":
        return
    now = datetime.datetime.now()
    if not os.path.isfile(checkin.STATE_FILE):
        scheduler.add_job(_login_job, trigger="date", run_date=now,
                          args=("저장 세션 없음", state.LOGIN_WINDOW_MINUTES),
                          id="boot-login", replace_existing=True)
    elif state.state["settings"]["claimed_day"] != datetime.datetime.now(state.UTC8).day:
        scheduler.add_job(_cycle_job, trigger="date", run_date=now,
                          id="boot-cycle", replace_existing=True)


def start() -> None:
    h, m = runner.check_hour_minute()
    scheduler.add_job(_cycle_job, CronTrigger(hour=h, minute=m, timezone=TZ),
                      id="daily", replace_existing=True,
                      coalesce=True, misfire_grace_time=300, max_instances=1)
    start_boot_jobs()
    if not scheduler.running:
        scheduler.start()
    _refresh_next_run()


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)