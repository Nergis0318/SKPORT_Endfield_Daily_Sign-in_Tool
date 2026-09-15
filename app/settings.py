"""설정 모델 + settings.json persistence. manager.py:74-84의 검증 강화판."""
import json
import os

from pydantic import BaseModel, ConfigDict, ValidationError

from app import state


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")  # refresh_minutes 등 구키 무시
    telegram: bool = True
    claimed_day: int = 0


def load_settings() -> None:
    """settings.json → 검증 → state에 dict 저장. 없음·파손·검증실패 → 기본값."""
    raw: dict = {}
    try:
        with open(state.get_settings_file(), encoding="utf-8") as f:
            loaded = json.load(f)
        raw = loaded if isinstance(loaded, dict) else {}
    except (FileNotFoundError, ValueError):
        raw = {}
    try:
        validated = Settings(**raw)
    except ValidationError:
        print("[warn] settings invalid, using defaults", flush=True)
        validated = Settings()
    state.state["settings"] = {"telegram": validated.telegram, "claimed_day": validated.claimed_day}


def save_settings(s: Settings) -> None:
    os.makedirs(state.get_data_dir(), exist_ok=True)
    with open(state.get_settings_file(), "w", encoding="utf-8") as f:
        json.dump(s.model_dump(), f)
