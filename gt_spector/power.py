"""Bot power CLI: start/stop/restart bots via BotManager."""

from __future__ import annotations

import sys
import time
from typing import Any

from gt_spector.bot_manager import BotManager

ACTIONS = ("start", "stop", "restart")
START_WAIT = 5.0


def run_power_command(manager: BotManager, action: str, target: str) -> int:
    """Run start/stop/restart on a bot or all bots. Returns the exit code."""
    if action not in ACTIONS:
        print(f"error: unknown action '{action}'", file=sys.stderr)
        return 2
    targets = list(manager.bots) if target == "all" else [manager.get(target)]
    if not targets or targets[0] is None:
        print(f"error: unknown bot '{target}'", file=sys.stderr)
        return 1
    failed = False
    for bot in targets:
        if bot is None:
            continue
        try:
            _do(manager, action, bot)
        except (OSError, RuntimeError) as e:
            print(f"error: {bot.name}: {e}", file=sys.stderr)
            failed = True
            continue
        print(f"{bot.name}: {_state(manager, bot, action)}")
    return 1 if failed else 0


def _do(manager: BotManager, action: str, bot: Any) -> None:
    if action == "start":
        manager.start_game(bot)
    elif action == "stop":
        manager.stop_game(bot)
    else:
        manager.restart_game(bot)


def _state(manager: BotManager, bot: Any, action: str) -> str:
    if action in ("start", "restart"):
        time.sleep(START_WAIT)
    manager._refresh_state(bot)
    return bot.state.value if hasattr(bot.state, "value") else str(bot.state)
