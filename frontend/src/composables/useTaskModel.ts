/**
 * useTaskModel — bidirectional task.yaml ↔ reactive state sync.
 *
 * Handles project metadata, FreeRTOS task definitions, and business_flow
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
}

export interface AppTaskModel {
    name: string
    priority: number
    stack_size: number
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

export interface BusinessFlowModel {
    initial_state?: string
    types?: CustomTypeDef[]
    variables?: VariableModel[]
    events?: Record<string, unknown>[]
    states?: Record<string, unknown>[]
    regions?: Record<string, unknown>[]
}

export interface TaskModel {
    project: ProjectModel
    app_tasks: AppTaskModel[]
    business_flow: BusinessFlowModel | null
}

// ---------------------------------------------------------------------------
// Default empty model
// ---------------------------------------------------------------------------

function defaultModel(): TaskModel {
    return {
        project: { name: 'untitled', version: '0.1.0' },
        app_tasks: [],
        business_flow: null,
    }
}

// ---------------------------------------------------------------------------
// YAML dump / restore
// ---------------------------------------------------------------------------

function modelToYaml(model: TaskModel): string {
    const doc: Record<string, unknown> = {
        project: { name: model.project.name, version: model.project.version },
    }

    if (model.app_tasks.length > 0) {
        doc.app_tasks = model.app_tasks.map(t => ({
            name: t.name,
            priority: t.priority,
            stack_size: t.stack_size,
        }))
    }

    if (model.business_flow && Object.keys(model.business_flow).length > 0) {
        doc.business_flow = model.business_flow
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
            }
        }

        const rawTasks = Array.isArray(doc.app_tasks) ? doc.app_tasks : []
        model.app_tasks = rawTasks.map((t: any) => ({
            name: String(t.name ?? ''),
            priority: Number(t.priority ?? 3),
            stack_size: Number(t.stack_size ?? 512),
        }))

        model.business_flow = (doc.business_flow as BusinessFlowModel) ?? null

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

    function setBusinessFlow(flow: BusinessFlowModel | null) {
        model.business_flow = flow
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
        setBusinessFlow,
        loadFromApi,
    }
}
