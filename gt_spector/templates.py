from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image

GAME_VERSION = "Doomsday_1.59.0"

# Templates are version-controlled with the project. The store lives in the
# repo (git-tracked) so template data is never lost. Authoring via the viewer
# writes straight into the git tree. TEMPLATE_ROOT can be overridden for tests
# or a user-local overlay (e.g. env GT_SPECTOR_TEMPLATE_ROOT).
TEMPLATE_ROOT = Path(__file__).resolve().parent / "templates_store"
if env_root := os.environ.get("GT_SPECTOR_TEMPLATE_ROOT"):
    TEMPLATE_ROOT = Path(env_root)


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
    return _cached("index", p, lambda: _parse_index(p))


def _parse_index(p: Path) -> list[Template]:
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
    _invalidate_cache()
    return t


def delete_template(name: str) -> None:
    templates = [x for x in load_templates() if x.name != name]
    _index_path().write_text(json.dumps([asdict(x) for x in templates], indent=2))
    _patch_path(name).unlink(missing_ok=True)
    _mask_path(name).unlink(missing_ok=True)
    _invalidate_cache()


# ── Cache ─────────────────────────────────────────────────────────────
# Templates and patches are read from disk on every locate, which dominates
# the hot path (PNG decode ~20ms each). Cache them by file mtime so repeated
# calls are free while newly-authored templates (viewer writes new mtime) are
# picked up without a restart.
_cache: dict[str, tuple[float, object]] = {}


def _invalidate_cache() -> None:
    _cache.clear()


def _cached(key: str, path: Path, load) -> object | None:
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return None
    hit = _cache.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    value = load()
    _cache[key] = (mtime, value)
    return value


def get_patch(name: str) -> np.ndarray | None:
    p = _patch_path(name)
    return _cached(f"patch:{name}", p,
                   lambda: np.asarray(Image.open(p).convert("RGB")))


def get_mask(name: str) -> np.ndarray | None:
    p = _mask_path(name)
    if not p.exists():
        return None
    return _cached(f"mask:{name}", p,
                   lambda: (np.asarray(Image.open(p).convert("L")) > 127).astype(np.uint8))
