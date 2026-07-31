"""Persistent settings for gt-spector: global + per-bot JSON files.

Layout:
  ~/.config/gt-spector/settings.json        global settings
  ~/.config/gt-spector/bots/<name>.json     per-bot settings

All writes are atomic (write temp file, then os.replace).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, cast

CONFIG_DIR = Path.home() / ".config" / "gt-spector"
GLOBAL_PATH = CONFIG_DIR / "settings.json"
BOTS_DIR = CONFIG_DIR / "bots"

DEFAULT_LOG_MAX_BYTES = 512 * 1024
DEFAULT_SOUND_MODE = "viewer"
DEFAULT_VLM_INTERVAL = 10.0
DEFAULT_VLM_DOWNSCALE = 2


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        return cast(dict[str, Any], json.loads(path.read_text()))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def get_global() -> dict[str, Any]:
    return load_json(GLOBAL_PATH, {})


def set_global(**kwargs: Any) -> None:
    data = get_global()
    data.update(kwargs)
    save_json(GLOBAL_PATH, data)


def get_bot(name: str) -> dict[str, Any]:
    return load_json(BOTS_DIR / f"{name}.json", {})


def set_bot(name: str, **kwargs: Any) -> None:
    data = get_bot(name)
    data.update(kwargs)
    save_json(BOTS_DIR / f"{name}.json", data)


def overlay_global_enabled() -> bool:
    return bool(get_global().get("overlay_global_enabled", True))


def set_overlay_global(enabled: bool) -> None:
    set_global(overlay_global_enabled=enabled)


def bot_overlay_enabled(name: str) -> bool:
    return cast(bool, get_bot(name).get("overlay_enabled", True))


def set_bot_overlay(name: str, enabled: bool) -> None:
    set_bot(name, overlay_enabled=enabled)


def sound_mode() -> str:
    return cast(str, get_global().get("sound_mode", DEFAULT_SOUND_MODE))


def set_sound_mode(mode: str) -> None:
    set_global(sound_mode=mode)


def bot_sound_muted(name: str) -> bool:
    return cast(bool, get_bot(name).get("sound_muted", False))


def set_bot_sound_muted(name: str, muted: bool) -> None:
    set_bot(name, sound_muted=muted)


def log_max_bytes() -> int:
    try:
        return int(get_global().get("log_max_bytes", DEFAULT_LOG_MAX_BYTES))
    except (TypeError, ValueError):
        return DEFAULT_LOG_MAX_BYTES


def set_log_max_bytes(n: int) -> None:
    set_global(log_max_bytes=max(1024, int(n)))


def vlm_interval() -> float:
    try:
        return float(get_global().get("vlm_interval", DEFAULT_VLM_INTERVAL))
    except (TypeError, ValueError):
        return DEFAULT_VLM_INTERVAL


def set_vlm_interval(seconds: float) -> None:
    set_global(vlm_interval=max(1.0, float(seconds)))


def vlm_downscale() -> int:
    try:
        return max(1, int(get_global().get("vlm_downscale", DEFAULT_VLM_DOWNSCALE)))
    except (TypeError, ValueError):
        return DEFAULT_VLM_DOWNSCALE


def set_vlm_downscale(factor: int) -> None:
    set_global(vlm_downscale=max(1, int(factor)))
