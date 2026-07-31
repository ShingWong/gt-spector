"""Rotating logs: one system log + one log per bot.

Rotation: when a file exceeds settings.log_max_bytes(), the current file is
renamed to <name>.log.1 (replacing any existing .1), and a new file starts.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from gt_spector import settings

LOGS_DIR = settings.CONFIG_DIR / "logs"


def _stamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _rotate(path: Path) -> None:
    try:
        if path.exists() and path.stat().st_size > settings.log_max_bytes():
            backup = path.with_suffix(path.suffix + ".1")
            if backup.exists():
                backup.unlink()
            os.replace(path, backup)
    except (OSError, ValueError):
        pass


def _append(path: Path, msg: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _rotate(path)
        with open(path, "a") as f:
            f.write(f"[{_stamp()}] {msg}\n")
    except OSError:
        print(f"log error: {path}: {msg}", file=__import__("sys").stderr)


def log_system(msg: str) -> None:
    _append(LOGS_DIR / "system.log", msg)


def log_bot(name: str, msg: str) -> None:
    _append(LOGS_DIR / f"{name}.log", msg)


def clear_all_logs() -> None:
    for p in LOGS_DIR.glob("*.log*"):
        try:
            p.unlink()
        except OSError:
            pass
