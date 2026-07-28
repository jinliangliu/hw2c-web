/**
 * useHardwareModel — bidirectional YAML ↔ reactive state sync.
 *
 * Single source of truth: the YAML string. All UI mutations go through
 * `write*` helpers that update the reactive model, which auto-dumps back
 * to YAML via js-yaml. External YAML edits (CodeMirror) are parsed back
 * into the reactive model.
 */
import { reactive, readonly, watch, type Ref } from 'vue'
import { load, dump } from 'js-yaml'

// ---------------------------------------------------------------------------
// Types (subset of ParsedHardware relevant for editing)
// ---------------------------------------------------------------------------

export interface McuModel {
    part: string
    core: string
    core_clock_mhz: number
    ram_kb: number
    flash_kb: number
    dual_bank: boolean
}

export interface FlashPartition {
    name: string
    bank: number
    offset_kb: number
    size_kb: number
}

export interface PinModel {
    id: string
    function: string
    label: string
    af?: number
    active_level?: string | null
    pull?: string | null
    exti?: Record<string, unknown> | null
}

export interface PeripheralModel {
    name: string
    type: string
    bus?: string | null
    uart?: string | null
    address?: number | null
    extra?: Record<string, unknown>
    features?: string[]
}

export interface TaskTrigger {
    type: 'timer' | 'event' | 'interrupt'
    /** Event/semaphore name for 'event' type, pin ID for 'interrupt' type, period_ms for 'timer' */
    source?: string
    period_ms?: number
}

export interface TaskSignal {
    name: string
    /** Target task name (empty = broadcast) */
    target?: string
}

export interface AppTaskModel {
    name: string
    priority: number
    stack_size: number
    /** 'once' = single-shot, 'loop' = continuous */
    run_mode: 'once' | 'loop'
    triggers: TaskTrigger[]
    signals: TaskSignal[]
}

export interface WakeupSourceModel {
    type: 'gpio' | 'rtc_alarm' | 'rtc_wakeup' | 'lpuart' | 'iwdg'
    pin?: string
    edge?: 'rising' | 'falling' | 'both'
    period_s?: number
}

export interface SleepModel {
    enabled: boolean
    mode: string
    enter_on_exit: boolean
    regulator_voltage_scale: number
    flash_power_down: boolean
    wakeup_sources: WakeupSourceModel[]
}

// ---------------------------------------------------------------------------
// Complex type definitions (behavior.types)
// ---------------------------------------------------------------------------

export interface StructField {
    name: string
    /** C type; omit for nested struct (detected by 'fields' presence) */
    type?: string
    array?: number
    /** Nested struct fields (level 2 only) */
    fields?: StructField[]
}

export interface EnumValue {
    name: string
    value: number
}

export interface UnionField {
    name: string
    type: string
    array?: number
}

export interface BitfieldField {
    name: string
    width: number
}

export interface CustomTypeDef {
    name: string
    struct?: StructField[]
    enum?: EnumValue[]
    union?: UnionField[]
    bitfield?: BitfieldField[]
}

export interface BehaviorModel {
    initial_state?: string
    types?: CustomTypeDef[]
    variables?: VariableModel[]
    events?: Record<string, unknown>[]
    states?: Record<string, unknown>[]
    regions?: Record<string, unknown>[]
}

export interface VariableModel {
    name: string
    type: string
    initial?: unknown
    array?: number
}

export interface ClockModel {
    hsi_hz: number
    lsi_hz: number
    hse: { present: boolean; frequency_hz: number }
    lse: { present: boolean; frequency_hz: number }
    pll: { source: string; m: number; n: number; r: number }
    sysclk: { source: string; frequency_hz: number }
    apb: { prescaler: number }
    freertos_tick: { source: string; frequency_hz: number }
}

export interface HardwareModel {
    mcu: McuModel
    pins: PinModel[]
    peripherals: PeripheralModel[]
    app_tasks: AppTaskModel[]
    sleep: SleepModel | null
    behavior: BehaviorModel | null
    clock: ClockModel | null
    flash_partitions: FlashPartition[]
}

// ---------------------------------------------------------------------------
// Default empty model
// ---------------------------------------------------------------------------

function defaultModel(): HardwareModel {
    return {
        mcu: { part: '', core: '', core_clock_mhz: 64, ram_kb: 144, flash_kb: 512, dual_bank: true },
        pins: [],
        peripherals: [],
        app_tasks: [],
        sleep: null,
        behavior: null,
        clock: null,
        flash_partitions: [],
    }
}

// ---------------------------------------------------------------------------
// YAML dump / restore
// ---------------------------------------------------------------------------

function modelToYaml(model: HardwareModel): string {
    const doc: Record<string, unknown> = {}

    doc.mcu = { ...model.mcu }
    doc.pins = model.pins.map(p => {
        const o: Record<string, unknown> = { id: p.id, function: p.function, label: p.label }
        if (p.af !== undefined && p.af !== 0) o.af = p.af
        if (p.active_level) o.active_level = p.active_level
        if (p.pull) o.pull = p.pull
        if (p.exti && Object.keys(p.exti).length) o.exti = p.exti
        return o
    })
    if (model.peripherals.length > 0) {
        doc.peripherals = model.peripherals.map(p => {
            const o: Record<string, unknown> = { name: p.name, type: p.type }
            if (p.bus) o.bus = p.bus
            if (p.address != null) o.address = p.address
            if (p.extra && Object.keys(p.extra).length) o.extra = p.extra
            if (p.features && p.features.length) o.features = p.features
            return o
        })
    }
    if (model.app_tasks.length > 0) {
        doc.app_tasks = model.app_tasks.map(t => {
            const o: Record<string, unknown> = {
                name: t.name,
                priority: t.priority,
                stack_size: t.stack_size,
                run_mode: t.run_mode,
            }
            if (t.triggers.length) o.triggers = t.triggers
            if (t.signals.length) o.signals = t.signals
            return o
        })
    }
    if (model.sleep?.enabled || model.sleep?.mode) {
        doc.sleep = {
            enabled: model.sleep.enabled,
            mode: model.sleep.mode || 'SLEEP',
            enter_on_exit: model.sleep.enter_on_exit,
            regulator_voltage_scale: model.sleep.regulator_voltage_scale ?? 2,
            flash_power_down: model.sleep.flash_power_down,
            wakeup_sources: model.sleep.wakeup_sources ?? [],
        }
    }
    if (model.behavior && Object.keys(model.behavior).length) {
        doc.behavior = model.behavior
    }
    if (model.clock) {
        doc.clock = {
            hsi_hz: model.clock.hsi_hz,
            lsi_hz: model.clock.lsi_hz,
            hse: { present: model.clock.hse.present, frequency_hz: model.clock.hse.frequency_hz },
            lse: { present: model.clock.lse.present, frequency_hz: model.clock.lse.frequency_hz },
            pll: { ...model.clock.pll },
            sysclk: { ...model.clock.sysclk },
            apb: { prescaler: model.clock.apb.prescaler },
            freertos_tick: { ...model.clock.freertos_tick },
        }
    }
    if (model.flash_partitions.length) {
        doc.flash_partitions = model.flash_partitions.map(p => ({
            name: p.name,
            bank: p.bank,
            offset_kb: p.offset_kb,
            size_kb: p.size_kb,
        }))
    }

    return dump(doc, { indent: 2, sortKeys: false })
}

export function yamlToModel(text: string): HardwareModel {
    try {
        const doc = load(text) as Record<string, unknown>
        if (!doc) return defaultModel()

        const model = defaultModel()

        if (doc.mcu && typeof doc.mcu === 'object') {
            const m = doc.mcu as Record<string, unknown>
            model.mcu = {
                part: String(m.part ?? ''),
                core: String(m.core ?? ''),
                core_clock_mhz: Number(m.core_clock_mhz ?? 64),
                ram_kb: Number(m.ram_kb ?? 144),
                flash_kb: Number(m.flash_kb ?? 512),
                dual_bank: Boolean(m.dual_bank ?? true),
            }
        }

        const rawPins = Array.isArray(doc.pins) ? doc.pins : []
        model.pins = rawPins.map((p: any) => ({
            id: String(p.id ?? ''),
            function: String(p.function ?? ''),
            label: String(p.label ?? ''),
            af: typeof p.af === 'number' ? p.af : undefined,
            active_level: p.active_level ?? null,
            pull: p.pull ?? null,
            exti: p.exti ?? null,
        }))

        const rawPeris = Array.isArray(doc.peripherals) ? doc.peripherals : []
        model.peripherals = rawPeris.map((p: any) => ({
            name: String(p.name ?? ''),
            type: String(p.type ?? ''),
            bus: p.bus ?? p.uart ?? null,
            address: p.address ?? null,
            extra: p.extra ?? undefined,
            features: Array.isArray(p.features) ? p.features : undefined,
        }))

        const rawTasks = Array.isArray(doc.app_tasks) ? doc.app_tasks : []
        model.app_tasks = rawTasks.map((t: any) => ({
            name: String(t.name ?? ''),
            priority: Number(t.priority ?? 3),
            stack_size: Number(t.stack_size ?? 512),
            run_mode: String(t.run_mode ?? 'loop') as 'once' | 'loop',
            triggers: Array.isArray(t.triggers) ? t.triggers : [],
            signals: Array.isArray(t.signals) ? t.signals : [],
        }))

        model.sleep = doc.sleep ? {
            enabled: Boolean((doc.sleep as any).enabled ?? false),
            mode: String((doc.sleep as any).mode ?? 'SLEEP'),
            enter_on_exit: Boolean((doc.sleep as any).enter_on_exit ?? false),
            regulator_voltage_scale: Number((doc.sleep as any).regulator_voltage_scale ?? 2),
            flash_power_down: Boolean((doc.sleep as any).flash_power_down ?? false),
            wakeup_sources: Array.isArray((doc.sleep as any).wakeup_sources)
                ? (doc.sleep as any).wakeup_sources : [],
        } : null
        model.behavior = (doc.behavior as BehaviorModel) ?? null

        // Clock config
        if (doc.clock && typeof doc.clock === 'object') {
            const c = doc.clock as Record<string, any>
            model.clock = {
                hsi_hz: Number(c.hsi_hz ?? 16_000_000),
                lsi_hz: Number(c.lsi_hz ?? 32_000),
                hse: {
                    present: Boolean((c.hse as any)?.present),
                    frequency_hz: Number((c.hse as any)?.frequency_hz ?? 8_000_000),
                },
                lse: {
                    present: Boolean((c.lse as any)?.present),
                    frequency_hz: Number((c.lse as any)?.frequency_hz ?? 32768),
                },
                pll: {
                    source: String((c.pll as any)?.source ?? 'HSI'),
                    m: Number((c.pll as any)?.m ?? 1),
                    n: Number((c.pll as any)?.n ?? 8),
                    r: Number((c.pll as any)?.r ?? 2),
                },
                sysclk: {
                    source: String((c.sysclk as any)?.source ?? 'PLL'),
                    frequency_hz: Number((c.sysclk as any)?.frequency_hz ?? 64_000_000),
                },
                apb: {
                    prescaler: Number((c.apb as any)?.prescaler ?? 1),
                },
                freertos_tick: {
                    source: String((c.freertos_tick as any)?.source ?? 'SysTick'),
                    frequency_hz: Number((c.freertos_tick as any)?.frequency_hz ?? 1000),
                },
            }
        }

        // Flash partitions
        if (Array.isArray(doc.flash_partitions)) {
            model.flash_partitions = doc.flash_partitions.map((p: any) => ({
                name: String(p.name ?? ''),
                bank: Number(p.bank ?? 1),
                offset_kb: Number(p.offset_kb ?? 0),
                size_kb: Number(p.size_kb ?? 0),
            }))
        }

        return model
    } catch {
        return defaultModel()
    }
}

// ---------------------------------------------------------------------------
// useHardwareModel composable
// ---------------------------------------------------------------------------

export function useHardwareModel(yamlRef: Ref<string>) {
    /** Reactive model — read by UI components, mutated via write helpers */
    const model = reactive<HardwareModel>(defaultModel())

    /** Flag to skip watcher loops when updating programmatically */
    let syncing = false

    // YAML → model (user typed in editor)
    watch(yamlRef, (newYaml) => {
        if (syncing) return
        const parsed = yamlToModel(newYaml)
        Object.assign(model, parsed)
    })

    /** Re-dump YAML from current model state */
    function flushToYaml() {
        syncing = true
        yamlRef.value = modelToYaml({ ...model })
        // Next tick reset flag so user edits are picked up again
        requestAnimationFrame(() => { syncing = false })
    }

    // ------------------------------------------------------------------
    // Mutation helpers — call these from UI components
    // ------------------------------------------------------------------

    function writeMcu(partial: Partial<McuModel>) {
        Object.assign(model.mcu, partial)
        flushToYaml()
    }

    function writePin(index: number, field: keyof PinModel, value: unknown) {
        if (index < 0 || index >= model.pins.length) return
        ;(model.pins[index] as any)[field] = value
        flushToYaml()
    }

    function addPin(pin: PinModel) {
        model.pins.push({ ...pin })
        flushToYaml()
    }

    function removePin(index: number) {
        if (index < 0 || index >= model.pins.length) return
        model.pins.splice(index, 1)
        flushToYaml()
    }

    function writePeripheral(index: number, field: keyof PeripheralModel, value: unknown) {
        if (index < 0 || index >= model.peripherals.length) return
        ;(model.peripherals[index] as any)[field] = value
        flushToYaml()
    }

    function addPeripheral(peri: PeripheralModel) {
        model.peripherals.push({ ...peri })
        flushToYaml()
    }

    function removePeripheral(index: number) {
        if (index < 0 || index >= model.peripherals.length) return
        model.peripherals.splice(index, 1)
        flushToYaml()
    }

    function writeTask(index: number, field: keyof AppTaskModel, value: unknown) {
        if (index < 0 || index >= model.app_tasks.length) return
        ;(model.app_tasks[index] as any)[field] = value
        flushToYaml()
    }

    function addTask(task: AppTaskModel) {
        model.app_tasks.push({ ...task })
        flushToYaml()
    }

    function removeTask(index: number) {
        if (index < 0 || index >= model.app_tasks.length) return
        model.app_tasks.splice(index, 1)
        flushToYaml()
    }

    function writeSleep(partial: Partial<SleepModel>) {
        if (!model.sleep) model.sleep = { enabled: false, mode: 'SLEEP', enter_on_exit: false, regulator_voltage_scale: 2, flash_power_down: false, wakeup_sources: [] }
        Object.assign(model.sleep, partial)
        flushToYaml()
    }

    function writeClock(partial: Partial<ClockModel>) {
        if (!model.clock) return
        Object.assign(model.clock, partial)
        flushToYaml()
    }

    function writeFlashPartitions(partitions: FlashPartition[]) {
        model.flash_partitions = partitions
        flushToYaml()
    }

    function setBehavior(flow: BehaviorModel | null) {
        model.behavior = flow
        flushToYaml()
    }

    /** Load fresh data from API — replaces entire model */
    function loadFromApi(yamlText: string) {
        syncing = true
        yamlRef.value = yamlText
        const parsed = yamlToModel(yamlText)
        Object.assign(model, parsed)
        requestAnimationFrame(() => { syncing = false })
    }

    return {
        /** Read-only model for UI components */
        model: readonly(model),
        /** Mutations */
        writeMcu,
        writePin,
        addPin,
        removePin,
        writePeripheral,
        addPeripheral,
        removePeripheral,
        writeTask,
        addTask,
        removeTask,
        writeSleep,
        writeClock,
        writeFlashPartitions,
        setBehavior,
        loadFromApi,
    }
}
