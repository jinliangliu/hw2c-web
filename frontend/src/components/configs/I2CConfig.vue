<script setup lang="ts">
/**
 * I2CConfig.vue — I2C peripheral configuration form.
 *
 * Editable fields: address (7-bit hex), speed (100k/400k), SCL/SDA pin assignment.
 */
import { computed } from 'vue'
import type { PinModel, PeripheralModel } from '../../composables/useHardwareModel'
import { findAlternativePins } from '../../composables/ConstraintEngine'

const props = defineProps<{
    peripheral: PeripheralModel
    pins: PinModel[]
    conflicts?: Set<string>
}>()

const emit = defineEmits<{
    (e: 'update-peripheral', field: string, value: unknown): void
    (e: 'update-pin', pinIndex: number, field: string, value: unknown): void
}>()

const address = computed({
    get: () => {
        const addr = (props.peripheral.extra as any)?.address ?? props.peripheral.address ?? 0x68
        return `0x${addr.toString(16).toUpperCase().padStart(2, '0')}`
    },
    set: (val: string) => {
        const num = parseInt(val, 16)
        if (!isNaN(num) && num >= 0x00 && num <= 0x7F) {
            emit('update-peripheral', 'extra', { ...props.peripheral.extra, address: num })
            emit('update-peripheral', 'address', num)
        }
    },
})

const speed = computed({
    get: () => {
        const hz = (props.peripheral.extra as any)?.speed_hz ?? 400000
        return hz >= 400000 ? '400000' : '100000'
    },
    set: (val: string) => {
        emit('update-peripheral', 'extra', { ...props.peripheral.extra, speed_hz: parseInt(val) })
    },
})

/* ---- Pin selectors ---- */
const I2C_SIGNALS = ['SCL', 'SDA'] as const

function i2cInstance(): string {
    const name = props.peripheral.name?.toUpperCase() ?? ''
    const bus = String(props.peripheral.bus ?? '')
    const match = (bus || name).match(/I2C\d+/)
    return match ? match[0] : ''
}

function candidatePins(signal: string): PinModel[] {
    const instance = i2cInstance()
    if (!instance) return []
    const fnName = `${instance}_${signal}`
    const assignments = props.pins.map(p => ({ pinId: p.id, function: p.function, af: p.af }))
    const alts = findAlternativePins(fnName, assignments)
    return alts.map(a => {
        const pin = props.pins.find(p => p.id === a.pinId)
        return pin ?? { id: a.pinId, function: '', label: '', af: a.af }
    })
}

function assignedPin(signal: string): PinModel | undefined {
    const instance = i2cInstance()
    return props.pins.find(p => p.function === `${instance}_${signal}`)
}

function assignPin(signal: string, pinId: string) {
    const idx = props.pins.findIndex(p => p.id === pinId)
    if (idx < 0) return
    const instance = i2cInstance()
    const fnName = instance ? `${instance}_${signal}` : `I2C_${signal}`
    const alts = findAlternativePins(fnName, props.pins.map(p => ({ pinId: p.id, function: p.function, af: p.af })))
    const match = alts.find(a => a.pinId === pinId)
    emit('update-pin', idx, 'function', fnName)
    emit('update-pin', idx, 'af', match?.af ?? 0)
}
</script>

<template>
    <div class="config-section">
        <h4>I2C Configuration</h4>

        <label>
            <span>Address</span>
            <input type="text" :value="address"
                @input="address = ($event.target as HTMLInputElement).value"
                maxlength="4" class="field" />
            <span class="hint">7-bit hex (0x00–0x7F)</span>
        </label>

        <label>
            <span>Speed</span>
            <select v-model="speed" class="field">
                <option value="100000">Standard (100 kHz)</option>
                <option value="400000">Fast (400 kHz)</option>
            </select>
        </label>

        <div class="pin-section-title">Pin Assignment</div>

        <label v-for="sig in I2C_SIGNALS" :key="sig">
            <span>{{ sig }} Pin</span>
            <select
                class="field"
                :value="assignedPin(sig)?.id ?? ''"
                @change="assignPin(sig, ($event.target as HTMLSelectElement).value)"
            >
                <option value="">-- Auto --</option>
                <option v-for="pin in candidatePins(sig)" :key="pin.id" :value="pin.id">
                    {{ pin.id }} (AF{{ pin.af ?? '?' }})
                </option>
            </select>
        </label>

        <div class="info-row">
            <span class="label">Bus</span>
            <span class="tag tag-i2c">{{ peripheral.bus || 'auto' }}</span>
        </div>
    </div>
</template>

<style scoped>
.config-section { display: flex; flex-direction: column; gap: 0.75rem; }
.config-section h4 { font-size: 0.85rem; font-weight: 600; color: var(--accent); margin-bottom: 0.25rem; }
label { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.75rem; color: var(--text-dim); }
.field { padding: 6px 8px; border: 1px solid var(--border); border-radius: 4px; background: var(--bg-input); color: var(--text); font-size: 0.8rem; }
.field:focus { outline: none; border-color: var(--accent); }
.hint { font-size: 0.65rem; color: var(--text-dim); }
.info-row { display: flex; justify-content: space-between; align-items: center; font-size: 0.75rem; }
.pin-section-title {
    font-size: 0.7rem; font-weight: 700; color: var(--text-dim);
    text-transform: uppercase; letter-spacing: 0.5px;
    padding-top: 0.25rem; border-top: 1px solid var(--border);
}
</style>
