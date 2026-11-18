"""POST /api/parse — upload netlist + optional BOM, return parsed hardware model."""

import sys
from pathlib import Path

from paths import get_hw2c_root

# Ensure hw2c (sibling project) is on sys.path for dev
_HW2C_ROOT = get_hw2c_root()
sys.path.insert(0, str(_HW2C_ROOT))

from fastapi import APIRouter, File, Form, UploadFile

from services.parse_service import (
    _extract_connections,
    build_default_component_templates,
    build_default_bind_yaml,
)

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
    components_yaml, params_yaml, pubsub_yaml = build_default_component_templates(hw_doc)
    components_doc = yaml.safe_load(components_yaml) or {}
    bind_yaml = build_default_bind_yaml(hw_doc, task_doc, components_doc)
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
