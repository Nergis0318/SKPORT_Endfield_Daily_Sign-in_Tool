"""SKPORT Endfield 일일 출석 (Playwright 실브라우저). Docker 컨테이너 전용."""
import datetime
import os

SIGNIN_URL = "https://game.skport.com/endfield/sign-in"
STATE_FILE = os.environ.get("SKPORT_STATE_FILE", "storage_state.json")
TIMEOUT_MS = 30_000

MESSAGES = {
    "success": "✅ SKPORT 출석 완료",
    "already": "✅ SKPORT 이미 출석됨 (중복 실행 없음)",
    "login_required": "🚨 SKPORT 로그인 만료 — UI/VNC에서 다시 로그인 필요",
    "unknown": "⚠️ SKPORT 출석 결과 불명 — 로그 확인 필요",
    "error": "❌ SKPORT 출석 실패(네트워크 오류) — 로그 확인 필요",
}


def classify_status(page_text):
    """Text-based result classifier. Order matters: already > success > login."""
    t = page_text.lower()
    if any(k in t for k in ("이미 출석", "이미 완료", "already checked in", "already completed")):
        return "already"
    if any(k in t for k in ("출석 완료", "출석 성공", "check-in complete", "checked in", "签到成功")):
        return "success"
    if any(k in t for k in ("로그인", "login", "sign in")):
        return "login_required"
    return "unknown"


UTC8 = datetime.timezone(datetime.timedelta(hours=8))
CONTENT_JS = "() => document.body && document.body.innerText.includes('Day ')"

# 오늘 카드(Day N, UTC+8 기준)에 svg 체크 표시가 있으면 출석 완료
CARD_JS = """(day) => {
  const el = [...document.querySelectorAll('*')].find(e => (e.innerText || '').trim() === 'Day ' + day);
  if (!el) return 'missing';
  return el.parentElement.querySelectorAll('svg').length > 0 ? 'claimed' : 'open';
}"""

CLICK_JS = """(day) => {
  const el = [...document.querySelectorAll('*')].find(e => (e.innerText || '').trim() === 'Day ' + day);
  if (el) el.parentElement.click();
}"""


def today_day():
    return datetime.datetime.now(UTC8).day


def safe_text(page):
    try:
        return page.inner_text("body")
    except Exception:
        return ""


def attempt_endfield(page):
    """카드 기반 출석 확인 + 미출석이면 카드 클릭. 반환: (status, utc8_day)."""
    day = today_day()
    try:
        page.wait_for_function(CONTENT_JS, timeout=20000)
    except Exception:
        return classify_status(safe_text(page)), day
    if page.evaluate(CARD_JS, day) == "claimed":
        return "already", day
    page.evaluate(CLICK_JS, day)
    page.wait_for_timeout(4000)
    if page.evaluate(CARD_JS, day) == "claimed":
        return "success", day
    page.reload(timeout=TIMEOUT_MS)  # 방문만으로 자동 수령되는 경우 대비 재확인
    try:
        page.wait_for_function(CONTENT_JS, timeout=20000)
    except Exception:
        return "unknown", day
    if page.evaluate(CARD_JS, day) == "claimed":
        return "success", day
    return classify_status(safe_text(page)), day


def launch_browser(pw):
    """Docker Xvfb(:99) 위 headed 실행. PLAYWRIGHT_CHANNEL=chrome(실크롬, Docker 기본)."""
    return pw.chromium.launch(
        headless=False,
        channel=os.environ.get("PLAYWRIGHT_CHANNEL") or None,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
