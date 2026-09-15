"""설정 모델 + settings.json persistence. manager.py:74-84의 검증 강화판."""
import json
import os

from pydantic import BaseModel, ConfigDict, ValidationError

from app import state

# 알림 자격 필드 → 환경변수. settings.json 값이 없으면 env로 폴백(Docker 하위호환).
ENV_FALLBACK = {
    "telegram_bot_token": "TELEGRAM_BOT_TOKEN",
    "telegram_chat_id": "TELEGRAM_CHAT_ID",
    "telegram_mention_id": "TELEGRAM_MENTION_ID",
    "discord_webhook_url": "DISCORD_WEBHOOK_URL",
}


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")  # refresh_minutes 등 구키 무시
    telegram: bool = True
    discord: bool = True
    claimed_day: int = 0
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_mention_id: str = ""
    discord_webhook_url: str = ""


def effective_settings(data: dict) -> dict:
    """저장값에 env 폴백을 적용한 실제 사용값(state/notify용)."""
    out = dict(data)
    for field, env in ENV_FALLBACK.items():
        if not out.get(field):
            out[field] = os.environ.get(env, "")
    return out


def read_raw_settings() -> dict:
    """settings.json 원문(env 폴백 없음). 없거나 파손이면 {}."""
    try:
        with open(state.get_settings_file(), encoding="utf-8") as f:
            loaded = json.load(f)
        return loaded if isinstance(loaded, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}


def load_settings() -> None:
    """settings.json → 검증 → env 폴백 → state에 저장. 없음·파손·검증실패 → 기본값."""
    raw = read_raw_settings()
    try:
        validated = Settings(**raw)
    except ValidationError:
        print("[warn] settings invalid, using defaults", flush=True)
        validated = Settings()
    state.state["settings"] = effective_settings(validated.model_dump())


def save_settings(s: Settings) -> None:
    os.makedirs(state.get_data_dir(), exist_ok=True)
    with open(state.get_settings_file(), "w", encoding="utf-8") as f:
        json.dump(s.model_dump(), f)


def save_claimed_day(day: int) -> None:
    """claimed_day만 원문 settings.json에 반영. env로만 준 시크릿을 파일에 굳히지 않는다."""
    try:
        raw = Settings(**read_raw_settings()).model_dump()
    except ValidationError:
        raw = Settings().model_dump()
    raw["claimed_day"] = day
    updated = Settings(**raw)
    save_settings(updated)
    state.state["settings"] = effective_settings(updated.model_dump())
