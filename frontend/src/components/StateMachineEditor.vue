<script setup lang="ts">
/**
 * StateMachineEditor.vue — Visual state machine editor using Vue Flow.
 *
 * Nodes: State (rounded rect with on_entry/on_exit actions).
 * Edges: Transition (arrow with event [guard] / actions label).
 *
 * Interactions:
 *   - Toolbar: Add State, Add Choice
 *   - Drag State → State to create Transition
 *   - Click node → bottom property panel
 *   - Click edge → edit event/guard/action inline
 *   - Delete / Backspace → remove selected node/edge
 */
import { ref, computed, watch, markRaw, onMounted, onUnmounted, type Component } from 'vue'
import {
    VueFlow, useVueFlow, Handle, MarkerType, Position,
    type Node, type Edge, type Connection,
} from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'

/* ---- Props / Emit ---- */
const props = defineProps<{
    /** Existing behavior model from task.yaml */
    behavior: {
        initial_state?: string
        states?: Record<string, unknown>[]
        events?: Record<string, unknown>[]
        variables?: { name: string; type: string; initial?: unknown; array?: number }[]
        types?: { name: string; struct?: unknown; enum?: unknown; union?: unknown; bitfield?: unknown }[]
    } | null
}>()

const emit = defineEmits<{
    (e: 'update-behavior', behavior: Record<string, unknown>): void
}>()

/* ---- Vue Flow instance ---- */
const {
    onConnect, addNodes, addEdges, removeNodes, removeEdges, getNodes, getEdges, fitView,
} = useVueFlow()

/* ---- Local state ---- */
interface StateData {
    label: string
    onEntry?: string
    onExit?: string
    isInitial?: boolean
}

interface TransitionData {
    event: string
    guard?: string
    actionsText?: string
}

const selectedNodeId = ref<string | null>(null)
const selectedEdgeId = ref<string | null>(null)
const nextStateIdx = ref(3)
const selectedStateData = ref<StateData>({ label: '', onEntry: '', onExit: '' })

/* ---- Priority/type colors reused ---- */
const STATE_COLOR = '#3b82f6'
const INITIAL_COLOR = '#10b981'
const EDGE_COLOR = '#8b5cf6'

/* ---- Build graph from behavior model ---- */
function buildGraph(): { nodes: Node[]; edges: Edge[] } {
    const nodes: Node[] = []
    const edges: Edge[] = []
    const states = props.behavior?.states as any[] ?? []
    const initial = props.behavior?.initial_state ?? (states.length > 0 ? states[0]?.name ?? '' : '')

    // Simple vertical layout
    const START_X = 150
    const START_Y = 60
    const GAP = 130

    states.forEach((s: any, i: number) => {
        nodes.push({
            id: `state-${i}`,
            type: 'state-node',
            position: { x: START_X + (i % 2) * 250, y: START_Y + Math.floor(i / 2) * GAP },
            data: {
                label: s.name ?? `State${i}`,
                onEntry: Array.isArray(s.on_entry) ? s.on_entry.join('\n') : '',
                onExit: Array.isArray(s.on_exit) ? s.on_exit.join('\n') : '',
                isInitial: s.name === initial,
            },
        })
    })

    // Build edges from the current hw2c schema:
    // states[].transitions[] = { event, target, guard, actions }
    states.forEach((s: any, fromIdx: number) => {
        const transitions = Array.isArray(s.transitions) ? s.transitions : []
        transitions.forEach((tr: any, edgeIdx: number) => {
            const toIdx = states.findIndex((candidate: any) => candidate.name === tr.target)
            if (toIdx < 0) return

            edges.push({
                id: `edge-${fromIdx}-${edgeIdx}`,
                source: `state-${fromIdx}`,
                target: `state-${toIdx}`,
                type: 'smoothstep',
                label: tr.event ?? '',
                animated: false,
                style: { stroke: EDGE_COLOR, strokeWidth: 2 },
                markerEnd: MarkerType.ArrowClosed,
                data: {
                    event: tr.event ?? '',
                    guard: tr.guard ?? '',
                    actionsText: Array.isArray(tr.actions) ? tr.actions.join('\n') : '',
                },
            })
        })
    })

    return { nodes, edges }
}

/* ---- Graph sync ---- */
const graphData = computed(() => buildGraph())

function syncGraph() {
    const { nodes, edges } = graphData.value
    const existingNodes = getNodes.value
    const existingEdges = getEdges.value
    if (existingNodes.length) removeNodes(existingNodes.map(n => n.id))
    if (existingEdges.length) removeEdges(existingEdges.map(e => e.id))
    if (nodes.length) addNodes(nodes)
    if (edges.length) addEdges(edges)
    setTimeout(() => fitView({ padding: 0.2 }), 100)
}

watch(() => props.behavior, syncGraph, { deep: true, immediate: true })

/* ---- Node click → select for editing ---- */
function handleNodeClick(node: Node) {
    selectedNodeId.value = node.id === selectedNodeId.value ? null : node.id
    selectedEdgeId.value = null
    const data = node.data as StateData
    if (node.id === selectedNodeId.value) {
        selectedStateData.value = { ...data }
    }
}

function handleEdgeClick(edge: Edge, _event: MouseEvent) {
    selectedEdgeId.value = edge.id === selectedEdgeId.value ? null : edge.id
    selectedNodeId.value = null
}

/* ---- Create new state node ---- */
function addState() {
    const nodes = getNodes.value
    const x = 150 + (nextStateIdx.value % 3) * 220
    const y = 300 + Math.floor(nextStateIdx.value / 3) * 120
    nodes.push({
        id: `state-new-${nextStateIdx.value}`,
        type: 'state-node',
        position: { x, y },
        data: {
            label: `State${nextStateIdx.value}`,
            onEntry: '',
            onExit: '',
            isInitial: nodes.length === 0,
        },
    })
    addNodes(nodes)
    nextStateIdx.value++
    emitCurrentModel()
}

/* ---- Connect → create transition ---- */
function handleConnect(connection: Connection) {
    const edges = getEdges.value
    edges.push({
        id: `edge-${Date.now()}`,
        source: connection.source!,
        target: connection.target!,
        type: 'smoothstep',
        label: 'event_name',
        animated: false,
        style: { stroke: EDGE_COLOR, strokeWidth: 2 },
        markerEnd: MarkerType.ArrowClosed,
        data: { event: '', guard: '', actionsText: '' },
    })
    addEdges(edges)
    emitCurrentModel()
}

/* ---- Emit model back to parent ---- */
function emitCurrentModel() {
    const nodes = getNodes.value
    const edges = getEdges.value

    const states = nodes
        .filter(n => n.type === 'state-node' || n.id.startsWith('state'))
        .map((n) => {
            const d = n.data as StateData
            return {
                name: d.label,
                on_entry: d.onEntry
                    ? d.onEntry.split('\n').map((line: string) => line.trim()).filter(Boolean)
                    : [],
                on_exit: d.onExit
                    ? d.onExit.split('\n').map((line: string) => line.trim()).filter(Boolean)
                    : [],
                transitions: [],
            }
        })

    const stateNameByNodeId = new Map(
        nodes
            .filter(n => n.type === 'state-node' || n.id.startsWith('state'))
            .map(n => [n.id, (n.data as StateData).label]),
    )

    for (const edge of edges) {
        const d = edge.data as TransitionData
        const fromName = stateNameByNodeId.get(edge.source)
        const toName = stateNameByNodeId.get(edge.target)
        if (!fromName || !toName) continue

        const sourceState = states.find(s => s.name === fromName)
        if (!sourceState) continue

        sourceState.transitions.push({
            event: d.event || 'unnamed',
            target: toName,
            guard: d.guard || undefined,
            actions: d.actionsText
                ? d.actionsText.split('\n').map((line: string) => line.trim()).filter(Boolean)
                : [],
        })
    }

    emit('update-behavior', {
        initial_state: states.length > 0 ? states[0].name : '',
        states,
        variables: props.behavior?.variables ?? [],
        types: props.behavior?.types ?? [],
    })
}

/* ---- Update selected state from form ---- */
function updateStateField(field: string, value: string) {
    if (!selectedNodeId.value) return
    const nodes = getNodes.value
    const node = nodes.find(n => n.id === selectedNodeId.value)
    if (!node) return
    ;(node.data as any)[field] = value
    addNodes([...nodes])
    emitCurrentModel()
}

function updateEdgeField(field: string, value: string) {
    if (!selectedEdgeId.value) return
    const edges = getEdges.value
    const edge = edges.find(e => e.id === selectedEdgeId.value)
    if (!edge) return
    ;(edge.data as any)[field] = value
    if (field === 'event') edge.label = value || 'event_name'
    addEdges([...edges])
    emitCurrentModel()
}

/* ---- Delete selected ---- */
function deleteSelected() {
    if (selectedNodeId.value) {
        removeNodes([selectedNodeId.value])
        selectedNodeId.value = null
        emitCurrentModel()
    } else if (selectedEdgeId.value) {
        removeEdges([selectedEdgeId.value])
        selectedEdgeId.value = null
        emitCurrentModel()
    }
}

/* ---- Keyboard ---- */
function onKeydown(e: KeyboardEvent) {
    if ((e.key === 'Delete' || e.key === 'Backspace') && (selectedNodeId.value || selectedEdgeId.value)) {
        e.preventDefault()
        deleteSelected()
    }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))

/* ---- Edge data for edit panel ---- */
const selectedEdgeData = computed(() => {
    if (!selectedEdgeId.value) return null
    const edge = getEdges.value.find(e => e.id === selectedEdgeId.value)
    return (edge?.data as TransitionData) ?? null
})

/* ---- Node types ---- */
const nodeTypes: Record<string, Component> = {
    'state-node': markRaw({
        props: ['data'],
        template: `
<div class="sm-state-node" :style="{ borderColor: data.isInitial ? '#10b981' : '#3b82f6' }">
  <div class="sm-state-icon" v-if="data.isInitial" style="background:#10b981;border-radius:50%;width:8px;height:8px;position:absolute;top:4px;left:4px;" title="Initial State"></div>
  <div class="sm-state-name">{{ data.label }}</div>
  <div class="sm-state-actions">
    <div v-if="data.onEntry" class="sm-action sm-entry" title="On Entry">E: {{ data.onEntry }}</div>
    <div v-if="data.onExit" class="sm-action sm-exit" title="On Exit">X: {{ data.onExit }}</div>
  </div>
  <Handle type="source" :position="Position.Right" />
  <Handle type="target" :position="Position.Left" />
  <Handle type="source" :position="Position.Bottom" />
  <Handle type="target" :position="Position.Top" />
</div>`,
    }),
}
</script>

<template>
    <div class="sm-panel">
        <!-- Toolbar -->
        <div class="sm-toolbar">
            <button class="btn btn-sm btn-primary" @click="addState">+ Add State</button>
            <button
                class="btn btn-sm btn-ghost"
                :disabled="!selectedNodeId && !selectedEdgeId"
                @click="deleteSelected"
            >Delete Selected</button>
            <span class="sm-hint">Drag handle to connect | Click to select | Delete key to remove</span>
        </div>

        <div class="sm-main">
            <!-- Graph area -->
            <div class="sm-graph" style="flex: 1; min-height: 0;">
                <VueFlow
                    :node-types="nodeTypes"
                    :default-edge-options="{ selectable: true, deletable: true }"
                    :fit-view-on-init="true"
                    :nodes-draggable="true"
                    :nodes-connectable="true"
                    @connect="handleConnect"
                    @node-click="(_evt: any, node: Node) => handleNodeClick(node)"
                    @edge-click="(_e: Edge, evt: MouseEvent) => handleEdgeClick(_e, evt)"
                    @pane-click="selectedNodeId = null; selectedEdgeId = null"
                    class="sm-flow"
                >
                    <Background variant="dots" :gap="24" :size="1" />
                    <Controls position="bottom-right" />

                    <!-- Custom node template -->
                    <template #node-state-node="nodeProps">
                        <div
                            class="sm-state-node"
                            :class="{ 'sm-selected': nodeProps.id === selectedNodeId }"
                            :style="{ borderColor: nodeProps.data.isInitial ? INITIAL_COLOR : STATE_COLOR }"
                        >
                            <div v-if="nodeProps.data.isInitial" class="sm-initial-dot" title="Initial State"></div>
                            <div class="sm-state-name">{{ nodeProps.data.label }}</div>
                            <div class="sm-state-actions">
                                <div v-if="nodeProps.data.onEntry" class="sm-action sm-entry" title="On Entry">E: {{ nodeProps.data.onEntry }}</div>
                                <div v-if="nodeProps.data.onExit" class="sm-action sm-exit" title="On Exit">X: {{ nodeProps.data.onExit }}</div>
                            </div>
                            <Handle type="source" :position="Position.Right" />
                            <Handle type="target" :position="Position.Left" />
                            <Handle type="source" :position="Position.Bottom" />
                            <Handle type="target" :position="Position.Top" />
                        </div>
                    </template>
                </VueFlow>
            </div>

            <!-- Property panel (right side) -->
            <div class="sm-properties" v-if="selectedNodeId || selectedEdgeId">
                <div class="sm-prop-title">
                    {{ selectedNodeId ? 'State Properties' : 'Transition Properties' }}
                    <button class="sm-close-btn" @click="selectedNodeId = null; selectedEdgeId = null">&times;</button>
                </div>

                <!-- State form -->
                <template v-if="selectedNodeId">
                    <label class="sm-label">
                        <span>Name</span>
                        <input
                            class="sm-input"
                            :value="selectedStateData.label"
                            @input="selectedStateData.label = ($event.target as HTMLInputElement).value; updateStateField('label', ($event.target as HTMLInputElement).value)"
                        />
                    </label>
                    <label class="sm-label">
                        <span>On Entry (one action per line)</span>
                        <textarea
                            class="sm-input"
                            :value="selectedStateData.onEntry ?? ''"
                            @input="selectedStateData.onEntry = ($event.target as HTMLTextAreaElement).value; updateStateField('onEntry', ($event.target as HTMLTextAreaElement).value)"
                            placeholder="e.g. set(led, on)"
                        ></textarea>
                    </label>
                    <label class="sm-label">
                        <span>On Exit (one action per line)</span>
                        <textarea
                            class="sm-input"
                            :value="selectedStateData.onExit ?? ''"
                            @input="selectedStateData.onExit = ($event.target as HTMLTextAreaElement).value; updateStateField('onExit', ($event.target as HTMLTextAreaElement).value)"
                            placeholder="e.g. set(led, off)"
                        ></textarea>
                    </label>
                </template>

                <!-- Edge form -->
                <template v-if="selectedEdgeId && selectedEdgeData">
                    <label class="sm-label">
                        <span>Event Name</span>
                        <input
                            class="sm-input"
                            :value="selectedEdgeData.event"
                            @input="updateEdgeField('event', ($event.target as HTMLInputElement).value)"
                            placeholder="e.g. BUTTON_PRESS"
                        />
                    </label>
                    <label class="sm-label">
                        <span>Guard (condition)</span>
                        <input
                            class="sm-input"
                            :value="selectedEdgeData.guard ?? ''"
                            @input="updateEdgeField('guard', ($event.target as HTMLInputElement).value)"
                            placeholder="e.g. count >= 3"
                        />
                    </label>
                    <label class="sm-label">
                        <span>Actions (one action per line)</span>
                        <textarea
                            class="sm-input"
                            :value="selectedEdgeData.actionsText ?? ''"
                            @input="updateEdgeField('actionsText', ($event.target as HTMLTextAreaElement).value)"
                            placeholder="e.g. publish(ALERT)"
                        ></textarea>
                    </label>
                </template>
            </div>
        </div>
    </div>
</template>

<style scoped>
.sm-panel {
    display: flex;
    flex-direction: column;
    height: 100%;
    gap: 0.5rem;
}

.sm-toolbar {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid var(--border);
}
.sm-hint {
    font-size: 0.6rem;
    color: var(--text-dim);
    margin-left: auto;
}

.sm-main {
    display: flex;
    gap: 0.5rem;
    flex: 1;
    min-height: 0;
}

.sm-graph {
    flex: 1;
    min-height: 400px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    background: var(--bg-card);
}

/* State node styles */
.sm-state-node {
    position: relative;
    padding: 10px 14px;
    background: #1a1f2e;
    border: 2px solid;
    border-radius: 10px;
    min-width: 140px;
    text-align: center;
}
.sm-state-node.sm-selected {
    box-shadow: 0 0 0 3px rgba(59,130,246,0.3);
}
.sm-initial-dot {
    position: absolute;
    top: 6px;
    left: 6px;
    width: 8px;
    height: 8px;
    background: #10b981;
    border-radius: 50%;
}
.sm-state-name {
    font-size: 0.85rem;
    font-weight: 700;
    color: #e2e8f0;
}
.sm-state-actions {
    display: flex;
    flex-direction: column;
    gap: 2px;
    margin-top: 4px;
}
.sm-action {
    font-size: 0.55rem;
    padding: 1px 4px;
    border-radius: 2px;
    text-align: left;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 130px;
}
.sm-entry { background: rgba(16,185,129,0.12); color: #34d399; }
.sm-do { background: rgba(59,130,246,0.12); color: #60a5fa; }
.sm-exit { background: rgba(239,68,68,0.1); color: #f87171; }

/* Properties panel */
.sm-properties {
    width: 220px;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding: 0.75rem;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow-y: auto;
}
.sm-prop-title {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.75rem;
    font-weight: 700;
    color: var(--accent);
}
.sm-close-btn {
    border: none;
    background: transparent;
    color: var(--text-dim);
    font-size: 1rem;
    cursor: pointer;
}
.sm-close-btn:hover { color: var(--text); }

.sm-label {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    font-size: 0.65rem;
    color: var(--text-dim);
}
.sm-input {
    padding: 5px 8px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg-input);
    color: var(--text);
    font-size: 0.75rem;
}
.sm-input:is(textarea) {
    min-height: 64px;
    resize: vertical;
    font-family: monospace;
}
.sm-input:focus {
    outline: none;
    border-color: var(--accent);
}
</style>
