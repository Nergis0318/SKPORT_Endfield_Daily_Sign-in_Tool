"""SKPORT 상시 에이전트(FastAPI). Docker 진입점(agent-entrypoint.sh)에서 uvicorn으로 기동."""
import os
import urllib.parse
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import checkin
from app import runner, scheduler, state
from app.settings import Settings, load_settings, save_settings
from app.vnc import proxy as vnc_proxy

templates = Jinja2Templates(directory="app/templates")


def _as_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "on", "yes")
    return bool(value)


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(state.get_data_dir(), exist_ok=True)
    load_settings()
    scheduler.start()
    state.add_log("에이전트 시작 (FastAPI)")
    yield
    scheduler.shutdown()
    runner.executor.shutdown(wait=False)


app = FastAPI(lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/api/status")
def api_status():
    return JSONResponse({**state.state, "has_session": os.path.isfile(checkin.STATE_FILE)})


@app.post("/api/settings")
async def api_settings(request: Request):
    if request.headers.get("content-type", "").startswith("application/json"):
        body = await request.json()
        if isinstance(body, dict):
            telegram = _as_bool(body.get("telegram", False))
        else:  # JSON 리스트 등 비객체 → 설정 변경 없음
            telegram = state.state["settings"]["telegram"]
    else:  # 기존 form 호환 (python-multipart 없이 수동 파싱)
        raw = (await request.body()).decode()
        telegram = "telegram" in urllib.parse.parse_qs(raw)
    updated = Settings(telegram=telegram, claimed_day=state.state["settings"]["claimed_day"])
    state.state["settings"] = {"telegram": updated.telegram, "claimed_day": updated.claimed_day}
    save_settings(updated)
    state.add_log(f"설정 변경: {state.state['settings']}")
    return {"settings": state.state["settings"]}


@app.post("/api/cycle", status_code=202)
def api_cycle():
    scheduler.request_cycle()
    return {"queued": True}


@app.post("/api/login", status_code=202)
def api_login():
    scheduler.request_login()
    return {"queued": True}


@app.get("/preview.png")
def preview():
    return PlainTextResponse("브라우저 꺼짐 (매일 01:23 UTC+8에만 켜짐)", status_code=503)


@app.websocket("/websockify")
async def websockify(ws: WebSocket):
    await vnc_proxy(ws)


app.mount("/", StaticFiles(directory=state.NOVNC_DIR, html=True, check_dir=False), name="novnc")