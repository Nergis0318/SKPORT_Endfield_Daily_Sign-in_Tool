"""FastAPI 앱 공유 상태. manager.py:22-71에서 HTTP/WS 제외하고 이식."""
import datetime
import os
import threading
import time

UTC8 = datetime.timezone(datetime.timedelta(hours=8))
NOVNC_DIR = "/usr/share/novnc"  # Docker 이미지에 포함 (noVNC 정적 서빙)
VNC_HOST, VNC_PORT = "127.0.0.1", 5900
LOGIN_WINDOW_MINUTES = 10

state = {
    "settings": {
        "telegram": True,
        "discord": True,
        "claimed_day": 0,
        "telegram_bot_token": "",
        "telegram_chat_id": "",
        "telegram_mention_id": "",
        "discord_webhook_url": "",
    },
    "last_status": "-",
    "last_run": "-",
    "next_run": "-",
    "log": [],
}
login_open = threading.Event()  # 로그인 창이 열려 있으면 출석 사이클은 건너뜀


def get_data_dir() -> str:
    return os.environ.get("SKPORT_DATA_DIR", "data")


def get_settings_file() -> str:
    return os.path.join(get_data_dir(), "settings.json")


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def add_log(msg: str) -> None:
    state["log"].append(f"{now()} {msg}")
    del state["log"][:-20]
    print(msg, flush=True)
