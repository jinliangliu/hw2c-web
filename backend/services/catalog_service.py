"""Catalog service — examples, MCU pinout, dynamic schemas and knowledge docs.

All file access goes through ``_safe_read``: a single place that rejects path
traversal and absolute paths.  MCP tools and resources must never be able to
reach outside the hw2c root.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from paths import get_hw2c_root

_HW2C_ROOT = get_hw2c_root()
if str(_HW2C_ROOT) not in sys.path:
    sys.path.insert(0, str(_HW2C_ROOT))

LAYERS = ("hardware", "task", "components", "bind", "params", "pubsub")
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")

_LAYER_MODELS = {
    "hardware": ("generator.schemas.hardware", "HardwareModel"),
    "task": ("generator.schemas.task", "TaskModel"),
    "components": ("generator.schemas.component", "ComponentsModel"),
    "bind": ("generator.schemas.bind", "BindModel"),
    "params": ("generator.schemas.param", "ParamsModel"),
    "pubsub": ("generator.schemas.pubsub", "PubSubModel"),
}


def _check_name(name: str) -> str:
    if (
        not isinstance(name, str)
        or not name
        or name in (".", "..")
        or Path(name).name != name
        or not _SAFE_NAME.fullmatch(name)
    ):
        raise ValueError(f"E_FORBIDDEN: unsafe name {name!r}")
    return name


def _safe_read(root: Path, relative: str) -> str:
    """Read a file under *root*, rejecting traversal and absolute paths."""
    relative = _check_name(relative)
    base = root.resolve()
    target = (base / relative).resolve()
    if base != target.parent:
        raise ValueError(f"E_FORBIDDEN: path outside {base}: {relative}")
    if not target.is_file():
        raise FileNotFoundError(f"not found: {relative}")
    return target.read_text(encoding="utf-8")


def list_examples() -> list[dict]:
    """Return every shipped example with a one-line summary."""
    import yaml

    examples_dir = _HW2C_ROOT / "examples"
    result: list[dict] = []
    if not examples_dir.is_dir():
        return result
    for child in sorted(examples_dir.iterdir()):
        if not child.is_dir() or not _SAFE_NAME.fullmatch(child.name):
            continue
        hw_path = child / "hardware.yaml"
        summary = "six-layer example"
        if hw_path.is_file():
            try:
                doc = yaml.safe_load(hw_path.read_text(encoding="utf-8")) or {}
                part = (doc.get("mcu") or {}).get("part", "unknown mcu")
                n_pins = len(doc.get("pins") or [])
                n_peri = len(doc.get("peripherals") or [])
                summary = f"{part} — {n_pins} pins, {n_peri} peripherals"
            except Exception:  # noqa: BLE001 - a broken example must not kill listing
                summary = "six-layer example (hardware.yaml unreadable)"
        result.append({"name": child.name, "summary": summary})
    return result


def get_example(name: str, layer: str | None = None) -> dict:
    """Return one or all six layers of a shipped example."""
    name = _check_name(name)
    if name not in {item["name"] for item in list_examples()}:
        raise ValueError(f"E_FORBIDDEN: unknown example {name!r}")
    example_dir = _HW2C_ROOT / "examples" / name
    if layer is None:
        return {
            item: _safe_read(example_dir, f"{item}.yaml")
            for item in LAYERS
            if (example_dir / f"{item}.yaml").is_file()
        }
    if layer not in LAYERS:
        raise ValueError(f"E_FORBIDDEN: unknown layer {layer!r}")
    return {"name": name, "layer": layer, "yaml": _safe_read(example_dir, f"{layer}.yaml")}


def get_mcu_pinout(part: str) -> dict:
    """Return pin assignments observed for *part* across shipped examples.

    There is no separate pinout database in this repo; the examples are the
    truthful, build-tested source.  Unknown parts return an empty list rather
    than an invented pinout — inventing registers/pins is exactly the class of
    bug that passes host tests but dies on real silicon.
    """
    import yaml

    _check_name(part)
    pins: list[dict] = []
    seen: set[str] = set()
    for item in list_examples():
        hw_path = _HW2C_ROOT / "examples" / item["name"] / "hardware.yaml"
        if not hw_path.is_file():
            continue
        doc = yaml.safe_load(hw_path.read_text(encoding="utf-8")) or {}
        if (doc.get("mcu") or {}).get("part") != part:
            continue
        for pin in doc.get("pins") or []:
            key = (str(pin.get("id", "")), str(pin.get("function", "")))
            if key in seen:
                continue
            seen.add(key)
            pins.append({
                "id": pin.get("id", ""),
                "function": pin.get("function", ""),
                "af": pin.get("af"),
                "label": pin.get("label", ""),
                "example": item["name"],
            })
    return {"part": part, "pins": pins}


def get_schema(layer: str) -> dict:
    """Return the JSON schema generated from the authoritative Pydantic model."""
    if layer not in _LAYER_MODELS:
        raise ValueError(f"E_FORBIDDEN: unknown layer {layer!r}")
    module_name, model_name = _LAYER_MODELS[layer]
    module = __import__(module_name, fromlist=[model_name])
    return getattr(module, model_name).model_json_schema()


def get_requirements(section: str | None = None) -> str:
    """Return docs/requirements.md, optionally one '##' section."""
    text = _safe_read(_HW2C_ROOT / "docs", "requirements.md")
    if section is None:
        return text
    # Section titles contain spaces and punctuation ("9. 路线图"); they are
    # never used as a path, so only reject traversal characters here.
    if (
        not isinstance(section, str)
        or not section
        or "/" in section
        or "\\" in section
        or "\n" in section
        or ".." in section
    ):
        raise ValueError(f"E_FORBIDDEN: unsafe section {section!r}")
    heading = f"## {section}"
    start = text.find(heading)
    if start < 0:
        raise FileNotFoundError(f"section not found: {section}")
    end = text.find("\n## ", start + len(heading))
    return text[start:] if end < 0 else text[start:end]
