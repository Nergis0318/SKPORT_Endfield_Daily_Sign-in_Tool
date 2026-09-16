# AGENTS.md — skport

SKPORT Endfield 일일 출석 자동화. Playwright 실브라우저 기반, 한국어 주석/메시지. **Docker 컨테이너 전용** (Xvfb + x11vnc + 실크롬).

## 구조

- `checkin.py` — 출석 판정 핵심. `attempt_endfield(page) -> (status, utc8_day)`. 상태값: `success | already | login_required | unknown | error`
- `app/` — 상시 에이전트(FastAPI). `main.py`(앱·lifespan), `scheduler.py`(APScheduler), `runner.py`(Executor 직렬 실행), `settings.py`(Pydantic), `notify.py`(httpx), `vnc.py`(WS→TCP), `templates/index.html`
- `agent-entrypoint.sh` — Docker 진입점: Xvfb(:99) + x11vnc + uvicorn
- `tests/` — 단위테스트 (출석 판정·알림·설정·스케줄·API·VNC). 브라우저 불필요

## 명령

```bash
uv sync --frozen                # 개발 호스트 의존성 설치 (테스트용)
uv run pytest                   # 테스트 전체
uv run pytest tests/test_status.py  # 단일 파일
docker compose up --build       # 실행 (UI :8081, VNC /vnc.html)
```

## 환경변수

| 변수 | 기본값 | 비고 |
|---|---|---|
| `SKPORT_STATE_FILE` | `storage_state.json` | Docker: `/app/data/storage_state.json`. gitignore됨, 커밋 금지 |
| `SKPORT_DATA_DIR` | `data` | `settings.json` 위치. Docker: `/app/data` |
| `PLAYWRIGHT_CHANNEL` | (없음) | Docker는 `chrome`(실크롬) |
| `TELEGRAM_MENTION_ID` | (없음) | 숫자면 `tg://user?id=` 보이지 않는 멘션으로 전송 (parse_mode=HTML) |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | (없음) | Web UI 설정값이 없을 때 폴백. 둘 다 없으면 알림 조용히 스킵 (False 반환, 예외 없음) |
| `DISCORD_WEBHOOK_URL` | (없음) | Web UI 설정값이 없을 때 폴백. 없으면 디스코드 알림 조용히 스킵 |

## 반드시 알아야 할 것

- **Docker 전용:** 호스트에서 에이전트를 직접 실행하는 경로 없음. `docker compose up --build`가 유일한 실행법. 테스트(`uv run pytest`)는 브라우저 없이 호스트에서 실행 가능.
- **Playwright sync API는 생성 스레드 전용.** 다른 스레드에서 `page` 직접 호출 금지 — FastAPI에서는 `runner.executor` 경유만 허용, 이벤트루프 직접 호출 금지.
- **출석 판정 로직:** `#lottie-container`(출석 버튼)의 **형제 요소 중 `#completed-overlay` 존재 여부**로 출석 완료 판정(`CARD_JS`). 미출석이면 `#lottie-container` 자체를 클릭(카드 부모 클릭은 동작 안 함) → 4초 대기 → 미출석이면 reload 후 재확인 (방문만으로 자동수령되는 경우 대비). UTC+8 day는 알림 중복 판정용으로만 반환. 바꾸면 실출석에 영향 — `CARD_JS`/`CLICK_JS` 수정 시 신중히.
- **`classify_status` 순서 고정:** already → success → login. 순서 바꾸면 오분류 (예: "already checked in"이 "checked in"에 먼저 걸림).
- **`app/runner.py` 알림 조건:** 당일 첫 출석·상태 변화·오류만 전송. 중복 `already`는 `claimed_day == day`면 알림 없음.
- **로그인:** 세션 만료 시 runner가 10분 로그인 창을 자동으로 열고, UI 버튼/`POST /api/login`으로도 열 수 있음. VNC(`/vnc.html`)로 접속해 로그인.
- **로그인 창 즉시 종료:** UI '브라우저 즉시 종료' 버튼 → `POST /api/close` → `runner.request_close()`가 `state.close_requested`를 set하면, `do_login_window`의 대기(`close_requested.wait`)가 즉시 깨어나 세션을 저장하고 브라우저를 닫음. Playwright 객체는 스레드 전용이라 바깥에서 `browser.close()`를 직접 부를 수 없어 이벤트 기반 협조적 중단을 씀 — `time.sleep`으로 되돌리면 버튼이 무력화됨. `close_requested`는 창 시작/종료 시 clear.
- **알림 설정:** 봇 토큰·채널 ID·멘션 유저 ID·디스코드 웹훅는 Web UI(`/`)에서 설정하며 `settings.json`에 저장됨(파일 값 우선, 없으면 env 폴백). 시크릿(토큰·웹훅)은 `/api/status` 응답에서 빈 값으로 마스킹되고 `telegram_configured`/`discord_configured` 플래그로만 노출. `POST /api/settings`에서 생략한 필드는 유지, 빈 문자열은 삭제 후 env 폴백.
