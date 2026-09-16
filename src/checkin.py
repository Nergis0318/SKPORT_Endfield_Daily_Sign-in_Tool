"""SKPORT Endfield 일일 출석 (Playwright 실브라우저). Docker 컨테이너 전용."""

import datetime
import os

SIGNIN_URL = "https://game.skport.com/endfield/sign-in"
STATE_FILE = os.environ.get("SKPORT_STATE_FILE", "storage_state.json")
TIMEOUT_MS = 30_000
# 알림·로그 문구는 app/i18n.py가 단일 소유자다 (여기서 되살리지 말 것).


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


UTC8 = datetime.timezone(datetime.timedelta(hours=8))
CONTENT_JS = "() => document.body && document.body.innerText.includes('Day ')"

# 출석 버튼(#lottie-container)의 형제 요소에 #completed-overlay가 있으면 출석 완료
CARD_JS = """() => {
  const el = document.getElementById('lottie-container');
  if (!el || !el.parentElement) return 'missing';
  return [...el.parentElement.children].some(c => c.id === 'completed-overlay') ? 'claimed' : 'open';
}"""

# 출석 버튼은 lottie 애니메이션 컨테이너 자체가 클릭 대상 (카드 부모 클릭은 동작 안 함)
CLICK_JS = """() => {
  const el = document.getElementById('lottie-container');
  if (el) el.click();
}"""


def today_day():
    return datetime.datetime.now(UTC8).day


def safe_text(page):
    try:
        return page.inner_text("body")
    except Exception:
        return ""


def attempt_endfield(page):
    """출석 판정(#completed-overlay 형제 여부) + 미출석이면 클릭. 반환: (status, utc8_day)."""
    day = today_day()
    try:
        page.wait_for_function(CONTENT_JS, timeout=20000)
    except Exception:
        return classify_status(safe_text(page)), day
    if page.evaluate(CARD_JS) == "claimed":
        return "already", day
    page.evaluate(CLICK_JS)
    page.wait_for_timeout(4000)
    if page.evaluate(CARD_JS) == "claimed":
        return "success", day
    page.reload(timeout=TIMEOUT_MS)  # 방문만으로 자동 수령되는 경우 대비 재확인
    try:
        page.wait_for_function(CONTENT_JS, timeout=20000)
    except Exception:
        return "unknown", day
    if page.evaluate(CARD_JS) == "claimed":
        return "success", day
    return classify_status(safe_text(page)), day


def launch_browser(pw):
    """Docker Xvfb(:99) 위 headed 실행. PLAYWRIGHT_CHANNEL=chrome(실크롬, Docker 기본)."""
    return pw.chromium.launch(
        headless=False,
        channel=os.environ.get("PLAYWRIGHT_CHANNEL") or None,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
