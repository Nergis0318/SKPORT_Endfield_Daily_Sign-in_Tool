# AGENTS.md — skport

SKPORT Endfield 일일 출석 자동화. Playwright 실브라우저 기반, 한국어 주석/메시지.

## 구조

- `checkin.py` — 1회성 출석. `attempt_endfield(page) -> (status, utc8_day)`가 핵심. 상태값: `success | already | login_required | unknown | error`
- `login.py` — 1회 수동 로그인 부트스트랩. headed로 열고 로그인 후 터미널 Enter → `storage_state.json` 저장
- `manager.py` — 상시 에이전트. 브라우저 상시 오픈 + 주기 새로고침(F5) + 관리 UI. **stdlib만 사용 (의존성 추가 금지)**
- `agent-entrypoint.sh` — Docker 진입점: Xvfb(:99) + x11vnc + `manager.py`
- `tests/` — 순수함수 단위테스트만 (`classify_status`, `send_telegram`). 브라우저 불필요

## 명령 (uv 사용, bun/npm 아님)

```bash
uv sync --frozen                # 의존성 설치
uv run checkin.py               # 1회 출석 (headless)
uv run checkin.py --headed      # 디버깅용 가시 브라우저
uv run python login.py          # 세션 만료 시 재로그인 (headed 고정)
uv run python manager.py        # 상시 에이전트 로컬 실행
uv run pytest                   # 테스트 전체
uv run pytest tests/test_status.py  # 단일 파일
docker compose up --build       # 풀스택 (UI :8081, VNC /vnc.html)
```

## 환경변수

| 변수 | 기본값 | 비고 |
|---|---|---|
| `SKPORT_STATE_FILE` | `storage_state.json` | Docker: `/app/data/storage_state.json`. gitignore됨, 커밋 금지 |
| `SKPORT_DATA_DIR` | `data` | `settings.json` 위치. Docker: `/app/data` |
| `SKPORT_SCREENSHOT_DIR` | `screenshots` | 실패 덤프(`*.png/*.html`). Docker: `/app/data/screenshots` |
| `MANAGER_PORT` | `8080` | compose는 `8081:8080` 매핑 |
| `PLAYWRIGHT_CHANNEL` | (없음) | Docker는 `chrome`(실크롬). 비우면 번들 Chromium |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | (없음) | 없으면 알림 조용히 스킵 (`send_telegram` False 반환, 예외 없음) |
| `TELEGRAM_NOTIFY` | `true` | `checkin.py` 단발 실행용. manager는 `settings.json`의 `telegram` 사용 |

## 반드시 알아야 할 것

- **Playwright sync API는 생성 스레드 전용.** `manager.py`에서 브라우저 호출은 반드시 `call(fn)` 큐 경유 (`browser_main` 스레드). 다른 스레드에서 `page` 직접 호출 금지.
- **출석 판정 로직 (UTC+8 기준):** `Day N` exact innerText 요소 탐색 → 부모의 `svg` 유무로 출석 여부. 클릭 후 4초 대기 → 미체크면 reload 후 재확인 (방문만으로 자동수령되는 경우 대비). 바꾸면 실출석에 영향 — `CARD_JS`/`CLICK_JS` 수정 시 신중히.
- **`classify_status` 순서 고정:** already → success → login. 순서 바꾸면 오분류 (예: "already checked in"이 "checked in"에 먼저 걸림).
- **manager 알림 조건:** 당일 첫 출석·상태 변화·오류만 전송. 중복 `already`는 `claimed_day == day`면 알림 없음.
- **VNC(`/vnc.html`)는 Docker에서만 동작** (`/usr/share/novnc` 필요). 로컬 `manager.py` 실행 시 미리보기(`/preview.png`)와 API만 사용.
- 브라우저 첫 기동 타임아웃 120초 (`browser_ready.wait`). Docker 외부에서 headed 실행 시 DISPLAY 필요.
