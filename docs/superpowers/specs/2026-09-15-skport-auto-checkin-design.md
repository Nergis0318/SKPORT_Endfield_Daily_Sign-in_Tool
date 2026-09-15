# SKPORT 자동 출석체크 설계 (B안: 브라우저 자동화)

날짜: 2026-09-15
상태: 승인됨 (사용자 승인 4/4 완료)

## 1. 배경·목표

- 대상: `https://game.skport.com/endfield/sign-in` (Arknights: Endfield, GRYPHLINE SKPORT 일일 출석)
- 목표: Docker 컨테이너가 매일 자동으로 실페이지에 접속해 출석 버튼을 클릭하고 결과를 텔레그램으로 알림
- 확정 조건: Docker+스케줄러 / 단일 계정 / Telegram 알림 / Asia 서버 / B안(브라우저 자동화)

## 2. 접근법 (A vs B vs C 중 B 선택)

- A: API 직접 호출 — 가볍지만 Sign 서명 변경에 취약, cred/token 추출 필요
- B (선택): Playwright 실브라우저 클릭 — Sign 변경에 면역, DOM 변경에만 취약, 이미지 무거움(~1GB), 토큰 추출 불필요
- C: Python 스케줄러 내장 — cron 불필요하지만 상시 실행 필요
- 선택 이유: 사용자가 B로 변경 요청. 보안 서명 이슈 회피 우선.

## 3. 구조

```
skport/
  checkin.py            # 출석 본체 (storage_state 로드 → 접속 → 클릭 → 판정 → 텔레그램)
  login.py              # 최초 1회 수동 로그인 → storage_state.json 저장
  Dockerfile            # playwright/python 이미지 + cron, TZ=Asia/Seoul
  docker-compose.yml    # env_file .env + storage_state.json 마운트 + cron 09:30 KST
  .env.example          # TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_NOTIFY
  docs/superpowers/specs/2026-09-15-skport-auto-checkin-design.md (본 문서)
```

- 단일 계정만 지원. 다계정·웹UI·DB는 스킵 (YAGNI).
- 시크릿은 `.env` + `storage_state.json`에만 저장, 모두 git 제외.

## 4. 데이터 흐름

1. 최초 1회: 로컬에서 `python login.py` 실행 → headed 브라우저에서 수동 로그인 → `storage_state.json` 저장
2. 매일 09:30 KST cron이 `checkin.py` 실행
3. `storage_state.json` 로드 → headless Chromium으로 sign-in 페이지 접속
4. 로그인 풀림 감지 시: 중단 + 스크린샷 + 텔레그램에 수동 로그인 요청
5. 출석 버튼 탐색: 텍스트 기반 (`role=button`, 이름에 출석/Check-in/签到 포함)으로 DOM 변경에 버팀
6. 클릭 → 성공/이미완료 문구로 판정 → 텔레그램 Bot API(`sendMessage`)로 결과 전송

## 5. 에러·스케줄

- 페이지 타임아웃 30초, 네트워크 오류 1회 재시도 후 실패 알림
- 실패 시 스크린샷 + HTML 저장 → 텔레그램에 첨부/언급
- cron: 매일 09:30 KST (서버 리셋 01시 이후 여유, off-peak)
- 로그: stdout → `docker logs`로 확인

## 6. 테스트·운영

- `python login.py` 로컬 로그인 1회 검증
- `docker compose run --rm skport python checkin.py` 수동 출석 1회 검증
- `--headed` 옵션으로 눈으로 확인 가능
- 성공 기준: 당일 출석 완료 문구 + 텔레그램 수신

## 7. Self-review

- 플레이스홀더 없음. 셀렉터·URL·시간·시크릿 위치 모두 명시.
- 일관성: 단일계정 전제와 파일 구성 일치. DB/다계정 언급은 스킵으로 명시.
- 스코프: 단일 플랜으로 구현 가능 (파일 4개 + 문서).
- 모호성: Asia 서버는 B안에서 `sk-game-role` 불필요하므로 참고용으로만 유지. 언어 설정 불필요 (실페이지 렌더 언어 따름).

## 8. 다음 단계

- 사용자가 본 spec 리뷰 후 `writing-plans` 스킬로 구현 플랜 작성
