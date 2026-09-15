# skport

SKPORT Endfield 일일 출석 자동화. Playwright 실브라우저로 출석 카드를 확인·클릭하며, 출석일은 UTC+8 기준입니다.

Docker 컨테이너에서만 실행됩니다 (Xvfb + x11vnc + 실크롬 포함).

## 요구사항

- Docker / Docker Compose (실행)
- Python 3.12+, [uv](https://docs.astral.sh/uv/) (테스트 전용)

## 실행

```bash
docker compose up --build
```

- UI: `http://localhost:8081` / VNC: `http://localhost:8081/vnc.html`
- 매일 **01:23 (UTC+8)** 자동 출석, 시작 시 당일 미출석이면 즉시 1회 실행
- `already`/`success`/상태 변화/오류일 때만 텔레그램 알림 (중복 알림 없음)
- 세션 만료 시 로그인용 브라우저를 10분간 열어두고 알림 — UI 버튼 또는 VNC로 로그인
- API: `GET /api/status`, `POST /api/cycle`, `POST /api/login`, `POST /api/settings`
- 데이터는 `./data` 볼륨에 유지 (`storage_state.json`, `settings.json`)

`storage_state.json`은 세션이므로 **커밋 금지** (gitignore됨).

## 환경변수

| 변수 | 기본값 | 비고 |
|---|---|---|
| `SKPORT_STATE_FILE` | `storage_state.json` | Docker: `/app/data/storage_state.json` |
| `SKPORT_DATA_DIR` | `data` | `settings.json` 위치. Docker: `/app/data` |
| `SKPORT_CHECK_TIME` | `01:23` | 매일 실행 시각 (UTC+8, `HH:MM`) |
| `SKPORT_DISABLE_BOOT` | (없음) | `1`이면 시작 시 즉시 실행 생략 |
| `PLAYWRIGHT_CHANNEL` | (없음) | Docker는 `chrome`(실크롬) |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | (없음) | 없으면 알림 조용히 스킵 |

## 테스트 (개발 호스트, 브라우저 불필요)

```bash
uv sync --frozen
uv run pytest
```

## 구조

```
checkin.py            # 출석 판정 핵심 (launch_browser, attempt_endfield, classify_status)
app/main.py           # FastAPI 앱 + lifespan
app/scheduler.py      # APScheduler (01:23 UTC+8 Cron + 부팅/수동 잡)
app/runner.py         # 단일 워커 Executor에서 Playwright 직렬 실행
app/settings.py       # 설정 모델 + settings.json
app/notify.py         # httpx 텔레그램 알림
app/state.py          # 공유 상태
app/vnc.py            # WebSocket → VNC TCP 프록시
agent-entrypoint.sh   # Docker 진입점 (Xvfb + x11vnc + uvicorn)
```
