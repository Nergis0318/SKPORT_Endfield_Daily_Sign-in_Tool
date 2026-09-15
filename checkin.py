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
    if any(k in t for k in ("이미 출석", "이미 완료", "already checked in", "already completed")):
        return "already"
    if any(k in t for k in ("출석 완료", "출석 성공", "check-in complete", "checked in", "签到成功")):
        return "success"
    if any(k in t for k in ("로그인", "login", "sign in")):
        return "login_required"
    return "unknown"
