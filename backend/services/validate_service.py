"""Validation service — structured, MCP-friendly validation of six-layer YAML."""

from __future__ import annotations

import sys
from pathlib import Path

from paths import get_hw2c_root

_HW2C_ROOT = get_hw2c_root()
if str(_HW2C_ROOT) not in sys.path:
    sys.path.insert(0, str(_HW2C_ROOT))

LAYERS = ("hardware", "task", "components", "bind", "params", "pubsub")

# (module, top-level model) — kept in sync with generator/schemas/*.py.
_LAYER_MODELS = {
    "hardware": ("generator.schemas.hardware", "HardwareModel"),
    "task": ("generator.schemas.task", "TaskModel"),
    "components": ("generator.schemas.component", "ComponentsModel"),
    "bind": ("generator.schemas.bind", "BindModel"),
    "params": ("generator.schemas.param", "ParamsModel"),
    "pubsub": ("generator.schemas.pubsub", "PubSubModel"),
}
_FATAL = {"CRITICAL", "ERROR"}


def _issue(severity: str, code: str, message: str, layer: str, path: str = "") -> dict:
    return {
        "severity": severity,
        "code": code,
        "message": str(message)[:200],
        "layer": layer,
        "path": path,
    }


def _load_model(module_name: str, model_name: str):
    module = __import__(module_name, fromlist=[model_name])
    return getattr(module, model_name)


def validate_config(layers: dict) -> dict:
    """Validate the supplied YAML layers.

    Missing optional layers are skipped — omission is not an error.
    Parsing/schema failures and cross-field errors become structured issues;
    ``ok`` is false only for CRITICAL/ERROR, never for WARNING/INFO.
    """
    import yaml
    from pydantic import ValidationError as PydanticValidationError

    issues: list[dict] = []
    docs: dict[str, dict] = {}

    for layer in LAYERS:
        text = layers.get(layer)
        if not text:
            continue
        if not isinstance(text, str):
            issues.append(_issue("ERROR", "E_NOT_TEXT", "layer must be YAML text", layer))
            continue
        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            issues.append(_issue("ERROR", "E_YAML_SYNTAX", str(exc), layer))
            continue
        if not isinstance(doc, dict):
            issues.append(_issue("ERROR", "E_NOT_MAPPING", "top level must be a mapping", layer))
            continue
        docs[layer] = doc

        module_name, model_name = _LAYER_MODELS[layer]
        model = _load_model(module_name, model_name)
        try:
            model.model_validate(doc)
        except PydanticValidationError as exc:
            for err in exc.errors():
                loc = ".".join(str(part) for part in err.get("loc", ()))
                issues.append(_issue(
                    "ERROR", "E_SCHEMA", err.get("msg", "invalid value"), layer, loc,
                ))

    if "hardware" in docs:
        from generator.validator import validate_hardware
        for finding in validate_hardware(docs["hardware"]):
            issues.append(_issue(
                finding.get("severity", "ERROR"),
                "E_CROSS_HARDWARE",
                finding.get("message", ""),
                "hardware",
            ))

    if "hardware" in docs and "bind" in docs:
        from generator.validator import validate_bind_cross_refs
        for finding in validate_bind_cross_refs(
            docs["hardware"],
            docs.get("task"),
            docs["bind"],
            docs.get("components"),
        ):
            issues.append(_issue(
                finding.get("severity", "ERROR"),
                "E_CROSS_BIND",
                finding.get("message", ""),
                "bind",
            ))

    issues = issues[:20]
    ok = not any(item["severity"] in _FATAL for item in issues)
    return {"ok": ok, "issues": issues}
