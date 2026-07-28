<script setup lang="ts">
/**
 * PeripheralList.vue — unified peripheral list with pin assignments.
 *
 * Each peripheral row expands to show assigned pins.  Standalone
 * GPIO / EXTI pins are shown as a separate group at the bottom.
 */
import { computed } from 'vue'
import type { PeripheralModel, PinModel } from '../composables/useHardwareModel'
import { busTagClass, extractBusType } from '../composables/BusColorMap'

const props = defineProps<{
    peripherals: PeripheralModel[]
    pins: PinModel[]
    selectedIndex?: number
}>()

const emit = defineEmits<{
    (e: 'select', index: number): void
    (e: 'remove', index: number): void
}>()

function busTag(bus: string | null | undefined): string {
    return busTagClass(extractBusType(bus))
}

/* ---- Pin → peripheral matching ---- */
interface PeriUsage {
    name: string
    type: string
    pins: { id: string; function: string; label: string }[]
}

const peripheralUsage = computed<PeriUsage[]>(() => {
    return props.peripherals.map(peri => {
        const busInst = peri.bus || peri.name
        return {
            name: peri.name,
            type: peri.type,
            pins: props.pins
                .filter(p => {
                    if (!p.function) return false
                    if (p.function.startsWith(busInst + '_')) return true
                    if (p.function.startsWith(peri.name + '_')) return true
                    if (p.label && p.label.startsWith(busInst + '_')) return true
                    return false
                })
                .map(p => ({ id: p.id, function: p.function, label: p.label })),
        }
    })
})

/** Short pin function name (strip bus prefix) */
function shortFn(fn: string): string {
    const idx = fn.indexOf('_')
    return idx >= 0 ? fn.slice(idx + 1) : fn
}

/** Standalone GPIO/EXTI pins not claimed by any peripheral */
interface GpioEntry {
    id: string
    function: string
    label: string
    exti?: Record<string, unknown> | null
    isExti: boolean
}

const gpioPins = computed<GpioEntry[]>(() => {
    const claimed = new Set<string>()
    for (const pu of peripheralUsage.value) {
        for (const p of pu.pins) claimed.add(p.id)
    }
    return props.pins
        .filter(p => {
            if (!p.function) return false
            if (claimed.has(p.id)) return false
            const fn = p.function.toUpperCase()
            return fn.startsWith('GPIO_')
        })
        .map(p => ({
            id: p.id,
            function: p.function,
            label: p.label,
            exti: p.exti,
            isExti: !!p.exti,
        }))
})
</script>

<template>
    <div class="panel peri-panel">
        <div class="panel-title">
            Peripherals ({{ peripherals.length }})
            <span class="stat-badge" v-if="gpioPins.length">{{ gpioPins.length }} GPIO</span>
        </div>

        <!-- Peripheral table -->
        <table v-if="peripherals.length" class="peri-table">
            <thead>
                <tr>
                    <th class="col-name">Name</th>
                    <th class="col-type">Type</th>
                    <th class="col-bus">Bus</th>
                    <th class="col-pins">Pins</th>
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
                    <td><span class="type-tag">{{ peri.type }}</span></td>
                    <td>
                        <span v-if="peri.bus" :class="'tag bus-tag ' + busTag(peri.bus)">
                            {{ peri.bus }}
                        </span>
                        <span v-else class="tag tag-gpio">—</span>
                    </td>
                    <td class="pin-cell">
                        <template v-if="peripheralUsage[idx]?.pins.length">
                            <span
                                v-for="p in peripheralUsage[idx].pins"
                                :key="p.id"
                                class="pu-pin"
                            >
                                <code>{{ p.id }}</code>
                                <small>{{ shortFn(p.function) }}</small>
                            </span>
                        </template>
                        <span v-else class="no-pins">—</span>
                    </td>
                    <td>
                        <button
                            class="btn-mini btn-remove"
                            @click.stop="emit('remove', idx)"
                        >Remove</button>
                    </td>
                </tr>
            </tbody>
        </table>

        <!-- GPIO / EXTI pins -->
        <div v-if="gpioPins.length" class="gpio-section">
            <div class="gpio-title">GPIO / Interrupts</div>
            <div class="gpio-chips">
                <span
                    v-for="pin in gpioPins"
                    :key="pin.id"
                    :class="['gpio-chip', { 'is-exti': pin.isExti }]"
                >
                    <code>{{ pin.id }}</code>
                    <small>{{ pin.label || shortFn(pin.function) }}</small>
                    <span v-if="pin.isExti" class="exti-badge">EXTI</span>
                </span>
            </div>
        </div>

        <p v-if="!peripherals.length && !gpioPins.length" class="empty">
            No peripherals detected
        </p>
    </div>
</template>

<style scoped>
.peri-panel { display: flex; flex-direction: column; gap: 0.5rem; }

.stat-badge {
    font-size: 0.6rem;
    color: #8b5cf6;
    background: rgba(139,92,246,0.12);
    border-radius: 99px;
    padding: 1px 6px;
    margin-left: auto;
}

/* Table */
.peri-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.75rem;
}
.peri-table thead { border-bottom: 1px solid var(--border); }
.peri-table th {
    text-align: left;
    padding: 0.3rem 0.4rem;
    color: var(--text-dim);
    font-weight: 600;
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    white-space: nowrap;
}
.peri-table td {
    padding: 0.4rem;
    vertical-align: middle;
    border-bottom: 1px solid rgba(255,255,255,0.04);
}
.col-name { width: auto; }
.col-type { width: 80px; }
.col-bus  { width: 50px; }
.col-pins { width: auto; }
strong { font-weight: 600; }

.type-tag {
    font-size: 0.65rem;
    color: var(--text-dim);
    background: rgba(107,114,128,0.1);
    border-radius: 3px;
    padding: 0 4px;
}

.bus-tag {
    font-size: 0.6rem;
    font-weight: 600;
    border-radius: 3px;
    padding: 0 4px;
    white-space: nowrap;
}

/* Pin chips in table */
.pin-cell { display: flex; flex-wrap: wrap; gap: 0.2rem; }
.pu-pin {
    display: inline-flex; align-items: center; gap: 0.15rem;
    background: rgba(0,0,0,0.25); border-radius: 3px; padding: 0 4px;
}
.pu-pin code {
    font-size: 0.6rem; font-weight: 700; color: #60a5fa;
}
.pu-pin small {
    font-size: 0.55rem; color: var(--text-dim);
}
.no-pins {
    font-size: 0.65rem; color: var(--text-dim); font-style: italic;
}

/* GPIO section */
.gpio-section {
    margin-top: 0.25rem;
    padding-top: 0.5rem;
    border-top: 1px solid var(--border);
}
.gpio-title {
    font-size: 0.7rem;
    font-weight: 600;
    color: var(--text-dim);
    margin-bottom: 0.35rem;
}
.gpio-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
}
.gpio-chip {
    display: inline-flex; align-items: center; gap: 0.2rem;
    padding: 2px 6px;
    border-radius: 4px;
    background: rgba(107,114,128,0.12);
    font-size: 0.7rem;
}
.gpio-chip code {
    font-size: 0.65rem; font-weight: 700; color: #a78bfa;
}
.gpio-chip small {
    font-size: 0.6rem; color: var(--text-dim);
}
.gpio-chip.is-exti {
    background: rgba(245,158,11,0.1);
    border: 1px solid rgba(245,158,11,0.25);
}
.exti-badge {
    font-size: 0.5rem;
    font-weight: 700;
    color: #f59e0b;
    background: rgba(245,158,11,0.2);
    border-radius: 2px;
    padding: 0 2px;
}

.empty { color: var(--text-dim); font-size: 0.8rem; text-align: center; padding: 1rem; }
</style>
