# SKPORT FastAPI 포팅 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `manager.py`(stdlib HTTP + 수제 WS/VNC)를 FastAPI `app/` 패키지로 교체하고 uvicorn으로 실행한다.

**Architecture:** `app/main.py`(FastAPI + lifespan), `app/scheduler.py`(APScheduler Cron 01:23 Asia/Shanghai), `app/runner.py`(sync Playwright를 단일 Executor에서 직렬 실행), `app/settings.py`(Pydantic 검증 + settings.json 호환), `app/notify.py`(httpx 비동기), `app/vnc.py`(Starlette WS binary proxy). `checkin.py`·`login.py` 무수정.

**Tech Stack:** fastapi, uvicorn[standard], apscheduler, pydantic, pydantic-settings, jinja2, httpx, pytest + fastapi TestClient.

**Spec:** `docs/superpowers/specs/2026-09-15-fastapi-port-design.md`

## Global Constraints

- `requires-python = ">=3.12"`, 패키지 관리는 `uv` (`uv sync --frozen`, `uv run ...`).
- sync Playwright는 이벤트루프에서 직접 호출 금지. `runner.executor`(`max_workers=1`) 경유만 허용.
- APScheduler 타임존은 반드시 `Asia/Shanghai` 명시.
- `checkin.py` 출석 판정 로직·`classify_status` 순서 변경 금지. `login.py` 변경 금지.
- 텔레그램 토큰/챗ID 없으면 조용히 스킵(False, 예외 없음).
- 브라우저 실테스트 금지. VNC는 Docker 수동 확인(`/vnc.html`).
- `state["settings"]`는 항상 dict(`{"telegram": bool, "claimed_day": int}`) — manager.py와 동일 형태. Pydantic 모델은 load/save 경계에서만 검증용.

---

## 파일 구조

- Create: `app/__init__.py` — 빈 패키지 마커.
- Create: `app/state.py` — 공유 상수·`state` dict·`login_open`·`now()`·`add_log()`·`get_data_dir()`·`get_settings_file()`.
- Create: `app/settings.py` — `Settings` 모델 + `load_settings()`/`save_settings()`.
- Create: `app/notify.py` — `send_telegram()`(httpx) + `notify()`/`notify_sync()`.
- Create: `app/runner.py` — `check_hour_minute()`/`next_check_delay()` + `executor` + `do_cycle()`/`do_login_window()` 이식.
- Create: `app/scheduler.py` — `AsyncIOScheduler` 설정·부팅잡·`request_cycle()`/`request_login()`.
- Create: `app/vnc.py` — `proxy()` WS→TCP 브리지.
- Create: `app/main.py` — FastAPI app + lifespan + 7개 엔드포인트 + StaticFiles.
- Create: `app/templates/index.html` — 기존 `PAGE` 이식 (form → fetch JSON).
- Test: `tests/test_state.py`, `tests/test_settings.py`, `tests/test_notify_httpx.py`, `tests/test_schedule.py`, `tests/test_api.py` (기존 `test_status.py`·`test_notify.py` 유지).
- Modify: `pyproject.toml` (deps 7개), `Dockerfile` (`COPY app/`, uvicorn CMD), `agent-entrypoint.sh` (마지막 줄), `AGENTS.md` (stdlib 문구 갱신).
- Delete: `manager.py` (Task 10, 전부 동작 확인 후).

---

### Task 1: 의존성 + 패키지 스켈레톤

**Files:**
- Modify: `pyproject.toml`
- Create: `app/__init__.py` (0바이트)
- Test: import 스모크 (신규 테스트 파일 없음)

**Interfaces:**
- Consumes: 없음.
- Produces: 설치된 7개 패키지. 후속 Task가 `import app.x` 가능.

- [ ] **Step 1: pyproject 의존성 추가**

```toml
dependencies = [
  "playwright>=1.44",
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "apscheduler>=3.10",
  "pydantic>=2",
  "pydantic-settings>=2",
  "jinja2>=3.1",
  "httpx>=0.27",
]
```

- [ ] **Step 2: 설치 확인**

Run: `uv sync --frozen && uv run python -c "import fastapi, uvicorn, apscheduler, pydantic, jinja2, httpx; print('deps ok')"`
Expected: `deps ok`, exit 0.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock app/__init__.py
git commit -m "chore: add fastapi stack deps and app package skeleton"
```

---

### Task 2: `app/state.py` 공유 상태

**Files:**
- Create: `app/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: 없음.
- Produces: `state: dict`, `login_open: threading.Event`, `now() -> str`, `add_log(msg: str) -> None`, `get_data_dir() -> str`, `get_settings_file() -> str`, 상수 `NOVNC_DIR`, `VNC_HOST`, `VNC_PORT`, `LOGIN_WINDOW_MINUTES`, `UTC8`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_state.py -v`
Expected: FAIL with "No module named 'app.state'".

- [ ] **Step 3: Write minimal implementation**

```python
"""FastAPI 앱 공유 상태. manager.py:22-71에서 HTTP/WS 제외하고 이식."""
import datetime
import os
import threading
import time

UTC8 = datetime.timezone(datetime.timedelta(hours=8))
NOVNC_DIR = "/usr/share/novnc"  # 없을 때(로컬 실행)는 VNC 비활성
VNC_HOST, VNC_PORT = "127.0.0.1", 5900
LOGIN_WINDOW_MINUTES = 10

state = {
    "settings": {"telegram": True, "claimed_day": 0},
    "last_status": "-",
    "last_run": "-",
    "next_run": "-",
    "log": [],
}
login_open = threading.Event()  # 로그인 창이 열려 있으면 출석 사이클은 건너뜀


def get_data_dir() -> str:
    return os.environ.get("SKPORT_DATA_DIR", "data")


def get_settings_file() -> str:
    return os.path.join(get_data_dir(), "settings.json")


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def add_log(msg: str) -> None:
    state["log"].append(f"{now()} {msg}")
    del state["log"][:-20]
    print(msg, flush=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_state.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/state.py tests/test_state.py
git commit -m "feat: add app shared state"
```

---

### Task 3: `app/settings.py` Pydantic 검증 + 파일 persistence

**Files:**
- Create: `app/settings.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- Consumes: `app.state` (Task 2).
- Produces: `Settings(BaseModel)` 필드 `telegram: bool = True`, `claimed_day: int = 0` (`extra="ignore"` — `refresh_minutes` 등 무시). `load_settings() -> None` (검증 후 dict로 state에 저장). `save_settings(s: Settings) -> None`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_settings.py -v`
Expected: FAIL with "No module named 'app.settings'".

- [ ] **Step 3: Write minimal implementation**

```python
"""설정 모델 + settings.json persistence. manager.py:74-84의 검증 강화판."""
import json
import os

from pydantic import BaseModel, ConfigDict, ValidationError

from app import state


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")  # refresh_minutes 등 구키 무시
    telegram: bool = True
    claimed_day: int = 0


def load_settings() -> None:
    """settings.json → 검증 → state에 dict 저장. 없음·파손·검증실패 → 기본값."""
    raw: dict = {}
    try:
        with open(state.get_settings_file(), encoding="utf-8") as f:
            loaded = json.load(f)
        raw = loaded if isinstance(loaded, dict) else {}
    except (FileNotFoundError, ValueError):
        raw = {}
    try:
        validated = Settings(**raw)
    except ValidationError:
        print("[warn] settings invalid, using defaults", flush=True)
        validated = Settings()
    state.state["settings"] = {"telegram": validated.telegram, "claimed_day": validated.claimed_day}


def save_settings(s: Settings) -> None:
    os.makedirs(state.get_data_dir(), exist_ok=True)
    with open(state.get_settings_file(), "w", encoding="utf-8") as f:
        json.dump(s.model_dump(), f)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_settings.py tests/test_state.py -v`
Expected: 전부 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/settings.py tests/test_settings.py
git commit -m "feat: add pydantic settings with file persistence"
```

---

### Task 4: `app/notify.py` httpx 텔레그램

**Files:**
- Create: `app/notify.py`
- Test: `tests/test_notify_httpx.py` (기존 `tests/test_notify.py`는 checkin용으로 유지)

**Interfaces:**
- Consumes: `app.state` (Task 2).
- Produces: `async send_telegram(bot_token: str, chat_id: str, text: str, client=None) -> bool`, `async notify(text: str) -> None`, `notify_sync(text: str) -> None` (Executor 스레드용 동기 래퍼).

- [ ] **Step 1: Write the failing test** (anyio 없이 stdlib `asyncio.run()`만 사용)

```python
import asyncio
import httpx

from app import notify, state


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=15)


def test_send_telegram_posts():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.read().decode()
        return httpx.Response(200)

    ok = asyncio.run(notify.send_telegram("TOKEN", "123", "hi", client=_client(handler)))
    assert ok is True
    assert seen["url"] == "https://api.telegram.org/botTOKEN/sendMessage"
    assert "chat_id=123" in seen["body"] and "text=hi" in seen["body"]


def test_send_telegram_false_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    assert asyncio.run(notify.send_telegram("T", "1", "x", client=_client(handler))) is False


def test_send_telegram_false_on_network_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    assert asyncio.run(notify.send_telegram("T", "1", "x", client=_client(handler))) is False


def test_send_telegram_missing_creds():
    assert asyncio.run(notify.send_telegram("", "", "x")) is False


def test_notify_gated_by_settings(monkeypatch):
    calls = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    state.state["settings"] = {"telegram": False, "claimed_day": 0}

    async def fake(bot, chat, text, client=None):
        calls.append(text)
        return True

    monkeypatch.setattr(notify, "send_telegram", fake)
    asyncio.run(notify.notify("hello"))
    assert calls == []
```

- [ ] **Step 3: Write minimal implementation**

```python
"""httpx 기반 텔레그램 알림. checkin.send_telegram 계약 유지(무자격 스킵, 무예외)."""
import asyncio
import os

import httpx

from app import state


async def send_telegram(bot_token: str, chat_id: str, text: str, client=None) -> bool:
    if not bot_token or not chat_id:
        return False
    owned = client is None
    if owned:
        client = httpx.AsyncClient(timeout=15)
    try:
        resp = await client.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data={"chat_id": chat_id, "text": text},
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"[warn] telegram failed: {e}", flush=True)
        return False
    finally:
        if owned:
            await client.aclose()


async def notify(text: str) -> None:
    if state.state["settings"]["telegram"]:
        await send_telegram(os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", ""), text)


def notify_sync(text: str) -> None:
    """Executor 스레드용 동기 래퍼. 이벤트루프가 없는 스레드에서만 호출할 것."""
    asyncio.run(notify(text))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_notify_httpx.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add app/notify.py tests/test_notify_httpx.py
git commit -m "feat: add httpx telegram notify"
```

### Task 5: `app/runner.py` 출석 실행 이식

**Files:**
- Create: `app/runner.py`
- Test: `tests/test_schedule.py` (스케줄 시각 + `do_cycle` dedup; 브라우저는 모킹)

**Interfaces:**
- Consumes: `app.state`, `app.settings.Settings`/`save_settings`, `app.notify.notify_sync`, `checkin` (무수정 import).
- Produces: `check_hour_minute() -> tuple[int, int]`, `next_check_delay(now=None) -> tuple[float, datetime]`, `executor: ThreadPoolExecutor(max_workers=1)`, `do_cycle(reason: str) -> None`, `do_login_window(reason: str, minutes: int) -> None`. `login_required` 시 후속 로그인창은 `executor.submit`으로 직렬 등록 (기존 daemon-Thread 대체).

- [ ] **Step 1: Write the failing test**

```python
import datetime

import pytest

import checkin
from app import runner, state


def _reset():
    state.state.update({"last_status": "-", "last_run": "-", "next_run": "-", "log": []})
    state.state["settings"] = {"telegram": True, "claimed_day": 0}
    state.login_open.clear()


def test_next_check_before_target(monkeypatch):
    monkeypatch.setenv("SKPORT_CHECK_TIME", "01:23")
    now = datetime.datetime(2026, 9, 15, 0, 0, tzinfo=state.UTC8)
    delay, target = runner.next_check_delay(now)
    assert delay == 23 * 60
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_schedule.py -v`
Expected: FAIL with "No module named 'app.runner'".

- [ ] **Step 3: Write minimal implementation**

manager.py:45-61을 그대로 옮기고, 92-173을 아래 규칙으로 이식한다 (나머지 줄은 바이트 동일):
- `from app import state` 사용, `state`/`login_open`/`now`/`add_log` 참조에 `state.` 접두.
- `notify(` → `notify_sync(` (import: `from app.notify import notify_sync`).
- `save_settings()` → `save_settings(Settings(**state.state["settings"]))`.
- `threading.Thread(target=do_login_window, ...).start()` → `executor.submit(do_login_window, "세션 만료")`.
- 브라우저 본문(99-114)은 `_run_once()`로 분리. `import time` 유지.

```python
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
        browser = checkin.launch_browser(pw, headed=True)
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
            browser = checkin.launch_browser(pw, headed=True)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_schedule.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add app/runner.py tests/test_schedule.py
git commit -m "feat: port checkin cycle runner with serial executor"
```

---

### Task 6: `app/scheduler.py` APScheduler

**Files:**
- Create: `app/scheduler.py`
- Modify: `tests/test_schedule.py` (스케줄러 등록 테스트 추가)
- Test: `uv run pytest tests/test_schedule.py -v`

**Interfaces:**
- Consumes: `app.runner` (Task 5: `check_hour_minute`, `do_cycle`, `do_login_window`, `executor`), `app.state`, `checkin.STATE_FILE`.
- Produces: `scheduler: AsyncIOScheduler(timezone="Asia/Shanghai")`, `start() -> None`, `shutdown() -> None`, `request_cycle() -> bool`, `request_login(minutes: int = 10) -> bool`. `SKPORT_DISABLE_BOOT=1`이면 부팅잡 생략 (테스트 심).

- [ ] **Step 1: Write the failing test** (`tests/test_schedule.py` 맨 뒤에 추가)

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_schedule.py -v`
Expected: FAIL with "No module named 'app.scheduler'".

- [ ] **Step 3: Write minimal implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_schedule.py -v`
Expected: 10 passed (Task 5의 7개 + 신규 3개).

- [ ] **Step 5: Commit**

```bash
git add app/scheduler.py tests/test_schedule.py
git commit -m "feat: add apscheduler cron and manual triggers"
```

### Task 7: `app/vnc.py` WS→TCP 브리지

**Files:**
- Create: `app/vnc.py`
- Test: `tests/test_vnc.py` (로컬 TCP 에코 서버로 binary 왕복 검증. 브라우저·VNC 불필요)

**Interfaces:**
- Consumes: `app.state` (`VNC_HOST`, `VNC_PORT`).
- Produces: `async proxy(ws: WebSocket) -> None`. WS 프레임 처리(마스크 해제 등)는 Starlette가 담당하므로 raw binary만 TCP로 중계한다 — 기존 `relay_websockify` 수제 파싱과 동등. VNC 미접속이면 조용히 close.

- [ ] **Step 1: Write the failing test**

```python
import asyncio

from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from app import state
from app.vnc import proxy


async def _echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        while True:
            data = await reader.read(32768)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    finally:
        writer.close()


def _tiny_app():
    t = FastAPI()

    @t.websocket("/ws")
    async def ep(ws: WebSocket):
        await proxy(ws)

    return t


def test_proxy_echoes_binary(monkeypatch):
    async def go():
        server = await asyncio.start_server(_echo, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        monkeypatch.setattr(state, "VNC_PORT", port)
        try:
            with TestClient(_tiny_app()) as c:
                with c.websocket_connect("/ws", subprotocols=["binary"]) as w:
                    w.send_bytes(b"\x01\x02binary")
                    assert w.receive_bytes() == b"\x01\x02binary"
        finally:
            server.close()

    asyncio.run(go())


def test_proxy_closes_when_no_vnc(monkeypatch):
    monkeypatch.setattr(state, "VNC_PORT", 59999)  # 닫힌 포트
    with TestClient(_tiny_app()) as c:
        with c.websocket_connect("/ws", subprotocols=["binary"]) as w:
            import pytest

            with pytest.raises(Exception):
                w.send_bytes(b"ping")
                w.receive_bytes()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_vnc.py -v`
Expected: FAIL with "No module named 'app.vnc'".

- [ ] **Step 3: Write minimal implementation**

```python
"""Starlette WebSocket ↔ TCP(VNC) 브리지. manager.relay_websockify의 Starlette판."""
import asyncio

from fastapi import WebSocket, WebSocketDisconnect

from app import state


async def proxy(ws: WebSocket) -> None:
    await ws.accept(subprotocol="binary")
    try:
        reader, writer = await asyncio.open_connection(state.VNC_HOST, state.VNC_PORT)
    except OSError:
        await ws.close()
        return

    async def c2s():
        try:
            while True:
                writer.write(await ws.receive_bytes())
                await writer.drain()
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            writer.close()

    async def s2c():
        try:
            while True:
                data = await reader.read(32768)
                if not data:
                    break
                await ws.send_bytes(data)
        except (WebSocketDisconnect, RuntimeError):
            pass

    t1 = asyncio.create_task(c2s())
    t2 = asyncio.create_task(s2c())
    _, pending = await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_vnc.py -v`
Expected: 2 passed (`test_proxy_closes_when_no_vnc`가 TestClient WS 버전 따라 실패하면 `receive_bytes` 타임아웃 대신 종료 코드만 확인하도록 테스트를 그 환경에 맞게 최소 수정).

- [ ] **Step 5: Commit**

```bash
git add app/vnc.py tests/test_vnc.py
git commit -m "feat: add websocket to vnc bridge"
```

---

### Task 8: `app/main.py` + 템플릿 + API 테스트

**Files:**
- Create: `app/main.py`
- Create: `app/templates/index.html`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: 전부 (Tasks 2-7). `request.form()` 대신 body 수동 파싱 — `python-multipart` 의존성 추가 금지.
- Produces: uvicorn 실행 대상 `app` (`uv run uvicorn app.main:app --host 0.0.0.0 --port 8080`). 엔드포인트: `GET /`, `GET /api/status`, `POST /api/settings`(JSON 우선·form 허용·JSON 응답), `POST /api/cycle`→202, `POST /api/login`→202, `GET /preview.png`→503, `WS /websockify`, noVNC StaticFiles(없으면 `/vnc.html` 503 안내).

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api.py -v`
Expected: FAIL with "No module named 'app.main'".

- [ ] **Step 3: Write minimal implementation**

`app/templates/index.html` (manager.py:191-218 이식, form → fetch JSON):

```html
<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SKPORT 에이전트</title>
<style>body{font-family:sans-serif;max-width:900px;margin:20px auto;padding:0 12px}
pre{background:#f4f4f4;padding:8px;white-space:pre-wrap}
button{padding:6px 14px;margin:4px 4px 4px 0}</style></head><body>
<h1>SKPORT 에이전트</h1>
<p>매일 01:23 (UTC+8)에만 브라우저를 켜서 출석합니다. 평소에는 브라우저가 꺼져 있습니다.</p>
<p><a href="/vnc.html">VNC로 브라우저 열기</a> (로그인용, Docker에서만 동작)</p>
<h2>상태</h2>
<ul><li>결과: <b id="st">-</b></li><li>마지막 실행: <span id="last">-</span></li>
<li>다음 실행: <span id="next">-</span></li><li>저장 세션: <span id="sess">-</span></li></ul>
<h2>설정</h2>
<label><input type="checkbox" id="tg" checked> 텔레그램 알림</label>
<button onclick="save()">저장</button>
<button onclick="post('/api/cycle')">지금 출석 1회 실행</button>
<button onclick="post('/api/login')">로그인용 브라우저 10분 열기</button>
<h2>로그</h2><pre id="log"></pre>
<script>
async function post(u){await fetch(u,{method:'POST'});}
async function save(){await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram:tg.checked})});}
async function tick(){
 try{const r=await fetch('/api/status');const s=await r.json();
 st.textContent=s.last_status;last.textContent=s.last_run;next.textContent=s.next_run;
 tg.checked=s.settings.telegram;sess.textContent=s.has_session ? '있음' : '없음 (로그인 필요)';
 log.textContent=s.log.slice().reverse().join('\n');}catch(e){}
}
setInterval(tick,5000);tick();
</script></body></html>
```

`app/main.py`:

```python
"""SKPORT 상시 에이전트(FastAPI). 실행: uv run uvicorn app.main:app --host 0.0.0.0 --port 8080."""
import os
import urllib.parse
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import checkin
from app import runner, scheduler, state
from app.settings import Settings, load_settings, save_settings
from app.vnc import proxy as vnc_proxy

templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(state.get_data_dir(), exist_ok=True)
    load_settings()
    scheduler.start()
    state.add_log("에이전트 시작 (FastAPI)")
    yield
    scheduler.shutdown()
    runner.executor.shutdown(wait=False)


app = FastAPI(lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/status")
def api_status():
    return JSONResponse({**state.state, "has_session": os.path.isfile(checkin.STATE_FILE)})


@app.post("/api/settings")
async def api_settings(request: Request):
    if request.headers.get("content-type", "").startswith("application/json"):
        body = await request.json()
        telegram = bool(body.get("telegram", False))
    else:  # 기존 form 호환 (python-multipart 없이 수동 파싱)
        raw = (await request.body()).decode()
        telegram = "telegram" in urllib.parse.parse_qs(raw)
    updated = Settings(telegram=telegram, claimed_day=state.state["settings"]["claimed_day"])
    state.state["settings"] = {"telegram": updated.telegram, "claimed_day": updated.claimed_day}
    save_settings(updated)
    state.add_log(f"설정 변경: {state.state['settings']}")
    return {"settings": state.state["settings"]}


@app.post("/api/cycle", status_code=202)
def api_cycle():
    scheduler.request_cycle()
    return {"queued": True}


@app.post("/api/login", status_code=202)
def api_login():
    scheduler.request_login()
    return {"queued": True}


@app.get("/preview.png")
def preview():
    return PlainTextResponse("브라우저 꺼짐 (매일 01:23 UTC+8에만 켜짐)", status_code=503)


@app.websocket("/websockify")
async def websockify(ws: WebSocket):
    await vnc_proxy(ws)


if os.path.isdir(state.NOVNC_DIR):
    app.mount("/", StaticFiles(directory=state.NOVNC_DIR, html=True), name="novnc")
else:
    @app.get("/vnc.html")
    def vnc_missing():
        return PlainTextResponse("VNC 비활성 (로컬 실행, Docker에서만 동작)", status_code=503)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add app/main.py app/templates/index.html tests/test_api.py
git commit -m "feat: add fastapi app with lifecycle and routes"
```

---

### Task 9: 배포 전환 + `manager.py` 제거

**Files:**
- Modify: `Dockerfile`, `agent-entrypoint.sh`, `AGENTS.md` (Read 후 현재 문자열에 맞춰 수정)
- Delete: `manager.py` (`git rm`, 스모크 통과 후)
- Test: 전체 `uv run pytest` + uvicorn 스모크 (`curl /api/status`)

**Interfaces:**
- Consumes: Task 8까지의 `app/`.
- Produces: Docker에서도 uvicorn 기동. `compose.yaml` 변경 없음 (포트 그대로).

- [ ] **Step 1: Dockerfile 수정**

```dockerfile
COPY checkin.py login.py agent-entrypoint.sh ./
COPY app/ ./app/
EXPOSE 8080
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

기존 3줄(`COPY checkin.py login.py manager.py agent-entrypoint.sh ./`, `CMD ["uv", "run", "checkin.py"]`)을 위 4줄로 교체한다.

- [ ] **Step 2: agent-entrypoint.sh 마지막 줄 교체**

```bash
exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8080
```

(Xvfb/x11vnc 윗부분 유지.)

- [ ] **Step 3: AGENTS.md 갱신** (Read로 현재 문구 확인 후 수정)

  - 구조: `` `manager.py` — 상시 에이전트... **stdlib만 사용 (의존성 추가 금지)** `` → `` `app/` — 상시 에이전트(FastAPI). `main.py`(앱·lifespan), `scheduler.py`(APScheduler), `runner.py`(Executor 직렬 실행), `settings.py`(Pydantic), `notify.py`(httpx), `vnc.py`(WS→TCP), `templates/index.html` ``.
  - 명령: `uv run python manager.py` → `uv run uvicorn app.main:app --host 0.0.0.0 --port 8080`.
  - Playwright 규칙: "다른 스레드에서 `page` 직접 호출 금지" 뒤에 " — FastAPI에서는 `runner.executor` 경유만 허용, 이벤트루프 직접 호출 금지" 추가.
  - VNC·알림·판정 관련 불릿은 유지.

- [ ] **Step 4: 전체 테스트 + 스모크 후 manager.py 제거**

```bash
uv run pytest
SKPORT_DISABLE_BOOT=1 uv run uvicorn app.main:app --port 8080 &
sleep 5
curl -s localhost:8080/api/status | head -c 300
curl -s -o /dev/null -w "%{http_code}" localhost:8080/
kill %1
```

Expected: pytest 전부 PASS, `/api/status` 200 JSON, `/` 200. 통과하면:

```bash
git rm manager.py
git add Dockerfile agent-entrypoint.sh AGENTS.md
git commit -m "chore: switch deployment to uvicorn and drop stdlib manager"
```

---

## Self-Review (작성자 체크)

1. **Spec coverage:** 아키텍처 분리(Tasks 1,2,5-8) ✓ / Settings 검증+호환(Task 3, `refresh_minutes` 무시 테스트 포함) ✓ / Cron 01:23 Asia/Shanghai+coalesce+misfire(Task 6, 트리거 문자열·시각 테스트) ✓ / 부팅잡(세션없음→로그인·미출석→즉시, DISABLE_BOOT 심) ✓ / Executor 직렬+login_open(Task 5 테스트 3건) ✓ / API 7종 매핑(Task 8 테스트 6건; `/websockify`는 Task 7 테스트 2건) ✓ / StaticFiles+로컬 폴백(Task 8 본문) ✓ / 에러 dedup(Task 5 본문, 기존 규칙 그대로) ✓ / httpx 계약(Task 4 테스트 5건) ✓ / 배포 7deps·Docker·entrypoint·AGENTS(Task 1, 9) ✓ / 리스크 3건(프레임 동등성→Task 7 본문 주석, 303→JSON→Task 8 템플릿 fetch, 타임존→Task 6 상수) ✓ / 비범위(checkin·login·novnc 불변→Global Constraints) ✓.
2. **Placeholder scan:** "그대로 이식" 언급은 전부 정확한 원본 줄번호+치환 목록 병기. `TBD/TODO/적절히` 없음. Task 7 Step 4의 테스트 최소수정 허용 문구는 환경 의존(TestClient WS 구현) 탈출구로 1줄만 허용.
3. **Type consistency:** `state["settings"]`는 전 Task에서 dict로 통일. `save_settings(Settings)` / `Settings(**dict)` 경계 변환은 Task 3·5·8에서 동일 시그니처. `notify_sync(text)` 시그니처 Task 4·5 일치. `request_cycle()/request_login()` Task 6·8 일치. `proxy(ws)` Task 7·8 일치.


