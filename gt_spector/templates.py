from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image

GAME_VERSION = "Doomsday_1.59.0"
TEMPLATE_ROOT = Path.home() / ".config" / "gt-spector" / "templates"


@dataclass
class Template:
    name: str
    shape: str
    x: int
    y: int
    w: int
    h: int
    game_version: str
    score_threshold: float
    reader: str = "vlm"


def _index_path() -> Path:
    return TEMPLATE_ROOT / "templates.json"


def _patch_path(name: str) -> Path:
    return TEMPLATE_ROOT / "patches" / f"{name}.png"


def _mask_path(name: str) -> Path:
    return TEMPLATE_ROOT / "patches" / f"{name}_mask.png"


def template_dir() -> Path:
    return TEMPLATE_ROOT


def load_templates() -> list[Template]:
    p = _index_path()
    if not p.exists():
        return []
    data = json.loads(p.read_text())
    try:
        return [Template(**m) for m in data]
    except (KeyError, TypeError):
        return []


def save_template(t: Template, patch: np.ndarray, mask: np.ndarray | None = None) -> Template:
    templates = [x for x in load_templates() if x.name != t.name]
    TEMPLATE_ROOT.mkdir(parents=True, exist_ok=True)
    (TEMPLATE_ROOT / "patches").mkdir(parents=True, exist_ok=True)
    Image.fromarray(patch[:, :, :3]).save(_patch_path(t.name))
    if mask is not None:
        Image.fromarray((mask * 255).astype(np.uint8)).save(_mask_path(t.name))
    templates.append(t)
    _index_path().write_text(json.dumps([asdict(x) for x in templates], indent=2))
    return t


def delete_template(name: str) -> None:
    templates = [x for x in load_templates() if x.name != name]
    _index_path().write_text(json.dumps([asdict(x) for x in templates], indent=2))
    _patch_path(name).unlink(missing_ok=True)
    _mask_path(name).unlink(missing_ok=True)


def get_patch(name: str) -> np.ndarray | None:
    p = _patch_path(name)
    if not p.exists():
        return None
    return np.asarray(Image.open(p).convert("RGB"))


def get_mask(name: str) -> np.ndarray | None:
    p = _mask_path(name)
    if not p.exists():
        return None
    return (np.asarray(Image.open(p).convert("L")) > 127).astype(np.uint8)
