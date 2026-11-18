"""Parsing service — the single place that turns EDA input into six-layer YAML.

Both the Web route and the MCP tool call this module.  The helper builders were
moved here from ``routes/parse.py`` so there is exactly one implementation of
"what a minimal companion layer looks like".
"""

from __future__ import annotations

import sys
from pathlib import Path

from paths import get_hw2c_root

_HW2C_ROOT = get_hw2c_root()
if str(_HW2C_ROOT) not in sys.path:
    sys.path.insert(0, str(_HW2C_ROOT))


def _extract_connections(parsed_yaml: str) -> list[dict]:
    """Derive best-effort net edges from the parsed hardware YAML.

    The YAML remains the source of truth; this is only a visual mapping for
    the Web preview.
    """
    import yaml

    doc = yaml.safe_load(parsed_yaml)
    if not doc:
        return []

    pins = doc.get("pins", [])
    peripherals = doc.get("peripherals", [])

    bus_pins: dict[str, list[dict]] = {}
    for pin in pins:
        func = pin.get("function", "")
        bus = func.rsplit("_", 1)[0] if "_" in func else func
        bus_pins.setdefault(bus, []).append(pin)

    connections: list[dict] = []
    for peri in peripherals:
        bus = peri.get("bus", "") or peri.get("uart", "")
        if bus and bus in bus_pins:
            for pin in bus_pins[bus]:
                connections.append({
                    "from_ref": "MCU",
                    "from_pin": pin["id"],
                    "to_ref": peri.get("name", "??"),
                    "to_pin": pin.get("label", "??"),
                    "net": pin.get("label", ""),
                })
        elif not bus:
            for pin in pins:
                peri_name = peri.get("name", "").upper()
                pin_label = pin.get("label", "").upper()
                if peri_name in pin_label or (
                    "LED" in peri_name and "LED" in pin_label
                ) or (
                    "BUTTON" in peri_name and "BUTTON" in pin_label
                ):
                    connections.append({
                        "from_ref": "MCU",
                        "from_pin": pin["id"],
                        "to_ref": peri.get("name", "??"),
                        "to_pin": pin.get("label", "??"),
                        "net": pin.get("label", ""),
                    })
    return connections


def build_default_component_templates(hw_doc: dict) -> tuple[str, str, str]:
    """Build minimal components/params/pubsub layers from parsed hardware."""
    import yaml

    pins = hw_doc.get("pins", []) or []
    peripherals = hw_doc.get("peripherals", []) or []

    def pin_has_label(token: str) -> bool:
        token = token.upper()
        return any(token in str(p.get("label", "")).upper() for p in pins)

    components: list[dict] = []
    params: list[dict] = []
    topics: list[dict] = []

    uart = next(
        (p for p in peripherals if p.get("type") == "UART_Serial"),
        None,
    )
    if uart and uart.get("name"):
        components.append({
            "name": "shell",
            "type": "shell_cli",
            "driver": uart["name"],
            "period_ms": 50,
            "sleep_compat": "STOP1",
            "config": {"prompt": "hw2c> ", "history_size": 8},
        })
        params.append({
            "name": "log_level",
            "component": "shell",
            "type": "uint32",
            "default": 3,
            "min": 0,
            "max": 4,
            "description": "Log level (0=OFF, 1=ERROR, 2=WARN, 3=INFO, 4=DEBUG)",
        })

    if pin_has_label("LED"):
        components.append({
            "name": "led",
            "type": "led",
            "driver": "gpio",
            "period_ms": 50,
            "sleep_compat": "STOP1",
            "config": {"default_pattern": "off"},
        })
        topics.append({
            "name": "led_state",
            "description": "LED on/off state change",
            "value": {"type": "uint32", "unit": "0/1"},
        })

    if pin_has_label("BUTTON") or pin_has_label("BTN"):
        components.append({
            "name": "btn",
            "type": "btn",
            "driver": "gpio",
            "period_ms": 10,
            "sleep_compat": "STOP1",
            "config": {
                "long_press_ms": 3000,
                "double_click_ms": 500,
                "debounce_ms": 50,
            },
        })
        topics.append({
            "name": "button_press",
            "description": "Button press event (button_id as value)",
            "value": {"type": "uint32", "unit": "button_id"},
        })

    params.append({
        "name": "telemetry_enabled",
        "component": "system",
        "type": "bool",
        "default": True,
        "description": "Enable periodic telemetry snapshot logging",
    })

    return (
        "# Minimal component registry generated from parsed hardware.\n"
        + yaml.dump({"components": components}, sort_keys=False, allow_unicode=True),
        "# Minimal runtime parameter registry generated from parsed hardware.\n"
        + yaml.dump({"params": params}, sort_keys=False, allow_unicode=True),
        "# Minimal pub/sub topics generated from parsed hardware.\n"
        + yaml.dump({"topics": topics}, sort_keys=False, allow_unicode=True),
    )


def build_default_bind_yaml(
    hw_doc: dict,
    task_doc: dict,
    components_doc: dict,
) -> str:
    """Build a minimal, valid bind.yaml from parsed hardware and tasks."""
    import re
    import yaml

    component_names = {
        comp.get("name", "").lower()
        for comp in components_doc.get("components", [])
        if isinstance(comp, dict)
    }
    task_names = {
        task.get("name", "").lower()
        for task in task_doc.get("app_tasks", [])
        if isinstance(task, dict)
    }

    bind_doc = {
        "version": 1,
        "hardware": "hardware.yaml",
        "task": "task.yaml",
        "interrupt": [],
        "peripheral_assign": [],
        "routing": [],
    }

    if "btn" in component_names:
        for pin in hw_doc.get("pins", []) or []:
            label = str(pin.get("label", "")).upper()
            if "BUTTON" not in label and "BTN" not in label:
                continue
            if not (pin.get("exti") or {}).get("enable"):
                continue
            match = re.match(r"^P[A-F](\d+)$", str(pin.get("id", "")).upper())
            event = f"EXTI{match.group(1)}" if match else ""
            bind_doc["interrupt"].append({
                "pin": pin.get("id", ""),
                "component": "btn",
                "event": event,
            })

    for peri in hw_doc.get("peripherals", []) or []:
        peri_name = str(peri.get("name", ""))
        if not peri_name:
            continue
        peri_lower = peri_name.lower()
        task_name = None
        direct = f"{peri_lower}_task"
        if direct in task_names:
            task_name = direct
        else:
            for candidate in task_names:
                if peri_lower in candidate or candidate in peri_lower:
                    task_name = candidate
                    break
        if task_name:
            bind_doc["peripheral_assign"].append({
                "peripheral": peri_name,
                "task": task_name,
                "role": "",
            })

    return (
        "# Minimal hardware/software bindings generated from parsed hardware.\n"
        + yaml.dump(bind_doc, sort_keys=False, allow_unicode=True)
    )


def parse_to_layers(
    netlist_text: str,
    bom_text: str | None = None,
    filename: str | None = None,
) -> dict:
    """Run the hw2c parser and return the six YAML layers plus structured issues.

    This is the MCP-facing entry point.  Unlike the Web route it returns only
    data — no FastAPI response objects, no UploadFile, no HTTP status codes.
    """
    import yaml

    from parser.pipeline import run_pipeline

    issues: list[dict] = []
    if not netlist_text or not netlist_text.strip():
        return {
            "hardware_yaml": "",
            "task_yaml": "",
            "components_yaml": "",
            "bind_yaml": "",
            "params_yaml": "",
            "pubsub_yaml": "",
            "issues": [{
                "severity": "ERROR",
                "code": "E_EMPTY_INPUT",
                "message": "netlist_text is empty",
                "layer": "hardware",
                "path": "netlist_text",
            }],
        }

    try:
        result = run_pipeline(
            netlist_text=netlist_text,
            bom_text=bom_text,
            hw_yaml_text=None,
        )
    except Exception as exc:  # noqa: BLE001 - surface parser failures as issues
        return {
            "hardware_yaml": "",
            "task_yaml": "",
            "components_yaml": "",
            "bind_yaml": "",
            "params_yaml": "",
            "pubsub_yaml": "",
            "issues": [{
                "severity": "ERROR",
                "code": "E_PARSE_FAILED",
                "message": f"{type(exc).__name__}: {exc}"[:200],
                "layer": "hardware",
                "path": filename or "netlist",
            }],
        }

    hardware_yaml = result.hardware_yaml or result.yaml or ""
    task_yaml = result.task_yaml or ""
    if not task_yaml and result.yaml:
        from generator.mapper import split_legacy
        hardware_yaml, task_yaml, bind_yaml = split_legacy(result.yaml)
    else:
        bind_yaml = ""

    hw_doc = yaml.safe_load(hardware_yaml) or {}
    task_doc = yaml.safe_load(task_yaml) if task_yaml else {}
    components_yaml, params_yaml, pubsub_yaml = build_default_component_templates(hw_doc)
    components_doc = yaml.safe_load(components_yaml) or {}
    if not bind_yaml:
        bind_yaml = build_default_bind_yaml(hw_doc, task_doc, components_doc)

    for raw in result.warnings or []:
        issues.append({
            "severity": "WARNING",
            "code": "W_PARSE",
            "message": str(raw)[:200],
            "layer": "hardware",
            "path": filename or "netlist",
        })

    return {
        "hardware_yaml": hardware_yaml,
        "task_yaml": task_yaml,
        "components_yaml": components_yaml,
        "bind_yaml": bind_yaml,
        "params_yaml": params_yaml,
        "pubsub_yaml": pubsub_yaml,
        "issues": issues,
    }
