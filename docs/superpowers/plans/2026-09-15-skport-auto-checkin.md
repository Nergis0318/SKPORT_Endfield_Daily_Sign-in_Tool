# SKPORT 자동 출석체크 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Playwright 실브라우저로 SKPORT 엔드필드 일일 출석을 수행하는 Docker+cron 자동화 구축

**Architecture:** `checkin.py`가 저장된 로그인 세션(`storage_state.json`)으로 headless Chromium을 열어 출석 페이지에 접속·클릭하고, 텍스트 기반 판정 후 텔레그램으로 알림. 최초 1회만 `login.py`로 수동 로그인. 매일 09:30 KST에 컨테이너 내 cron 실행.

**Tech Stack:** Python >=3.12, Playwright >=1.44 (Chromium), cron (Docker 내), Telegram Bot HTTP API (표준라이브러리 urllib), pytest >=8

**Spec:** `docs/superpowers/specs/2026-09-15-skport-auto-checkin-design.md`

## Global Constraints

- Python >=3.12, Playwright >=1.44
- 단일 계정만 지원. 다계정·웹UI·DB 금지 (YAGNI).
- 시크릿(`.env`, `storage_state.json`)은 절대 커밋 금지 — `.gitignore`에 이미 등록됨
- cron: 매일 09:30 KST, TZ=Asia/Seoul (서버 리셋 01시 이후 여유)
- 로그는 stdout (`docker logs`로 확인), 실패 시 `screenshots/`에 png+html 저장
- 텔레그램 전송 실패가 출석 exit code에 영향 금지 (알림은 best-effort)

---

### Task 1: 프로젝트 스켈레톤 + 순수 함수 + 단위 테스트

**Files:**

- Create: `pyproject.toml`
- Create: `checkin.py`
- Create: `tests/test_status.py`
- Create: `tests/test_notify.py`

**Interfaces:**

- Consumes: 없음 (첫 태스크)
- Produces (Task 2가 사용): `checkin.SIGNIN_URL: str`, `checkin.STATE_FILE: str`, `checkin.TIMEOUT_MS: int = 30000`, `checkin.BUTTON_PATTERN: re.Pattern`, `checkin.classify_status(page_text: str) -> str` (`"already" | "success" | "login_required" | "unknown"`), `checkin.send_telegram(bot_token: str, chat_id: str, text: str) -> bool`, `checkin.notify_enabled() -> bool`, `checkin.notify(text: str) -> None`, `checkin.MESSAGES: dict[str, str]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_status.py
from checkin import classify_status


def test_already_ko():
    assert classify_status("이미 출석하셨습니다") == "already"


def test_already_en():
    assert classify_status("You have already checked in today") == "already"


def test_success_ko():
    assert classify_status("출석 완료! 보상을 수령하세요") == "success"


def test_success_en():
    assert classify_status("Checked in successfully") == "success"


def test_login_required():
    assert classify_status("로그인이 필요합니다") == "login_required"


def test_unknown():
    assert classify_status("Welcome to the SKPORT community") == "unknown"
```

```python
# tests/test_notify.py
import urllib.error

import checkin


class FakeResp:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_send_telegram_posts(monkeypatch):
    seen = {}

    def fake_urlopen(url, data, timeout):
        seen["url"] = url
        seen["data"] = data
        return FakeResp()

    monkeypatch.setattr(checkin.urllib.request, "urlopen", fake_urlopen)
    assert checkin.send_telegram("TOKEN", "123", "hi") is True
    assert seen["url"] == "https://api.telegram.org/botTOKEN/sendMessage"
    assert b"chat_id=123" in seen["data"]
    assert b"text=hi" in seen["data"]


def test_send_telegram_false_on_error(monkeypatch):
    def boom(url, data, timeout):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(checkin.urllib.request, "urlopen", boom)
    assert checkin.send_telegram("T", "1", "x") is False


def test_send_telegram_missing_creds():
    assert checkin.send_telegram("", "", "x") is False


def test_notify_disabled(monkeypatch):
    monkeypatch.setenv("TELEGRAM_NOTIFY", "false")
    assert checkin.notify_enabled() is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv sync --extra dev 2>/dev/null; uv run pytest tests/ -v`
Expected: FAIL with "No module named 'checkin'" (파일이 아직 없음)

- [ ] **Step 3: Write minimal implementation**

```toml
# pyproject.toml
[project]
name = "skport"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["playwright>=1.44"]

[project.optional-dependencies]
dev = ["pytest>=8"]
```

```python
# checkin.py
"""SKPORT Endfield daily check-in via a real browser (Playwright).

Usage:
  python checkin.py            # headless, uses storage_state.json
  python checkin.py --headed   # visible browser for debugging
"""

import os
import re
import sys
import time
import urllib.parse
import urllib.request

SIGNIN_URL = "https://game.skport.com/endfield/sign-in"
STATE_FILE = os.environ.get("SKPORT_STATE_FILE", "storage_state.json")
TIMEOUT_MS = 30_000

BUTTON_PATTERN = re.compile("출석|check-in|check in|签到", re.IGNORECASE)

MESSAGES = {
    "success": "✅ SKPORT 출석 완료",
    "already": "✅ SKPORT 이미 출석됨 (중복 실행 없음)",
    "login_required": "🚨 SKPORT 로그인 만료 — login.py로 다시 로그인 필요",
    "unknown": "⚠️ SKPORT 출석 결과 불명 — screenshots/ 확인 필요",
    "error": "❌ SKPORT 출석 실패(네트워크 오류) — 로그 확인 필요",
}


def env(name, default=""):
    return os.environ.get(name, default)


def notify_enabled():
    return env("TELEGRAM_NOTIFY", "true").lower() not in ("0", "false", "no")


def send_telegram(bot_token, chat_id, text):
    """POST text via Telegram Bot API. Never raises; returns True on ok."""
    if not bot_token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    try:
        with urllib.request.urlopen(url, data, timeout=15) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[warn] telegram failed: {e}", flush=True)
        return False


def notify(text):
    if notify_enabled():
        send_telegram(env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_CHAT_ID"), text)


def classify_status(page_text):
    """Text-based result classifier. Order matters: already > success > login."""
    t = page_text.lower()
    if any(
        k in t
        for k in ("이미 출석", "이미 완료", "already checked in", "already completed")
    ):
        return "already"
    if any(
        k in t
        for k in (
            "출석 완료",
            "출석 성공",
            "check-in complete",
            "checked in",
            "签到成功",
        )
    ):
        return "success"
    if any(k in t for k in ("로그인", "login", "sign in")):
        return "login_required"
    return "unknown"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv sync --extra dev && uv run pytest tests/ -v`
Expected: 10 passed (6 status + 4 notify)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml checkin.py tests/
git commit -m "feat: add checkin pure functions with unit tests"
```

---

### Task 2: 브라우저 출석 플로우 (`run_checkin` + `main`)

**Files:**

- Modify: `checkin.py` (아래 함수 추가 — Task 1 코드는 그대로 유지)
- Test: 수동 실행 (브라우저 필요라 pytest 불가 — `--headed` 눈검증 + 로그인 전 상태에서 `login_required` 반환 확인)

**Interfaces:**

- Consumes (Task 1): `SIGNIN_URL`, `STATE_FILE`, `TIMEOUT_MS`, `BUTTON_PATTERN`, `classify_status`, `notify`, `MESSAGES`
- Produces (Task 3, 4가 사용): `checkin.run_checkin(headed: bool = False) -> str`, `checkin.main(argv: list[str]) -> int` (exit 0 = success/already, 1 = 그 외)

- [ ] **Step 1: Append browser flow to `checkin.py`**

```python
# checkin.py 에 추가 (MESSAGES 아래)


def dump_debug(page, prefix):
    os.makedirs("screenshots", exist_ok=True)
    page.screenshot(path=f"screenshots/{prefix}.png")
    with open(f"screenshots/{prefix}.html", "w", encoding="utf-8") as f:
        f.write(page.content())


def _attempt(pw, headed):
    browser = pw.chromium.launch(headless=not headed)
    try:
        ctx_kwargs = {"storage_state": STATE_FILE} if os.path.exists(STATE_FILE) else {}
        ctx = browser.new_context(**ctx_kwargs)
        page = ctx.new_page()
        page.goto(SIGNIN_URL, timeout=TIMEOUT_MS)
        page.wait_for_timeout(3000)
        if page.get_by_role("button", name=BUTTON_PATTERN).count() == 0:
            status = classify_status(page.inner_text("body"))
            if status == "unknown":
                dump_debug(page, "checkin_unknown")
            return status
        page.get_by_role("button", name=BUTTON_PATTERN).first.click(timeout=TIMEOUT_MS)
        page.wait_for_timeout(3000)
        status = classify_status(page.inner_text("body"))
        if status in ("unknown", "login_required"):
            dump_debug(page, "checkin_result")
        return status
    finally:
        browser.close()


def run_checkin(headed=False):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        try:
            return _attempt(pw, headed)
        except Exception as e:
            print(f"[warn] first try failed ({e}), retrying once...", flush=True)
            time.sleep(10)
            try:
                return _attempt(pw, headed)
            except Exception as e2:
                print(f"[error] retry failed: {e2}", flush=True)
                return "error"


def main(argv):
    headed = "--headed" in argv
    status = run_checkin(headed=headed)
    msg = MESSAGES[status]
    print(msg, flush=True)
    notify(msg)
    return 0 if status in ("success", "already") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 2: Install browser and dry-run without login**

Run: `uv run playwright install --with-deps chromium` (리눅스에서 sudo 비밀번호 물을 수 있음)
Then: `uv run python checkin.py --headed`
Expected: `🚨 SKPORT 로그인 만료` 출력 + exit 1 + `screenshots/checkin_unknown.png` 또는 login 판정 (로그인 전이므로 success/already가 아니면 정상)

- [ ] **Step 3: Re-run unit tests (regression)**

Run: `uv run pytest tests/ -v`
Expected: 10 passed (Task 1 코드 untouched 확인)

- [ ] **Step 4: Commit**

```bash
git add checkin.py
git commit -m "feat: add playwright checkin flow with retry and debug dumps"
```

---

### Task 3: 최초 로그인 부트스트랩 (`login.py`) + 실제 출석 검증

**Files:**

- Create: `login.py`
- Test: 실제 수동 로그인 1회 + headless 출석 실행 (사용자 개입 1회 필요)

**Interfaces:**

- Consumes (Task 2): `checkin.SIGNIN_URL`, `checkin.STATE_FILE`, `checkin.TIMEOUT_MS`, `checkin.run_checkin`
- Produces (Task 4가 사용): `storage_state.json` (git 제외, Docker 볼륨 마운트용), `login.py`

- [ ] **Step 1: Write `login.py`**

```python
# login.py
"""One-time manual login: saves storage_state.json for checkin.py."""

import checkin
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False)
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(checkin.SIGNIN_URL, timeout=checkin.TIMEOUT_MS)
    print(
        "브라우저에서 로그인을 완료한 뒤, 이 터미널에서 Enter를 누르세요.", flush=True
    )
    input()
    ctx.storage_state(path=checkin.STATE_FILE)
    print(f"saved: {checkin.STATE_FILE}", flush=True)
    browser.close()
```

- [ ] **Step 2: Manual login (사용자 1회 개입)**

Run: `uv run python login.py`
Expected: headed 브라우저가 열림 → 사용자가 직접 로그인 → Enter → `saved: storage_state.json` 출력. `git status --short`에 `storage_state.json`이 나타나지 않아야 정상 (.gitignore 확인).

- [ ] **Step 3: Real headless check-in**

Run: `TELEGRAM_NOTIFY=false uv run python checkin.py; echo "exit=$?"`
Expected: `✅ SKPORT 출석 완료` 또는 `✅ SKPORT 이미 출석됨` + exit=0. `unknown`/`error`가 나오면 `screenshots/` 확인 후 셀렉터(`BUTTON_PATTERN`) 수정.

- [ ] **Step 4: Commit**

```bash
git add login.py
git commit -m "feat: add one-time manual login bootstrap"
```

---

### Task 4: Docker + cron + compose + 텔레그램 종단 검증

**Files:**

- Create: `Dockerfile`
- Create: `crontab`
- Create: `docker-compose.yml`
- Create: `.env.example`

**Interfaces:**

- Consumes (Task 3): `checkin.py`, `login.py`, `storage_state.json` (호스트에 존재), `.env` (사용자가 `.env.example` 복사 후 작성)
- Produces: 매일 09:30 KST 자동 실행 컨테이너

- [ ] **Step 1: Write Docker files**

```dockerfile
# Dockerfile
FROM python:3.12-slim
ENV TZ=Asia/Seoul PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends cron tzdata \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN pip install --no-cache-dir "playwright>=1.44" \
 && python -m playwright install --with-deps chromium
COPY checkin.py ./
COPY crontab /etc/cron.d/skport
RUN chmod 0644 /etc/cron.d/skport && touch /var/log/cron.log
CMD ["sh", "-c", "cron && tail -F /var/log/cron.log"]
```

```
# crontab (파일 끝 개행 필수)
30 9 * * * root cd /app && /usr/local/bin/python /app/checkin.py >> /var/log/cron.log 2>&1
```

```yaml
# docker-compose.yml
services:
  skport:
    build: .
    container_name: skport
    env_file: .env
    environment:
      TZ: Asia/Seoul
    volumes:
      - ./storage_state.json:/app/storage_state.json:ro
    restart: unless-stopped
```

```
# .env.example
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_CHAT_ID=123456789
TELEGRAM_NOTIFY=true
```

- [ ] **Step 2: Create `.env` and build**

Run: `cp .env.example .env` → 텔레그램 토큰/챗ID 기입 후 `docker compose build`
Expected: 빌드 성공 (Chromium 포함이라 수 분 소요)

- [ ] **Step 3: End-to-end run inside container**

Run: `docker compose run --rm skport /usr/local/bin/python /app/checkin.py; echo "exit=$?"`
Expected: `✅` 메시지 + exit=0 + 텔레그램 수신. `git status --short`에 `.env`가 나타나지 않아야 정상.

- [ ] **Step 4: Start scheduler and check logs**

Run: `docker compose up -d && docker logs skport --tail 5`
Expected: 컨테이너 running, cron 데몬 로그 tail 중. 다음날 09:30 KST 이후 `docker logs skport`에서 출석 기록 확인.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile crontab docker-compose.yml .env.example
git commit -m "feat: add docker cron scheduler with compose"
```

---

## Self-review

- Spec coverage: 구조(checkin/login/Dockerfile/compose/.env.example) → Task 1~~4. 데이터 흐름(세션→접속→클릭→판정→텔레그램) → Task 2. 에러(30초 타임아웃·1회 재시도·스크린샷·로그인만료 알림) → Task 2. 스케줄(09:30 KST·stdout) → Task 4. 테스트(수동 1회·--headed) → Task 2~~3. 전 섹션 매핑됨.
- Placeholder scan: URL·시간·파일명·커맨드·assert 전부 구체값. "적절히 처리" 같은 문구 없음.
- Type consistency: `classify_status(str)->str` 5값이 `MESSAGES` 키 5개와 일치. `run_checkin(bool)->str`, `main(list[str])->int`, `send_telegram(str,str,str)->bool` 전 태스크 동일.
