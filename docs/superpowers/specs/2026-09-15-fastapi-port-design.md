# SKPORT FastAPI 포팅 디자인 (C안: 풀 FastAPI화)

- 일자: 2026-09-15
- 대상: `manager.py` (stdlib `ThreadingHTTPServer` + 수제 WS/VNC 중계) → FastAPI 앱
- 비대상: `checkin.py` 출석 판정 로직(`CARD_JS`/`CLICK_JS`, `classify_status` 순서)은 그대로

## 확정된 결정

1. 범위: manager 전체 구조 개편 (UI/API + 스케줄러까지)
2. VNC: 순수파이썬 중계 로직 그대로 이식 (Starlette WS binary proxy + StaticFiles noVNC)
3. 실행: APScheduler + 단일 ThreadPool에서 sync Playwright 직렬 실행 (전용스레드 원칙 유지)
4. 텔레그램: `urllib` 대신 `httpx` 비동기 사용 (사용자 지정)

## 아키텍처

단일파일 `manager.py` → `app/` 패키지 분리:

- `app/main.py`: FastAPI app, lifespan(설정로드→스케줄러 시작→종료시 정리), 라우트/WS 마운트, `uvicorn app.main:app` 실행
- `app/settings.py`: Pydantic Settings 모델 + `data/settings.json` 파일 persistence
- `app/scheduler.py`: APScheduler (`AsyncIOScheduler`, CronTrigger daily 01:23 Asia/Shanghai) + 수동 트리거
- `app/runner.py`: 브라우저 실행 래퍼 (`do_cycle`/`do_login_window` 로직 이식, `asyncio.to_thread` + `max_workers=1` Executor로 직렬화, `login_open` 우선 규칙 유지)
- `app/notify.py`: httpx 기반 텔레그램 전송 + 기존 dedup 규칙(당일 첫출석·상태변화·오류만)
- `app/vnc.py`: WS(`/websockify`)→TCP(VNC 5900) binary proxy (기존 `relay_websockify` 프레임 로직 이식)
- `app/templates/index.html`: 기존 `PAGE` HTML 이식 (Jinja, 폴링 JS 유지)
- `checkin.py`: 수정 없음 (그대로 import)

## 컴포넌트

- Settings: 필드 `telegram: bool=True`, `claimed_day: int=0`; 파일에 없는 키(`refresh_minutes` 등)는 무시. 검증 실패 시 기본값 + 로그.
- Scheduler: CronTrigger(hour=1, minute=23, timezone=Asia/Shanghai), `coalesce=True`, `misfire_grace_time=300`. 시작 시 세션없음→로그인잡, 미출석→즉시 1회 실행 (기존 `worker()` 부팅 로직 유지).
- Runner: sync Playwright는 절대 이벤트루프에서 직접 호출 금지. 단일 워커 Executor로 `do_cycle`/`do_login_window` 직렬 실행.
- API: 기존 7개 엔드포인트 1:1 이식 (하단 매핑표).
- Notify: `httpx.AsyncClient` (timeout 15s), 토큰/챗ID 없으면 조용히 스킵(False 반환, 예외 없음) — 기존 `send_telegram` 계약 유지.

## API 매핑 (기존 → 신규)

| 기존 (`Handler`) | 신규 |
|---|---|
| `GET /` (PAGE 인라인) | `GET /` (Jinja `index.html`) |
| `GET /api/status` | `GET /api/status` (동일 JSON + `has_session`) |
| `POST /api/settings` (form, 303 리다이렉트) | `POST /api/settings` (JSON body 우선, 기존 form도 허용, JSON 응답) |
| `POST /api/cycle` | `POST /api/cycle` (스케줄러에 1회성 잡 등록, 즉시 202 반환) |
| `POST /api/login` | `POST /api/login` (10분 로그인잡 등록) |
| `GET /preview.png` (503 고정) | `GET /preview.png` (동일 503 유지) |
| `GET /websockify` (수제 핸드셰이크) | `WS /websockify` (Starlette WebSocket, binary proxy) |
| noVNC 정적 서빙 (`/vnc.html` 등) | `StaticFiles(directory=/usr/share/novnc)`, 없으면(로컬) VNC 비활성 + 안내 |

## 데이터 플로우

lifespan startup → settings 로드 → scheduler 시작(부팅잡: 세션체크/즉시출석) → cron/수동 트리거 → Executor에서 runner 실행 → state 갱신 + settings.json 저장 → dedup 조건 충족 시 httpx 알림.

## 에러 처리

- Playwright 예외 → `status=error`, 로그 + 이전과 다를 때만 알림 (기존 규칙).
- `login_required` → UI 안내 로그 + 로그인잡 자동 시작 (기존 동작).
- 스케줄러 misfire는 coalesce로 합침, VNC 연결 끊김은 조용히 종료, settings 검증 실패는 기본값으로 기동.

## 테스트

- 기존 `tests/` (순수함수) 유지, 브라우저 불필요 원칙 유지.
- 신규: settings 모델 검증 테스트, Cron 발화시각 테스트(기존 `next_check_delay` 기대값과 일치), `TestClient` API 테스트(`/api/status`, `/api/settings`, `/api/cycle`은 runner 모킹).
- VNC 프록시·실출석은 테스트 제외 (수동 확인: Docker에서 `/vnc.html`).

## 의존성·배포

- `pyproject.toml` 추가: `fastapi`, `uvicorn[standard]`, `apscheduler`, `pydantic`, `pydantic-settings`, `jinja2`, `httpx`.
- `Dockerfile`: `COPY app/`, `CMD uvicorn` 계열로 변경. `agent-entrypoint.sh` 마지막 줄 `exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8080` (Xvfb/x11vnc 부분 유지).
- `compose.yaml` 포트 매핑 그대로 (`8081:8080`).
- `AGENTS.md`의 "manager.py stdlib만 사용" 문구 갱신 (FastAPI 기반으로 변경 + Playwright 스레드 규칙은 유지).

## 리스크

- Starlette WS binary 프록시 이식 시 기존 수제 프레임 파싱(`relay_websockify`)의 마스크 해제/바이너리 전송 동등성 확인 필요.
- `POST /api/*`가 303 리다이렉트→JSON 응답으로 바뀌므로, 구 UI 하드코딩 클라이언트가 있으면 영향 (현 UI는 자체 폴링 JS라 무영향).
- APScheduler 타임존: 반드시 `Asia/Shanghai` 명시 (UTC+8 고정, DST 없음).

## 비범위

- `checkin.py` 판정 로직 변경 없음. `login.py` 부트스트랩 변경 없음. noVNC 자체 수정 없음.
