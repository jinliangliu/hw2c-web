<script setup lang="ts">
/**
 * SPIConfig.vue — SPI peripheral configuration form.
 *
 * Editable: mode (0–3), speed (presets), NSS strategy (HW/SW).
 */
import { computed } from 'vue'
import type { PeripheralModel } from '../../composables/useHardwareModel'

const props = defineProps<{
    peripheral: PeripheralModel
}>()

const emit = defineEmits<{
    (e: 'update', field: string, value: unknown): void
}>()

const mode = computed({
    get: () => (props.peripheral.extra as any)?.mode ?? 0,
    set: (val: number) => {
        emit('update', 'extra', { ...props.peripheral.extra, mode: Number(val) })
    },
})

const speed = computed({
    get: () => {
        const hz = (props.peripheral.extra as any)?.speed_hz ?? 10000000
        if (hz >= 40000000) return '40000000'
        if (hz >= 20000000) return '20000000'
        if (hz >= 10000000) return '10000000'
        return '5000000'
    },
    set: (val: string) => {
        emit('update', 'extra', { ...props.peripheral.extra, speed_hz: parseInt(val) })
    },
})

const nss = computed({
    get: () => (props.peripheral.extra as any)?.nss ?? 'hw',
    set: (val: string) => {
        emit('update', 'extra', { ...props.peripheral.extra, nss: val })
    },
})

const MODE_LABELS: Record<number, string> = {
    0: 'Mode 0 (CPOL=0, CPHA=0)',
    1: 'Mode 1 (CPOL=0, CPHA=1)',
    2: 'Mode 2 (CPOL=1, CPHA=0)',
    3: 'Mode 3 (CPOL=1, CPHA=1)',
}
</script>

<template>
    <div class="config-section">
        <h4>SPI Configuration</h4>

        <label>
            <span>Mode</span>
            <select v-model.number="mode" class="field">
                <option v-for="(label, key) in MODE_LABELS" :key="key" :value="Number(key)">
                    {{ label }}
                </option>
            </select>
        </label>

        <label>
            <span>Speed</span>
            <select v-model="speed" class="field">
                <option value="5000000">5 MHz</option>
                <option value="10000000">10 MHz</option>
                <option value="20000000">20 MHz</option>
                <option value="40000000">40 MHz</option>
            </select>
        </label>

        <label>
            <span>NSS Strategy</span>
            <select v-model="nss" class="field">
                <option value="hw">Hardware (AF pin)</option>
                <option value="sw">Software (GPIO toggle)</option>
            </select>
        </label>

        <div class="info-row">
            <span class="label">Bus</span>
            <span class="tag tag-spi">{{ peripheral.bus || 'auto' }}</span>
        </div>
    </div>
</template>

<style scoped>
.config-section { display: flex; flex-direction: column; gap: 0.75rem; }
.config-section h4 {
    font-size: 0.85rem; font-weight: 600; color: var(--green); margin-bottom: 0.25rem;
}
label {
    display: flex; flex-direction: column; gap: 0.25rem;
    font-size: 0.75rem; color: var(--text-dim);
}
.field {
    padding: 6px 8px; border: 1px solid var(--border); border-radius: 4px;
    background: var(--bg-input); color: var(--text); font-size: 0.8rem;
}
.field:focus { outline: none; border-color: var(--green); }
.info-row {
    display: flex; justify-content: space-between; align-items: center; font-size: 0.75rem;
}
</style>
