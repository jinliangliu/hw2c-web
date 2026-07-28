<script setup lang="ts">
/**
 * PinAfSelector.vue — AF function selector popup for a single pin.
 *
 * Shown when user clicks a pin on the MCU chip view.
 * Lists all available AF functions for the pin and lets user pick one.
 * Also supports GPIO config (direction, pull, speed).
 */
import { computed, ref } from 'vue'
import type { PinModel } from '../composables/useHardwareModel'
import { LQFP64_MAP } from '../composables/Lqfp64Pinout'
import type { AfEntry } from '../composables/Lqfp64Pinout'
import { findFunctionsForPin } from '../composables/ConstraintEngine'
import { pinBusColor } from '../composables/BusColorMap'

const props = defineProps<{
    pinId: string
    pins: PinModel[]
    /** Pin IDs with constraint errors */
    conflicts?: Set<string>
}>()

const emit = defineEmits<{
    (e: 'assign-function', pinId: string, afFunction: string, af: number): void
    (e: 'update-gpio', pinId: string, field: string, value: unknown): void
    (e: 'close'): void
}>()

/* ---- Current pin state ---- */
const currentPin = computed(() =>
    props.pins.find(p => p.id === props.pinId)
)

const currentFunction = computed(() =>
    currentPin.value?.function ?? 'Unassigned'
)

const currentAf = computed(() =>
    currentPin.value?.af ?? 0
)

/* ---- Available AF functions ---- */
const afFunctions = computed<AfEntry[]>(() =>
    findFunctionsForPin(props.pinId)
)

/* ---- Grouped by bus type ---- */
const groupedFunctions = computed(() => {
    const groups: Record<string, AfEntry[]> = {}
    for (const af of afFunctions.value) {
        const bus = af.function.includes('GPIO') ? 'GPIO' :
            af.function.includes('EXTI') ? 'EXTI' :
            af.function.includes('TIM') ? 'TIM' :
            af.function.includes('USART') || af.function.includes('LPUART') ? 'UART' :
            af.function.includes('SPI') ? 'SPI' :
            af.function.includes('I2C') ? 'I2C' :
            af.function.includes('ADC') ? 'ADC' :
            'Other'
        if (!groups[bus]) groups[bus] = []
        groups[bus].push(af)
    }
    return groups
})

/* ---- GPIO config (when selecting GPIO function) ---- */
const gpioDirection = ref(currentFunction.value.includes('Input') ? 'input' : 'output')
const gpioPull = ref(currentPin.value?.pull ?? 'none')
const gpioSpeed = ref('low')

const BUS_COLORS: Record<string, string> = {
    GPIO: '#8b5cf6', EXTI: '#f59e0b', TIM: '#06b6d4',
    UART: '#f97316', SPI: '#10b981', I2C: '#3b82f6',
    ADC: '#ef4444', Other: '#6b7280',
}

function selectAf(af: AfEntry) {
    if (af.function.startsWith('GPIO')) {
        const dir = currentFunction.value.includes('Input') ? 'GPIO_Input' : 'GPIO_Output'
        emit('assign-function', props.pinId, dir, af.af)
    } else {
        emit('assign-function', props.pinId, af.function, af.af)
    }
    emit('close')
}

function applyGpioConfig() {
    const fn = gpioDirection.value === 'input' ? 'GPIO_Input' : 'GPIO_Output'
    emit('assign-function', props.pinId, fn, 0)
    emit('update-gpio', props.pinId, 'pull', gpioPull.value)
    emit('update-gpio', props.pinId, 'active_level', currentPin.value?.active_level ?? 'high')
}

function isSelected(af: AfEntry): boolean {
    const cur = currentFunction.value
    if (af.function.startsWith('GPIO')) {
        return cur === 'GPIO_Input' || cur === 'GPIO_Output'
    }
    return af.function === cur
}

// Pin info from LQFP64
const pinInfo = computed(() => LQFP64_MAP.get(props.pinId))
const pinNum = computed(() => pinInfo.value?.num ?? 0)
</script>

<template>
    <div class="af-selector-overlay" @click.self="emit('close')">
        <div class="af-selector-card">
            <!-- Header -->
            <div class="af-selector-head">
                <div>
                    <span class="af-pin-id">{{ pinId }}</span>
                    <span class="af-pin-num">Pin {{ pinNum }}</span>
                    <span v-if="currentFunction !== 'Unassigned'"
                        class="af-current-tag"
                        :style="{ background: pinBusColor(currentFunction) + '22', color: pinBusColor(currentFunction), borderColor: pinBusColor(currentFunction) }">
                        {{ currentFunction }}
                    </span>
                </div>
                <button class="af-close-btn" @click="emit('close')">&times;</button>
            </div>

            <!-- AF Function List -->
            <div class="af-section-title">Alternate Functions</div>
            <div v-for="(afs, bus) in groupedFunctions" :key="bus" class="af-bus-group">
                <div class="af-bus-label" :style="{ color: BUS_COLORS[bus] ?? '#6b7280' }">{{ bus }}</div>
                <div class="af-fn-list">
                    <button
                        v-for="af in afs"
                        :key="af.function"
                        class="af-fn-btn"
                        :class="{ 'af-fn-selected': isSelected(af) }"
                        :style="isSelected(af) ? { borderColor: BUS_COLORS[bus] ?? '#6b7280' } : {}"
                        @click="selectAf(af)"
                    >
                        <span class="af-fn-name">{{ af.function }}</span>
                        <span class="af-fn-af">AF{{ af.af }}</span>
                    </button>
                </div>
            </div>

            <!-- GPIO Quick Config -->
            <div class="af-section-title">GPIO Quick Config</div>
            <div class="af-gpio-row">
                <label class="af-gpio-label">
                    <span>Dir</span>
                    <select v-model="gpioDirection" class="af-gpio-select" @change="applyGpioConfig">
                        <option value="output">Output</option>
                        <option value="input">Input</option>
                    </select>
                </label>
                <label class="af-gpio-label">
                    <span>Pull</span>
                    <select v-model="gpioPull" class="af-gpio-select" @change="applyGpioConfig">
                        <option value="none">None</option>
                        <option value="up">Pull-Up</option>
                        <option value="down">Pull-Down</option>
                    </select>
                </label>
            </div>

            <div v-if="conflicts?.has(pinId)" class="af-conflict-notice">
                This pin has a constraint conflict. Check the validation badge.
            </div>
        </div>
    </div>
</template>

<style scoped>
.af-selector-overlay {
    position: fixed;
    inset: 0;
    z-index: 100;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0,0,0,0.4);
}

.af-selector-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    width: 360px;
    max-height: 70vh;
    overflow-y: auto;
    padding: 1rem;
    box-shadow: 0 8px 32px rgba(0,0,0,0.5);
}

.af-selector-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 0.75rem;
}
.af-pin-id {
    font-size: 1rem;
    font-weight: 700;
    color: var(--text);
}
.af-pin-num {
    font-size: 0.7rem;
    color: var(--text-dim);
    margin-left: 0.5rem;
}
.af-current-tag {
    display: inline-block;
    margin-left: 0.5rem;
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 0.65rem;
    font-weight: 600;
    border: 1px solid;
}

.af-close-btn {
    border: none;
    background: transparent;
    color: var(--text-dim);
    font-size: 1.25rem;
    cursor: pointer;
    padding: 0 4px;
    line-height: 1;
}
.af-close-btn:hover { color: var(--text); }

.af-section-title {
    font-size: 0.7rem;
    font-weight: 700;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin: 0.75rem 0 0.4rem 0;
    padding-bottom: 0.25rem;
    border-bottom: 1px solid var(--border);
}

.af-bus-group { margin-bottom: 0.35rem; }
.af-bus-label {
    font-size: 0.6rem;
    font-weight: 700;
    margin-bottom: 2px;
    padding-left: 2px;
}
.af-fn-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
}
.af-fn-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 4px 10px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg-input);
    color: var(--text);
    font-size: 0.75rem;
    cursor: pointer;
    transition: all 0.12s;
}
.af-fn-btn:hover {
    border-color: var(--accent);
    background: rgba(59,130,246,0.1);
}
.af-fn-selected {
    background: rgba(59,130,246,0.12);
    border-width: 2px;
}
.af-fn-name { font-weight: 500; }
.af-fn-af {
    font-size: 0.6rem;
    color: var(--text-dim);
    background: rgba(255,255,255,0.05);
    padding: 0 3px;
    border-radius: 2px;
}

.af-gpio-row {
    display: flex;
    gap: 0.5rem;
}
.af-gpio-label {
    display: flex;
    flex-direction: column;
    gap: 2px;
    flex: 1;
    font-size: 0.65rem;
    color: var(--text-dim);
}
.af-gpio-select {
    padding: 4px 6px;
    border: 1px solid var(--border);
    border-radius: 3px;
    background: var(--bg-input);
    color: var(--text);
    font-size: 0.7rem;
}
.af-gpio-select:focus { outline: none; border-color: var(--accent); }

.af-conflict-notice {
    margin-top: 0.75rem;
    padding: 0.4rem 0.6rem;
    background: rgba(239,68,68,0.1);
    border: 1px solid rgba(239,68,68,0.3);
    border-radius: 4px;
    font-size: 0.65rem;
    color: #f87171;
}
</style>
