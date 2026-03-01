from __future__ import annotations

import copy
import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.app_setting import AppSetting

STREAMER_SCORE_CONFIG_KEY = "streamer_score_config"

DEFAULT_STREAMER_SCORE_CONFIG: dict[str, Any] = {
    "league_influence": {
        "enabled": True,
        "weight": 0.35,
        "minimum_games": 3,
    },
    "skater": {
        "weights": {
            "points_per_game": 17.0,
            "shots_per_game": 17.0,
            "power_play_points_per_game": 5.0,
            "time_on_ice_per_game": 24.0,
            "plus_minus_per_game": 5.0,
            "hits_blocks_per_game": 5.0,
            "trend_hot_bonus": 15.0,
            "trend_stable_bonus": 5.0,
            "availability_bonus": 14.0,
        },
        "caps": {
            "forward": {
                "points_per_game": 1.4,
                "shots_per_game": 3.0,
                "power_play_points_per_game": 0.5,
                "time_on_ice_per_game": 21.0,
                "hits_blocks_per_game": 4.0,
            },
            "defense": {
                "points_per_game": 1.0,
                "shots_per_game": 2.6,
                "power_play_points_per_game": 0.6,
                "time_on_ice_per_game": 24.0,
                "hits_blocks_per_game": 5.0,
            },
        },
        "toggles": {
            "use_plus_minus": True,
            "use_hits_blocks": True,
            "use_trend_bonus": True,
            "use_availability_bonus": False,
            "use_toi_gate_for_availability": True,
        },
        "toi_gate": {
            "forward_floor": 14.0,
            "defense_floor": 16.0,
        },
    },
    "goalie": {
        "weights": {
            "save_percentage": 20.0,
            "goals_against_average": 15.0,
            "wins": 18.0,
            "starts": 17.0,
            "trend_hot_bonus": 15.0,
            "trend_stable_bonus": 5.0,
            "availability_bonus": 10.0,
        },
        "scales": {
            "save_percentage_floor": 0.88,
            "save_percentage_range": 0.05,
            "goals_against_average_ceiling": 3.5,
            "goals_against_average_range": 1.5,
        },
        "toggles": {
            "use_trend_bonus": True,
            "use_availability_bonus": False,
            "use_sample_penalty": True,
        },
    },
}


def get_default_streamer_score_config() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_STREAMER_SCORE_CONFIG)


def _to_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _sanitize_value(default_value: Any, user_value: Any) -> Any:
    if isinstance(default_value, bool):
        return _to_bool(user_value, default_value)
    if isinstance(default_value, (int, float)):
        return _to_float(user_value, float(default_value))
    if isinstance(default_value, dict):
        out: dict[str, Any] = {}
        user_dict = user_value if isinstance(user_value, dict) else {}
        for key, nested_default in default_value.items():
            out[key] = _sanitize_value(nested_default, user_dict.get(key))
        return out
    return user_value if user_value is not None else default_value


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(value, max_value))


def sanitize_streamer_score_config(payload: Any) -> dict[str, Any]:
    defaults = get_default_streamer_score_config()
    sanitized = _sanitize_value(defaults, payload)

    league_cfg = sanitized.get("league_influence", {})
    league_cfg["enabled"] = _to_bool(league_cfg.get("enabled"), True)
    league_cfg["weight"] = _clamp(_to_float(league_cfg.get("weight"), 0.35), 0.0, 1.0)
    min_games = int(round(_to_float(league_cfg.get("minimum_games"), 3)))
    league_cfg["minimum_games"] = max(0, min(82, min_games))
    sanitized["league_influence"] = league_cfg
    return sanitized


def get_streamer_score_config(db: Session) -> dict[str, Any]:
    row = db.query(AppSetting).filter(AppSetting.key == STREAMER_SCORE_CONFIG_KEY).first()
    if not row:
        defaults = get_default_streamer_score_config()
        db.add(
            AppSetting(
                key=STREAMER_SCORE_CONFIG_KEY,
                value_json=json.dumps(defaults, separators=(",", ":")),
                updated_at=datetime.utcnow(),
            )
        )
        db.commit()
        return defaults

    try:
        raw = json.loads(row.value_json)
    except json.JSONDecodeError:
        raw = {}

    sanitized = sanitize_streamer_score_config(raw)
    if sanitized != raw:
        row.value_json = json.dumps(sanitized, separators=(",", ":"))
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
    return sanitized


def save_streamer_score_config(db: Session, payload: Any) -> dict[str, Any]:
    sanitized = sanitize_streamer_score_config(payload)
    row = db.query(AppSetting).filter(AppSetting.key == STREAMER_SCORE_CONFIG_KEY).first()
    encoded = json.dumps(sanitized, separators=(",", ":"))
    if row:
        row.value_json = encoded
        row.updated_at = datetime.utcnow()
    else:
        row = AppSetting(
            key=STREAMER_SCORE_CONFIG_KEY,
            value_json=encoded,
            updated_at=datetime.utcnow(),
        )
    db.add(row)
    db.commit()
    return sanitized
