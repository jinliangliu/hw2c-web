<script setup lang="ts">
/**
 * PinTable.vue — interactive pin allocator with bus color coding,
 * conflict detection, and reserved-pin marking (SWD).
 */
import { computed } from 'vue'
import type { PinModel } from '../composables/useHardwareModel'
import {
    pinBusColor,
    extractBusType,
    RESERVED_PINS,
} from '../composables/BusColorMap'
import { validate, type PinAssignment } from '../composables/ConstraintEngine'

const props = defineProps<{
    pins: PinModel[]
    connections?: { from_ref: string; from_pin: string; to_ref: string; to_pin: string; net: string }[]
}>()

const emit = defineEmits<{
    (e: 'edit-pin', index: number, field: string, value: unknown): void
}>()

/* ---- Derived data ---- */

const validationResult = computed(() => {
    const assignments: PinAssignment[] = props.pins.map(p => ({
        pinId: p.id,
        function: p.function,
    }))
    return validate(assignments)
})

const conflictPins = computed(() => {
    const s = new Set<string>()
    for (const issue of validationResult.value.issues) {
        if (issue.severity === 'error') {
            for (const pin of issue.pins) s.add(pin)
        }
    }
    return s
})

const validationIssues = computed(() =>
    validationResult.value.issues.filter(i => i.severity === 'error')
)

function isReserved(pinId: string): boolean {
    return RESERVED_PINS.has(pinId)
}

function busLabel(func: string): string {
    return extractBusType(func)
}

function afName(af: number | undefined): string {
    if (af === undefined || af === 0) return '-'
    return `AF${af}`
}

function signalName(func: string): string {
    // Strip bus prefix to show signal role, e.g. "I2C1_SCL" → "SCL"
    const idx = func.indexOf('_')
    return idx >= 0 ? func.slice(idx + 1) : func
}

/* ---- Stats ---- */

const stats = computed(() => {
    const total = props.pins.length
    let used = 0
    let reserved = 0
    let conflicted = conflictPins.value.size
    for (const p of props.pins) {
        if (p.function && p.function !== 'GPIO_INPUT' && p.function !== 'GPIO_OUTPUT')
            used++
        if (isReserved(p.id))
            reserved++
    }
    return { total, used, reserved, conflicted }
})
</script>

<template>
    <div class="panel pin-panel">
        <div class="panel-title-row">
            <span class="panel-title">Pin Assignments ({{ pins.length }})</span>
            <span class="pin-stats">
                <span class="stat" v-if="stats.used">{{ stats.used }} used</span>
                <span class="stat stat-reserved" v-if="stats.reserved">{{ stats.reserved }} reserved</span>
                <span class="stat stat-conflict" v-if="stats.conflicted">{{ stats.conflicted }} conflict</span>
            </span>
        </div>

        <div class="pin-table-wrap" v-if="pins.length">
            <table>
                <thead>
                    <tr>
                        <th class="col-pin">Pin</th>
                        <th class="col-func">Function</th>
                        <th class="col-bus">Bus</th>
                        <th class="col-label">Label</th>
                        <th class="col-level">Level</th>
                        <th class="col-af">AF</th>
                    </tr>
                </thead>
                <tbody>
                    <tr
                        v-for="(pin, idx) in pins"
                        :key="pin.id"
                        :class="{
                            'row-reserved': isReserved(pin.id),
                            'row-conflict': conflictPins.has(pin.id),
                        }"
                        :style="{ '--bus-color': pinBusColor(pin.function) }"
                    >
                        <!-- Pin ID -->
                        <td class="col-pin">
                            <code :class="{
                                'code-reserved': isReserved(pin.id),
                            }">{{ pin.id }}</code>
                            <span v-if="isReserved(pin.id)" class="badge-reserved">SWD</span>
                        </td>

                        <!-- Function (editable via text input on click) -->
                        <td class="col-func">
                            <span class="func-name">{{ signalName(pin.function) }}</span>
                            <span class="func-full" v-if="pin.function">{{ pin.function }}</span>
                        </td>

                        <!-- Bus color tag -->
                        <td class="col-bus">
                            <span
                                class="bus-dot"
                                :style="{ background: pinBusColor(pin.function) }"
                            ></span>
                            {{ busLabel(pin.function) }}
                        </td>

                        <!-- Label -->
                        <td class="col-label">
                            <span v-if="pin.label" class="label-text">{{ pin.label }}</span>
                            <span v-else class="text-dim">—</span>
                        </td>

                        <!-- Active level toggle -->
                        <td class="col-level" @click="emit('edit-pin', idx, 'active_level', pin.active_level === 'low' ? 'high' : 'low')">
                            <span
                                v-if="pin.active_level"
                                class="level-chip"
                                :class="pin.active_level === 'low' ? 'level-low' : 'level-high'"
                            >
                                {{ pin.active_level === 'low' ? 'LOW' : 'HIGH' }}
                            </span>
                            <span v-else class="text-dim">—</span>
                        </td>

                        <!-- AF number -->
                        <td class="col-af">
                            <code v-if="pin.af && pin.af !== 0" class="af-code">{{ afName(pin.af) }}</code>
                            <span v-else class="text-dim">—</span>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>

        <!-- Constraint warnings -->
        <div v-if="validationIssues.length" class="conflict-box">
            <div class="conflict-title">Constraint Errors</div>
            <div v-for="(issue, i) in validationIssues" :key="i" class="conflict-item">
                {{ issue.message }}
                <span v-if="issue.suggestion" class="conflict-suggestion">{{ issue.suggestion }}</span>
            </div>
        </div>

        <p v-if="!pins.length" class="empty">Upload a netlist to see pin assignments</p>
    </div>
</template>

<style scoped>
.pin-panel {
    max-height: 480px;
    display: flex;
    flex-direction: column;
}

.panel-title-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
}
.panel-title-row .panel-title { margin-bottom: 0; }

.pin-stats {
    display: flex;
    gap: 0.5rem;
    font-size: 0.7rem;
}
.stat {
    padding: 1px 6px;
    border-radius: 99px;
    background: rgba(59,130,246,0.15);
    color: #60a5fa;
}
.stat-reserved { background: rgba(107,114,128,0.15); color: #9ca3af; }
.stat-conflict { background: rgba(239,68,68,0.15); color: #f87171; }

.pin-table-wrap {
    overflow-y: auto;
    flex: 1;
    min-height: 0;
}

/* Row styling */
tr {
    transition: background 0.15s;
    border-left: 3px solid transparent;
}
tr:hover td { background: rgba(59,130,246,0.05); }
tr.row-reserved {
    opacity: 0.55;
    border-left-color: var(--bus-color, #6b7280);
}
tr.row-conflict {
    background: rgba(239,68,68,0.08) !important;
    border-left-color: #ef4444;
}
tr td { border-left: 3px solid transparent; }
tr:not(.row-reserved):not(.row-conflict) {
    border-left-color: var(--bus-color, transparent);
}

/* Column widths */
.col-pin   { width: 70px; }
.col-func  { min-width: 120px; }
.col-bus   { width: 80px; }
.col-label { min-width: 80px; }
.col-level { width: 60px; cursor: pointer; }
.col-af    { width: 50px; }

/* Pin ID */
code {
    background: var(--bg-input);
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 0.75rem;
    font-weight: 600;
}
.code-reserved {
    opacity: 0.5;
    color: var(--text-dim);
}
.badge-reserved {
    display: inline-block;
    margin-left: 4px;
    padding: 0 4px;
    border-radius: 3px;
    font-size: 0.6rem;
    font-weight: 600;
    background: rgba(107,114,128,0.2);
    color: #9ca3af;
    vertical-align: middle;
}

/* Function display */
.func-name {
    font-weight: 600;
    font-size: 0.8rem;
}
.func-full {
    display: block;
    font-size: 0.65rem;
    color: var(--text-dim);
}

/* Bus dot */
.bus-dot {
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    margin-right: 4px;
    vertical-align: middle;
}

/* Label */
.label-text {
    font-size: 0.75rem;
    color: var(--text-dim);
}

/* Active level chip */
.level-chip {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 0.65rem;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.15s;
}
.level-chip:hover { opacity: 0.8; }
.level-low {
    background: rgba(59,130,246,0.2);
    color: #60a5fa;
}
.level-high {
    background: rgba(245,158,11,0.2);
    color: #fbbf24;
}

/* AF */
.af-code {
    font-size: 0.7rem;
}

/* Conflict box */
.conflict-box {
    margin-top: 0.75rem;
    padding: 0.6rem;
    background: rgba(239,68,68,0.08);
    border: 1px solid rgba(239,68,68,0.3);
    border-radius: var(--radius);
    font-size: 0.75rem;
}
.conflict-title {
    font-weight: 600;
    color: var(--red);
    margin-bottom: 0.25rem;
}
.conflict-item {
    color: var(--text-dim);
    line-height: 1.5;
}
.conflict-item code {
    font-weight: 600;
    color: var(--text);
}
.conflict-item strong {
    color: var(--orange);
}
.conflict-suggestion {
    display: block;
    color: #60a5fa;
    font-style: italic;
    margin-top: 2px;
}

.empty {
    color: var(--text-dim);
    font-size: 0.8rem;
    text-align: center;
    padding: 1rem;
}
</style>
