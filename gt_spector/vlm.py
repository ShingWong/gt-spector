"""VLM client for Qwen3-VL via llama.cpp server (OpenAI-compatible API)."""

import base64
import io
import json
import logging
from pathlib import Path

import numpy as np
import requests
from PIL import Image

logger = logging.getLogger(__name__)

SERVER_URL = "http://127.0.0.1:8080/v1/chat/completions"
MODEL = "/usr/local/devel/models/Qwen3VL-8B-Instruct-Q4_K_M.gguf"

ANALYSIS_PROMPT = """Describe this game screen from Doomsday: Last Survivors in detail.
What screen is this? List all UI elements you see: buttons, text, icons, numbers, bars, dialog boxes.
What interactive elements are present? What is the user supposed to do on this screen?
Look for: tutorial hand/glove pointers, popup dialogs, hero interfaces, resource displays, bottom toolbar.
If you see a tutorial hand or glove, describe exactly where it is pointing and what it is pointing at.
If you see any numbers on buttons (badges), note their positions and values.
If you see a popup dialog, describe its title, buttons, and text content."""


def frame_to_jpeg_base64(frame: np.ndarray, quality: int = 85) -> str:
    img = Image.fromarray(frame[:, :, :3])
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode()


def analyze_frame(frame: np.ndarray, prompt: str | None = None, max_tokens: int = 500, temperature: float = 0) -> dict:
    b64 = frame_to_jpeg_base64(frame)
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": prompt or ANALYSIS_PROMPT},
                ],
            }
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    resp = requests.post(SERVER_URL, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()


def analyze_crop(frame: np.ndarray, box: tuple[int, int, int, int],
                 prompt: str, upscale: int = 3) -> str:
    """Crop `box=(x0,y0,x1,y1)`, upscale, and run the VLM. Returns text."""
    x0, y0, x1, y1 = box
    crop = frame[y0:y1, x0:x1, :3]
    img = Image.fromarray(crop)
    if upscale > 1:
        img = img.resize((img.width * upscale, img.height * upscale), Image.Resampling.LANCZOS)
    result = analyze_frame(np.asarray(img), prompt=prompt)
    return str(result["choices"][0]["message"]["content"])


def analyze_screen(frame: np.ndarray) -> dict:
    """Quick screen classification: returns screen name and brief description."""
    prompt = """Identify this game screen from Doomsday: Last Survivors in ONE phrase (e.g. 'LOBBY - shelter base view', 'HERO_HEALING - Norah recovery', 'REGION_MAP - world view', 'ALLIANCE_MAIN', 'ALLIANCE_HELP', 'EXIT_DIALOG', 'EVENT_CALENDAR', 'TUTORIAL_OVERLAY', 'LOGIN_SCREEN', 'BATTLE', 'SHOP', 'BAG_INVENTORY', 'CAMPAIGN_MAP', 'UNKNOWN').
Then list visible interactive buttons/coordinates the player could click.
Format:
SCREEN: <name>
BUTTONS: <label1> at (~x,y), <label2> at (~x,y), ...
NOTES: <anything notable>"""
    return analyze_frame(frame, prompt=prompt, max_tokens=200)


def save_analysis_log(frame: np.ndarray, display: int, log_dir: str | Path, tag: str = "") -> dict:
    """Analyze frame, save screenshot + analysis JSON, return result."""
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    result = analyze_screen(frame)
    content = result["choices"][0]["message"]["content"]
    usage = result.get("usage", {})
    timings = result.get("timings", {})

    ts = int(__import__("time").time())
    suffix = f"_{tag}" if tag else ""
    img_path = log_dir / f"screen{ts}{suffix}.jpg"
    Image.fromarray(frame[:, :, :3]).save(str(img_path), quality=85)

    entry = {
        "timestamp": ts,
        "display": display,
        "analysis": content,
        "usage": usage,
        "timings": timings,
        "screenshot": str(img_path),
    }
    log_path = log_dir / "exploration_log.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")

    logger.info("Screen: %s", content.split("\n")[0] if "\n" in content else content[:80])
    return result
