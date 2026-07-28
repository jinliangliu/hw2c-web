<script setup lang="ts">
/**
 * TaskAllocator.vue — FreeRTOS task configuration with triggers & signals.
 *
 * Features:
 *   - Rename tasks inline
 *   - Run mode: once (single-shot) or loop (continuous)
 *   - Triggers: timer/periodic, event/semaphore, interrupt (EXTI pin)
 *   - Signals: named events/semaphores with optional target task
 *   - Priority & stack size configuration
 */
import { ref, computed } from 'vue'
import type { AppTaskModel, TaskTrigger, TaskSignal, PinModel } from '../composables/useHardwareModel'

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

/* ---- Available EXTI pins for interrupt triggers ---- */
const extiPins = computed(() => {
    if (!props.pins) return []
    return props.pins
        .filter(p => p.exti || p.function === 'GPIO_Input')
        .map(p => p.id)
})

/* ---- New task form ---- */
const showForm = ref(false)
const newName = ref('')
const newPriority = ref(3)
const newStack = ref(512)
const newRunMode = ref<'once' | 'loop'>('loop')

function resetForm() {
    newName.value = ''
    newPriority.value = 3
    newStack.value = 512
    newRunMode.value = 'loop'
}

function handleAdd() {
    if (!newName.value.trim()) return
    emit('add-task', {
        name: newName.value.trim(),
        priority: newPriority.value,
        stack_size: newStack.value,
        run_mode: newRunMode.value,
        triggers: [],
        signals: [],
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

function triggerIcon(t: TaskTrigger): string {
    switch (t.type) {
        case 'timer': return '\u23F0'       // ⏰
        case 'event': return '\u26A1'       // ⚡
        case 'interrupt': return '\u26A0'   // ⚠
        default: return ''
    }
}

function triggerLabel(t: TaskTrigger): string {
    switch (t.type) {
        case 'timer': return t.period_ms ? `${t.period_ms}ms` : 'timer'
        case 'event': return t.source || 'event'
        case 'interrupt': return t.source || 'interrupt'
        default: return ''
    }
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

/* ---- Trigger management ---- */
const showTriggerForm = ref<number | null>(null)
const newTriggerType = ref<'timer' | 'event' | 'interrupt'>('timer')
const newTriggerSource = ref('')
const newTriggerPeriod = ref(100)

function addTrigger(idx: number) {
    let trigger: TaskTrigger
    if (newTriggerType.value === 'timer') {
        trigger = { type: 'timer', period_ms: newTriggerPeriod.value }
    } else if (newTriggerType.value === 'interrupt') {
        trigger = { type: 'interrupt', source: newTriggerSource.value || undefined }
    } else {
        trigger = { type: 'event', source: newTriggerSource.value || undefined }
    }
    const updated = [...props.tasks[idx].triggers, trigger]
    emit('update-task', idx, 'triggers', updated)
    showTriggerForm.value = null
    newTriggerSource.value = ''
    newTriggerPeriod.value = 100
}

function removeTrigger(taskIdx: number, trigIdx: number) {
    const updated = props.tasks[taskIdx].triggers.filter((_, i) => i !== trigIdx)
    emit('update-task', taskIdx, 'triggers', updated)
}

/* ---- Signal management ---- */
const showSignalForm = ref<number | null>(null)
const newSignalName = ref('')
const newSignalTarget = ref('')

function addSignal(idx: number) {
    if (!newSignalName.value.trim()) return
    const updated = [...props.tasks[idx].signals, {
        name: newSignalName.value.trim(),
        target: newSignalTarget.value || undefined,
    }]
    emit('update-task', idx, 'signals', updated)
    showSignalForm.value = null
    newSignalName.value = ''
    newSignalTarget.value = ''
}

function removeSignal(taskIdx: number, sigIdx: number) {
    const updated = props.tasks[taskIdx].signals.filter((_, i) => i !== sigIdx)
    emit('update-task', taskIdx, 'signals', updated)
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
                    Run mode:
                    <select v-model="newRunMode" class="select-inline">
                        <option value="loop">Loop</option>
                        <option value="once">Once</option>
                    </select>
                </label>
            </div>

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
                <!-- Task name & mode -->
                <div class="task-head">
                    <div class="task-name-row">
                        <template v-if="editingName === idx">
                            <input
                                v-model="editNameValue"
                                class="input-inline"
                                @keyup.enter="commitRename(idx)"
                                @keyup.escape="cancelRename"
                                @blur="commitRename(idx)"
                                ref="nameInput"
                            />
                        </template>
                        <template v-else>
                            <span class="task-name" @dblclick="startRename(idx, task.name)">{{ task.name }}</span>
                            <span
                                :class="['mode-badge', task.run_mode === 'once' ? 'mode-once' : 'mode-loop']"
                            >{{ task.run_mode === 'once' ? 'once' : 'loop' }}</span>
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

                    <!-- Triggers -->
                    <div class="task-triggers" v-if="task.triggers.length">
                        <span
                            v-for="(t, ti) in task.triggers"
                            :key="ti"
                            class="trigger-chip"
                        >
                            <span class="trigger-icon">{{ triggerIcon(t) }}</span>
                            {{ triggerLabel(t) }}
                            <button class="chip-remove" @click="removeTrigger(idx, ti)">&times;</button>
                        </span>
                    </div>

                    <!-- Signals -->
                    <div class="task-signals" v-if="task.signals.length">
                        <span
                            v-for="(s, si) in task.signals"
                            :key="si"
                            class="signal-chip"
                        >
                            &rarr; {{ s.name }}
                            <small v-if="s.target">to {{ s.target }}</small>
                            <button class="chip-remove" @click="removeSignal(idx, si)">&times;</button>
                        </span>
                    </div>
                </div>

                <!-- Actions -->
                <div class="task-actions">
                    <!-- Run mode toggle -->
                    <select
                        class="select-mini"
                        :value="task.run_mode"
                        @change="emit('update-task', idx, 'run_mode', ($event.target as HTMLSelectElement).value)"
                    >
                        <option value="loop">Loop</option>
                        <option value="once">Once</option>
                    </select>

                    <!-- Priority -->
                    <select
                        class="select-mini"
                        :value="task.priority"
                        @change="emit('update-task', idx, 'priority', Number(($event.target as HTMLSelectElement).value))"
                    >
                        <option v-for="p in 5" :key="p" :value="p">P{{ p }}</option>
                    </select>

                    <!-- Add trigger button -->
                    <button class="btn-mini btn-trigger" @click="showTriggerForm = showTriggerForm === idx ? null : idx" title="Add trigger">
                        +Trig
                    </button>

                    <!-- Add signal button -->
                    <button class="btn-mini btn-signal" @click="showSignalForm = showSignalForm === idx ? null : idx" title="Add signal">
                        +Sig
                    </button>

                    <button class="btn-mini btn-remove" @click="emit('remove-task', idx)">Remove</button>
                </div>

                <!-- Inline trigger form -->
                <div v-if="showTriggerForm === idx" class="inline-form">
                    <select v-model="newTriggerType" class="select-inline">
                        <option value="timer">Timer</option>
                        <option value="event">Event</option>
                        <option value="interrupt">Interrupt</option>
                    </select>

                    <template v-if="newTriggerType === 'timer'">
                        <input v-model.number="newTriggerPeriod" type="number" class="input-inline input-num" placeholder="ms" min="1" />
                        <span class="form-hint">ms</span>
                    </template>
                    <template v-else-if="newTriggerType === 'interrupt'">
                        <select v-model="newTriggerSource" class="select-inline">
                            <option value="">-- select pin --</option>
                            <option v-for="pin in extiPins" :key="pin" :value="pin">{{ pin }}</option>
                        </select>
                    </template>
                    <template v-else>
                        <input v-model="newTriggerSource" type="text" class="input-inline" placeholder="event name" @keyup.enter="addTrigger(idx)" />
                    </template>

                    <button class="btn-mini btn-confirm-inline" @click="addTrigger(idx)">Add</button>
                </div>

                <!-- Inline signal form -->
                <div v-if="showSignalForm === idx" class="inline-form">
                    <input v-model="newSignalName" type="text" class="input-inline" placeholder="signal name" @keyup.enter="addSignal(idx)" />
                    <select v-model="newSignalTarget" class="select-inline">
                        <option value="">-- broadcast --</option>
                        <option v-for="t in tasks" :key="t.name" :value="t.name" v-if="t.name !== task.name">{{ t.name }}</option>
                    </select>
                    <button class="btn-mini btn-confirm-inline" @click="addSignal(idx)">Add</button>
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
            No tasks configured. Tasks are auto-suggested from peripherals.
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

.select-inline {
    padding: 1px 4px; border: 1px solid var(--border);
    border-radius: 3px; background: var(--bg-card);
    color: var(--text); font-size: 0.7rem; cursor: pointer;
    margin-left: 0.25rem;
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
.task-head {
    display: flex; flex-direction: column; gap: 0.25rem;
}
.task-name-row {
    display: flex; align-items: center; gap: 0.4rem;
}
.task-name {
    font-size: 0.8rem; font-weight: 600; cursor: default;
}
.task-name:hover { color: var(--accent); }

.mode-badge {
    font-size: 0.55rem; font-weight: 700;
    border-radius: 3px; padding: 0 4px;
    text-transform: uppercase;
}
.mode-loop { background: rgba(16,185,129,0.15); color: #34d399; }
.mode-once { background: rgba(59,130,246,0.15); color: #60a5fa; }

.task-meta { display: flex; gap: 0.35rem; }

.tag-prio {
    border: 1px solid; border-radius: 3px;
    padding: 0 4px; font-size: 0.6rem; font-weight: 600;
}
.tag-stack {
    padding: 0 4px; border-radius: 3px; font-size: 0.6rem;
    background: rgba(107,114,128,0.15); color: #9ca3af;
}

/* Triggers */
.task-triggers { display: flex; flex-wrap: wrap; gap: 0.25rem; margin-top: 0.15rem; }
.trigger-chip {
    display: inline-flex; align-items: center; gap: 0.15rem;
    padding: 0 5px; border-radius: 3px; font-size: 0.6rem;
    background: rgba(245,158,11,0.1); color: #fbbf24;
    border: 1px solid rgba(245,158,11,0.2);
}
.trigger-icon { font-size: 0.65rem; }

/* Signals */
.task-signals { display: flex; flex-wrap: wrap; gap: 0.25rem; margin-top: 0.1rem; }
.signal-chip {
    display: inline-flex; align-items: center; gap: 0.15rem;
    padding: 0 5px; border-radius: 3px; font-size: 0.6rem;
    background: rgba(139,92,246,0.1); color: #a78bfa;
    border: 1px solid rgba(139,92,246,0.2);
}
.signal-chip small { font-size: 0.55rem; color: #7c6fa8; }

.chip-remove {
    background: none; border: none; color: inherit;
    cursor: pointer; font-size: 0.7rem; opacity: 0.5;
    padding: 0; line-height: 1; margin-left: 1px;
}
.chip-remove:hover { opacity: 1; }

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

/* Inline form */
.inline-form {
    display: flex; align-items: center; gap: 0.3rem;
    margin-top: 0.35rem; padding: 0.35rem 0;
}
.input-inline {
    padding: 1px 4px; border: 1px solid var(--border);
    border-radius: 3px; background: var(--bg-card);
    color: var(--text); font-size: 0.65rem; width: 100px;
}
.input-inline:focus { outline: none; border-color: var(--accent); }
.input-num { width: 50px; }
.form-hint { font-size: 0.6rem; color: var(--text-dim); }

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
.btn-trigger { color: #f59e0b; border-color: rgba(245,158,11,0.3); }
.btn-trigger:hover { background: rgba(245,158,11,0.1); color: #fbbf24; }
.btn-signal { color: #8b5cf6; border-color: rgba(139,92,246,0.3); }
.btn-signal:hover { background: rgba(139,92,246,0.1); color: #a78bfa; }
.btn-confirm-inline { color: #10b981; border-color: rgba(16,185,129,0.3); }
.btn-confirm-inline:hover { background: rgba(16,185,129,0.1); }

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
