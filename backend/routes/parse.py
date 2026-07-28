"""POST /api/parse — upload netlist + optional BOM, return parsed hardware model."""

import sys
from pathlib import Path

# Ensure hw2c (sibling project) is on sys.path for dev
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hw2c"))

from fastapi import APIRouter, File, Form, UploadFile

from schemas import (
    ParseResponse, McuInfo, PinInfo, PeripheralInfo,
    ConnectionInfo, AppTaskInfo, Annotations,
    BusHint, PeripheralHint, PowerHint, SignalRoleHint,
    PassiveConstraints,
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
        yaml_text=None,
    )

    # Build response from pipeline result
    import yaml
    doc = yaml.safe_load(result.yaml) or {}

    # MCU
    mcu = McuInfo(**doc.get("mcu", {}))

    # Pins
    pins = [PinInfo(**p) for p in doc.get("pins", [])]

    # Peripherals
    peripherals = [PeripheralInfo(**p) for p in doc.get("peripherals", [])]

    # Connections (derived)
    connections = _extract_connections(result.yaml)

    # App tasks
    app_tasks = [AppTaskInfo(**t) for t in doc.get("app_tasks", [])]

    # Clock config (optional)
    from schemas import ClockConfig
    clock = None
    if "clock" in doc:
        clock = ClockConfig(**doc["clock"])

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
        yaml=result.yaml,
        warning=warning,
    )
