"""Pydantic models for hw2c-web API request/response."""
from typing import List, Optional, Dict
from pydantic import BaseModel, Field


# ---- Pin ----
class PinInfo(BaseModel):
    id: str = Field(..., description="Pin identifier, e.g. 'PB6'")
    function: str = Field(..., description="Assigned function, e.g. 'I2C1_SCL'")
    label: str = ""
    af: int = 0
    active_level: Optional[str] = None
    pull: Optional[str] = None
    exti: Optional[dict] = None


# ---- Peripheral ----
class PeripheralInfo(BaseModel):
    name: str
    type: str
    bus: Optional[str] = None
    uart: Optional[str] = None
    address: Optional[int] = None


# ---- Connection (for topology graph) ----
class ConnectionInfo(BaseModel):
    from_ref: str
    from_pin: str
    to_ref: str
    to_pin: str
    net: str


# ---- MCU ----
class McuInfo(BaseModel):
    part: str = ""
    core_clock_mhz: int = 64


# ---- Annotations ----
class BusHint(BaseModel):
    bus_name: str
    bus_type: str
    signals: List[str] = Field(default_factory=list)
    nets: List[str] = Field(default_factory=list)


class PeripheralHint(BaseModel):
    name: str
    interface: str = ""
    nets: List[str] = Field(default_factory=list)


class PowerHint(BaseModel):
    net_name: str
    voltage: Optional[float] = None
    domain: str = "unknown"


class SignalRoleHint(BaseModel):
    net: str
    role: str


class Annotations(BaseModel):
    bus_hints: List[BusHint] = Field(default_factory=list)
    peripheral_hints: List[PeripheralHint] = Field(default_factory=list)
    power_hints: List[PowerHint] = Field(default_factory=list)
    signal_role_hints: List[SignalRoleHint] = Field(default_factory=list)


# ---- App Task ----
class AppTaskInfo(BaseModel):
    name: str
    priority: int = 3
    stack_size: int = 512


# ---- Passive Constraints ----
class PassiveConstraints(BaseModel):
    summary_text: str = ""


# ---- Main Response ----
class ParseResponse(BaseModel):
    status: str = "ok"
    mcu: McuInfo = Field(default_factory=McuInfo)
    pins: List[PinInfo] = Field(default_factory=list)
    peripherals: List[PeripheralInfo] = Field(default_factory=list)
    connections: List[ConnectionInfo] = Field(default_factory=list)
    app_tasks: List[AppTaskInfo] = Field(default_factory=list)
    annotations: Annotations = Field(default_factory=Annotations)
    passive_constraints: PassiveConstraints = Field(default_factory=PassiveConstraints)
    yaml: str = ""
    warning: Optional[str] = None
