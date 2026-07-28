<script setup lang="ts">
/**
 * I2CConfig.vue — I2C peripheral configuration form.
 *
 * Editable fields: address (7-bit hex), speed (100k/400k Standard/Fast).
 * Mutations go through writePeripheral which auto-updates the YAML.
 */
import { computed } from 'vue'
import type { PeripheralModel } from '../../composables/useHardwareModel'

const props = defineProps<{
    peripheral: PeripheralModel
}>()

const emit = defineEmits<{
    (e: 'update', field: string, value: unknown): void
}>()

const address = computed({
    get: () => {
        const addr = (props.peripheral.extra as any)?.address ?? props.peripheral.address ?? 0x68
        return `0x${addr.toString(16).toUpperCase().padStart(2, '0')}`
    },
    set: (val: string) => {
        const num = parseInt(val, 16)
        if (!isNaN(num) && num >= 0x00 && num <= 0x7F) {
            emit('update', 'extra', { ...props.peripheral.extra, address: num })
            emit('update', 'address', num)
        }
    },
})

const speed = computed({
    get: () => {
        const hz = (props.peripheral.extra as any)?.speed_hz ?? 400000
        return hz >= 400000 ? '400000' : '100000'
    },
    set: (val: string) => {
        emit('update', 'extra', { ...props.peripheral.extra, speed_hz: parseInt(val) })
    },
})
</script>

<template>
    <div class="config-section">
        <h4>I2C Configuration</h4>

        <label>
            <span>Address</span>
            <input
                type="text"
                :value="address"
                @input="address = ($event.target as HTMLInputElement).value"
                maxlength="4"
                class="field"
            />
            <span class="hint">7-bit hex (0x00–0x7F)</span>
        </label>

        <label>
            <span>Speed</span>
            <select v-model="speed" class="field">
                <option value="100000">Standard (100 kHz)</option>
                <option value="400000">Fast (400 kHz)</option>
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
.config-section h4 {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--accent);
    margin-bottom: 0.25rem;
}
label {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    font-size: 0.75rem;
    color: var(--text-dim);
}
.field {
    padding: 6px 8px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg-input);
    color: var(--text);
    font-size: 0.8rem;
}
.field:focus { outline: none; border-color: var(--accent); }
.hint { font-size: 0.65rem; color: var(--text-dim); }
.info-row {
    display: flex; justify-content: space-between; align-items: center;
    font-size: 0.75rem;
}
</style>
