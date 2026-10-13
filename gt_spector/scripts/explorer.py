"""Interactive game explorer with VLM-based screen analysis.

Usage:
  python -m gt_spector.scripts.explorer <display>   — interactive mode
  python -m gt_spector.scripts.explorer <display> analyze   — one-shot analyze

Interactive commands:
  a[nalyze] [prompt..] — capture + VLM analyze current screen
  click x y            — click at coordinates
  c[coord] label       — click a nav_table label (e.g., c alliance)
  esc [n]              — press Escape n times
  key k                — press a keyboard key
  scroll up/down [n]   — scroll
  drag x1 y1 x2 y2     — drag from (x1,y1) to (x2,y2)
  wait [s]             — wait seconds
  sa[ve] [tag]         — save screenshot
  pixel x y            — read RGB at pixel
  nav NAME             — navigate to named screen (shelter, alliance, region)
  ask "question"       — ask VLM a custom question about current screen
  go                   — VLM decides what to click to progress
  status               — show display, window, cycle info
  log msg              — write message to log
  mark x y [label]     — persistent overlay marker on game window
  unmark [label]       — remove marker(s)
  overlay start|stop   — manage overlay daemon
  help                 — this help
  quit                 — exit
"""

import json
import logging
import mmap
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("explorer")

LOG_DIR = Path(os.path.expanduser("~/.config/gt-spector/exploration"))
NAV_TABLE_PATH = Path(os.path.expanduser("~/.config/gt-spector/nav_table.json"))


class ShmReader:
    def __init__(self, display: int):
        self._path = f"/dev/shm/gt-spector-{display}-frame"
        self._mmap = None

    def read_frame(self) -> np.ndarray | None:
        try:
            if self._mmap is None:
                fd = os.open(self._path, os.O_RDONLY)
                size = os.lseek(fd, 0, os.SEEK_END)
                self._mmap = mmap.mmap(fd, size, access=mmap.ACCESS_READ)
                os.close(fd)
            header = bytes(self._mmap[:16])
            _c, w, h = struct.unpack("<QII", header)
            data = np.frombuffer(self._mmap, dtype=np.uint8, offset=16, count=w * h * 4)
            return data.copy().reshape(h, w, 4)
        except Exception as e:
            logger.error("SHM read failed: %s", e)
            return None


class Input:
    def __init__(self, display: int):
        self._env = {"DISPLAY": f":{display}"}
        self._wid = None

    def _find_window(self) -> str:
        if self._wid:
            return self._wid
        r = subprocess.run(
            ["xdotool", "search", "--name", "Doomsday: Last Survivors"],
            capture_output=True, text=True, env=self._env, timeout=5,
        )
        wins = r.stdout.strip().split()
        self._wid = wins[0] if wins else ""
        return self._wid

    def click(self, x: int, y: int):
        w = self._find_window()
        if not w:
            logger.error("No game window found")
            return
        subprocess.run(["xdotool", "mousemove", "--window", w, str(x), str(y)],
                       env=self._env, timeout=5, capture_output=True)
        subprocess.run(["xdotool", "click", "--window", w, "1"],
                       env=self._env, timeout=5, capture_output=True)

    def key(self, key: str):
        w = self._find_window()
        args = ["xdotool", "key"]
        if w:
            args += ["--window", w]
        args.append(key)
        subprocess.run(args, env=self._env, timeout=5, capture_output=True)

    def scroll(self, direction: str, amount: int = 3):
        btn = "4" if direction == "up" else "5"
        subprocess.run(["xdotool", "click", "--repeat", str(amount), "--delay", "100", btn],
                       env=self._env, timeout=5, capture_output=True)

    def drag(self, x1: int, y1: int, x2: int, y2: int):
        w = self._find_window()
        if not w:
            return
        subprocess.run(["xdotool", "mousemove", "--window", w, str(x1), str(y1)],
                       env=self._env, timeout=5, capture_output=True)
        subprocess.run(["xdotool", "mousedown", "1"], env=self._env, timeout=5, capture_output=True)
        steps = max(1, int(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 / 10))
        for i in range(1, steps + 1):
            t = i / steps
            x = int(x1 + (x2 - x1) * t)
            y = int(y1 + (y2 - y1) * t)
            subprocess.run(["xdotool", "mousemove", "--window", w, str(x), str(y)],
                           env=self._env, timeout=5, capture_output=True)
            time.sleep(0.01)
        subprocess.run(["xdotool", "mouseup", "1"], env=self._env, timeout=5, capture_output=True)


class Explorer:
    def __init__(self, display: int):
        self.display = display
        self.shm = ShmReader(display)
        self.input = Input(display)
        self._cycle = 0
        self._nav_table = self._load_nav_table()
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self._log_file = LOG_DIR / f"explore_d{display}.jsonl"

    def _load_nav_table(self) -> dict:
        try:
            return json.loads(NAV_TABLE_PATH.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {"states": {}, "transitions": []}

    def _save_screenshot(self, frame: np.ndarray, tag: str = "") -> str:
        ts = int(time.time())
        name = f"d{self.display}_{ts}{'_' + tag if tag else ''}.jpg"
        path = str(LOG_DIR / name)
        Image.fromarray(frame[:, :, :3]).save(path, quality=85)
        return path

    def _log_entry(self, entry: dict):
        with open(self._log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def _call_vlm(self, prompt: str, max_tokens: int = 500) -> str:
        import requests as req
        frame = self.shm.read_frame()
        if frame is None:
            return "No frame available"
        import base64
        import io
        buf = io.BytesIO()
        Image.fromarray(frame[:, :, :3]).save(buf, format="JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode()
        resp = req.post("http://127.0.0.1:8080/v1/chat/completions", json={
            "model": "/usr/local/devel/models/Qwen3VL-8B-Instruct-Q4_K_M.gguf",
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": prompt},
            ]}],
            "max_tokens": max_tokens,
            "temperature": 0,
        }, timeout=120)
        result = resp.json()
        content = result["choices"][0]["message"]["content"]
        timings = result.get("timings", {})
        if timings:
            info = f"[{timings.get('prompt_n',0)}p/{timings.get('predicted_n',0)}g tok, {timings.get('prompt_per_token_ms',0):.1f}ms/pt]"
        else:
            info = ""
        self._log_entry({
            "ts": int(time.time()), "cycle": self._cycle,
            "action": "vlm", "prompt": prompt[:100], "result": content,
        })
        return content + "\n" + info

    def analyze(self) -> str:
        result = self._call_vlm(
            "Identify this Doomsday: Last Survivors screen in ONE phrase. "
            "Then list every interactive element (buttons, tabs, icons) with exact x,y pixel coordinates. "
            "Note any tutorial pointers, popups, red badges, or unread indicators. "
            "Format: SCREEN: <name> | BUTTONS: <label> @ (x,y), ... | NOTES: <anything notable>",
            max_tokens=400,
        )
        self._cycle += 1
        return result.replace("\n", "\n  ")

    def ask(self, question: str) -> str:
        return self._call_vlm(question, max_tokens=600).replace("\n", "\n  ")

    def go(self) -> str:
        """VLM decides the next click to progress the game/tutorial."""
        return self._call_vlm(
            "Look at this Doomsday: Last Survivors screen. "
            "What is the single most important thing to click next to progress the game or tutorial? "
            "Answer ONLY with: x=<x> y=<y> reason=<one sentence>",
            max_tokens=50,
        )

    def screenshot(self, tag: str = "") -> str | None:
        frame = self.shm.read_frame()
        if frame is None:
            return None
        return self._save_screenshot(frame, tag)

    def click(self, x: int, y: int):
        logger.info("click %s %s", x, y)
        self.input.click(x, y)
        self._log_entry({"ts": int(time.time()), "action": "click", "x": x, "y": y})

    def coord_click(self, label: str) -> bool:
        for state_name, state in self._nav_table.get("states", {}).items():
            for btn in state.get("buttons", []):
                if btn["label"].lower() == label.lower():
                    self.click(btn["x"], btn["y"])
                    return True
        logger.warning("No nav_table entry for '%s'", label)
        return False

    def esc(self, n: int = 1):
        for _ in range(n):
            self.input.key("Escape")
            time.sleep(1.5)
        self._log_entry({"ts": int(time.time()), "action": "esc", "n": n})

    def key(self, k: str):
        self.input.key(k)
        self._log_entry({"ts": int(time.time()), "action": "key", "key": k})

    def scroll(self, direction: str, amount: int = 3):
        self.input.scroll(direction, amount)
        self._log_entry({"ts": int(time.time()), "action": "scroll", "direction": direction, "amount": amount})

    def drag(self, x1: int, y1: int, x2: int, y2: int):
        self.input.drag(x1, y1, x2, y2)
        self._log_entry({"ts": int(time.time()), "action": "drag", "x1": x1, "y1": y1, "x2": x2, "y2": y2})

    def wait(self, s: float = 2.0):
        time.sleep(s)
        self._log_entry({"ts": int(time.time()), "action": "wait", "seconds": s})

    def pixel(self, x: int, y: int) -> str:
        frame = self.shm.read_frame()
        if frame is None:
            return "No frame"
        r, g, b = frame[y, x, :3]
        return f"({x},{y}) = RGB({r},{g},{b})  #{r<<16|g<<8|b:06x}"

    def nav_to(self, target: str):
        target = target.lower()
        if target == "shelter":
            self("NAV to shelter (ESC x8)")
            for _ in range(8):
                self.input.key("Escape")
                time.sleep(2)
        elif target == "alliance":
            self.nav_to("shelter")
            self.wait(1)
            self.click(847, 740)
            self.wait(3)
        elif target == "region":
            self.nav_to("shelter")
            self.wait(1)
            self.click(50, 764)
            self.wait(3)
        else:
            logger.warning("Unknown nav target: %s", target)

    def status(self):
        print(f"  Display: :{self.display}")
        print(f"  Cycle:   {self._cycle}")
        print(f"  Log:     {self._log_file}")
        print(f"  Nav tbl: {len(self._nav_table.get('states',{}))} states, {len(self._nav_table.get('transitions',[]))} transitions")

    def run_cmd(self, line: str):
        args = line.strip().split()
        if not args:
            return
        cmd = args[0]

        if cmd in ("q", "quit", "exit"):
            return False

        elif cmd in ("a", "analyze"):
            if len(args) > 1:
                prompt = " ".join(args[1:])
                print(self._call_vlm(prompt, max_tokens=600))
            else:
                print(self.analyze())

        elif cmd in ("ask",):
            print(self.ask(" ".join(args[1:])))
            self._cycle += 1

        elif cmd == "go":
            print(self.go())
            self._cycle += 1

        elif cmd == "click":
            if len(args) >= 3:
                self.click(int(args[1]), int(args[2]))
            else:
                logger.warning("Usage: click x y")

        elif cmd in ("c", "coord"):
            if len(args) >= 2:
                self.coord_click(args[1])
            else:
                logger.warning("Usage: c <label>")

        elif cmd == "esc":
            n = int(args[1]) if len(args) > 1 and args[1].isdigit() else 1
            self.esc(n)

        elif cmd == "key":
            if len(args) >= 2:
                self.key(args[1])
            else:
                logger.warning("Usage: key <keyname>")

        elif cmd == "scroll":
            direction = args[1] if len(args) > 1 else "down"
            amount = int(args[2]) if len(args) > 2 and args[2].isdigit() else 3
            self.scroll(direction, amount)

        elif cmd == "drag":
            if len(args) >= 5:
                self.drag(int(args[1]), int(args[2]), int(args[3]), int(args[4]))
            else:
                logger.warning("Usage: drag x1 y1 x2 y2")

        elif cmd in ("w", "wait"):
            s = float(args[1]) if len(args) > 1 else 2.0
            self.wait(s)

        elif cmd in ("sa", "save"):
            tag = " ".join(args[1:]) if len(args) > 1 else ""
            path = self.screenshot(tag)
            if path:
                print(f"  Saved: {path}")

        elif cmd == "pixel":
            if len(args) >= 3:
                print(f"  {self.pixel(int(args[1]), int(args[2]))}")
            else:
                logger.warning("Usage: pixel x y")

        elif cmd == "nav":
            if len(args) >= 2:
                self.nav_to(args[1])
            else:
                logger.warning("Usage: nav shelter|alliance|region")

        elif cmd == "status":
            self.status()

        elif cmd == "log":
            if len(args) > 1:
                self._log_entry({"ts": int(time.time()), "action": "manual_log", "msg": " ".join(args[1:])})
                print("  logged:", " ".join(args[1:]))

        elif cmd in ("mark", "unmark", "overlay"):
            self._handle_overlay(cmd, args[1:])

        elif cmd in ("h", "help"):
            print(__doc__)

        else:
            logger.warning("Unknown: %s (try 'help')", cmd)
        return True

    def _handle_overlay(self, cmd: str, args: list[str]):
        """mark <x> <y> [label] | unmark [label] | overlay start|stop|status"""
        try:
            from gt_spector.overlay import _send_cmd
        except ImportError:
            logger.error("overlay module not available")
            return

        if cmd == "overlay":
            action = args[0] if args else "status"
            if action == "start":
                import subprocess
                import sys
                proc = subprocess.Popen(
                    [sys.executable, "-m", "gt_spector.overlay",
                     str(self.display), "start"],
                    env={**os.environ, "DISPLAY": f":{self.display}"},
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                logger.info("  Overlay started (pid %s)", proc.pid)
                time.sleep(0.5)
            elif action == "stop":
                resp = _send_cmd(self.display, {"cmd": "quit"})
                logger.info("  Overlay: %s", resp.get("ok", False))
            else:
                resp = _send_cmd(self.display, {"cmd": "list"})
                logger.info("  Overlay: %s", "running" if resp.get("ok") else "stopped")

        elif cmd == "mark":
            if len(args) < 2:
                logger.warning("Usage: mark <x> <y> [label]")
                return
            x, y = int(args[0]), int(args[1])
            label = " ".join(args[2:]) if len(args) > 2 else f"m{x}_{y}"
            mid = label
            resp = _send_cmd(self.display, {
                "cmd": "mark", "id": mid, "x": x, "y": y,
                "r": 0, "g": 255, "b": 0, "label": label,
            })
            if resp.get("ok"):
                logger.info("  Marker '%s' at (%d,%d)", label, x, y)
            else:
                logger.warning("  Marker failed: %s", resp.get("error", "unknown"))
            # Auto-start overlay if not running
            if not resp.get("ok") and "not running" in resp.get("error", ""):
                self._handle_overlay("overlay", ["start"])
                resp = _send_cmd(self.display, {
                    "cmd": "mark", "id": mid, "x": x, "y": y,
                    "r": 0, "g": 255, "b": 0, "label": label,
                })
                if resp.get("ok"):
                    logger.info("  Marker '%s' at (%d,%d)", label, x, y)

        elif cmd == "unmark":
            label = " ".join(args) if args else None
            resp = _send_cmd(self.display, {"cmd": "clear", "id": label})
            if resp.get("ok"):
                logger.info("  Cleared marker '%s'", label or "all")
            else:
                logger.warning("  Clear failed: %s", resp.get("error", "unknown"))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    display = int(sys.argv[1])
    exp = Explorer(display)

    if len(sys.argv) > 2:
        exp.run_cmd(" ".join(sys.argv[2:]))
        return

    print(f"gt-spector explorer — display :{display}")
    print("Type 'help' for commands, Ctrl+D or 'quit' to exit")
    print()

    while True:
        try:
            line = input(">> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if exp.run_cmd(line) is False:
            break


if __name__ == "__main__":
    main()
