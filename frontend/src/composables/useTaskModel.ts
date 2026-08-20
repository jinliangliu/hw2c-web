/**
 * useTaskModel — bidirectional task.yaml ↔ reactive state sync.
 *
 * Handles project metadata, FreeRTOS task definitions, and behavior
 * (state machine DSL). Synchronises with a dedicated YAML string ref.
 */
import { reactive, readonly, watch, type Ref } from 'vue'
import { load, dump } from 'js-yaml'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ProjectModel {
    name: string
    version: string
    /** FreeRTOS heap size in bytes (configTOTAL_HEAP_SIZE) */
    heap_size: number
}

export interface AppTaskModel {
    name: string
    priority: number
    stack_size: number
}

/**
 * Global event dispatcher task configuration.
 *
 * All timer / periodic / one-shot events are posted to a single FreeRTOS
 * queue consumed by this task.  The event task preprocesses and dispatches
 * to the appropriate application tasks.
 */
export interface EventTaskConfig {
    /** Task name, appears in FreeRTOS trace */
    name: string
    /** Entry function name */
    entry: string
    /** FreeRTOS priority (1-5) */
    priority: number
    /** Stack size in bytes */
    stack_size: number
    /** Maximum number of queued events */
    queue_depth: number
}

export interface VariableModel {
    name: string
    type: string
    initial?: unknown
    array?: number
}

export interface StructField {
    name: string
    type?: string
    array?: number
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

export interface TaskModel {
    project: ProjectModel
    /** Global event dispatcher task + queue config */
    event_task: EventTaskConfig
    app_tasks: AppTaskModel[]
    behavior: BehaviorModel | null
}

// ---------------------------------------------------------------------------
// Default empty model
// ---------------------------------------------------------------------------

function defaultModel(): TaskModel {
    return {
        project: { name: 'untitled', version: '0.1.0', heap_size: 16384 },
        event_task: {
            name: 'event_task',
            entry: 'vEventTask',
            priority: 3,
            stack_size: 1024,
            queue_depth: 32,
        },
        app_tasks: [],
        behavior: null,
    }
}

// ---------------------------------------------------------------------------
// YAML dump / restore
// ---------------------------------------------------------------------------

function modelToYaml(model: TaskModel): string {
    const doc: Record<string, unknown> = {
        project: {
            name: model.project.name,
            version: model.project.version,
            heap_size: model.project.heap_size,
        },
    }

    /* Global event task */
    doc.event_task = {
        name: model.event_task.name,
        entry: model.event_task.entry,
        priority: model.event_task.priority,
        stack_size: model.event_task.stack_size,
        queue_depth: model.event_task.queue_depth,
    }

    if (model.app_tasks.length > 0) {
        doc.app_tasks = model.app_tasks.map(t => {
            return {
                name: t.name,
                priority: t.priority,
                stack_size: t.stack_size,
            }
        })
    }

    if (model.behavior && Object.keys(model.behavior).length > 0) {
        doc.behavior = model.behavior
    }

    return dump(doc, { indent: 2, sortKeys: false })
}

export function yamlToModel(text: string): TaskModel {
    try {
        const doc = load(text) as Record<string, unknown>
        if (!doc) return defaultModel()

        const model = defaultModel()

        if (doc.project && typeof doc.project === 'object') {
            const p = doc.project as Record<string, unknown>
            model.project = {
                name: String(p.name ?? 'untitled'),
                version: String(p.version ?? '0.1.0'),
                heap_size: Number(p.heap_size ?? 16384),
            }
        }

        if (doc.event_task && typeof doc.event_task === 'object') {
            const et = doc.event_task as Record<string, unknown>
            model.event_task = {
                name: String(et.name ?? 'event_task'),
                entry: String(et.entry ?? 'vEventTask'),
                priority: Number(et.priority ?? 3),
                stack_size: Number(et.stack_size ?? 1024),
                queue_depth: Number(et.queue_depth ?? 32),
            }
        }

        const rawTasks = Array.isArray(doc.app_tasks) ? doc.app_tasks : []
        model.app_tasks = rawTasks.map((t: any) => ({
            name: String(t.name ?? ''),
            priority: Number(t.priority ?? 3),
            stack_size: Number(t.stack_size ?? 512),
        }))

        model.behavior = (doc.behavior as BehaviorModel) ?? null

        return model
    } catch {
        return defaultModel()
    }
}

// ---------------------------------------------------------------------------
// useTaskModel composable
// ---------------------------------------------------------------------------

export function useTaskModel(yamlRef: Ref<string>) {
    const model = reactive<TaskModel>(defaultModel())
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

    function writeProject(partial: Partial<ProjectModel>) {
        Object.assign(model.project, partial)
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

    function setBehavior(flow: BehaviorModel | null) {
        model.behavior = flow
        flushToYaml()
    }

    function writeHeapSize(size: number) {
        model.project.heap_size = size
        flushToYaml()
    }

    function writeEventTask(partial: Partial<EventTaskConfig>) {
        Object.assign(model.event_task, partial)
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
        writeProject,
        writeTask,
        addTask,
        removeTask,
        setBehavior,
        writeHeapSize,
        writeEventTask,
        loadFromApi,
    }
}
