<script setup lang="ts">
/**
 * TaskGraph.vue — Visual task overview (pure task definitions).
 *
 * Simplified: triggers/signals moved to bind.yaml (BindGraph).
 * Shows task nodes in a flow layout with name, priority badge, and stack size.
 * Double-click a node to rename the task.
 */
import { computed, ref, watch, markRaw, type Component } from 'vue'
import { VueFlow, useVueFlow, type Node, type Edge } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import type { AppTaskModel } from '../composables/useTaskModel'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'

const props = defineProps<{
    tasks: AppTaskModel[]
    pins: { id: string }[]
    hasRtc?: boolean
}>()

const emit = defineEmits<{
    (e: 'update-task', index: number, field: string, value: unknown): void
}>()

/* ---- Vue Flow instance ---- */
const { addNodes, getNodes, removeNodes, fitView } = useVueFlow()

/* ---- Rename state ---- */
const renamingIdx = ref(-1)
const renameInput = ref('')

/* ---- Priority color ---- */
function prioColor(p: number): string {
    const m: Record<number, string> = { 1: '#6b7280', 2: '#3b82f6', 3: '#10b981', 4: '#f59e0b', 5: '#ef4444' }
    return m[p] ?? '#10b981'
}

/* ---- Build task-only nodes ---- */
function buildGraph(): { nodes: Node[]; edges: Edge[] } {
    const nodes: Node[] = []
    const TASK_X = 100
    const TASK_START_Y = 40
    const TASK_GAP = 100

    props.tasks.forEach((task, i) => {
        nodes.push({
            id: `task-${i}`,
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

    return { nodes, edges: [] }
}

/* ---- Sync ---- */
const graphData = computed(() => buildGraph())

function syncGraph() {
    const { nodes } = graphData.value
    const existingNodes = getNodes.value
    if (existingNodes.length) removeNodes(existingNodes.map(n => n.id))
    if (nodes.length) addNodes(nodes)
    setTimeout(() => fitView({ padding: 0.15 }), 100)
}

watch(() => props.tasks, syncGraph, { deep: true, immediate: true })

/* ---- Double-click to rename ---- */
function handleNodeDoubleClick(node: Node) {
    const idx = (node.data as any).taskIndex
    if (idx != null && props.tasks[idx]) {
        renamingIdx.value = idx
        renameInput.value = props.tasks[idx].name
        // Focus input via next tick
        requestAnimationFrame(() => {
            const input = document.querySelector('.task-rename-input') as HTMLInputElement
            input?.focus()
            input?.select()
        })
    }
}

function applyRename() {
    if (renamingIdx.value >= 0 && renameInput.value.trim()) {
        emit('update-task', renamingIdx.value, 'name', renameInput.value.trim())
    }
    renamingIdx.value = -1
}

function cancelRename() {
    renamingIdx.value = -1
}

function onRenameKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') applyRename()
    if (e.key === 'Escape') cancelRename()
}

/* ---- Node types ---- */
const nodeTypes: Record<string, Component> = {
    'task-node': markRaw({
        props: ['data'],
        template: `
<div class="vf-task-node">
  <div class="vf-task-head">
    <span class="vf-task-name">{{ data.label }}</span>
  </div>
  <div class="vf-task-meta">
    <span class="vf-tag vf-tag-prio" :style="{ background: data.prioColor + '22', color: data.prioColor }">P{{ data.priority }}</span>
    <span class="vf-tag vf-tag-stack">{{ data.stack }}B</span>
  </div>
</div>`,
    }),
}
</script>

<template>
    <div class="task-graph-panel panel">
        <div class="panel-title">
            Task Overview
            <span class="graph-hint">Double-click task to rename</span>
        </div>

        <div class="graph-container" style="position: relative;">
            <VueFlow
                :node-types="nodeTypes"
                :default-edge-options="{ selectable: false, deletable: false }"
                :fit-view-on-init="true"
                :nodes-draggable="true"
                :nodes-connectable="false"
                :edges-updatable="false"
                :elements-selectable="false"
                @node-double-click="handleNodeDoubleClick"
                @pane-click="cancelRename"
                class="task-flow"
            >
                <Background variant="dots" :gap="20" :size="1" />
                <Controls position="bottom-right" />

                <template #node-task-node="nodeProps">
                    <div class="vf-task-node" style="position: relative;">
                        <div class="vf-task-head">
                            <span class="vf-task-name">{{ nodeProps.data.label }}</span>
                        </div>
                        <div class="vf-task-meta">
                            <span class="vf-tag vf-tag-prio" :style="{ background: nodeProps.data.prioColor + '22', color: nodeProps.data.prioColor, borderColor: nodeProps.data.prioColor }">P{{ nodeProps.data.priority }}</span>
                            <span class="vf-tag vf-tag-stack">{{ nodeProps.data.stack }}B</span>
                        </div>
                    </div>
                </template>
            </VueFlow>
        </div>

        <!-- Rename modal -->
        <div v-if="renamingIdx >= 0" class="rename-modal" @click.stop>
            <div class="rename-modal-card">
                <div class="rename-modal-title">Rename Task</div>
                <input
                    v-model="renameInput"
                    class="task-rename-input"
                    @keydown="onRenameKeydown"
                    placeholder="Task name"
                />
                <div class="rename-modal-actions">
                    <button class="btn btn-sm btn-ghost" @click="cancelRename">Cancel</button>
                    <button class="btn btn-sm btn-primary" @click="applyRename">OK</button>
                </div>
            </div>
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

.graph-container {
    height: 400px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    background: var(--bg-card);
}

.rename-modal {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1rem;
}
.rename-modal-card {
    background: #1a1f2e;
    border: 1px solid var(--accent);
    border-radius: 8px;
    padding: 1rem;
    width: 260px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.5);
}
.rename-modal-title {
    font-size: 0.75rem;
    font-weight: 700;
    color: var(--accent);
    margin-bottom: 0.5rem;
}
.task-rename-input {
    width: 100%;
    padding: 6px 10px;
    background: var(--bg-input);
    border: 1px solid var(--border);
    border-radius: 4px;
    color: var(--text);
    font-size: 0.8rem;
    font-family: inherit;
    margin-bottom: 0.6rem;
}
.task-rename-input:focus {
    border-color: var(--accent);
    outline: none;
}
.rename-modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.4rem;
}

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
.btn-ghost {
    background: transparent;
    color: var(--text-dim);
    border: 1px solid var(--border);
}
.btn-ghost:hover { border-color: var(--accent); color: var(--text); }
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
}
.vf-task-node:hover { border-color: var(--vue-flow-primary, #3b82f6); }
.vf-task-head { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.vf-task-name { font-size: 0.8rem; font-weight: 700; color: #e2e8f0; }
.vf-task-meta { display: flex; gap: 4px; }
.vf-tag { font-size: 0.55rem; padding: 0 3px; border-radius: 2px; font-weight: 600; }
.vf-tag-prio { border: 1px solid; }
.vf-tag-stack { background: rgba(107,114,128,0.15); color: #9ca3af; }

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
</style>
