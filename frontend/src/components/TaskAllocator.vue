<script setup lang="ts">
/**
 * TaskAllocator.vue — FreeRTOS task configuration.
 *
 * Simplified: triggers/signals moved to bind.yaml (BindGraph tab).
 * Pure task definitions only: name, priority, stack size.
 */
import { ref, computed } from 'vue'
import type { AppTaskModel } from '../composables/useTaskModel'
import type { PinModel } from '../composables/useHardwareModel'

const props = defineProps<{
    tasks: AppTaskModel[]
    pins?: PinModel[]
    /** Peripheral names for task name suggestions */
    peripheralNames?: string[]
}>()

const emit = defineEmits<{
    (e: 'add-task', task: AppTaskModel): void
    (e: 'remove-task', index: number): void
    (e: 'update-task', index: number, field: string, value: unknown): void
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
</script>

<template>
    <div class="panel task-panel">
        <div class="panel-title-row">
            <span class="panel-title">Tasks ({{ tasks.length }})</span>
            <button class="btn-add" @click="showForm = !showForm">
                {{ showForm ? 'Cancel' : '+ Add' }}
            </button>
        </div>

        <!-- Add form -->
        <div v-if="showForm" class="add-form">
            <input
                v-model="newName"
                type="text"
                placeholder="Task name (e.g. sensor_read)"
                class="input"
                @keyup.enter="handleAdd"
            />

            <div class="form-row">
                <label class="form-label">
                    Priority: <strong>{{ priorityLabel(newPriority) }}</strong>
                </label>
                <input
                    v-model.number="newPriority"
                    type="range"
                    min="1" max="5" step="1"
                    class="slider"
                />
            </div>

            <div class="form-row">
                <label class="form-label">
                    Stack: <strong>{{ newStack }} B</strong>
                </label>
                <input
                    v-model.number="newStack"
                    type="range"
                    min="128" max="4096" step="128"
                    class="slider"
                />
            </div>

            <button class="btn btn-primary btn-confirm" @click="handleAdd">Add Task</button>
        </div>

        <!-- Task list -->
        <div class="task-list" v-if="tasks.length">
            <div
                v-for="(task, idx) in tasks"
                :key="idx"
                class="task-item"
            >
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
                        >
                            {{ priorityLabel(task.priority) }}
                        </span>
                        <span class="tag tag-stack">{{ task.stack_size }} B</span>
                    </div>
                </div>

                <!-- Actions -->
                <div class="task-actions">
                    <select
                        class="select-mini"
                        :value="task.priority"
                        @change="emit('update-task', idx, 'priority', Number(($event.target as HTMLSelectElement).value))"
                    >
                        <option v-for="p in 5" :key="p" :value="p">P{{ p }}</option>
                    </select>

                    <select
                        class="select-mini"
                        :value="task.stack_size"
                        @change="emit('update-task', idx, 'stack_size', Number(($event.target as HTMLSelectElement).value))"
                    >
                        <option :value="128">128 B</option>
                        <option :value="256">256 B</option>
                        <option :value="512">512 B</option>
                        <option :value="1024">1 KB</option>
                        <option :value="2048">2 KB</option>
                        <option :value="4096">4 KB</option>
                    </select>

                    <button class="btn-mini btn-remove" @click="emit('remove-task', idx)">Remove</button>
                </div>
            </div>
        </div>

        <!-- Suggested tasks -->
        <div v-if="suggestedNames.length && tasks.length === 0" class="suggested">
            <div class="suggested-title">Suggested from peripherals:</div>
            <div class="suggested-chips">
                <span
                    v-for="name in suggestedNames"
                    :key="name"
                    class="suggested-chip"
                    @click="newName = name; showForm = true"
                >
                    + {{ name }}
                </span>
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
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.panel-title-row .panel-title { margin-bottom: 0; }

.btn-add {
    padding: 2px 10px;
    border: 1px solid var(--accent);
    border-radius: 4px;
    background: transparent;
    color: var(--accent);
    cursor: pointer;
    font-size: 0.75rem;
    font-weight: 600;
    transition: all 0.15s;
}
.btn-add:hover { background: var(--accent); color: #fff; }

/* Add form */
.add-form {
    display: flex; flex-direction: column; gap: 0.5rem;
    padding: 0.75rem; background: var(--bg-input);
    border-radius: var(--radius);
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
    border: 1px solid var(--border);
    transition: border-color 0.15s;
}
.task-item:hover { border-color: var(--accent); }

/* Task head */
.task-head { display: flex; flex-direction: column; gap: 0.25rem; }
.task-name-row { display: flex; align-items: center; gap: 0.4rem; }
.task-name {
    font-size: 0.8rem; font-weight: 600; cursor: default;
}
.task-name:hover { color: var(--accent); }

.task-meta { display: flex; gap: 0.35rem; }

.tag-prio {
    border: 1px solid; border-radius: 3px;
    padding: 0 4px; font-size: 0.6rem; font-weight: 600;
}
.tag-stack {
    padding: 0 4px; border-radius: 3px; font-size: 0.6rem;
    background: rgba(107,114,128,0.15); color: #9ca3af;
}

/* Actions row */
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
    font-size: 0.6rem; font-weight: 600;
    white-space: nowrap;
}
.btn-mini:hover { border-color: var(--text-dim); color: var(--text); }
.btn-remove { color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-remove:hover { background: rgba(239,68,68,0.1); color: #f87171; }

/* Suggestions */
.suggested { padding: 0.5rem 0; }
.suggested-title { font-size: 0.7rem; color: var(--text-dim); margin-bottom: 0.35rem; }
.suggested-chips { display: flex; flex-wrap: wrap; gap: 0.35rem; }
.suggested-chip {
    display: inline-block; padding: 2px 8px;
    border-radius: 99px; font-size: 0.7rem;
    background: rgba(59,130,246,0.1); color: #60a5fa;
    border: 1px dashed rgba(59,130,246,0.3);
    cursor: pointer; transition: all 0.15s;
}
.suggested-chip:hover {
    background: var(--accent); color: #fff;
    border-style: solid;
}

.empty { color: var(--text-dim); font-size: 0.75rem; text-align: center; padding: 0.5rem; }
</style>
