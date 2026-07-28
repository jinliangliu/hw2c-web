<script setup lang="ts">
/**
 * BindGraph.vue — Visual binding editor using Vue Flow.
 *
 * Two-zone canvas:
 *   LEFT  (x ~ 50):  Hardware sources — GPIO EXTI pins, peripherals, Timer, RTC
 *   RIGHT (x ~ 500): Software tasks — name, priority badge, stack size
 *
 * Edges:
 *   - Source → Task (interrupt):     solid orange, event label
 *   - Source → Task (periph assign): solid green, role label
 *   - Task → Task (routing):         dashed purple, signal label
 *
 * Interactions:
 *   - Drag from Handle dots to create connections
 *   - Click an edge to open the inline editor (top-right corner)
 *   - Press Delete/Backspace on a selected edge to remove the binding
 *   - Vue Flow native edge removal (@edges-remove) also syncs bindings
 */
import { computed, ref, watch, markRaw, onMounted, onUnmounted, type Component } from 'vue'
import {
    VueFlow, useVueFlow, Handle, MarkerType,
    type Node, type Edge, type Connection,
} from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'

/* ---- Props ---- */
const props = defineProps<{
    extiPins: { id: string; label: string }[]
    peripherals: { name: string; type: string }[]
    tasks: { name: string; priority: number; stack_size: number }[]
    bindInterrupt: { pin: string; task: string; event: string }[]
    bindPeripheralAssign: { peripheral: string; task: string; role: string }[]
    bindRouting: { from: string; to?: string | null; signal: string; condition?: string | null }[]
    hasRtc?: boolean
}>()

/* ---- Emits ---- */
const emit = defineEmits<{
    (e: 'add-interrupt', binding: { pin: string; task: string; event: string }): void
    (e: 'remove-interrupt', index: number): void
    (e: 'add-peripheral-assign', binding: { peripheral: string; task: string; role: string }): void
    (e: 'remove-peripheral-assign', index: number): void
    (e: 'add-routing', binding: { from: string; to: string; signal: string; condition?: string }): void
    (e: 'remove-routing', index: number): void
    (e: 'update-routing', index: number, field: string, value: unknown): void
}>()

/* ---- Vue Flow instance ---- */
const { onConnect, addNodes, addEdges, removeNodes, removeEdges, getNodes, getEdges, fitView } = useVueFlow()

/* ---- Priority color ---- */
function prioColor(p: number): string {
    const m: Record<number, string> = { 1: '#6b7280', 2: '#3b82f6', 3: '#10b981', 4: '#f59e0b', 5: '#ef4444' }
    return m[p] ?? '#10b981'
}

/* ---- Selected edge for editing ---- */
interface EdgeEditInfo {
    edgeId: string
    type: 'interrupt' | 'peripheral_assign' | 'routing'
    index: number
}
const selectedEdge = ref<EdgeEditInfo | null>(null)

/* ---- Edit panel form state ---- */
const editForm = ref({
    eventName: '',
    role: '',
    signalName: '',
    signalTarget: '',
    signalCondition: '',
})

/* ------------------------------------------------------------------ */
/* Build graph nodes & edges                                           */
/* ------------------------------------------------------------------ */

interface GraphData {
    nodes: Node[]
    edges: Edge[]
}

function buildGraph(): GraphData {
    const nodes: Node[] = []
    const edges: Edge[] = []
    const SOURCE_X = 50
    const TASK_X = 500
    const SOURCE_START_Y = 40
    const TASK_START_Y = 60
    const SOURCE_GAP = 62
    const TASK_GAP = 110

    /* -- Source nodes: GPIO EXTI pins -- */
    props.extiPins.forEach((pin, i) => {
        nodes.push({
            id: `src-gpio-${pin.id}`,
            type: 'source-node',
            position: { x: SOURCE_X, y: SOURCE_START_Y + i * SOURCE_GAP },
            data: {
                srcType: 'gpio',
                srcBadge: 'EXTI',
                label: pin.id,
                detail: pin.label || '',
                pinId: pin.id,
            },
        })
    })

    let nextSrcIdx = props.extiPins.length

    /* -- Source nodes: Peripherals -- */
    props.peripherals.forEach((peri, i) => {
        nodes.push({
            id: `src-peri-${peri.name}`,
            type: 'source-node',
            position: { x: SOURCE_X, y: SOURCE_START_Y + (nextSrcIdx + i) * SOURCE_GAP },
            data: {
                srcType: 'peri',
                srcBadge: 'PERI',
                label: peri.name,
                detail: peri.type || '',
                periName: peri.name,
            },
        })
    })

    nextSrcIdx += props.peripherals.length

    /* -- Timer node -- */
    nodes.push({
        id: 'src-timer',
        type: 'source-node',
        position: { x: SOURCE_X, y: SOURCE_START_Y + nextSrcIdx * SOURCE_GAP + 6 },
        data: {
            srcType: 'timer',
            srcBadge: 'TIMER',
            label: 'Software Timer',
            detail: '',
        },
    })
    nextSrcIdx++

    /* -- RTC node (optional) -- */
    if (props.hasRtc) {
        nodes.push({
            id: 'src-rtc',
            type: 'source-node',
            position: { x: SOURCE_X, y: SOURCE_START_Y + nextSrcIdx * SOURCE_GAP + 6 },
            data: {
                srcType: 'rtc',
                srcBadge: 'RTC',
                label: 'RTC Tick',
                detail: '',
            },
        })
    }

    /* -- Task nodes -- */
    const taskNodeId = (i: number) => `task-${i}`
    function findTaskNodeId(name: string): string | null {
        const idx = props.tasks.findIndex(t => t.name === name)
        return idx >= 0 ? taskNodeId(idx) : null
    }

    props.tasks.forEach((task, i) => {
        nodes.push({
            id: taskNodeId(i),
            type: 'task-node',
            position: { x: TASK_X, y: TASK_START_Y + i * TASK_GAP },
            data: {
                label: task.name,
                priority: task.priority,
                stack: task.stack_size,
                prioColor: prioColor(task.priority),
                taskIndex: i,
            },
        })
    })

    /* -- Edges: interrupt bindings -- */
    props.bindInterrupt.forEach((b, i) => {
        const srcId = `src-gpio-${b.pin}`
        const tgtId = findTaskNodeId(b.task)
        if (!tgtId) return
        edges.push({
            id: `e-int-${i}`,
            source: srcId,
            target: tgtId,
            label: b.event || b.pin,
            type: 'smoothstep',
            animated: false,
            style: { stroke: '#f59e0b', strokeWidth: 2 },
            markerEnd: MarkerType.ArrowClosed,
            data: { edgeType: 'interrupt', index: i, binding: b },
        })
    })

    /* -- Edges: peripheral_assign bindings -- */
    props.bindPeripheralAssign.forEach((b, i) => {
        const srcId = `src-peri-${b.peripheral}`
        const tgtId = findTaskNodeId(b.task)
        if (!tgtId) return
        edges.push({
            id: `e-pa-${i}`,
            source: srcId,
            target: tgtId,
            label: b.role || b.peripheral,
            type: 'smoothstep',
            animated: false,
            style: { stroke: '#10b981', strokeWidth: 2 },
            markerEnd: MarkerType.ArrowClosed,
            data: { edgeType: 'peripheral_assign', index: i, binding: b },
        })
    })

    /* -- Edges: routing bindings (task → task) -- */
    props.bindRouting.forEach((b, i) => {
        const srcId = findTaskNodeId(b.from)
        const tgtId = b.to ? findTaskNodeId(b.to) : null
        if (!srcId || !tgtId) return
        edges.push({
            id: `e-route-${i}`,
            source: srcId,
            target: tgtId,
            label: b.signal || 'signal',
            type: 'smoothstep',
            animated: false,
            style: { stroke: '#8b5cf6', strokeWidth: 1.5, strokeDasharray: '5 3' },
            markerEnd: MarkerType.ArrowClosed,
            data: { edgeType: 'routing', index: i, binding: b },
        })
    })

    return { nodes, edges }
}

/* ---- Graph sync ---- */
const graphData = computed<GraphData>(() => {
    /* touch reactives */
    void props.extiPins.length
    void props.peripherals.length
    void props.tasks.length
    void props.bindInterrupt.length
    void props.bindPeripheralAssign.length
    void props.bindRouting.length
    void props.hasRtc
    return buildGraph()
})

function syncGraph() {
    const { nodes, edges } = graphData.value
    const existingNodes = getNodes.value
    const existingEdges = getEdges.value
    if (existingNodes.length) removeNodes(existingNodes.map(n => n.id))
    if (existingEdges.length) removeEdges(existingEdges.map(e => e.id))
    if (nodes.length) addNodes(nodes)
    if (edges.length) addEdges(edges)
    setTimeout(() => fitView({ padding: 0.15 }), 100)
}

watch(
    () => [
        props.extiPins,
        props.peripherals,
        props.tasks,
        props.bindInterrupt,
        props.bindPeripheralAssign,
        props.bindRouting,
        props.hasRtc,
    ],
    syncGraph,
    { deep: true, immediate: true },
)

/* ------------------------------------------------------------------ */
/* Drag-to-connect handler                                             */
/* ------------------------------------------------------------------ */

function handleConnect(connection: Connection) {
    const sourceNode = getNodes.value.find(n => n.id === connection.source)
    const targetNode = getNodes.value.find(n => n.id === connection.target)
    if (!sourceNode || !targetNode) return

    const srcData = sourceNode.data as any
    const tgtData = targetNode.data as any
    const tgtTaskName: string | undefined = tgtData?.label

    if (!tgtTaskName) return

    if (sourceNode.type === 'source-node') {
        const srcType: string = srcData?.srcType ?? ''

        if (srcType === 'gpio') {
            const pinId: string = srcData?.pinId ?? ''
            emit('add-interrupt', { pin: pinId, task: tgtTaskName, event: pinId })
        } else if (srcType === 'peri') {
            const periName: string = srcData?.periName ?? srcData?.label ?? ''
            emit('add-peripheral-assign', { peripheral: periName, task: tgtTaskName, role: '' })
        } else if (srcType === 'timer') {
            emit('add-interrupt', { pin: 'TIME', task: tgtTaskName, event: 'TIMER' })
        } else if (srcType === 'rtc') {
            emit('add-interrupt', { pin: 'RTC', task: tgtTaskName, event: 'RTC_TICK' })
        }
    } else if (sourceNode.type === 'task-node' && srcData?.label) {
        const fromName: string = srcData.label
        const toName: string = tgtTaskName
        const signalName = `${fromName}_to_${toName}`
        emit('add-routing', { from: fromName, to: toName, signal: signalName })
    }
}

/* ------------------------------------------------------------------ */
/* Edge click → open editor                                            */
/* ------------------------------------------------------------------ */

function handleEdgeClick(edge: Edge, _event: MouseEvent) {
    const data = edge.data as any
    if (!data || !data.edgeType) return

    selectedEdge.value = {
        edgeId: edge.id,
        type: data.edgeType,
        index: data.index,
    }

    const binding = data.binding
    if (data.edgeType === 'interrupt' && binding) {
        editForm.value.eventName = binding.event ?? ''
    } else if (data.edgeType === 'peripheral_assign' && binding) {
        editForm.value.role = binding.role ?? ''
    } else if (data.edgeType === 'routing' && binding) {
        editForm.value.signalName = binding.signal ?? ''
        editForm.value.signalTarget = binding.to ?? ''
        editForm.value.signalCondition = binding.condition ?? ''
    }
}

function closeEditor() {
    selectedEdge.value = null
}

/* ------------------------------------------------------------------ */
/* Apply editor changes                                                */
/* ------------------------------------------------------------------ */

function applyEdit() {
    if (!selectedEdge.value) return
    const { type, index } = selectedEdge.value

    if (type === 'interrupt') {
        const binding = props.bindInterrupt[index]
        if (!binding) return
        /* remove old + add new with updated event */
        emit('remove-interrupt', index)
        emit('add-interrupt', {
            pin: binding.pin,
            task: binding.task,
            event: editForm.value.eventName || binding.event,
        })
    } else if (type === 'peripheral_assign') {
        const binding = props.bindPeripheralAssign[index]
        if (!binding) return
        emit('remove-peripheral-assign', index)
        emit('add-peripheral-assign', {
            peripheral: binding.peripheral,
            task: binding.task,
            role: editForm.value.role || binding.role,
        })
    } else if (type === 'routing') {
        emit('update-routing', index, 'signal', editForm.value.signalName)
        if (editForm.value.signalTarget) {
            emit('update-routing', index, 'to', editForm.value.signalTarget)
        }
        if (editForm.value.signalCondition !== undefined) {
            emit('update-routing', index, 'condition', editForm.value.signalCondition || null)
        }
    }

    closeEditor()
}

/* ------------------------------------------------------------------ */
/* Delete selected edge                                                */
/* ------------------------------------------------------------------ */

function deleteSelectedEdge() {
    if (!selectedEdge.value) return
    const { type, index } = selectedEdge.value

    if (type === 'interrupt') {
        emit('remove-interrupt', index)
    } else if (type === 'peripheral_assign') {
        emit('remove-peripheral-assign', index)
    } else if (type === 'routing') {
        emit('remove-routing', index)
    }

    closeEditor()
}

/* ---- Vue Flow native edge removal: sync back to bindings ---- */
function handleEdgesRemove(edges: Edge[]) {
    for (const edge of edges) {
        const data = edge.data as any
        if (!data || !data.edgeType) continue

        if (data.edgeType === 'interrupt') {
            emit('remove-interrupt', data.index)
        } else if (data.edgeType === 'peripheral_assign') {
            emit('remove-peripheral-assign', data.index)
        } else if (data.edgeType === 'routing') {
            emit('remove-routing', data.index)
        }
    }
}

/* ------------------------------------------------------------------ */
/* Keyboard: Delete/Backspace on selected edge, Esc to close           */
/* ------------------------------------------------------------------ */

function handleKeydown(e: KeyboardEvent) {
    if (selectedEdge.value && (e.key === 'Delete' || e.key === 'Backspace')) {
        e.preventDefault()
        deleteSelectedEdge()
    }
    if (e.key === 'Escape') {
        closeEditor()
    }
}

onMounted(() => document.addEventListener('keydown', handleKeydown))
onUnmounted(() => document.removeEventListener('keydown', handleKeydown))

/* ---- Click on pane to close editor ---- */
function handlePaneClick() {
    closeEditor()
}

/* ------------------------------------------------------------------ */
/* Node type component templates                                       */
/* ------------------------------------------------------------------ */

const nodeTypes: Record<string, Component> = {
    'task-node': markRaw({
        props: ['data'],
        template: `
<div class="vf-bind-task-node">
  <div class="vf-bind-task-head">
    <span class="vf-bind-task-name">{{ data.label }}</span>
  </div>
  <div class="vf-bind-task-meta">
    <span class="vf-tag vf-tag-prio" :style="{ background: data.prioColor + '22', color: data.prioColor }">P{{ data.priority }}</span>
    <span class="vf-tag vf-tag-stack">{{ data.stack }}B</span>
  </div>
</div>`,
    }),
    'source-node': markRaw({
        props: ['data'],
        template: `
<div :class="['vf-bind-source-node', 'vf-bind-src-' + data.srcType]">
  <span class="vf-src-badge">{{ data.srcBadge }}</span>
  <span class="vf-src-name">{{ data.label }}</span>
  <span class="vf-src-detail" v-if="data.detail">{{ data.detail }}</span>
</div>`,
    }),
}

/** Task names for routing target dropdown */
const taskNames = computed(() => props.tasks.map(t => t.name))

/* ---- Current editing helper ---- */
const editingInterrupt = computed(() => {
    if (!selectedEdge.value || selectedEdge.value.type !== 'interrupt') return null
    return props.bindInterrupt[selectedEdge.value.index] ?? null
})
const editingPeripheralAssign = computed(() => {
    if (!selectedEdge.value || selectedEdge.value.type !== 'peripheral_assign') return null
    return props.bindPeripheralAssign[selectedEdge.value.index] ?? null
})
</script>

<template>
    <div class="bind-graph-panel panel">
        <div class="panel-title">
            Bind Graph
            <span class="graph-hint" v-if="!selectedEdge">Drag handles to connect | Click edge to edit | Del to remove</span>
            <span class="graph-hint graph-hint-active" v-else>Editing — Esc to cancel, Del to remove</span>
        </div>

        <div class="graph-container" style="position: relative;">
            <VueFlow
                :node-types="nodeTypes"
                :default-edge-options="{ type: 'smoothstep', animated: false, interactionWidth: 20, selectable: true, deletable: true }"
                :fit-view-on-init="true"
                :snap-to-grid="true"
                :snap-grid="[10, 10]"
                @connect="handleConnect"
                @edge-click="handleEdgeClick"
                @edges-remove="handleEdgesRemove"
                @pane-click="handlePaneClick"
                class="bind-flow"
            >
                <Background variant="dots" :gap="20" :size="1" />
                <Controls position="bottom-right" />

                <!-- Task node template -->
                <template #node-task-node="nodeProps">
                    <div class="vf-bind-task-node">
                        <div class="vf-bind-task-head">
                            <span class="vf-bind-task-name">{{ nodeProps.data.label }}</span>
                        </div>
                        <div class="vf-bind-task-meta">
                            <span
                                class="vf-tag vf-tag-prio"
                                :style="{ background: nodeProps.data.prioColor + '22', color: nodeProps.data.prioColor, borderColor: nodeProps.data.prioColor }"
                            >P{{ nodeProps.data.priority }}</span>
                            <span class="vf-tag vf-tag-stack">{{ nodeProps.data.stack }}B</span>
                        </div>
                        <!-- Left: target handle (accepts incoming connections) -->
                        <Handle type="target" :position="'left'" :id="'t-left'" class="vf-handle-custom vf-handle-target" />
                        <!-- Right: source handle (emits outgoing connections) -->
                        <Handle type="source" :position="'right'" :id="'s-right'" class="vf-handle-custom vf-handle-source-right" />
                    </div>
                </template>

                <!-- Source node template -->
                <template #node-source-node="nodeProps">
                    <div :class="['vf-bind-source-node', 'vf-bind-src-' + nodeProps.data.srcType]">
                        <span class="vf-src-badge">{{ nodeProps.data.srcBadge }}</span>
                        <span class="vf-src-name">{{ nodeProps.data.label }}</span>
                        <span class="vf-src-detail" v-if="nodeProps.data.detail">{{ nodeProps.data.detail }}</span>
                        <!-- Right handle only: source nodes emit outgoing connections -->
                        <Handle type="source" :position="'right'" :id="'s-right'" class="vf-handle-custom vf-handle-source-right" />
                    </div>
                </template>
            </VueFlow>

            <!-- Inline edge editor popup -->
            <div
                v-if="selectedEdge"
                class="edge-editor"
                @click.stop
            >
                <div class="edge-editor-head">
                    <span>
                        Edit
                        <strong>{{
                            selectedEdge.type === 'interrupt' ? 'Interrupt' :
                            selectedEdge.type === 'peripheral_assign' ? 'Peripheral Assign' : 'Routing'
                        }}</strong>
                    </span>
                    <button class="edge-editor-close" @click="closeEditor">&times;</button>
                </div>

                <!-- Interrupt editor -->
                <template v-if="selectedEdge.type === 'interrupt' && editingInterrupt">
                    <div class="edge-editor-row">
                        <label>Pin</label>
                        <code class="edge-editor-code">{{ editingInterrupt.pin }}</code>
                    </div>
                    <div class="edge-editor-row">
                        <label>Task</label>
                        <code class="edge-editor-code">{{ editingInterrupt.task }}</code>
                    </div>
                    <div class="edge-editor-row">
                        <label>Event Name</label>
                        <input
                            v-model="editForm.eventName"
                            type="text"
                            placeholder="e.g. FALLING_EDGE"
                            class="edge-editor-input"
                        />
                    </div>
                    <div class="edge-editor-actions">
                        <button class="btn btn-sm btn-danger" @click="deleteSelectedEdge">Remove</button>
                        <button class="btn btn-sm btn-primary" @click="applyEdit">Apply</button>
                    </div>
                </template>

                <!-- Peripheral assign editor -->
                <template v-if="selectedEdge.type === 'peripheral_assign' && editingPeripheralAssign">
                    <div class="edge-editor-row">
                        <label>Peripheral</label>
                        <code class="edge-editor-code peri-code">{{ editingPeripheralAssign.peripheral }}</code>
                    </div>
                    <div class="edge-editor-row">
                        <label>Task</label>
                        <code class="edge-editor-code">{{ editingPeripheralAssign.task }}</code>
                    </div>
                    <div class="edge-editor-row">
                        <label>Role</label>
                        <input
                            v-model="editForm.role"
                            type="text"
                            placeholder="e.g. MASTER"
                            class="edge-editor-input"
                        />
                    </div>
                    <div class="edge-editor-actions">
                        <button class="btn btn-sm btn-danger" @click="deleteSelectedEdge">Remove</button>
                        <button class="btn btn-sm btn-primary" @click="applyEdit">Apply</button>
                    </div>
                </template>

                <!-- Routing editor -->
                <template v-if="selectedEdge.type === 'routing'">
                    <div class="edge-editor-row">
                        <label>Signal Name</label>
                        <input
                            v-model="editForm.signalName"
                            type="text"
                            placeholder="e.g. DATA_READY"
                            class="edge-editor-input"
                        />
                    </div>
                    <div class="edge-editor-row">
                        <label>Target Task</label>
                        <select v-model="editForm.signalTarget" class="edge-editor-input">
                            <option v-for="n in taskNames" :key="n" :value="n">{{ n }}</option>
                        </select>
                    </div>
                    <div class="edge-editor-row">
                        <label>Condition (optional)</label>
                        <input
                            v-model="editForm.signalCondition"
                            type="text"
                            placeholder="e.g. count >= 3"
                            class="edge-editor-input"
                        />
                    </div>
                    <div class="edge-editor-actions">
                        <button class="btn btn-sm btn-danger" @click="deleteSelectedEdge">Remove</button>
                        <button class="btn btn-sm btn-primary" @click="applyEdit">Apply</button>
                    </div>
                </template>
            </div>
        </div>

        <!-- Legend -->
        <div class="graph-legend">
            <span class="legend-line legend-interrupt">Hardware → Task</span>
            <span class="legend-line legend-routing">Task → Task</span>
            <span class="legend-line legend-peri">Peripheral Assign</span>
        </div>
    </div>
</template>

<style scoped>
.bind-graph-panel {
    display: flex;
    flex-direction: column;
}

.graph-hint {
    font-size: 0.6rem;
    color: var(--text-dim);
    font-weight: 400;
    margin-left: auto;
}
.graph-hint-active {
    color: var(--accent);
}

.graph-container {
    height: 460px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    background: var(--bg-card);
}

/* ---- Edge editor popup ---- */
.edge-editor {
    position: absolute;
    top: 8px;
    right: 8px;
    width: 260px;
    background: #1a1f2e;
    border: 1px solid var(--accent);
    border-radius: 8px;
    padding: 0.75rem;
    z-index: 100;
    box-shadow: 0 4px 20px rgba(0,0,0,0.5);
}
.edge-editor-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.6rem;
    font-size: 0.75rem;
    color: var(--text);
}
.edge-editor-head strong {
    color: var(--accent);
}
.edge-editor-close {
    background: none;
    border: none;
    color: var(--text-dim);
    cursor: pointer;
    font-size: 1rem;
    line-height: 1;
}
.edge-editor-close:hover {
    color: #f87171;
}
.edge-editor-row {
    margin-bottom: 0.5rem;
}
.edge-editor-row label {
    display: block;
    font-size: 0.65rem;
    font-weight: 600;
    color: var(--text-dim);
    margin-bottom: 0.2rem;
    text-transform: uppercase;
}
.edge-editor-input {
    width: 100%;
    padding: 4px 8px;
    background: var(--bg-input);
    border: 1px solid var(--border);
    border-radius: 4px;
    color: var(--text);
    font-size: 0.75rem;
    font-family: inherit;
}
.edge-editor-input:focus {
    border-color: var(--accent);
    outline: none;
}
.edge-editor-code {
    display: block;
    font-size: 0.75rem;
    color: #f59e0b;
    background: rgba(245,158,11,0.1);
    padding: 2px 6px;
    border-radius: 3px;
}
.peri-code {
    color: #34d399;
    background: rgba(16,185,129,0.1);
}
.edge-editor-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.4rem;
    margin-top: 0.6rem;
    padding-top: 0.5rem;
    border-top: 1px solid var(--border);
}

/* ---- Legend ---- */
.graph-legend {
    display: flex;
    gap: 1rem;
    justify-content: center;
    margin-top: 0.4rem;
}
.legend-line {
    font-size: 0.65rem;
    position: relative;
    padding-left: 18px;
    color: var(--text-dim);
}
.legend-line::before {
    content: '';
    position: absolute;
    left: 0;
    top: 50%;
    width: 12px;
    height: 3px;
    border-radius: 2px;
    transform: translateY(-50%);
}
.legend-interrupt::before {
    background: #f59e0b;
}
.legend-routing::before {
    background: repeating-linear-gradient(90deg, #8b5cf6 0, #8b5cf6 4px, transparent 4px, transparent 6px);
}
.legend-peri::before {
    background: #10b981;
}

/* Small button variants */
.btn-sm {
    padding: 3px 10px;
    font-size: 0.7rem;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-weight: 600;
}
.btn-primary {
    background: var(--accent);
    color: #fff;
}
.btn-primary:hover { opacity: 0.9; }
.btn-danger {
    background: rgba(239,68,68,0.15);
    color: #f87171;
}
.btn-danger:hover { background: rgba(239,68,68,0.3); }
</style>

<!-- Global styles for nodes (VueFlow portal) -->
<style>
/* ---- Task node ---- */
.vf-bind-task-node {
    background: #1e2433;
    border: 1px solid #3b4a63;
    border-radius: 8px;
    padding: 8px 12px;
    min-width: 140px;
    font-family: 'Inter', sans-serif;
    cursor: grab;
    transition: border-color 0.15s;
    position: relative;
}
.vf-bind-task-node:hover {
    border-color: var(--vue-flow-primary, #3b82f6);
}
.vf-bind-task-head {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 4px;
}
.vf-bind-task-name {
    font-size: 0.8rem;
    font-weight: 700;
    color: #e2e8f0;
}
.vf-bind-task-meta {
    display: flex;
    gap: 4px;
}

/* ---- Source nodes ---- */
.vf-bind-source-node {
    background: #1a1f2e;
    border: 1px solid #2d3748;
    border-radius: 20px;
    padding: 6px 12px 6px 8px;
    display: flex;
    align-items: center;
    gap: 6px;
    font-family: 'Inter', sans-serif;
    cursor: grab;
    transition: border-color 0.15s;
    position: relative;
}
.vf-bind-source-node:hover {
    border-color: #f59e0b;
}

/* Source type border accents */
.vf-bind-src-gpio  { border-left: 3px solid #f59e0b; }
.vf-bind-src-peri  { border-left: 3px solid #10b981; }
.vf-bind-src-timer { border-left: 3px solid #3b82f6; }
.vf-bind-src-rtc   { border-left: 3px solid #10b981; }

/* Source badge colors */
.vf-bind-src-gpio .vf-src-badge,
.vf-bind-src-peri .vf-src-badge {
    background: rgba(245,158,11,0.2);
    color: #fbbf24;
}
.vf-bind-src-peri .vf-src-badge {
    background: rgba(16,185,129,0.2);
    color: #34d399;
}
.vf-bind-src-timer .vf-src-badge {
    background: rgba(59,130,246,0.2);
    color: #60a5fa;
}
.vf-bind-src-rtc .vf-src-badge {
    background: rgba(16,185,129,0.2);
    color: #34d399;
}

/* Shared source spans */
.vf-src-badge {
    font-size: 0.5rem;
    font-weight: 700;
    border-radius: 3px;
    padding: 0 3px;
    white-space: nowrap;
}
.vf-src-name {
    font-size: 0.7rem;
    font-weight: 600;
    color: #e2e8f0;
}
.vf-src-detail {
    font-size: 0.6rem;
    color: #8899aa;
}

/* Shared task tags (reuse from TaskGraph) */
.vf-tag {
    font-size: 0.55rem;
    padding: 0 3px;
    border-radius: 2px;
    font-weight: 600;
}
.vf-tag-prio {
    border: 1px solid;
}
.vf-tag-stack {
    background: rgba(107,114,128,0.15);
    color: #9ca3af;
}

/* ---- Vue Flow handles ---- */
.vf-handle-custom {
    width: 10px !important;
    height: 10px !important;
    border: 2px solid #1e2433 !important;
    border-radius: 50% !important;
    cursor: crosshair !important;
    transition: transform 0.1s;
}
.vf-handle-target {
    background: #ef4444 !important;
}
.vf-handle-source-right {
    background: #3b82f6 !important;
}
.vf-handle-custom:hover {
    transform: scale(1.4);
}
.vf-handle-target:hover {
    background: #f87171 !important;
}
.vf-handle-source-right:hover {
    background: #60a5fa !important;
}

/* ---- Edge labels ---- */
.vue-flow__edge-textbg {
    fill: #1a1f2e;
}
.vue-flow__edge-text {
    font-size: 0.55rem;
    font-weight: 600;
    fill: #8899aa;
}

/* ---- Selected edge highlight ---- */
.vue-flow__edge.selected .vue-flow__edge-path {
    stroke: #60a5fa !important;
    stroke-width: 3 !important;
}

/* ---- Background dots ---- */
.vue-flow__background pattern circle {
    fill: #2d3748;
}

/* ---- Controls ---- */
.vue-flow__controls-button {
    background: #1e2433 !important;
    border-color: #3b4a63 !important;
    color: #e2e8f0 !important;
    fill: #e2e8f0 !important;
}
.vue-flow__controls-button:hover {
    background: #2d3748 !important;
}

/* ---- Edge cursor ---- */
.vue-flow__edge {
    cursor: pointer;
}
.vue-flow__edge:hover .vue-flow__edge-path {
    stroke-width: 3 !important;
}
</style>
