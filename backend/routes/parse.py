"""POST /api/parse — upload netlist + optional BOM, return parsed hardware model."""

import sys
from pathlib import Path

from paths import get_hw2c_root

# Ensure hw2c (sibling project) is on sys.path for dev
_HW2C_ROOT = get_hw2c_root()
sys.path.insert(0, str(_HW2C_ROOT))

from fastapi import APIRouter, File, Form, UploadFile

from schemas import (
    ParseResponse, McuInfo, PinInfo, PeripheralInfo,
    ConnectionInfo, AppTaskInfo, Annotations,
    BusHint, PeripheralHint, PowerHint, SignalRoleHint,
    PassiveConstraints, ProjectInfo, BindInfo,
    BindInterruptInfo, BindPeripheralAssignInfo, BindRoutingInfo,
)

router = APIRouter()


async def _safe_read(upload: UploadFile | None) -> str | None:
    """Read upload content safely, return None if absent."""
    if upload is None:
        return None
    content = await upload.read()
    return content.decode("utf-8") if content else None


def _extract_connections(parsed_yaml: str) -> list[ConnectionInfo]:
    """Extract net connections from parsed YAML by reading pin assignments.

    Since the pipeline internally resolves connections, we derive
    connection edges from nets with same label in pin assignments.
    This is a best-effort visual mapping — the YAML is the source of truth.
    """
    import yaml
    doc = yaml.safe_load(parsed_yaml)
    if not doc:
        return []

    pins = doc.get("pins", [])
    peripherals = doc.get("peripherals", [])
    mcu_info = doc.get("mcu", {})

    connections: list[ConnectionInfo] = []

    # Build peripheral pin info: {designator: {pin_number: ...}}
    # For now, derive connections from YAML pin labels that mention bus names
    bus_pins: dict[str, list[dict]] = {}
    for pin in pins:
        label = pin.get("label", "")
        func = pin.get("function", "")
        if "_" in func:
            bus = func.rsplit("_", 1)[0]  # e.g., I2C1_SCL → I2C1
        else:
            bus = func
        if bus not in bus_pins:
            bus_pins[bus] = []
        bus_pins[bus].append(pin)

    # Match peripherals to bus pins
    for peri in peripherals:
        bus = peri.get("bus", "") or peri.get("uart", "")
        if bus and bus in bus_pins:
            for pin in bus_pins[bus]:
                connections.append(ConnectionInfo(
                    from_ref="MCU",
                    from_pin=pin["id"],
                    to_ref=peri.get("name", "??"),
                    to_pin=pin.get("label", "??"),
                    net=pin.get("label", ""),
                ))
        elif not bus:
            # GPIO peripherals (LED, Button)
            for pin in pins:
                peri_name = peri.get("name", "").upper()
                pin_label = pin.get("label", "").upper()
                if peri_name in pin_label or (
                    "LED" in peri_name and "LED" in pin_label
                ) or (
                    "BUTTON" in peri_name and "BUTTON" in pin_label
                ):
                    connections.append(ConnectionInfo(
                        from_ref="MCU",
                        from_pin=pin["id"],
                        to_ref=peri.get("name", "??"),
                        to_pin=pin.get("label", "??"),
                        net=pin.get("label", ""),
                    ))

    return connections


def _build_default_component_templates(hw_doc: dict) -> tuple[str, str, str]:
    """Build minimal six-layer companion templates from parsed hardware.

    hw2c's parser produces hardware.yaml and task.yaml. components.yaml,
    params.yaml, and pubsub.yaml are configuration layers that the parser
    cannot derive from a netlist in the general case. Return a small,
    editable starting point that still generates successfully with the
    parsed hardware model.
    """
    import yaml

    pins = hw_doc.get("pins", []) or []
    peripherals = hw_doc.get("peripherals", []) or []

    def pin_has_label(token: str) -> bool:
        token = token.upper()
        return any(token in str(p.get("label", "")).upper() for p in pins)

    components: list[dict] = []
    params: list[dict] = []
    topics: list[dict] = []

    # Serial shell is the most universally useful component when a UART exists.
    uart = next(
        (p for p in peripherals if p.get("type") == "UART_Serial"),
        None,
    )
    if uart and uart.get("name"):
        driver = uart["name"]
        components.append({
            "name": "shell",
            "type": "shell_cli",
            "driver": driver,
            "period_ms": 50,
            "sleep_compat": "STOP1",
            "config": {
                "prompt": "hw2c> ",
                "history_size": 8,
            },
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
        exti_button = any(
            (p.get("exti") or {}).get("enable")
            for p in pins
            if "BUTTON" in str(p.get("label", "")).upper()
            or "BTN" in str(p.get("label", "")).upper()
        )
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
        _ = exti_button  # reserved for future EXTI-specific defaults

    # Keep a system-level toggle so the param registry has a useful default
    # even when no peripheral-specific parameters were generated.
    params.append({
        "name": "telemetry_enabled",
        "component": "system",
        "type": "bool",
        "default": True,
        "description": "Enable periodic telemetry snapshot logging",
    })

    components_yaml = (
        "# Minimal component registry generated from parsed hardware.\n"
        + yaml.dump({"components": components}, sort_keys=False, allow_unicode=True)
    )
    params_yaml = (
        "# Minimal runtime parameter registry generated from parsed hardware.\n"
        + yaml.dump({"params": params}, sort_keys=False, allow_unicode=True)
    )
    pubsub_yaml = (
        "# Minimal pub/sub topics generated from parsed hardware.\n"
        + yaml.dump({"topics": topics}, sort_keys=False, allow_unicode=True)
    )

    return components_yaml, params_yaml, pubsub_yaml


def _build_default_bind_yaml(
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

    # Button EXTI pins map to the generated `btn` component.
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

    # Assign peripherals to matching parsed FreeRTOS tasks.
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


@router.post("/api/parse", response_model=ParseResponse)
async def parse_netlist(
    netlist: UploadFile = File(...),
    bom: UploadFile | None = File(None),
):
    """Upload netlist (.enet / .net) + optional BOM (.csv), return parsed hardware model."""
    from parser.pipeline import run_pipeline

    # Read uploaded files
    netlist_text = await _safe_read(netlist)
    if not netlist_text:
        return ParseResponse(status="error", warning="Empty or unreadable netlist file")

    bom_text = await _safe_read(bom)

    # Run the hw2c pipeline
    result = run_pipeline(
        netlist_text=netlist_text,
        bom_text=bom_text,
        hw_yaml_text=None,
    )

    # Determine which YAML strings to use
    hardware_yaml = result.hardware_yaml or result.yaml
    task_yaml = result.task_yaml or ""

    # Fallback: if pipeline didn't produce task_yaml, split from monolithic
    if not task_yaml and result.yaml:
        from generator.mapper import split_legacy
        hw_str, task_str, bind_str = split_legacy(result.yaml)
        hardware_yaml = hw_str
        task_yaml = task_str
        bind_yaml = bind_str
    else:
        bind_yaml = ""

    # Build response from hardware_yaml for MCU/pins/peripherals
    import yaml
    hw_doc = yaml.safe_load(hardware_yaml) or {}
    task_doc = yaml.safe_load(task_yaml) if task_yaml else {}
    components_yaml, params_yaml, pubsub_yaml = _build_default_component_templates(hw_doc)
    components_doc = yaml.safe_load(components_yaml) or {}
    bind_yaml = _build_default_bind_yaml(hw_doc, task_doc, components_doc)
    bind_doc = yaml.safe_load(bind_yaml) if bind_yaml else {}

    # MCU
    mcu = McuInfo(**hw_doc.get("mcu", {}))

    # Pins
    pins = [PinInfo(**p) for p in hw_doc.get("pins", [])]

    # Peripherals
    peripherals = [PeripheralInfo(**p) for p in hw_doc.get("peripherals", [])]

    # Connections (derived from hardware_yaml)
    connections = _extract_connections(hardware_yaml)

    # App tasks (from task_yaml)
    app_tasks = [AppTaskInfo(**t) for t in task_doc.get("app_tasks", [])]

    # Clock config (optional, from hardware_yaml)
    from schemas import ClockConfig
    clock = None
    if "clock" in hw_doc:
        clock = ClockConfig(**hw_doc["clock"])

    # Project info
    project = None
    if "project" in task_doc:
        project = ProjectInfo(**task_doc["project"])

    # Bind info
    bind = None
    if bind_doc:
        bind_interrupt = [BindInterruptInfo(**b) for b in bind_doc.get("interrupt", [])]
        bind_pa = [BindPeripheralAssignInfo(**b) for b in bind_doc.get("peripheral_assign", [])]
        bind_routing = [BindRoutingInfo(**b) for b in bind_doc.get("routing", [])]
        bind = BindInfo(
            hardware=bind_doc.get("hardware", "hardware.yaml"),
            task=bind_doc.get("task", "task.yaml"),
            interrupt=bind_interrupt,
            peripheral_assign=bind_pa,
            routing=bind_routing,
        )
    elif not bind_yaml:
        # Provide empty bind template for frontend
        bind = BindInfo()

    # Annotations
    ann = result.annotations
    annotations = Annotations(
        bus_hints=[
            BusHint(
                bus_name=h.bus_name, bus_type=h.bus_type,
                signals=sorted(h.signals), nets=h.nets,
            )
            for h in ann.bus_hints
        ],
        peripheral_hints=[
            PeripheralHint(name=h.name, interface=h.interface, nets=h.nets)
            for h in ann.peripheral_hints
        ],
        power_hints=[
            PowerHint(net_name=h.net_name, voltage=h.voltage, domain=h.domain)
            for h in ann.power_hints
        ],
        signal_role_hints=[
            SignalRoleHint(net=net, role=role)
            for net, role in ann.signal_role_hints.items()
        ],
    )

    # Passive constraints
    passive = PassiveConstraints()
    if result.passive_constraints:
        passive.summary_text = result.passive_constraints.summary()

    # Warnings
    warning = None
    if result.warnings:
        warning = "\n".join(result.warnings)

    return ParseResponse(
        mcu=mcu,
        pins=pins,
        peripherals=peripherals,
        connections=connections,
        app_tasks=app_tasks,
        clock=clock,
        annotations=annotations,
        passive_constraints=passive,
        project=project,
        bind=bind,
        yaml=result.yaml,                    # backward compat
        hardware_yaml=hardware_yaml,
        task_yaml=task_yaml,
        components_yaml=components_yaml,
        bind_yaml=bind_yaml,
        params_yaml=params_yaml,
        pubsub_yaml=pubsub_yaml,
        warning=warning,
    )
