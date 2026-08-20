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
    core: str = ""
    core_clock_mhz: int = 64
    ram_kb: int = 144
    flash_kb: int = 512
    dual_bank: bool = True


# ---- Clock Config ----
class HseConfig(BaseModel):
    present: bool = False
    frequency_hz: int = 8000000


class LseConfig(BaseModel):
    present: bool = False
    frequency_hz: int = 32768


class PllConfig(BaseModel):
    source: str = "HSI"  # HSI | HSE
    m: int = 1
    n: int = 8
    r: int = 2


class SysclkConfig(BaseModel):
    source: str = "PLL"  # HSI | HSE | PLL
    frequency_hz: int = 64_000_000


class ApbConfig(BaseModel):
    prescaler: int = 1


class FreeRtosTickConfig(BaseModel):
    source: str = "SysTick"
    frequency_hz: int = 1000


class ClockConfig(BaseModel):
    hsi_hz: int = 16_000_000
    lsi_hz: int = 32_000
    hse: HseConfig = Field(default_factory=HseConfig)
    lse: LseConfig = Field(default_factory=LseConfig)
    pll: PllConfig = Field(default_factory=PllConfig)
    sysclk: SysclkConfig = Field(default_factory=SysclkConfig)
    apb: ApbConfig = Field(default_factory=ApbConfig)
    freertos_tick: FreeRtosTickConfig = Field(default_factory=FreeRtosTickConfig)


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


# ---- App Task (simplified — triggers/signals moved to bind.yaml) ----
class AppTaskInfo(BaseModel):
    name: str
    priority: int = 3
    stack_size: int = 512


# ---- Project ----
class ProjectInfo(BaseModel):
    name: str = "untitled"
    version: str = "0.1.0"


# ---- Bind YAML models ----
class BindInterruptInfo(BaseModel):
    pin: str
    task: str = ""
    component: Optional[str] = None
    event: str = ""


class BindPeripheralAssignInfo(BaseModel):
    peripheral: str
    task: str
    role: str = ""


class BindRoutingInfo(BaseModel):
    from_task: str = Field(alias="from")
    to: Optional[str] = None
    signal: str
    condition: Optional[str] = None

    class Config:
        populate_by_name = True


class BindInfo(BaseModel):
    hardware: str = "hardware.yaml"
    task: str = "task.yaml"
    interrupt: List[BindInterruptInfo] = Field(default_factory=list)
    peripheral_assign: List[BindPeripheralAssignInfo] = Field(default_factory=list)
    routing: List[BindRoutingInfo] = Field(default_factory=list)


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
    clock: Optional[ClockConfig] = None
    annotations: Annotations = Field(default_factory=Annotations)
    passive_constraints: PassiveConstraints = Field(default_factory=PassiveConstraints)
    project: Optional[ProjectInfo] = None
    bind: Optional[BindInfo] = None
    yaml: str = ""
    hardware_yaml: str = ""
    task_yaml: str = ""
    components_yaml: str = ""
    bind_yaml: str = ""
    params_yaml: str = ""
    pubsub_yaml: str = ""
    warning: Optional[str] = None
