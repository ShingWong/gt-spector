"""Control game audio via PipeWire pactl.

Each game process emits sink-inputs carrying application.process.id = game_pid.
"""

from __future__ import annotations

import re
import subprocess


def _pactl_list() -> str:
    try:
        r = subprocess.run(
            ["pactl", "list", "sink-inputs"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        return r.stdout
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return ""


def get_sink_inputs(game_pid: int) -> list[int]:
    out = _pactl_list()
    result: list[int] = []
    current: int | None = None
    for line in out.splitlines():
        m = re.match(r"Sink Input #(\d+)", line.strip())
        if m:
            current = int(m.group(1))
            continue
        if current is None:
            continue
        pm = re.search(r'application\.process\.id\s*=\s*"(\d+)"', line)
        if pm and int(pm.group(1)) == game_pid:
            result.append(current)
    return result


def set_muted(game_pid: int, muted: bool) -> None:
    for sid in get_sink_inputs(game_pid):
        try:
            subprocess.run(
                ["pactl", "set-sink-input-mute", str(sid), "1" if muted else "0"],
                capture_output=True, timeout=5, check=False,
            )
        except (FileNotFoundError, subprocess.SubprocessError, OSError):
            pass


def is_muted(game_pid: int) -> bool | None:
    out = _pactl_list()
    ids = set(get_sink_inputs(game_pid))
    if not ids:
        return None
    states: list[bool] = []
    current: int | None = None
    for line in out.splitlines():
        m = re.match(r"Sink Input #(\d+)", line.strip())
        if m:
            current = int(m.group(1))
            continue
        if current not in ids:
            continue
        mm = re.search(r"Mute:\s*(\w+)", line)
        if mm:
            states.append(mm.group(1) == "yes")
    if not states:
        return None
    return all(states)
