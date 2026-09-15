# login.py
"""One-time manual login: saves storage_state.json for checkin.py."""
import checkin
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = checkin.launch_browser(pw, headed=True)
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(checkin.SIGNIN_URL, timeout=checkin.TIMEOUT_MS)
    print("브라우저에서 로그인을 완료한 뒤, 이 터미널에서 Enter를 누르세요.", flush=True)
    input()
    ctx.storage_state(path=checkin.STATE_FILE)
    print(f"saved: {checkin.STATE_FILE}", flush=True)
    browser.close()
