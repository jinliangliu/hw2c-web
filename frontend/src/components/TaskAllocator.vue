<script setup lang="ts">
/**
 * TaskAllocator.vue — FreeRTOS task configuration.
 *
 * Task definition matches hw2c task.yaml app_tasks: name, priority, stack_size.
 * Global event_task dispatcher configuration with queue depth.
 */
import { ref, computed } from 'vue'
import type { AppTaskModel, EventTaskConfig } from '../composables/useTaskModel'
import type { PinModel } from '../composables/useHardwareModel'

const props = defineProps<{
    tasks: AppTaskModel[]
    pins?: PinModel[]
    /** Peripheral names for task name suggestions */
    peripheralNames?: string[]
    /** FreeRTOS heap size in bytes */
    heapSize: number
    /** Global event dispatcher task config */
    eventTask: EventTaskConfig
}>()

const emit = defineEmits<{
    (e: 'add-task', task: AppTaskModel): void
    (e: 'remove-task', index: number): void
    (e: 'update-task', index: number, field: string, value: unknown): void
    (e: 'update-heap', size: number): void
    (e: 'update-event-task', partial: Record<string, unknown>): void
}>()

/* ---- New task form ---- */
const showForm = ref(false)
const newName = ref('')
const newPriority = ref(3)
const newStack = ref(512)

function resetForm() {
    newName.value = ''
    newPriority.value = 3
    newStack.value = 512
}

function handleAdd() {
    if (!newName.value.trim()) return
    emit('add-task', {
        name: newName.value.trim(),
        priority: newPriority.value,
        stack_size: newStack.value,
    })
    resetForm()
    showForm.value = false
}

/* ---- Suggested names ---- */
const suggestedNames = computed(() => {
    if (!props.peripheralNames?.length) return []
    const existing = new Set(props.tasks.map(t => t.name))
    return props.peripheralNames.filter(n => !existing.has(n))
})

/* ---- Format helpers ---- */
function priorityLabel(p: number): string {
    const labels: Record<number, string> = { 1: 'Idle', 2: 'Low', 3: 'Normal', 4: 'High', 5: 'Critical' }
    return labels[p] ?? 'Normal'
}

function priorityColor(p: number): string {
    const colors: Record<number, string> = { 1: '#6b7280', 2: '#3b82f6', 3: '#10b981', 4: '#f59e0b', 5: '#ef4444' }
    return colors[p] ?? '#10b981'
}

/* ---- Inline editing state per task ---- */
const editingName = ref<number | null>(null)
const editNameValue = ref('')

function startRename(idx: number, name: string) {
    editingName.value = idx
    editNameValue.value = name
}

function commitRename(idx: number) {
    if (editNameValue.value.trim()) {
        emit('update-task', idx, 'name', editNameValue.value.trim())
    }
    editingName.value = null
}

function cancelRename() {
    editingName.value = null
}

/* ---- Heap size ---- */
function fmtHeap(size: number): string {
    return size >= 1024 ? (size / 1024).toFixed(0) + ' KB' : size + ' B'
}

const HEAP_PRESETS = [4096, 8192, 16384, 24576, 32768, 65536]

const showHeapCustom = ref(false)
const customHeap = ref(props.heapSize)

function setHeap(size: number) {
    emit('update-heap', size)
    showHeapCustom.value = false
}

function applyCustomHeap() {
    if (customHeap.value >= 256) {
        emit('update-heap', customHeap.value)
    }
    showHeapCustom.value = false
}

/** Emit a single event_task field change */
function updateEventField(field: string, value: unknown) {
    emit('update-event-task', { [field]: value })
}
</script>

<template>
    <div class="panel task-panel">
        <div class="panel-title-row">
            <span class="panel-title">Tasks ({{ tasks.length }})</span>
            <button class="btn-add" @click="showForm = !showForm">
                {{ showForm ? 'Cancel' : '+ Add' }}
            </button>
        </div>

        <!-- Heap configuration -->
        <div class="heap-row">
            <span class="heap-label">FreeRTOS Heap:</span>
            <div class="heap-presets">
                <button
                    v-for="sz in HEAP_PRESETS"
                    :key="sz"
                    :class="['heap-chip', { active: heapSize === sz }]"
                    @click="setHeap(sz)"
                >{{ fmtHeap(sz) }}</button>
            </div>
            <div class="heap-custom" v-if="showHeapCustom">
                <input
                    v-model.number="customHeap"
                    type="number"
                    min="256"
                    step="256"
                    class="heap-input"
                    @keyup.enter="applyCustomHeap"
                />
                <button class="heap-apply" @click="applyCustomHeap">OK</button>
            </div>
            <button
                v-if="!showHeapCustom"
                class="heap-custom-btn"
                @click="customHeap = heapSize; showHeapCustom = true"
            >Custom</button>
        </div>

        <!-- Event Task (global dispatcher) -->
        <div class="event-task-card">
            <div class="event-task-header">
                <span class="event-task-icon">&#9889;</span>
                <span class="event-task-title">Event Task (Queue Dispatcher)</span>
            </div>
            <div class="event-task-body">
                <div class="event-field">
                    <label class="event-label">Name</label>
                    <input
                        class="input input-sm"
                        :value="eventTask.name"
                        @change="updateEventField('name', ($event.target as HTMLInputElement).value)"
                    />
                </div>
                <div class="event-field">
                    <label class="event-label">Entry</label>
                    <input
                        class="input input-sm"
                        :value="eventTask.entry"
                        @change="updateEventField('entry', ($event.target as HTMLInputElement).value)"
                    />
                </div>
                <div class="event-field">
                    <label class="event-label">Priority</label>
                    <select
                        class="select-mini"
                        :value="eventTask.priority"
                        @change="updateEventField('priority', Number(($event.target as HTMLSelectElement).value))"
                    >
                        <option v-for="p in 5" :key="p" :value="p">P{{ p }}</option>
                    </select>
                </div>
                <div class="event-field">
                    <label class="event-label">Stack</label>
                    <select
                        class="select-mini"
                        :value="eventTask.stack_size"
                        @change="updateEventField('stack_size', Number(($event.target as HTMLSelectElement).value))"
                    >
                        <option :value="256">256B</option>
                        <option :value="512">512B</option>
                        <option :value="1024">1KB</option>
                        <option :value="2048">2KB</option>
                        <option :value="4096">4KB</option>
                    </select>
                </div>
                <div class="event-field">
                    <label class="event-label">Queue Depth</label>
                    <input
                        class="input input-sm input-num"
                        type="number"
                        min="4"
                        max="256"
                        step="4"
                        :value="eventTask.queue_depth"
                        @change="updateEventField('queue_depth', Number(($event.target as HTMLInputElement).value))"
                    />
                </div>
            </div>
        </div>

        <!-- Add form -->
        <div v-if="showForm" class="add-form">
            <input
                v-model="newName"
                type="text"
                placeholder="Task name (e.g. sensor_read)"
                class="input"
                @keyup.enter="showForm && handleAdd()"
            />

            <div class="form-row">
                <label class="form-label">
                    Priority: <strong>{{ priorityLabel(newPriority) }}</strong>
                </label>
                <input v-model.number="newPriority" type="range" min="1" max="5" step="1" class="slider" />
            </div>

            <div class="form-row">
                <label class="form-label">
                    Stack: <strong>{{ newStack }} B</strong>
                </label>
                <input v-model.number="newStack" type="range" min="128" max="4096" step="128" class="slider" />
            </div>

            <button class="btn btn-primary btn-confirm" @click="handleAdd">Add Task</button>
        </div>

        <!-- Task list -->
        <div class="task-list" v-if="tasks.length">
            <div v-for="(task, idx) in tasks" :key="idx" class="task-item">
                <div class="task-head">
                    <div class="task-name-row">
                        <template v-if="editingName === idx">
                            <input
                                v-model="editNameValue"
                                class="input-inline"
                                @keyup.enter="commitRename(idx)"
                                @keyup.escape="cancelRename"
                                @blur="commitRename(idx)"
                            />
                        </template>
                        <template v-else>
                            <span class="task-name" @dblclick="startRename(idx, task.name)">{{ task.name }}</span>
                        </template>
                    </div>

                    <div class="task-meta">
                        <span
                            class="tag tag-prio"
                            :style="{ background: priorityColor(task.priority) + '22', color: priorityColor(task.priority), borderColor: priorityColor(task.priority) }"
                        >{{ priorityLabel(task.priority) }}</span>
                        <span class="tag tag-stack">{{ task.stack_size }} B</span>
                    </div>
                </div>

                <!-- Actions -->
                <div class="task-actions">
                    <select class="select-mini" :value="task.priority"
                        @change="emit('update-task', idx, 'priority', Number(($event.target as HTMLSelectElement).value))">
                        <option v-for="p in 5" :key="p" :value="p">P{{ p }}</option>
                    </select>

                    <select class="select-mini" :value="task.stack_size"
                        @change="emit('update-task', idx, 'stack_size', Number(($event.target as HTMLSelectElement).value))">
                        <option :value="128">128B</option>
                        <option :value="256">256B</option>
                        <option :value="512">512B</option>
                        <option :value="1024">1KB</option>
                        <option :value="2048">2KB</option>
                        <option :value="4096">4KB</option>
                    </select>

                    <button class="btn-mini btn-remove" @click="emit('remove-task', idx)">Remove</button>
                </div>
            </div>
        </div>

        <!-- Suggested tasks -->
        <div v-if="suggestedNames.length && tasks.length === 0" class="suggested">
            <div class="suggested-title">Suggested from peripherals:</div>
            <div class="suggested-chips">
                <span v-for="name in suggestedNames" :key="name"
                    class="suggested-chip" @click="newName = name; showForm = true">+ {{ name }}</span>
            </div>
        </div>

        <p v-if="!tasks.length && !suggestedNames.length" class="empty">
            No tasks configured. Tasks are auto-suggested from peripherals. Switch to Bind tab to wire hardware to tasks.
        </p>
    </div>
</template>

<style scoped>
.task-panel { display: flex; flex-direction: column; gap: 0.5rem; }

.panel-title-row {
    display: flex; justify-content: space-between; align-items: center;
}
.panel-title-row .panel-title { margin-bottom: 0; }

.btn-add {
    padding: 2px 10px; border: 1px solid var(--accent); border-radius: 4px;
    background: transparent; color: var(--accent); cursor: pointer;
    font-size: 0.75rem; font-weight: 600; transition: all 0.15s;
}
.btn-add:hover { background: var(--accent); color: #fff; }

.add-form {
    display: flex; flex-direction: column; gap: 0.5rem;
    padding: 0.75rem; background: var(--bg-input); border-radius: var(--radius);
}
.input {
    width: 100%; padding: 0.4rem 0.6rem;
    border: 1px solid var(--border); border-radius: 4px;
    background: var(--bg-card); color: var(--text); font-size: 0.8rem;
}
.input:focus { outline: none; border-color: var(--accent); }

.form-row { display: flex; flex-direction: column; gap: 0.25rem; }
.form-label { font-size: 0.7rem; color: var(--text-dim); }
.form-label strong { color: var(--text); margin-left: 0.25rem; }
.slider { width: 100%; accent-color: var(--accent); cursor: pointer; }

.toggle-row {
    display: flex; flex-direction: row; align-items: center; gap: 0.5rem;
}
.toggle-row input[type="checkbox"] { accent-color: var(--accent); }

.btn-confirm {
    align-self: stretch; text-align: center;
    justify-content: center; font-weight: 600;
    font-size: 0.8rem; padding: 0.35rem;
}

/* Task items */
.task-list { display: flex; flex-direction: column; gap: 0.4rem; }
.task-item {
    display: flex; flex-direction: column;
    padding: 0.5rem 0.6rem;
    background: var(--bg-input); border-radius: 6px;
    border: 1px solid var(--border); transition: border-color 0.15s;
}
.task-item:hover { border-color: var(--accent); }

.task-head { display: flex; flex-direction: column; gap: 0.25rem; }
.task-name-row { display: flex; align-items: center; gap: 0.4rem; }
.task-name { font-size: 0.8rem; font-weight: 600; cursor: default; }
.task-name:hover { color: var(--accent); }

.task-meta { display: flex; gap: 0.35rem; flex-wrap: wrap; }
.task-sub {
    display: flex; align-items: center; gap: 0.5rem; margin-top: 2px;
}
.task-entry {
    font-size: 0.65rem; background: var(--bg-card); padding: 1px 4px;
    border-radius: 3px; color: var(--text-dim);
}
.task-period {
    font-size: 0.6rem; color: #06b6d4;
}

.tag-prio { border: 1px solid; border-radius: 3px; padding: 0 4px; font-size: 0.6rem; font-weight: 600; }
.tag-stack { padding: 0 4px; border-radius: 3px; font-size: 0.6rem; background: rgba(107,114,128,0.15); color: #9ca3af; }
.tag-type { border: 1px solid; border-radius: 3px; padding: 0 4px; font-size: 0.6rem; font-weight: 600; }

.task-actions {
    display: flex; align-items: center; gap: 0.3rem;
    margin-top: 0.35rem; padding-top: 0.35rem;
    border-top: 1px solid rgba(255,255,255,0.05);
}

.select-mini {
    padding: 1px 3px; border: 1px solid var(--border);
    border-radius: 3px; background: var(--bg-card);
    color: var(--text); font-size: 0.6rem; cursor: pointer;
}

.input-inline {
    padding: 1px 4px; border: 1px solid var(--border);
    border-radius: 3px; background: var(--bg-card);
    color: var(--text); font-size: 0.65rem; width: 120px;
}
.input-inline:focus { outline: none; border-color: var(--accent); }

.btn-mini {
    padding: 1px 6px; border: 1px solid var(--border);
    border-radius: 3px; background: var(--bg-card);
    color: var(--text-dim); cursor: pointer;
    font-size: 0.6rem; font-weight: 600; white-space: nowrap;
}
.btn-mini:hover { border-color: var(--text-dim); color: var(--text); }
.btn-remove { color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-remove:hover { background: rgba(239,68,68,0.1); color: #f87171; }

/* ---- Global Event Task card ---- */
.event-task-card {
    padding: 0.5rem 0.6rem;
    background: linear-gradient(135deg, rgba(245,158,11,0.08), rgba(245,158,11,0.02));
    border: 1px solid rgba(245,158,11,0.25);
    border-radius: var(--radius);
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
}
.event-task-header {
    display: flex;
    align-items: center;
    gap: 0.3rem;
}
.event-task-icon {
    font-size: 0.75rem;
    color: #f59e0b;
}
.event-task-title {
    font-size: 0.65rem;
    font-weight: 700;
    color: #f59e0b;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}
.event-task-body {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    align-items: flex-end;
}
.event-field {
    display: flex;
    flex-direction: column;
    gap: 2px;
}
.event-label {
    font-size: 0.55rem;
    font-weight: 600;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.2px;
}
.input-sm {
    font-size: 0.65rem;
    padding: 2px 5px;
    width: 100px;
}
.input-num {
    width: 64px;
    font-family: monospace;
    text-align: center;
}

.suggested { padding: 0.5rem 0; }
.suggested-title { font-size: 0.7rem; color: var(--text-dim); margin-bottom: 0.35rem; }
.suggested-chips { display: flex; flex-wrap: wrap; gap: 0.35rem; }
.suggested-chip {
    display: inline-block; padding: 2px 8px; border-radius: 99px; font-size: 0.7rem;
    background: rgba(59,130,246,0.1); color: #60a5fa;
    border: 1px dashed rgba(59,130,246,0.3);
    cursor: pointer; transition: all 0.15s;
}
.suggested-chip:hover { background: var(--accent); color: #fff; border-style: solid; }

.empty { color: var(--text-dim); font-size: 0.75rem; text-align: center; padding: 0.5rem; }

/* ---- Heap config ---- */
.heap-row {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.35rem;
    padding: 0.45rem 0.6rem;
    background: var(--bg-input);
    border-radius: var(--radius);
}
.heap-label {
    font-size: 0.65rem;
    font-weight: 600;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.3px;
    white-space: nowrap;
}
.heap-presets {
    display: flex;
    gap: 0.2rem;
    flex-wrap: wrap;
}
.heap-chip {
    padding: 1px 7px;
    border: 1px solid var(--border);
    border-radius: 99px;
    background: var(--bg-card);
    color: var(--text-dim);
    font-size: 0.62rem;
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
}
.heap-chip:hover { border-color: var(--accent); color: var(--text); }
.heap-chip.active {
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
    font-weight: 600;
}
.heap-custom {
    display: flex;
    gap: 2px;
    align-items: center;
}
.heap-input {
    width: 60px;
    padding: 2px 4px;
    border: 1px solid var(--accent);
    border-radius: 3px;
    background: var(--bg-card);
    color: var(--text);
    font-size: 0.65rem;
    font-family: monospace;
    text-align: center;
}
.heap-input:focus { outline: none; }
.heap-apply {
    padding: 2px 6px;
    border: none;
    border-radius: 3px;
    background: var(--accent);
    color: #fff;
    font-size: 0.6rem;
    font-weight: 600;
    cursor: pointer;
}
.heap-custom-btn {
    padding: 1px 6px;
    border: 1px dashed var(--border);
    border-radius: 99px;
    background: transparent;
    color: var(--text-dim);
    font-size: 0.6rem;
    cursor: pointer;
    transition: all 0.15s;
}
.heap-custom-btn:hover { border-color: var(--accent); color: var(--accent); }
</style>
