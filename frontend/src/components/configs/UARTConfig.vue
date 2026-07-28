<script setup lang="ts">
/**
 * UARTConfig.vue — UART peripheral configuration form.
 *
 * Editable: baud rate, data bits, parity, stop bits.
 */
import { computed } from 'vue'
import type { PeripheralModel } from '../../composables/useHardwareModel'

const props = defineProps<{
    peripheral: PeripheralModel
}>()

const emit = defineEmits<{
    (e: 'update', field: string, value: unknown): void
}>()

const extra = computed(() => (props.peripheral.extra as Record<string, unknown>) || {})

const baud = computed({
    get: () => String(extra.value.baud ?? 115200),
    set: (val: string) => emit('update', 'extra', { ...extra.value, baud: parseInt(val) }),
})

const dataBits = computed({
    get: () => extra.value.data_bits ?? 8,
    set: (val: number) => emit('update', 'extra', { ...extra.value, data_bits: val }),
})

const parity = computed({
    get: () => String(extra.value.parity ?? 'none'),
    set: (val: string) => emit('update', 'extra', { ...extra.value, parity: val }),
})

const stopBits = computed({
    get: () => extra.value.stop_bits ?? 1,
    set: (val: number) => emit('update', 'extra', { ...extra.value, stop_bits: val }),
})
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
</style>
