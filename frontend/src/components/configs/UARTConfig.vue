<script setup lang="ts">
/**
 * UARTConfig.vue — UART peripheral configuration form.
 *
 * Editable: baud rate, data bits, parity, stop bits, TX/RX pin assignment.
 */
import { computed } from 'vue'
import type { PinModel, PeripheralModel } from '../../composables/useHardwareModel'
import { findAlternativePins } from '../../composables/ConstraintEngine'
import { pinBusColor } from '../../composables/BusColorMap'

const props = defineProps<{
    peripheral: PeripheralModel
    pins: PinModel[]
    /** Pin IDs with constraint errors */
    conflicts?: Set<string>
}>()

const emit = defineEmits<{
    (e: 'update-peripheral', field: string, value: unknown): void
    (e: 'update-pin', pinIndex: number, field: string, value: unknown): void
}>()

const extra = computed(() => (props.peripheral.extra as Record<string, unknown>) || {})

const baud = computed({
    get: () => String(extra.value.baud ?? 115200),
    set: (val: string) => emit('update-peripheral', 'extra', { ...extra.value, baud: parseInt(val) }),
})

const dataBits = computed({
    get: () => extra.value.data_bits ?? 8,
    set: (val: number) => emit('update-peripheral', 'extra', { ...extra.value, data_bits: val }),
})

const parity = computed({
    get: () => String(extra.value.parity ?? 'none'),
    set: (val: string) => emit('update-peripheral', 'extra', { ...extra.value, parity: val }),
})

const stopBits = computed({
    get: () => extra.value.stop_bits ?? 1,
    set: (val: number) => emit('update-peripheral', 'extra', { ...extra.value, stop_bits: val }),
})

/* ---- Pin selectors ---- */
/** Find which UART instance this peripheral uses (e.g. "USART1", "USART2") */
function uartInstance(): string {
    const name = props.peripheral.name?.toUpperCase() ?? ''
    const bus = String(props.peripheral.bus ?? props.peripheral.uart ?? '')
    // Extract instance: "USART2", "UART1" etc.
    const match = (bus || name).match(/(?:UART|USART|LPUART)\d+/)
    return match ? match[0] : ''
}

/** Find pins supporting a specific UART signal (TX/RX) */
function candidatePins(signal: 'TX' | 'RX' | 'RTS' | 'CTS'): PinModel[] {
    const instance = uartInstance()
    if (!instance) return []
    const fnName = `${instance}_${signal}`

    // Find from current assignments first
    const current = props.pins.filter(p => p.function === fnName)

    // Find alternatives from AF table
    const assignments = props.pins.map(p => ({
        pinId: p.id, function: p.function, af: p.af,
    }))
    const alts = findAlternativePins(fnName, assignments)
    const altIds = new Set(alts.map(a => a.pinId))

    // Build candidate list
    const candidates = [...current]
    for (const alt of alts) {
        const pin = props.pins.find(p => p.id === alt.pinId)
        if (!candidates.find(c => c.id === alt.pinId)) {
            candidates.push(pin ?? { id: alt.pinId, function: '', label: '', af: alt.af })
        }
    }
    return candidates
}

/** Currently assigned pin for a signal */
function assignedPin(signal: string): PinModel | undefined {
    return props.pins.find(p => p.function === signal)
}

function assignPin(signal: string, pinId: string) {
    const idx = props.pins.findIndex(p => p.id === pinId)
    if (idx < 0) return

    const instance = uartInstance()
    const fnName = instance ? `${instance}_${signal}` : `UART_${signal}`

    // Find AF number for this function
    const alts = findAlternativePins(fnName, props.pins.map(p => ({
        pinId: p.id, function: p.function, af: p.af,
    })))
    const match = alts.find(a => a.pinId === pinId)
    const af = match?.af ?? 0

    emit('update-pin', idx, 'function', fnName)
    emit('update-pin', idx, 'af', af)
}

// Pin list for available pins dropdown
const freePins = computed(() =>
    props.pins.filter(p => !p.function || p.function.includes('GPIO'))
)
</script>

<template>
    <div class="config-section">
        <h4>UART Configuration</h4>

        <label>
            <span>Baud Rate</span>
            <select v-model="baud" class="field">
                <option value="9600">9600</option>
                <option value="19200">19200</option>
                <option value="38400">38400</option>
                <option value="57600">57600</option>
                <option value="115200">115200</option>
                <option value="230400">230400</option>
                <option value="460800">460800</option>
                <option value="921600">921600</option>
                <option value="1000000">1 Mbps</option>
                <option value="2000000">2 Mbps</option>
            </select>
        </label>

        <label>
            <span>Data Bits</span>
            <select v-model.number="dataBits" class="field">
                <option :value="8">8</option>
                <option :value="9">9</option>
            </select>
        </label>

        <label>
            <span>Parity</span>
            <select v-model="parity" class="field">
                <option value="none">None</option>
                <option value="odd">Odd</option>
                <option value="even">Even</option>
            </select>
        </label>

        <label>
            <span>Stop Bits</span>
            <select v-model.number="stopBits" class="field">
                <option :value="0.5">0.5</option>
                <option :value="1">1</option>
                <option :value="1.5">1.5</option>
                <option :value="2">2</option>
            </select>
        </label>

        <!-- Pin assignment -->
        <div class="pin-section-title">Pin Assignment</div>

        <label v-for="sig in ['TX', 'RX']" :key="sig">
            <span>{{ sig }} Pin</span>
            <select
                class="field"
                :value="assignedPin(`${uartInstance()}_${sig}`)?.id ?? ''"
                @change="assignPin(sig, ($event.target as HTMLSelectElement).value)"
            >
                <option value="">-- Auto --</option>
                <option
                    v-for="pin in candidatePins(sig as 'TX' | 'RX')"
                    :key="pin.id"
                    :value="pin.id"
                >
                    {{ pin.id }} (AF{{ pin.af ?? '?' }})
                </option>
                <option
                    v-for="pin in freePins"
                    :key="'free-' + pin.id"
                    :value="pin.id"
                    v-show="!candidatePins(sig as 'TX' | 'RX').find(c => c.id === pin.id)"
                >
                    {{ pin.id }} (GPIO)
                </option>
            </select>
        </label>

        <div class="info-row">
            <span class="label">Bus</span>
            <span class="tag tag-uart">{{ peripheral.bus || 'auto' }}</span>
        </div>
    </div>
</template>

<style scoped>
.config-section { display: flex; flex-direction: column; gap: 0.75rem; }
.config-section h4 {
    font-size: 0.85rem; font-weight: 600; color: var(--orange); margin-bottom: 0.25rem;
}
label {
    display: flex; flex-direction: column; gap: 0.25rem;
    font-size: 0.75rem; color: var(--text-dim);
}
.field {
    padding: 6px 8px; border: 1px solid var(--border); border-radius: 4px;
    background: var(--bg-input); color: var(--text); font-size: 0.8rem;
}
.field:focus { outline: none; border-color: var(--orange); }
.info-row {
    display: flex; justify-content: space-between; align-items: center; font-size: 0.75rem;
}
.pin-section-title {
    font-size: 0.7rem;
    font-weight: 700;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding-top: 0.25rem;
    border-top: 1px solid var(--border);
}
</style>
