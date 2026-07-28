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
    core_clock_mhz: number
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
    address?: number | null
    extra?: Record<string, unknown>
    features?: string[]
}

export interface AppTaskModel {
    name: string
    priority: number
    stack_size: number
}

export interface SleepModel {
    mode: string
}

export interface HardwareModel {
    mcu: McuModel
    pins: PinModel[]
    peripherals: PeripheralModel[]
    app_tasks: AppTaskModel[]
    sleep: SleepModel | null
    business_flow: Record<string, unknown> | null
}

// ---------------------------------------------------------------------------
// Default empty model
// ---------------------------------------------------------------------------

function defaultModel(): HardwareModel {
    return {
        mcu: { part: '', core_clock_mhz: 64 },
        pins: [],
        peripherals: [],
        app_tasks: [],
        sleep: null,
        business_flow: null,
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
        doc.app_tasks = model.app_tasks.map(t => ({
            name: t.name,
            priority: t.priority,
            stack_size: t.stack_size,
        }))
    }
    if (model.sleep?.mode) {
        doc.sleep = { mode: model.sleep.mode }
    }
    if (model.business_flow && Object.keys(model.business_flow).length) {
        doc.business_flow = model.business_flow
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
                core_clock_mhz: Number(m.core_clock_mhz ?? 64),
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
            bus: p.bus ?? null,
            address: p.address ?? null,
            extra: p.extra ?? undefined,
            features: Array.isArray(p.features) ? p.features : undefined,
        }))

        const rawTasks = Array.isArray(doc.app_tasks) ? doc.app_tasks : []
        model.app_tasks = rawTasks.map((t: any) => ({
            name: String(t.name ?? ''),
            priority: Number(t.priority ?? 3),
            stack_size: Number(t.stack_size ?? 512),
        }))

        model.sleep = doc.sleep ? { mode: String((doc.sleep as any).mode ?? 'SLEEP') } : null
        model.business_flow = (doc.business_flow as Record<string, unknown>) ?? null

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
        if (!model.sleep) model.sleep = { mode: 'SLEEP' }
        Object.assign(model.sleep, partial)
        flushToYaml()
    }

    function setBusinessFlow(flow: Record<string, unknown> | null) {
        model.business_flow = flow
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
        setBusinessFlow,
        loadFromApi,
    }
}
