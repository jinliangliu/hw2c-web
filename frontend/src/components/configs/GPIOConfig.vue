<script setup lang="ts">
/**
 * GPIOConfig.vue — GPIO peripheral (LED, Button) configuration form.
 *
 * Editable: direction, pull, active_level, EXTI enable, pin selector.
 */
import { computed } from 'vue'
import type { PinModel, PeripheralModel } from '../../composables/useHardwareModel'

const props = defineProps<{
    peripheral: PeripheralModel
    pins: PinModel[]
}>()

const emit = defineEmits<{
    (e: 'update-peripheral', field: string, value: unknown): void
    (e: 'update-pin', pinIndex: number, field: string, value: unknown): void
}>()

/** Find the pin connected to this peripheral by label prefix match */
const linkedPin = computed<PinModel | null>(() => {
    const name = props.peripheral.name.toLowerCase()
    return props.pins.find(p => {
        const label = p.label.toLowerCase()
        if (label.includes('led') || label.includes('button')) {
            return label.includes(name) || name.includes(label.replace('_', ' '))
        }
        return false
    }) ?? null
})

const pinIdx = computed(() => {
    const p = linkedPin.value
    if (!p) return -1
    return props.pins.indexOf(p)
})

function isLED(): boolean {
    const t = props.peripheral.type
    return t.includes('LED') || t.includes('Neopixel') || t.includes('Buzzer') || t.includes('Relay')
}

function isButton(): boolean {
    const t = props.peripheral.type
    return t.includes('Button') || t.includes('BUTTON') || t.includes('SWITCH')
}

const direction = computed({
    get: () => {
        if (!linkedPin.value) return ''
        return linkedPin.value.function.includes('Input') ? 'input' : 'output'
    },
    set: (val: string) => {
        if (pinIdx.value >= 0) {
            emit('update-pin', pinIdx.value, 'function', val === 'input' ? 'GPIO_Input' : 'GPIO_Output')
        }
    },
})

const pull = computed({
    get: () => linkedPin.value?.pull ?? 'none',
    set: (val: string) => {
        if (pinIdx.value >= 0) {
            emit('update-pin', pinIdx.value, 'pull', val)
        }
    },
})

const activeLevel = computed({
    get: () => linkedPin.value?.active_level ?? 'high',
    set: (val: string) => {
        if (pinIdx.value >= 0) {
            emit('update-pin', pinIdx.value, 'active_level', val)
        }
    },
})

const extiEnabled = computed({
    get: () => !!(linkedPin.value?.exti),
    set: (val: boolean) => {
        if (pinIdx.value >= 0) {
            emit('update-pin', pinIdx.value, 'exti', val ? { enable: true } : null)
        }
    },
})

/** Available GPIO pins (free or already assigned to this peripheral) */
const availableGpioPins = computed(() =>
    props.pins.filter(p =>
        p.function.includes('GPIO') || p.function === '' || p.id === linkedPin.value?.id
    )
)

function assignPin(pinId: string) {
    // Un-assign current if any
    if (pinIdx.value >= 0 && linkedPin.value) {
        emit('update-pin', pinIdx.value, 'function', '')
    }
    // Assign new
    const idx = props.pins.findIndex(p => p.id === pinId)
    if (idx >= 0) {
        const fn = isButton() ? 'GPIO_Input' : 'GPIO_Output'
        emit('update-pin', idx, 'function', fn)
    }
}
</script>

<template>
    <div class="config-section">
        <h4>{{ isLED() ? 'Output' : isButton() ? 'Input' : 'GPIO' }} Configuration</h4>

        <label>
            <span>Pin</span>
            <select class="field" :value="linkedPin?.id ?? ''" @change="assignPin(($event.target as HTMLSelectElement).value)">
                <option value="">-- Select Pin --</option>
                <option v-for="pin in availableGpioPins" :key="pin.id" :value="pin.id">
                    {{ pin.id }} {{ pin.label ? '(' + pin.label + ')' : '' }}
                </option>
            </select>
        </label>

        <label v-if="!isLED() && !isButton()">
            <span>Direction</span>
            <select v-model="direction" class="field">
                <option value="output">Output</option>
                <option value="input">Input</option>
            </select>
        </label>

        <label>
            <span>Pull</span>
            <select v-model="pull" class="field">
                <option value="none">None</option>
                <option value="up">Pull-Up</option>
                <option value="down">Pull-Down</option>
            </select>
        </label>

        <label>
            <span>Active Level</span>
            <select v-model="activeLevel" class="field">
                <option value="high">High</option>
                <option value="low">Low</option>
            </select>
        </label>

        <label v-if="isButton()">
            <span>EXTI Interrupt</span>
            <div class="toggle-row">
                <input type="checkbox" v-model="extiEnabled" />
                <span>{{ extiEnabled ? 'Enabled' : 'Disabled' }}</span>
            </div>
        </label>

        <div class="info-row" v-if="linkedPin">
            <span class="label">Pin</span>
            <code>{{ linkedPin.id }}</code>
        </div>
    </div>
</template>

<style scoped>
.config-section { display: flex; flex-direction: column; gap: 0.75rem; }
.config-section h4 { font-size: 0.85rem; font-weight: 600; color: var(--purple); margin-bottom: 0.25rem; }
label { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.75rem; color: var(--text-dim); }
.field { padding: 6px 8px; border: 1px solid var(--border); border-radius: 4px; background: var(--bg-input); color: var(--text); font-size: 0.8rem; }
.field:focus { outline: none; border-color: var(--purple); }
.toggle-row { display: flex; align-items: center; gap: 0.5rem; padding-top: 4px; }
.toggle-row input[type="checkbox"] { accent-color: var(--accent); }
.info-row { display: flex; justify-content: space-between; align-items: center; font-size: 0.75rem; }
code { background: var(--bg-input); padding: 1px 6px; border-radius: 3px; font-size: 0.75rem; }
</style>
