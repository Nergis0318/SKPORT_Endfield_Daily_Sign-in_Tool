# skport

SKPORT Endfield 일일 출석 자동화. Playwright 실브라우저로 출석 카드를 확인·클릭하고, 출석일은 **UTC+8** 기준입니다.

Xvfb + x11vnc + 실크롬을 포함한 **Docker 컨테이너 전용** 구성입니다 (호스트 직접 실행 경로 없음).

## 요구사항

- Docker / Docker Compose — 실행
- Python 3.12+ 와 [uv](https://docs.astral.sh/uv/) — 테스트 전용 (브라우저 불필요)

## 빠른 시작

```bash
docker compose up --build
```

|                   |                                  |
| ----------------- | -------------------------------- |
| 관리 UI           | <http://localhost:8081>          |
| VNC (로그인 화면) | <http://localhost:8081/vnc.html> |

1. 처음 띄우면 저장된 세션이 없으므로 **로그인용 브라우저가 자동으로 10분간 열립니다.**
2. `/vnc.html` 로 접속해 SKPORT 계정으로 로그인합니다.
3. 로그인 후 UI의 **브라우저 즉시 종료** 버튼을 누르면 남은 시간을 기다리지 않고 닫습니다 (세션은 그대로 저장). 기다려도 10분 뒤 자동 저장·종료됩니다.

데이터는 `./data` 볼륨에 남습니다 (`storage_state.json`, `settings.json`). 봇 토큰 같은 비밀값은 `.env`로도 넘길 수 있습니다 (선택, `compose.yaml`의 `env_file`).

`storage_state.json`은 로그인 세션이므로 **커밋 금지** (gitignore 처리됨).

## 동작 방식

- 매일 **01:23 (UTC+8)** 에 브라우저를 켜서 출석 1회 수행 — 상시 구동이 아니라 그때만 켜집니다. 시각은 `SKPORT_CHECK_TIME`으로 바꿉니다.
- 시작 시 부팅 잡: 저장 세션이 없으면 로그인 창을 열고, 있으면 **당일 미출석일 때만** 즉시 1회 실행합니다 (`SKPORT_DISABLE_BOOT=1`이면 생략).
- 출석 판정은 출석 카드의 완료 표시를 직접 확인하고, 미출석이면 버튼 클릭 → 4초 대기 → 페이지 새로고침 후 재확인 순서로 진행합니다 (방문만으로 자동 수령되는 경우 대비).
- 로그인 창이 열려 있는 동안에는 출석 사이클을 건너뜁니다.

판정 로직·스레드 제약 같은 내부 규칙은 `AGENTS.md`에 정리되어 있습니다.

## 알림

텔레그램과 디스코드를 지원하며, Web UI에서 설정하면 `settings.json`에 저장됩니다. 저장값이 없으면 환경변수로 폴백하고, 자격증명이 아예 없으면 조용히 건너뜁니다 (예외 없음).

- **전송 시점:** 당일 첫 출석(`success`, 또는 그날 처음 확인한 `already`), 상태 변화, 오류. 같은 날 중복 `already`는 알림을 보내지 않습니다.
- **텔레그램 멘션:** 멘션할 유저 ID가 숫자면 `tg://user?id=` 보이지 않는 멘션으로 전송합니다 (`parse_mode=HTML`).
- **비밀값 마스킹:** 봇 토큰과 웹훅 URL은 `/api/status` 응답에서 빈 값으로 내려가고 `telegram_configured` / `discord_configured` 플래그로만 노출됩니다.

세션이 만료되면 로그에 안내가 남고 알림이 전송되며, 로그인용 브라우저가 10분간 열립니다. UI 버튼이나 `POST /api/login`으로 직접 열 수도 있습니다.

## 관리 UI

<http://localhost:8081> — 5초마다 `/api/status`를 폴링합니다.

- **상태:** 마지막 결과 · 마지막 실행 · 다음 실행 시각 · 저장 세션 유무
- **언어:** 한국어 / English / 日本語 — UI 라벨뿐 아니라 알림·로그 문구까지 이 설정을 따릅니다 (기본 `ko`)
- **알림 설정:** 텔레그램(봇 토큰 / 채팅 ID / 멘션 유저 ID), 디스코드(웹훅 URL) 저장·삭제
- **버튼:** 지금 출석 1회 실행 · 로그인용 브라우저 10분 열기 · 브라우저 즉시 종료(창이 열려 있을 때만 활성)
- **로그:** 최근 20줄

VNC(`/vnc.html`)는 컨테이너의 Xvfb 화면을 그대로 보여줍니다 — 로그인 입력은 여기서 합니다.

## 다국어 (ko / en / jp)

관리 UI의 **언어** 선택으로 바꾸며 `settings.json`의 `language`에 저장됩니다 (기본 `ko`, `ja`는 `jp`로 흡수).

- 번역 대상: UI 라벨·상태 표시, 텔레그램/디스코드 알림 문구, 로그 문구.
- 언어를 바꾸면 페이지가 새로 고쳐지므로 **저장하지 않은 입력값은 사라집니다.**
- 로그는 기록 시점 언어로 저장되므로 지난 줄은 번역되지 않습니다.
- 번역 대상이 아닌 것: `/api/status`의 상태 코드(`success` 등 기계용 값), 출석 판정 키워드, VNC(noVNC) 화면.

## API

| 메서드 | 경로            | 설명                                                                                  |
| ------ | --------------- | ------------------------------------------------------------------------------------- |
| GET    | `/`             | 관리 UI                                                                               |
| GET    | `/api/status`   | 상태 + 설정(마스킹) + `has_session` + `login_open`                                    |
| POST   | `/api/settings` | 알림·언어 설정 저장. JSON 또는 form. 생략한 필드는 유지, 빈 문자열은 삭제 후 env 폴백 |
| POST   | `/api/cycle`    | 출석 1회 큐잉 (202, 실행은 직렬 처리)                                                 |
| POST   | `/api/login`    | 로그인용 브라우저 10분 열기 (202)                                                     |
| POST   | `/api/close`    | 열린 로그인 창 즉시 종료 → `{"closing": true\|false}`                                 |
| WS     | `/websockify`   | VNC WebSocket → TCP 5900 프록시                                                       |
| GET    | `/preview.png`  | 항상 503 (브라우저는 실행 시에만 켜짐)                                                |

## 환경변수

| 변수                                      | 기본값               | 비고                                                           |
| ----------------------------------------- | -------------------- | -------------------------------------------------------------- |
| `SKPORT_STATE_FILE`                       | `storage_state.json` | 저장 세션 경로. Docker: `/app/data/storage_state.json`         |
| `SKPORT_DATA_DIR`                         | `data`               | `settings.json` 위치. Docker: `/app/data`                      |
| `SKPORT_CHECK_TIME`                       | `01:23`              | 매일 실행 시각 (UTC+8, `HH:MM`)                                |
| `SKPORT_DISABLE_BOOT`                     | (없음)               | `1`이면 시작 시 부팅 잡 생략                                   |
| `PLAYWRIGHT_CHANNEL`                      | (없음)               | Docker는 `chrome` (실크롬)                                     |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | (없음)               | Web UI 설정값이 없을 때 폴백. 둘 다 없으면 알림 조용히 스킵    |
| `TELEGRAM_MENTION_ID`                     | (없음)               | 숫자면 `tg://user?id=` 보이지 않는 멘션으로 전송               |
| `DISCORD_WEBHOOK_URL`                     | (없음)               | Web UI 설정값이 없을 때 폴백. 없으면 디스코드 알림 조용히 스킵 |

## 테스트 (개발 호스트, 브라우저 불필요)

```bash
uv sync --frozen                     # 개발 호스트 의존성 설치
uv run pytest                        # 테스트 전체
uv run pytest tests/test_status.py   # 단일 파일
```

출석 판정·알림·설정·스케줄·API·VNC·다국어를 단위 테스트로 덮습니다.

## 구조

```
checkin.py                # 출석 판정 핵심 (launch_browser, attempt_endfield, classify_status)
app/main.py               # FastAPI 앱·라우트·lifespan
app/scheduler.py          # APScheduler (01:23 UTC+8 Cron + 부팅/수동 잡)
app/runner.py             # 단일 워커 Executor에서 Playwright 직렬 실행 + 알림 조건
app/settings.py           # 설정 모델 + settings.json + env 폴백
app/i18n.py               # 사용자 노출 문구 카탈로그 (ko/en/jp)
app/notify.py             # httpx 텔레그램/디스코드 알림
app/state.py              # 공유 상태·로그·데이터 경로
app/vnc.py                # WebSocket → VNC TCP 프록시
app/templates/index.html  # 관리 UI
agent-entrypoint.sh       # Docker 진입점 (Xvfb :99 + x11vnc + uvicorn)
```

`.env`, `./data`, `storage_state.json`은 gitignore 대상입니다.
