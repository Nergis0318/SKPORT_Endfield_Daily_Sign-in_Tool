"""SKPORT 상시 에이전트: 매일 01:23(UTC+8)에만 브라우저 켜서 출석 + 관리 UI.

실행: agent-entrypoint.sh (Xvfb + noVNC + 이 파일)
UI: http://localhost:8080, VNC: http://localhost:7900/vnc.html
표준라이브러리만 사용 (추가 의존성 없음).
"""
import base64
import datetime
import hashlib
import json
import os
import select
import socket
import struct
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import checkin

DATA_DIR = os.environ.get("SKPORT_DATA_DIR", "data")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
UI_PORT = int(os.environ.get("MANAGER_PORT", "8080"))
NOVNC_DIR = "/usr/share/novnc"  # 없을 때(로컬 실행)는 VNC 비활성
VNC_HOST, VNC_PORT = "127.0.0.1", 5900
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
UTC8 = datetime.timezone(datetime.timedelta(hours=8))
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css",
        ".png": "image/png", ".ico": "image/x-icon", ".svg": "image/svg+xml",
        ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf", ".json": "application/json"}

state = {
    "settings": {"telegram": True, "claimed_day": 0},
    "last_status": "-",
    "last_run": "-",
    "next_run": "-",
    "log": [],
}
wake = threading.Event()
login_open = threading.Event()  # 로그인 창이 열려 있으면 출석 사이클은 건너뜀
LOGIN_WINDOW_MINUTES = 10


def check_hour_minute():
    """매일 실행 시각(UTC+8). SKPORT_CHECK_TIME="01:23" 로 변경 가능."""
    try:
        h, m = os.environ.get("SKPORT_CHECK_TIME", "01:23").split(":")
        return int(h), int(m)
    except ValueError:
        return 1, 23


def next_check_delay(now=None):
    """다음 01:23(UTC+8)까지 남은 초 + 목표 시각. 순수함수(테스트 가능)."""
    h, m = check_hour_minute()
    now = now or datetime.datetime.now(UTC8)
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    return (target - now).total_seconds(), target


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def add_log(msg):
    state["log"].append(f"{now()} {msg}")
    del state["log"][:-20]
    print(msg, flush=True)


def load_settings():
    try:
        saved = json.load(open(SETTINGS_FILE, encoding="utf-8"))
        state["settings"].update({k: saved[k] for k in ("telegram", "claimed_day") if k in saved})
    except (FileNotFoundError, ValueError, KeyError, AttributeError):
        pass


def save_settings():
    os.makedirs(DATA_DIR, exist_ok=True)
    json.dump(state["settings"], open(SETTINGS_FILE, "w", encoding="utf-8"))


def notify(text):
    if state["settings"]["telegram"]:
        checkin.send_telegram(checkin.env("TELEGRAM_BOT_TOKEN"), checkin.env("TELEGRAM_CHAT_ID"), text)


def do_cycle(reason):
    """브라우저를 켜서 출석 1회 수행 후 종료. 당일 첫 출석·상태 변화·오류만 알림."""
    if login_open.is_set():
        add_log("로그인 창이 열려 있어 이번 출석을 건너뜁니다.")
        return
    from playwright.sync_api import sync_playwright

    def _run():
        with sync_playwright() as pw:
            browser = checkin.launch_browser(pw, headed=True)
            try:
                ctx_kwargs = {"storage_state": checkin.STATE_FILE} if os.path.isfile(checkin.STATE_FILE) else {}
                ctx = browser.new_context(**ctx_kwargs)
                page = ctx.new_page()
                page.goto(checkin.SIGNIN_URL, timeout=checkin.TIMEOUT_MS)
                status, day = checkin.attempt_endfield(page)
                try:
                    ctx.storage_state(path=checkin.STATE_FILE)
                except Exception as e:
                    print(f"[warn] state save failed: {e}", flush=True)
                return status, day
            finally:
                browser.close()

    try:
        status, day = _run()
        prev = state["last_status"]
        state["last_status"] = status
        state["last_run"] = f"{now()} ({reason})"
        if status == "success" or (status == "already" and state["settings"].get("claimed_day") != day):
            state["settings"]["claimed_day"] = day
            save_settings()
            msg = f"{checkin.MESSAGES['success']} [{reason}]"
            add_log(msg)
            notify(msg)
        elif status != prev:
            msg = f"{checkin.MESSAGES.get(status, status)} [{reason}]"
            add_log(msg)
            notify(msg)
        if status == "login_required":
            add_log("관리 UI의 '로그인용 브라우저 열기' 버튼 또는 VNC로 로그인하세요.")
            threading.Thread(target=do_login_window, args=("세션 만료",), daemon=True).start()
    except Exception as e:
        add_log(f"실행 오류: {type(e).__name__}: {e}")
        prev = state["last_status"]
        state["last_status"] = "error"
        state["last_run"] = f"{now()} ({reason})"
        if prev != "error":
            notify(f"{checkin.MESSAGES['error']} [{reason}]")


def do_login_window(reason, minutes=LOGIN_WINDOW_MINUTES):
    """로그인용 브라우저를 minutes분간 열어둔다. 저장 세션이 없을 때 강제 실행용."""
    if login_open.is_set():
        add_log("로그인 창이 이미 열려 있습니다.")
        return
    login_open.set()
    try:
        from playwright.sync_api import sync_playwright

        add_log(f"{reason}: {minutes}분간 로그인용 브라우저를 엽니다. 화면/VNC(/vnc.html)에서 로그인하세요.")
        notify(f"🔑 SKPORT 로그인 필요 — {minutes}분간 브라우저를 열어둡니다. 화면/VNC(/vnc.html)로 로그인하세요.")
        with sync_playwright() as pw:
            browser = checkin.launch_browser(pw, headed=True)
            try:
                ctx_kwargs = {"storage_state": checkin.STATE_FILE} if os.path.isfile(checkin.STATE_FILE) else {}
                ctx = browser.new_context(**ctx_kwargs)
                page = ctx.new_page()
                page.goto(checkin.SIGNIN_URL, timeout=checkin.TIMEOUT_MS)
                state["last_run"] = f"{now()} ({reason})"
                time.sleep(minutes * 60)
                try:
                    ctx.storage_state(path=checkin.STATE_FILE)
                except Exception as e:
                    print(f"[warn] state save failed: {e}", flush=True)
            finally:
                browser.close()
        add_log("로그인 창을 닫았습니다.")
    except Exception as e:
        add_log(f"로그인 창 오류: {type(e).__name__}: {e}")
    finally:
        login_open.clear()


def worker():
    while not os.path.isfile(checkin.STATE_FILE):
        do_login_window("저장 세션 없음")
    today = datetime.datetime.now(UTC8).day
    if state["settings"].get("claimed_day") != today:
        do_cycle("시작 시 미출석 → 즉시 실행")
    while True:
        delay, target = next_check_delay()
        state["next_run"] = target.strftime("%Y-%m-%d %H:%M:%S") + " (UTC+8)"
        if wake.wait(delay):
            wake.clear()  # 설정 변경 시 스케줄 재계산
            continue
        do_cycle("01:23 정기 실행")


PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SKPORT 에이전트</title>
<style>body{font-family:sans-serif;max-width:900px;margin:20px auto;padding:0 12px}
pre{background:#f4f4f4;padding:8px;white-space:pre-wrap}
form{margin:12px 0}button{padding:6px 14px}</style></head><body>
<h1>SKPORT 에이전트</h1>
<p>매일 01:23 (UTC+8)에만 브라우저를 켜서 출석합니다. 평소에는 브라우저가 꺼져 있습니다.</p>
<p><a href="/vnc.html">VNC로 브라우저 열기</a> (로그인용, Docker에서만 동작)</p>
<h2>상태</h2>
<ul><li>결과: <b id="st">-</b></li><li>마지막 실행: <span id="last">-</span></li>
<li>다음 실행: <span id="next">-</span></li><li>저장 세션: <span id="sess">-</span></li></ul>
<h2>설정</h2>
<form method="post" action="/api/settings">
<label><input type="checkbox" name="telegram" id="tg" checked> 텔레그램 알림</label>
<button>저장</button></form>
<form method="post" action="/api/cycle"><button>지금 출석 1회 실행</button></form>
<form method="post" action="/api/login"><button>로그인용 브라우저 10분 열기</button></form>
<h2>로그</h2><pre id="log"></pre>
<script>
async function tick(){
 try{const r=await fetch('/api/status');const s=await r.json();
 st.textContent=s.last_status;last.textContent=s.last_run;next.textContent=s.next_run;
 tg.checked=s.settings.telegram;sess.textContent=s.has_session ? '있음' : '없음 (로그인 필요)';
 log.textContent=s.log.slice().reverse().join('\n');}catch(e){}
}
setInterval(tick,5000);tick();
</script></body></html>"""


def relay_websockify(conn):
    """noVNC용 WebSocket→VNC(TCP) 중계. 같은 포트에서 /websockify 경로로 받는다."""
    try:
        vnc = socket.create_connection((VNC_HOST, VNC_PORT), timeout=10)
    except OSError:
        return
    conn.setblocking(False)
    vnc.setblocking(False)
    cbuf = bytearray()
    try:
        while True:
            r, _, _ = select.select([conn, vnc], [], [], 120)
            if conn in r:
                data = conn.recv(65536)
                if not data:
                    break
                cbuf += data
                while True:  # 클라이언트 프레임 파싱 (마스크 해제)
                    if len(cbuf) < 2:
                        break
                    b1, b2 = cbuf[0], cbuf[1]
                    op, ln, idx = b1 & 15, b2 & 127, 2
                    if ln == 126:
                        if len(cbuf) < 4:
                            break
                        ln = struct.unpack(">H", cbuf[2:4])[0]
                        idx = 4
                    elif ln == 127:
                        if len(cbuf) < 10:
                            break
                        ln = struct.unpack(">Q", cbuf[2:10])[0]
                        idx = 10
                    if len(cbuf) < idx + 4 + ln:
                        break
                    mask = cbuf[idx:idx + 4]
                    # ponytail: pure-python unmask, LAN VNC 수준은 충분. 병목 보이면 C 확장 고려
                    payload = bytes(cbuf[idx + 4 + j] ^ mask[j % 4] for j in range(ln))
                    del cbuf[:idx + 4 + ln]
                    if op == 8:
                        return
                    if op == 9:
                        conn.sendall(b"\x8a\x00")  # pong
                    elif op in (0, 1, 2):
                        vnc.sendall(payload)
            if vnc in r:
                data = vnc.recv(32768)
                if not data:
                    break
                n = len(data)
                if n < 126:
                    hdr = bytes([0x82, n])
                elif n < 65536:
                    hdr = bytes([0x82, 126]) + struct.pack(">H", n)
                else:
                    hdr = bytes([0x82, 127]) + struct.pack(">Q", n)
                conn.sendall(hdr + data)
    except OSError:
        pass
    finally:
        try:
            vnc.close()
        except OSError:
            pass


class Handler(BaseHTTPRequestHandler):
    server_version = "skport-agent/1"

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            self._send(200, PAGE)
        elif self.path.startswith("/preview.png"):
            self._send(503, "브라우저 꺼짐 (매일 01:23 UTC+8에만 켜짐)", "text/plain; charset=utf-8")
        elif self.path == "/api/status":
            state["has_session"] = os.path.isfile(checkin.STATE_FILE)
            self._send(200, json.dumps(state, ensure_ascii=False), "application/json; charset=utf-8")
        elif self.path == "/websockify" or self.path.startswith("/websockify?"):
            if self.headers.get("Upgrade", "").lower() != "websocket":
                self._send(400, "websocket expected", "text/plain")
                return
            key = self.headers.get("Sec-WebSocket-Key", "")
            accept = base64.b64encode(hashlib.sha1((key + WS_GUID).encode()).digest()).decode()
            self.connection.sendall(
                ("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                 "Connection: Upgrade\r\nSec-WebSocket-Protocol: binary\r\n"
                 f"Sec-WebSocket-Accept: {accept}\r\n\r\n").encode())
            relay_websockify(self.connection)
        else:
            self._serve_novnc()

    def _serve_novnc(self):
        rel = urllib.parse.unquote(urllib.parse.urlparse(self.path).path.lstrip("/"))
        if not rel or rel.endswith("/"):
            rel += "vnc.html"
        target = os.path.realpath(os.path.join(NOVNC_DIR, rel))
        if not target.startswith(NOVNC_DIR + "/") or not os.path.isfile(target):
            self._send(404, "not found", "text/plain")
            return
        with open(target, "rb") as f:
            self._send(200, f.read(), MIME.get(os.path.splitext(target)[1].lower(), "application/octet-stream"))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        form = urllib.parse.parse_qs(self.rfile.read(length).decode())
        if self.path == "/api/settings":
            state["settings"]["telegram"] = "telegram" in form
            save_settings()
            wake.set()
            add_log(f"설정 변경: {state['settings']}")
        elif self.path == "/api/cycle":
            threading.Thread(target=do_cycle, args=("수동 실행",), daemon=True).start()
        elif self.path == "/api/login":
            threading.Thread(target=do_login_window, args=("수동 로그인",), daemon=True).start()
        else:
            self._send(404, "not found", "text/plain")
            return
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    load_settings()
    threading.Thread(target=worker, daemon=True).start()
    add_log(f"에이전트 시작 (UI :{UI_PORT})")
    ThreadingHTTPServer(("0.0.0.0", UI_PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
