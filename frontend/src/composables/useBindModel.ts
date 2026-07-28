/**
 * useBindModel — bidirectional bind.yaml ↔ reactive state sync.
 *
 * Manages interrupt bindings, peripheral assignments, and task-to-task
 * routing. Synchronises with a dedicated YAML string ref.
 */
import { reactive, readonly, watch, type Ref } from 'vue'
import { load, dump } from 'js-yaml'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface BindInterruptModel {
    pin: string
    task: string
    event: string
}

export interface BindPeripheralAssignModel {
    peripheral: string
    task: string
    role: string
}

export interface BindRoutingModel {
    from: string
    to?: string | null
    signal: string
    condition?: string | null
}

export interface BindModel {
    version: number
    hardware: string
    task: string
    interrupt: BindInterruptModel[]
    peripheral_assign: BindPeripheralAssignModel[]
    routing: BindRoutingModel[]
}

// ---------------------------------------------------------------------------
// Default empty model
// ---------------------------------------------------------------------------

function defaultModel(): BindModel {
    return {
        version: 1,
        hardware: 'hardware.yaml',
        task: 'task.yaml',
        interrupt: [],
        peripheral_assign: [],
        routing: [],
    }
}

// ---------------------------------------------------------------------------
// YAML dump / restore
// ---------------------------------------------------------------------------

function modelToYaml(model: BindModel): string {
    const doc: Record<string, unknown> = {
        version: model.version,
        hardware: model.hardware,
        task: model.task,
    }

    if (model.interrupt.length > 0) {
        doc.interrupt = model.interrupt.map(b => {
            const o: Record<string, unknown> = { pin: b.pin, task: b.task }
            if (b.event) o.event = b.event
            return o
        })
    }

    if (model.peripheral_assign.length > 0) {
        doc.peripheral_assign = model.peripheral_assign.map(b => {
            const o: Record<string, unknown> = { peripheral: b.peripheral, task: b.task }
            if (b.role) o.role = b.role
            return o
        })
    }

    if (model.routing.length > 0) {
        doc.routing = model.routing.map(b => {
            const o: Record<string, unknown> = { from: b.from, signal: b.signal }
            if (b.to) o.to = b.to
            if (b.condition) o.condition = b.condition
            return o
        })
    }

    return dump(doc, { indent: 2, sortKeys: false })
}

export function yamlToModel(text: string): BindModel {
    try {
        const doc = load(text) as Record<string, unknown>
        if (!doc) return defaultModel()

        const model = defaultModel()

        if (typeof doc.version === 'number') model.version = doc.version
        if (typeof doc.hardware === 'string') model.hardware = doc.hardware
        if (typeof doc.task === 'string') model.task = doc.task

        const rawInterrupt = Array.isArray(doc.interrupt) ? doc.interrupt : []
        model.interrupt = rawInterrupt.map((b: any) => ({
            pin: String(b.pin ?? ''),
            task: String(b.task ?? ''),
            event: String(b.event ?? ''),
        }))

        const rawPA = Array.isArray(doc.peripheral_assign) ? doc.peripheral_assign : []
        model.peripheral_assign = rawPA.map((b: any) => ({
            peripheral: String(b.peripheral ?? ''),
            task: String(b.task ?? ''),
            role: String(b.role ?? ''),
        }))

        const rawRouting = Array.isArray(doc.routing) ? doc.routing : []
        model.routing = rawRouting.map((b: any) => ({
            from: String(b.from ?? ''),
            to: b.to ?? null,
            signal: String(b.signal ?? ''),
            condition: b.condition ?? null,
        }))

        return model
    } catch {
        return defaultModel()
    }
}

// ---------------------------------------------------------------------------
// useBindModel composable
// ---------------------------------------------------------------------------

export function useBindModel(yamlRef: Ref<string>) {
    const model = reactive<BindModel>(defaultModel())
    let syncing = false

    watch(yamlRef, (newYaml) => {
        if (syncing) return
        const parsed = yamlToModel(newYaml)
        Object.assign(model, parsed)
    })

    function flushToYaml() {
        syncing = true
        yamlRef.value = modelToYaml({ ...model })
        requestAnimationFrame(() => { syncing = false })
    }

    // ------------------------------------------------------------------
    // Mutations
    // ------------------------------------------------------------------

    function writeInterrupt(index: number, field: keyof BindInterruptModel, value: unknown) {
        if (index < 0 || index >= model.interrupt.length) return
        ;(model.interrupt[index] as any)[field] = value
        flushToYaml()
    }

    function addInterrupt(binding: BindInterruptModel) {
        // Avoid duplicates: same pin → same task
        const exists = model.interrupt.some(
            b => b.pin === binding.pin && b.task === binding.task && b.event === binding.event,
        )
        if (!exists) {
            model.interrupt.push({ ...binding })
            flushToYaml()
        }
    }

    function removeInterrupt(index: number) {
        if (index < 0 || index >= model.interrupt.length) return
        model.interrupt.splice(index, 1)
        flushToYaml()
    }

    function writePeripheralAssign(index: number, field: keyof BindPeripheralAssignModel, value: unknown) {
        if (index < 0 || index >= model.peripheral_assign.length) return
        ;(model.peripheral_assign[index] as any)[field] = value
        flushToYaml()
    }

    function addPeripheralAssign(binding: BindPeripheralAssignModel) {
        const exists = model.peripheral_assign.some(
            b => b.peripheral === binding.peripheral && b.task === binding.task,
        )
        if (!exists) {
            model.peripheral_assign.push({ ...binding })
            flushToYaml()
        }
    }

    function removePeripheralAssign(index: number) {
        if (index < 0 || index >= model.peripheral_assign.length) return
        model.peripheral_assign.splice(index, 1)
        flushToYaml()
    }

    function writeRouting(index: number, field: keyof BindRoutingModel, value: unknown) {
        if (index < 0 || index >= model.routing.length) return
        ;(model.routing[index] as any)[field] = value
        flushToYaml()
    }

    function addRouting(binding: BindRoutingModel) {
        model.routing.push({ ...binding })
        flushToYaml()
    }

    function removeRouting(index: number) {
        if (index < 0 || index >= model.routing.length) return
        model.routing.splice(index, 1)
        flushToYaml()
    }

    function loadFromApi(yamlText: string) {
        syncing = true
        yamlRef.value = yamlText
        const parsed = yamlToModel(yamlText)
        Object.assign(model, parsed)
        requestAnimationFrame(() => { syncing = false })
    }

    return {
        model: readonly(model),
        writeInterrupt,
        addInterrupt,
        removeInterrupt,
        writePeripheralAssign,
        addPeripheralAssign,
        removePeripheralAssign,
        writeRouting,
        addRouting,
        removeRouting,
        loadFromApi,
    }
}
