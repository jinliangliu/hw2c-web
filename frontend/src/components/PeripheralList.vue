<script setup lang="ts">
import type { PeripheralModel } from '../composables/useHardwareModel'

const props = defineProps<{
    peripherals: PeripheralModel[]
    selectedIndex?: number
}>()

const emit = defineEmits<{
    (e: 'select', index: number): void
    (e: 'remove', index: number): void
}>()

function busTag(bus: string | null | undefined): string {
    if (!bus) return 'gpio'
    const b = bus.toUpperCase()
    if (b.startsWith('I2C')) return 'i2c'
    if (b.startsWith('SPI')) return 'spi'
    if (b.startsWith('USART') || b.startsWith('UART')) return 'uart'
    return 'gpio'
}
</script>

<template>
    <div class="panel">
        <div class="panel-title">Peripherals ({{ peripherals.length }})</div>
        <table v-if="peripherals.length">
            <thead>
                <tr>
                    <th>Name</th>
                    <th>Type</th>
                    <th>Bus</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>
                <tr
                    v-for="(peri, idx) in peripherals"
                    :key="peri.name"
                    :class="{ 'row-selected': idx === selectedIndex }"
                    @click="emit('select', idx)"
                    style="cursor: pointer"
                >
                    <td><strong>{{ peri.name }}</strong></td>
                    <td>{{ peri.type }}</td>
                    <td>
                        <span v-if="peri.bus" :class="'tag tag-' + busTag(peri.bus)">
                            {{ peri.bus }}
                        </span>
                        <span v-else class="tag tag-gpio">Internal</span>
                    </td>
                    <td>
                        <button class="btn-mini btn-remove" @click="emit('remove', idx)">Remove</button>
                    </td>
                </tr>
            </tbody>
        </table>
        <p v-else class="empty">No peripherals detected</p>
    </div>
</template>

<style scoped>
.empty { color: var(--text-dim); font-size: 0.8rem; text-align: center; padding: 1rem; }
strong { font-weight: 600; }
</style>
