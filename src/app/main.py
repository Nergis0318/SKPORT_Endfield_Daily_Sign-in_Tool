"""SKPORT 상시 에이전트(FastAPI). Docker 진입점(agent-entrypoint.sh)에서 uvicorn으로 기동."""

import os
import urllib.parse
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import checkin
from app import i18n, runner, scheduler, state
from app.settings import (
    Settings,
    effective_settings,
    load_settings,
    read_raw_settings,
    save_settings,
)
from app.vnc import proxy as vnc_proxy

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# 필드별 타입: bool 플래그 vs 문자열(자격증명·표시 언어)
BOOL_FIELDS = ("telegram", "discord")
STR_FIELDS = (
    "language",
    "telegram_bot_token",
    "telegram_chat_id",
    "telegram_mention_id",
    "discord_webhook_url",
)
# 시크릿 → 노출 플래그 이름
CONFIGURED_FLAGS = {
    "telegram_bot_token": "telegram_configured",
    "discord_webhook_url": "discord_configured",
}


def _as_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "on", "yes")
    return bool(value)


def _public_settings(s: dict) -> dict:
    """API 응답용. 시크릿 원문 대신 설정 여부 플래그만 노출."""
    out = dict(s)
    for field, flag in CONFIGURED_FLAGS.items():
        out[flag] = bool(s.get(field))
        out[field] = ""
    return out


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(state.get_data_dir(), exist_ok=True)
    load_settings()
    scheduler.start()
    state.add_log(i18n.t("log.agent_started"))
    yield
    scheduler.shutdown()
    runner.executor.shutdown(wait=False)


app = FastAPI(lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    lang = i18n.current_lang()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "t": i18n.t,  # 현재 언어로 렌더 (호출 시점 조회)
            "lang": lang,
            "html_lang": i18n.HTML_LANG[lang],
            "langs": i18n.LANGS,
            "lang_labels": i18n.LANG_LABELS,
            "status_text": i18n.status_texts(lang),  # 5초 폴링 JS가 쓰는 상태 라벨
        },
    )


@app.get("/api/status")
def api_status():
    return JSONResponse(
        {
            **state.state,
            "settings": _public_settings(state.state["settings"]),
            "has_session": os.path.isfile(checkin.STATE_FILE),
            "login_open": state.login_open.is_set(),
        }
    )


def _parse_form(raw: str) -> dict:
    """수동 form 파싱 (python-multipart 없이). 체크박스는 존재 시 True."""
    values = urllib.parse.parse_qs(raw)
    out: dict = {}
    for field in BOOL_FIELDS:
        out[field] = field in values
    for field in STR_FIELDS:
        if field in values:
            out[field] = values[field][0]
    return out


def _merge_settings(body: dict) -> Settings:
    """저장값(원문) 위에 요청 body를 병합. 생략 필드는 유지, 빈 문자열은 삭제."""
    try:
        current = Settings(**read_raw_settings()).model_dump()
    except Exception:
        current = Settings().model_dump()
    for field in BOOL_FIELDS:
        if field in body:
            current[field] = _as_bool(body[field])
    for field in STR_FIELDS:
        if field in body:
            current[field] = str(body[field]).strip()
    return Settings(**current)


@app.post("/api/settings")
async def api_settings(request: Request):
    if request.headers.get("content-type", "").startswith("application/json"):
        body = await request.json()
        body = body if isinstance(body, dict) else {}
    else:  # 기존 form 호환
        body = _parse_form((await request.body()).decode())
    if not body:  # 변경 없음 → 현재값 유지
        return {"settings": _public_settings(state.state["settings"])}
    updated = _merge_settings(body)
    save_settings(updated)
    state.state["settings"] = effective_settings(updated.model_dump())
    state.add_log(i18n.t("log.settings_changed", fields=", ".join(sorted(body))))
    return {"settings": _public_settings(state.state["settings"])}


@app.post("/api/cycle", status_code=202)
def api_cycle():
    scheduler.request_cycle()
    return {"queued": True}


@app.post("/api/login", status_code=202)
def api_login():
    scheduler.request_login()
    return {"queued": True}


@app.post("/api/close")
def api_close():
    """열려 있는 로그인용 브라우저를 즉시 닫는다. 열려 있지 않으면 closing=false."""
    return {"closing": runner.request_close()}


@app.get("/preview.png")
def preview():
    return PlainTextResponse(i18n.t("log.preview_off"), status_code=503)


@app.websocket("/websockify")
async def websockify(ws: WebSocket):
    await vnc_proxy(ws)


app.mount(
    "/",
    StaticFiles(directory=state.NOVNC_DIR, html=True, check_dir=False),
    name="novnc",
)
