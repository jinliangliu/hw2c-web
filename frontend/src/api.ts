/** API client for hw2c-web backend. */

export interface ParseResponse {
    status: string
    mcu:         { part: string; core: string; core_clock_mhz: number; ram_kb: number; flash_kb: number; dual_bank: boolean }
    clock?:      ClockConfig
    pins:        PinInfo[]
    peripherals: PeripheralInfo[]
    connections: ConnectionInfo[]
    app_tasks:   AppTaskInfo[]
    annotations: Annotations
    passive_constraints: { summary_text: string }
    yaml:        string                     /* [DEPRECATED] legacy monolithic */
    hardware_yaml: string
    task_yaml:   string
    bind_yaml:   string
    project?:    ProjectInfo
    bind?:       BindInfo
    warning?:    string
}

export interface ProjectInfo {
    name: string
    version: string
}

export interface BindInterruptInfo {
    pin: string
    task: string
    event: string
}

export interface BindPeripheralAssignInfo {
    peripheral: string
    task: string
    role: string
}

export interface BindRoutingInfo {
    from: string
    to?: string | null
    signal: string
    condition?: string | null
}

export interface BindInfo {
    hardware: string
    task: string
    interrupt: BindInterruptInfo[]
    peripheral_assign: BindPeripheralAssignInfo[]
    routing: BindRoutingInfo[]
}

export interface PinInfo {
    id: string
    function: string
    label: string
    af: number
    active_level?: string | null
    pull?: string | null
    exti?: Record<string, unknown> | null
}

export interface PeripheralInfo {
    name: string
    type: string
    bus?: string | null
    uart?: string | null
}

export interface ConnectionInfo {
    from_ref: string
    from_pin: string
    to_ref: string
    to_pin: string
    net: string
}

export interface AppTaskInfo {
    name: string
    priority: number
    stack_size: number
}

export interface Annotations {
    bus_hints:         BusHint[]
    peripheral_hints:  PeripheralHint[]
    power_hints:       PowerHint[]
    signal_role_hints: SignalRoleHint[]
}

export interface BusHint {
    bus_name: string
    bus_type: string
    signals:  string[]
    nets:     string[]
}

export interface PeripheralHint {
    name:       string
    interface:  string
    nets:       string[]
}

export interface PowerHint {
    net_name: string
    voltage?: number | null
    domain:   string
}

export interface SignalRoleHint {
    net:  string
    role: string
}

/** --- Clock configuration --- */
export interface HseConfig {
    present: boolean
    frequency_hz: number
}
export interface LseConfig {
    present: boolean
    frequency_hz: number
}
export interface PllConfig {
    source: string
    m: number
    n: number
    r: number
}
export interface SysclkConfig {
    source: string
    frequency_hz: number
}
export interface ApbConfig {
    prescaler: number
}
export interface FreeRtosTickConfig {
    source: string
    frequency_hz: number
}
export interface ClockConfig {
    hsi_hz: number
    lsi_hz: number
    hse: HseConfig
    lse: LseConfig
    pll: PllConfig
    sysclk: SysclkConfig
    apb: ApbConfig
    freertos_tick: FreeRtosTickConfig
}

const BASE = '/api'

export async function uploadNetlist(
    netlistFile: File,
    bomFile?: File,
): Promise<ParseResponse> {
    const form = new FormData()
    form.append('netlist', netlistFile)
    if (bomFile) {
        form.append('bom', bomFile)
    }

    const resp = await fetch(`${BASE}/parse`, { method: 'POST', body: form })
    if (!resp.ok) {
        const text = await resp.text()
        throw new Error(`Upload failed (${resp.status}): ${text}`)
    }
    return resp.json()
}

/** POST current YAMLs → download generated project zip. */
export async function generateFirmware(
    hardwareYaml: string,
    taskYaml: string = '',
    bindYaml: string = '',
    projectName: string = 'firmware',
): Promise<Blob> {
    const resp = await fetch(`${BASE}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            hardware_yaml: hardwareYaml,
            task_yaml: taskYaml,
            bind_yaml: bindYaml,
            project_name: projectName,
        }),
    })
    if (!resp.ok) {
        const text = await resp.text()
        throw new Error(`Generation failed (${resp.status}): ${text}`)
    }
    return resp.blob()
}
