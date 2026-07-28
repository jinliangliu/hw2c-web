<script setup lang="ts">
/**
 * TaskGraph.vue — Visual task orchestration with Vue Flow.
 *
 * Nodes:
 *   - Task nodes: rectangular, show name / priority / mode badge
 *   - Source nodes: GPIO EXTI / Timer / RTC trigger sources
 * Edges:
 *   - Source → Task: solid orange line, trigger label
 *   - Task → Task: dashed purple line, signal label
 *
 * Interactions:
 *   - Drag from Handle dots to create connections
 *   - Click an edge to open the inline editor (edit period / event name / signal name / condition)
 *   - Press Delete/Backspace on a selected edge to remove the connection
 */
import { computed, ref, watch, markRaw, h, onMounted, onUnmounted, type Component } from 'vue'
import {
    VueFlow, useVueFlow, Handle, MarkerType,
    type Node, type Edge, type Connection,
} from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import type { AppTaskModel, PinModel, TaskTrigger, TaskSignal } from '../composables/useHardwareModel'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'

const props = defineProps<{
    tasks: AppTaskModel[]
    pins: PinModel[]
    hasRtc?: boolean
}>()

const emit = defineEmits<{
    (e: 'update-task', index: number, field: string, value: unknown): void
}>()

/* ---- Vue Flow instance ---- */
const { onConnect, addNodes, addEdges, removeNodes, removeEdges, getNodes, getEdges, fitView } = useVueFlow()

/* ---- Selected edge for editing ---- */
interface EdgeEditInfo {
    edgeId: string
    type: 'trigger' | 'signal'
    taskIndex: number
    /** Index within triggers[] or signals[] */
    itemIndex: number
    trigger?: TaskTrigger
    signal?: TaskSignal
}
const selectedEdge = ref<EdgeEditInfo | null>(null)

/* ---- Edit panel form state ---- */
const editForm = ref({
    period_ms: 1000,
    eventSource: '',
    signalName: '',
    signalTarget: '',
    signalCondition: '',
    timerPresets: [100, 500, 1000, 5000, 10000],
})

/* ---- Priority color ---- */
function prioColor(p: number): string {
    const m: Record<number, string> = { 1: '#6b7280', 2: '#3b82f6', 3: '#10b981', 4: '#f59e0b', 5: '#ef4444' }
    return m[p] ?? '#10b981'
}

/* ---- EXTI-capable pins ---- */
const extiSources = computed(() =>
    props.pins.filter(p => p.exti || p.function === 'GPIO_Input' || p.function === 'GPIO_EXTI')
)

/* ---- Build graph nodes & edges ---- */
function buildGraph() {
    const nodes: Node[] = []
    const edges: Edge[] = []
    const TASK_X = 380
    const SOURCE_X = 80
    const TASK_START_Y = 60
    const SOURCE_START_Y = 40
    const TASK_GAP = 110
    const SOURCE_GAP = 60

    // --- Source nodes ---
    extiSources.value.forEach((pin, i) => {
        const trigger = pin.exti && (pin.exti as any).trigger ? (pin.exti as any).trigger : ''
        nodes.push({
            id: `src-gpio-${pin.id}`,
            type: 'source-node',
            position: { x: SOURCE_X, y: SOURCE_START_Y + i * SOURCE_GAP },
            data: {
                srcType: 'gpio',
                srcBadge: trigger ? `EXTI ${String(trigger).toUpperCase()}` : 'GPIO',
                label: pin.id,
                detail: pin.label || '',
                pinId: pin.id,
            },
        })
    })

    nodes.push({
        id: 'src-timer',
        type: 'source-node',
        position: { x: SOURCE_X, y: SOURCE_START_Y + extiSources.value.length * SOURCE_GAP + 10 },
        data: { srcType: 'timer', srcBadge: 'TIMER', label: 'Software Timer' },
    })

    if (props.hasRtc) {
        nodes.push({
            id: 'src-rtc',
            type: 'source-node',
            position: { x: SOURCE_X, y: SOURCE_START_Y + (extiSources.value.length + 1) * SOURCE_GAP + 10 },
            data: { srcType: 'rtc', srcBadge: 'RTC', label: 'RTC Tick' },
        })
    }

    // --- Task nodes ---
    props.tasks.forEach((task, i) => {
        nodes.push({
            id: `task-${i}`,
            type: 'task-node',
            position: { x: TASK_X, y: TASK_START_Y + i * TASK_GAP },
            data: {
                label: task.name,
                priority: task.priority,
                stack: task.stack_size,
                runMode: task.run_mode,
                prioColor: prioColor(task.priority),
                taskIndex: i,
            },
        })

        // Edges from triggers
        task.triggers?.forEach((trigger, ti) => {
            let sourceId = ''
            let label = ''
            if (trigger.type === 'interrupt' && trigger.source) {
                sourceId = `src-gpio-${trigger.source}`
                label = trigger.source
            } else if (trigger.type === 'timer') {
                sourceId = 'src-timer'
                label = trigger.period_ms ? `${trigger.period_ms}ms` : 'Timer'
            } else if (trigger.type === 'event' && trigger.source) {
                const srcIdx = props.tasks.findIndex(t => t.signals?.some(s => s.name === trigger.source))
                if (srcIdx >= 0) {
                    sourceId = `task-${srcIdx}`
                    label = trigger.source
                }
            }
            if (sourceId) {
                edges.push({
                    id: `e-trig-${i}-${ti}`,
                    source: sourceId,
                    target: `task-${i}`,
                    label,
                    type: 'smoothstep',
                    animated: trigger.type === 'timer',
                    style: { stroke: '#f59e0b', strokeWidth: 2 },
                    markerEnd: MarkerType.ArrowClosed,
                    data: { edgeType: 'trigger', taskIndex: i, itemIndex: ti, trigger },
                })
            }
        })

        // Edges from signals
        task.signals?.forEach((signal, si) => {
            const targetIdx = props.tasks.findIndex(t => t.name === signal.target)
            if (targetIdx >= 0) {
                edges.push({
                    id: `e-sig-${i}-${si}`,
                    source: `task-${i}`,
                    target: `task-${targetIdx}`,
                    label: signal.name || 'signal',
                    type: 'smoothstep',
                    style: { stroke: '#8b5cf6', strokeWidth: 1.5, strokeDasharray: '5 3' },
                    markerEnd: MarkerType.ArrowClosed,
                    data: { edgeType: 'signal', taskIndex: i, itemIndex: si, signal },
                })
            }
        })
    })

    return { nodes, edges }
}

/* ---- Graph sync ---- */
const graphData = computed(() => {
    void props.tasks.length; void props.pins.length
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

watch(() => [props.tasks, props.pins], syncGraph, { deep: true, immediate: true })

/* ---- Drag-to-connect handler ---- */
function handleConnect(connection: Connection) {
    const sourceNode = getNodes.value.find(n => n.id === connection.source)
    const targetNode = getNodes.value.find(n => n.id === connection.target)
    if (!sourceNode || !targetNode) return

    const sourceData = sourceNode.data as any
    const targetData = targetNode.data as any
    const taskIdx = targetData?.taskIndex

    if (taskIdx == null) return

    if (sourceNode.type === 'source-node') {
        const srcType = sourceData?.srcType
        if (srcType === 'gpio') {
            const current = props.tasks[taskIdx]
            const triggers = [...(current.triggers || [])]
            triggers.push({ type: 'interrupt', source: sourceData?.pinId })
            emit('update-task', taskIdx, 'triggers', triggers)
        } else if (srcType === 'timer') {
            const current = props.tasks[taskIdx]
            const triggers = [...(current.triggers || [])]
            triggers.push({ type: 'timer', period_ms: 1000 })
            emit('update-task', taskIdx, 'triggers', triggers)
        } else if (srcType === 'rtc') {
            const current = props.tasks[taskIdx]
            const triggers = [...(current.triggers || [])]
            triggers.push({ type: 'event', source: 'RTC_TICK' })
            emit('update-task', taskIdx, 'triggers', triggers)
        }
    } else if (sourceNode.type === 'task-node' && sourceData?.taskIndex != null) {
        const srcIdx = sourceData.taskIndex
        const current = props.tasks[srcIdx]
        const signals = [...(current.signals || [])]
        const sigName = `sig_${current.name}_to_${props.tasks[taskIdx].name}`
        if (!signals.find(s => s.name === sigName)) {
            signals.push({ name: sigName, target: props.tasks[taskIdx].name })
            emit('update-task', srcIdx, 'signals', signals)
        }
    }
}

/* ---- Edge click → open editor ---- */
function handleEdgeClick(edge: Edge, event: MouseEvent) {
    const data = edge.data as any
    if (!data || !data.edgeType) return

    selectedEdge.value = {
        edgeId: edge.id,
        type: data.edgeType,
        taskIndex: data.taskIndex,
        itemIndex: data.itemIndex,
        trigger: data.trigger,
        signal: data.signal,
    }

    // Initialize edit form
    if (data.edgeType === 'trigger' && data.trigger) {
        editForm.value.period_ms = data.trigger.period_ms ?? 1000
        editForm.value.eventSource = data.trigger.source ?? ''
    } else if (data.edgeType === 'signal' && data.signal) {
        editForm.value.signalName = data.signal.name ?? ''
        editForm.value.signalTarget = data.signal.target ?? ''
        editForm.value.signalCondition = ''
    }
}

function closeEditor() {
    selectedEdge.value = null
}

/* ---- Vue Flow native edge removal: sync back to task model ---- */
function handleEdgesRemove(edges: Edge[]) {
    for (const edge of edges) {
        const data = edge.data as any
        if (!data || !data.edgeType) continue

        const task = props.tasks[data.taskIndex]
        if (!task) continue

        if (data.edgeType === 'trigger') {
            const triggers = [...(task.triggers || [])]
            if (data.itemIndex < triggers.length) {
                triggers.splice(data.itemIndex, 1)
                emit('update-task', data.taskIndex, 'triggers', triggers)
            }
        } else if (data.edgeType === 'signal') {
            const signals = [...(task.signals || [])]
            if (data.itemIndex < signals.length) {
                signals.splice(data.itemIndex, 1)
                emit('update-task', data.taskIndex, 'signals', signals)
            }
        }
    }
}

/* ---- Apply editor changes ---- */
function applyTriggerEdit() {
    if (!selectedEdge.value) return
    const { taskIndex, itemIndex, trigger } = selectedEdge.value
    const task = props.tasks[taskIndex]
    const triggers = [...(task.triggers || [])]

    if (itemIndex < triggers.length) {
        if (triggers[itemIndex].type === 'timer') {
            triggers[itemIndex] = { ...triggers[itemIndex], period_ms: editForm.value.period_ms }
        } else if (triggers[itemIndex].type === 'event') {
            triggers[itemIndex] = { ...triggers[itemIndex], source: editForm.value.eventSource }
        }
        emit('update-task', taskIndex, 'triggers', triggers)
    }
    closeEditor()
}

function applySignalEdit() {
    if (!selectedEdge.value) return
    const { taskIndex, itemIndex } = selectedEdge.value
    const task = props.tasks[taskIndex]
    const signals = [...(task.signals || [])]

    if (itemIndex < signals.length) {
        signals[itemIndex] = {
            ...signals[itemIndex],
            name: editForm.value.signalName,
            target: editForm.value.signalTarget || signals[itemIndex].target,
        }
        emit('update-task', taskIndex, 'signals', signals)
    }
    closeEditor()
}

/* ---- Delete selected edge ---- */
function deleteSelectedEdge() {
    if (!selectedEdge.value) return
    const { type, taskIndex, itemIndex } = selectedEdge.value
    const task = props.tasks[taskIndex]

    if (type === 'trigger') {
        const triggers = [...(task.triggers || [])]
        triggers.splice(itemIndex, 1)
        emit('update-task', taskIndex, 'triggers', triggers)
    } else if (type === 'signal') {
        const signals = [...(task.signals || [])]
        signals.splice(itemIndex, 1)
        emit('update-task', taskIndex, 'signals', signals)
    }
    closeEditor()
}

/* ---- Keyboard: Delete/Backspace on selected edge ---- */
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

/* ---- Click outside to close editor ---- */
function handlePaneClick() {
    closeEditor()
}

/* ---- Node types ---- */
const nodeTypes: Record<string, Component> = {
    'task-node': markRaw({
        props: ['data'],
        template: `
<div class="vf-task-node">
  <div class="vf-task-head">
    <span class="vf-task-name">{{ data.label }}</span>
    <span :class="'vf-mode-badge vf-mode-' + data.runMode">{{ data.runMode }}</span>
  </div>
  <div class="vf-task-meta">
    <span class="vf-tag vf-tag-prio" :style="{ background: data.prioColor + '22', color: data.prioColor }">P{{ data.priority }}</span>
    <span class="vf-tag vf-tag-stack">{{ data.stack }}B</span>
  </div>
</div>`,
    }),
    'source-node': markRaw({
        props: ['data'],
        template: `
<div :class="['vf-source-node', 'vf-src-' + data.srcType]">
  <span class="vf-src-badge">{{ data.srcBadge }}</span>
  <span class="vf-src-name">{{ data.label }}</span>
  <span class="vf-src-detail" v-if="data.detail">{{ data.detail }}</span>
</div>`,
    }),
}

/** Task names for signal target dropdown */
const taskNames = computed(() => props.tasks.map(t => t.name))
</script>

<template>
    <div class="task-graph-panel panel">
        <div class="panel-title">
            Task Graph
            <span class="graph-hint" v-if="!selectedEdge">Drag handles to connect | Click edge to edit | Click edge + Del to remove</span>
            <span class="graph-hint graph-hint-active" v-else>Editing connection — Esc to cancel, Del to remove</span>
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
                class="task-flow"
            >
                <Background variant="dots" :gap="20" :size="1" />
                <Controls position="bottom-right" />

                <!-- Task node template -->
                <template #node-task-node="nodeProps">
                    <div class="vf-task-node">
                        <div class="vf-task-head">
                            <span class="vf-task-name">{{ nodeProps.data.label }}</span>
                            <span :class="'vf-mode-badge vf-mode-' + nodeProps.data.runMode">{{ nodeProps.data.runMode }}</span>
                        </div>
                        <div class="vf-task-meta">
                            <span class="vf-tag vf-tag-prio" :style="{ background: nodeProps.data.prioColor + '22', color: nodeProps.data.prioColor, borderColor: nodeProps.data.prioColor }">P{{ nodeProps.data.priority }}</span>
                            <span class="vf-tag vf-tag-stack">{{ nodeProps.data.stack }}B</span>
                        </div>
                        <!-- Four-side handles: target accepts incoming, source emits outgoing -->
                        <Handle type="target" :position="'top'"    :id="'t-top'"    class="vf-handle-custom" />
                        <Handle type="source" :position="'top'"    :id="'s-top'"    class="vf-handle-custom" />
                        <Handle type="target" :position="'right'"  :id="'t-right'"  class="vf-handle-custom" />
                        <Handle type="source" :position="'right'"  :id="'s-right'"  class="vf-handle-custom" />
                        <Handle type="target" :position="'bottom'" :id="'t-bottom'" class="vf-handle-custom" />
                        <Handle type="source" :position="'bottom'" :id="'s-bottom'" class="vf-handle-custom" />
                        <Handle type="target" :position="'left'"   :id="'t-left'"   class="vf-handle-custom" />
                        <Handle type="source" :position="'left'"   :id="'s-left'"   class="vf-handle-custom" />
                    </div>
                </template>

                <!-- Source node template -->
                <template #node-source-node="nodeProps">
                    <div :class="['vf-source-node', 'vf-src-' + nodeProps.data.srcType]">
                        <span class="vf-src-badge">{{ nodeProps.data.srcBadge }}</span>
                        <span class="vf-src-name">{{ nodeProps.data.label }}</span>
                        <span class="vf-src-detail" v-if="nodeProps.data.detail">{{ nodeProps.data.detail }}</span>
                        <!-- Right handle: emits outgoing edges only (source nodes are triggers) -->
                        <Handle type="source" :position="'right'" :id="'s-right'" class="vf-handle-custom" />
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
                        <strong>{{ selectedEdge.type === 'trigger' ? 'Trigger' : 'Signal' }}</strong>
                    </span>
                    <button class="edge-editor-close" @click="closeEditor">&times;</button>
                </div>

                <!-- Trigger editor -->
                <template v-if="selectedEdge.type === 'trigger' && selectedEdge.trigger">
                    <div class="edge-editor-row" v-if="selectedEdge.trigger.type === 'timer'">
                        <label>Period (ms)</label>
                        <div class="edge-editor-presets">
                            <button
                                v-for="p in editForm.timerPresets"
                                :key="p"
                                :class="['ee-preset', { active: editForm.period_ms === p }]"
                                @click="editForm.period_ms = p"
                            >{{ p }}</button>
                        </div>
                        <input
                            v-model.number="editForm.period_ms"
                            type="number" min="1" step="100"
                            class="edge-editor-input"
                        />
                    </div>
                    <div class="edge-editor-row" v-if="selectedEdge.trigger.type === 'event'">
                        <label>Event Name</label>
                        <input
                            v-model="editForm.eventSource"
                            type="text"
                            placeholder="e.g. DATA_READY"
                            class="edge-editor-input"
                        />
                    </div>
                    <div class="edge-editor-row" v-if="selectedEdge.trigger.type === 'interrupt'">
                        <label>Pin</label>
                        <code class="edge-editor-code">{{ selectedEdge.trigger.source }}</code>
                    </div>
                    <div class="edge-editor-actions">
                        <button class="btn btn-sm btn-danger" @click="deleteSelectedEdge">Remove</button>
                        <button class="btn btn-sm btn-primary" @click="applyTriggerEdit">Apply</button>
                    </div>
                </template>

                <!-- Signal editor -->
                <template v-if="selectedEdge.type === 'signal'">
                    <div class="edge-editor-row">
                        <label>Signal Name</label>
                        <input
                            v-model="editForm.signalName"
                            type="text"
                            placeholder="e.g. TEMP_READY"
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
                        <button class="btn btn-sm btn-primary" @click="applySignalEdit">Apply</button>
                    </div>
                </template>
            </div>
        </div>

        <!-- Legend -->
        <div class="graph-legend">
            <span class="legend-line legend-trigger">Trigger</span>
            <span class="legend-line legend-signal">Signal</span>
        </div>
    </div>
</template>

<style scoped>
.task-graph-panel { display: flex; flex-direction: column; }

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
.edge-editor-presets {
    display: flex;
    gap: 0.3rem;
    margin-bottom: 0.3rem;
    flex-wrap: wrap;
}
.ee-preset {
    font-size: 0.6rem;
    padding: 1px 5px;
    border: 1px solid var(--border);
    border-radius: 3px;
    background: var(--bg-input);
    color: var(--text-dim);
    cursor: pointer;
}
.ee-preset.active {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
}
.ee-preset:hover { border-color: var(--accent); }
.edge-editor-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.4rem;
    margin-top: 0.6rem;
    padding-top: 0.5rem;
    border-top: 1px solid var(--border);
}
</style>

<!-- Global styles for nodes (VueFlow portal) -->
<style>
.vf-task-node {
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
.vf-task-node:hover { border-color: var(--vue-flow-primary, #3b82f6); }
.vf-task-head { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.vf-task-name { font-size: 0.8rem; font-weight: 700; color: #e2e8f0; }
.vf-mode-badge {
    font-size: 0.5rem; font-weight: 700; text-transform: uppercase;
    border-radius: 3px; padding: 0 3px;
}
.vf-mode-loop { background: rgba(16,185,129,0.15); color: #34d399; }
.vf-mode-once { background: rgba(59,130,246,0.15); color: #60a5fa; }
.vf-task-meta { display: flex; gap: 4px; }
.vf-tag { font-size: 0.55rem; padding: 0 3px; border-radius: 2px; font-weight: 600; }
.vf-tag-prio { border: 1px solid; }
.vf-tag-stack { background: rgba(107,114,128,0.15); color: #9ca3af; }

.vf-source-node {
    background: #1a1f2e; border: 1px solid #2d3748; border-radius: 20px;
    padding: 6px 12px 6px 8px; display: flex; align-items: center; gap: 6px;
    font-family: 'Inter', sans-serif; cursor: grab;
    transition: border-color 0.15s; position: relative;
}
.vf-source-node:hover { border-color: #f59e0b; }
.vf-src-gpio { border-left: 3px solid #f59e0b; }
.vf-src-timer { border-left: 3px solid #3b82f6; }
.vf-src-rtc { border-left: 3px solid #10b981; }
.vf-src-badge {
    font-size: 0.5rem; font-weight: 700;
    background: rgba(245,158,11,0.2); color: #fbbf24;
    border-radius: 3px; padding: 0 3px; white-space: nowrap;
}
.vf-src-timer .vf-src-badge { background: rgba(59,130,246,0.2); color: #60a5fa; }
.vf-src-rtc .vf-src-badge { background: rgba(16,185,129,0.2); color: #34d399; }
.vf-src-name { font-size: 0.7rem; font-weight: 600; color: #e2e8f0; }
.vf-src-detail { font-size: 0.6rem; color: #8899aa; }

/* Vue Flow handles */
.vf-handle-custom {
    width: 10px !important;
    height: 10px !important;
    background: #3b82f6 !important;
    border: 2px solid #1e2433 !important;
    border-radius: 50% !important;
    cursor: crosshair !important;
    transition: transform 0.1s;
}
.vf-handle-custom:hover {
    transform: scale(1.4);
    background: #60a5fa !important;
}

/* Edge label */
.vue-flow__edge-textbg { fill: #1a1f2e; }
.vue-flow__edge-text { font-size: 0.55rem; font-weight: 600; fill: #8899aa; }

/* Selected edge highlight */
.vue-flow__edge.selected .vue-flow__edge-path {
    stroke: #60a5fa !important;
    stroke-width: 3 !important;
}

/* Background */
.vue-flow__background pattern circle { fill: #2d3748; }

/* Controls */
.vue-flow__controls-button {
    background: #1e2433 !important;
    border-color: #3b4a63 !important;
    color: #e2e8f0 !important;
    fill: #e2e8f0 !important;
}
.vue-flow__controls-button:hover { background: #2d3748 !important; }

.graph-legend {
    display: flex; gap: 1rem; justify-content: center; margin-top: 0.4rem;
}
.legend-line {
    font-size: 0.65rem; position: relative; padding-left: 18px;
}
.legend-line::before {
    content: ''; position: absolute; left: 0; top: 50%; width: 12px;
    height: 3px; border-radius: 2px; transform: translateY(-50%);
}
.legend-trigger::before { background: #f59e0b; }
.legend-signal::before {
    background: repeating-linear-gradient(90deg, #8b5cf6 0, #8b5cf6 4px, transparent 4px, transparent 6px);
}

/* Edge cursor */
.vue-flow__edge { cursor: pointer; }
.vue-flow__edge:hover .vue-flow__edge-path { stroke-width: 3 !important; }

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
