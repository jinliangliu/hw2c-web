<script setup lang="ts">
import type { PinModel } from '../composables/useHardwareModel'

defineProps<{ pins: PinModel[] }>()
const emit = defineEmits<{
    (e: 'edit-pin', index: number, field: string, value: unknown): void
}>()

function afName(af: number | undefined): string {
    if (af === undefined) return '-'
    const map: Record<number, string> = {
        0: 'GPIO', 1: 'AF1', 2: 'AF2', 3: 'AF3',
        4: 'AF4', 5: 'AF5', 6: 'AF6', 7: 'AF7',
    }
    return map[af] ?? `AF${af}`
}

function toggleLevel(index: number, current: string | null | undefined) {
    emit('edit-pin', index, 'active_level', current === 'low' ? 'high' : 'low')
}
</script>

<template>
    <div class="panel pin-table">
        <div class="panel-title">Pin Assignments ({{ pins.length }})</div>
        <table v-if="pins.length">
            <thead>
                <tr>
                    <th>Pin</th>
                    <th>Function</th>
                    <th>Label</th>
                    <th>Level</th>
                    <th>AF</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>
                <tr v-for="(pin, idx) in pins" :key="pin.id">
                    <td><code>{{ pin.id }}</code></td>
                    <td>{{ pin.function }}</td>
                    <td>{{ pin.label }}</td>
                    <td>
                        <span
                            v-if="pin.active_level"
                            class="tag level-tag"
                            :class="pin.active_level === 'low' ? 'tag-i2c' : 'tag-spi'"
                            @click="toggleLevel(idx, pin.active_level)"
                            style="cursor: pointer"
                        >
                            {{ pin.active_level === 'low' ? 'LOW' : 'HIGH' }}
                        </span>
                        <span v-else class="text-dim">—</span>
                    </td>
                    <td><span class="tag tag-gpio">{{ afName(pin.af) }}</span></td>
                    <td>
                        <button
                            class="btn-mini"
                            @click="toggleLevel(idx, pin.active_level)"
                        >Toggle</button>
                    </td>
                </tr>
            </tbody>
        </table>
        <p v-else class="empty">No pins assigned</p>
    </div>
</template>

<style scoped>
.pin-table { max-height: 400px; overflow-y: auto; }
code {
    background: var(--bg-input);
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 0.75rem;
}
.empty { color: var(--text-dim); font-size: 0.8rem; text-align: center; padding: 1rem; }
</style>
