<script setup lang="ts">
/**
 * ClockTree.vue — Interactive clock tree config (STM32Cube style).
 *
 * Editable: SYSCLK source mux, PLL M/N/R, APB prescaler, FreeRTOS tick.
 * SVG tree auto-updates based on configuration changes.
 * STM32G0B1 constraints: SYSCLK ≤ 64 MHz, PLL VCO in 2.66-16 MHz,
 * PLL VCO out 96-344 MHz, PLL out ≤ 64 MHz.
 */
import { computed } from 'vue'
import type { ClockModel } from '../composables/useHardwareModel'

const props = defineProps<{
    clock: ClockModel | null
}>()

const emit = defineEmits<{
    (e: 'update-clock', partial: Record<string, unknown>): void
}>()

/* ---- STM32G0B1 limits ---- */
const MAX_SYSCLK_MHZ = 64
const PLL_VCO_IN_MIN = 2.66
const PLL_VCO_IN_MAX = 16
const PLL_VCO_OUT_MIN = 96
const PLL_VCO_OUT_MAX = 344

/* ---- SYSCLK source options ---- */
const SYSCLK_SOURCES = ['HSI', 'HSE', 'PLL'] as const

/* ---- PLL source options ---- */
const PLL_SOURCES = ['HSI', 'HSE'] as const

/* ---- PLL M divider (STM32G0: /1../8) ---- */
const PLL_M_VALUES = [1, 2, 3, 4, 5, 6, 7, 8]

/* ---- PLL N multiplier (STM32G0: ×8..×86) ---- */
const PLL_N_MIN = 8
const PLL_N_MAX = 86

/* ---- PLL R divider (STM32G0: /2, /4, /6, /8) ---- */
const PLL_R_VALUES = [2, 4, 6, 8]

/* ---- APB prescaler ---- */
const APB_PRESCALERS = [1, 2, 4, 8, 16]

/* ---- FreeRTOS tick sources ---- */
const TICK_SOURCES = ['SysTick', 'TIM1', 'TIM2', 'TIM3', 'TIM16', 'TIM17', 'LPTIM']

/* ---- Computed values ---- */
const sysclkSource = computed({
    get: () => props.clock?.sysclk?.source ?? 'HSI',
    set: (val) => emitUpdate('sysclk', { source: val }),
})

const pllSource = computed({
    get: () => props.clock?.pll?.source ?? 'HSI',
    set: (val) => emitUpdate('pll', { source: val }),
})

const pllM = computed({
    get: () => props.clock?.pll?.m ?? 1,
    set: (val) => emitUpdate('pll', { m: Number(val) }),
})

const pllN = computed({
    get: () => props.clock?.pll?.n ?? 8,
    set: (val) => emitUpdate('pll', { n: Number(val) }),
})

const pllR = computed({
    get: () => props.clock?.pll?.r ?? 2,
    set: (val) => emitUpdate('pll', { r: Number(val) }),
})

const apbPrescaler = computed({
    get: () => props.clock?.apb?.prescaler ?? 1,
    set: (val) => emitUpdate('apb', { prescaler: Number(val) }),
})

const tickSource = computed({
    get: () => props.clock?.freertos_tick?.source ?? 'SysTick',
    set: (val) => emitUpdate('freertos_tick', { source: val }),
})

const tickFreq = computed({
    get: () => props.clock?.freertos_tick?.frequency_hz ?? 1000,
    set: (val) => emitUpdate('freertos_tick', { frequency_hz: Number(val) }),
})

function emitUpdate(section: string, partial: Record<string, unknown>) {
    emit('update-clock', { [section]: partial })
}

/* ---- Calculated frequencies (MHz) ---- */
const pllSourceFreqMhz = computed(() => {
    if (pllSource.value === 'HSE') {
        return (props.clock?.hse?.present ? (props.clock.hse.frequency_hz / 1e6) : 0)
    }
    return (props.clock?.hsi_hz ?? 16_000_000) / 1e6
})

const pllVcoInMhz = computed(() => pllSourceFreqMhz.value / pllM.value)
const pllVcoOutMhz = computed(() => pllVcoInMhz.value * pllN.value)
const pllOutMhz = computed(() => pllVcoOutMhz.value / pllR.value)

const sysclkMhz = computed(() => {
    switch (sysclkSource.value) {
        case 'HSE': return props.clock?.hse?.present ? (props.clock!.hse.frequency_hz / 1e6) : 0
        case 'PLL': return pllOutMhz.value
        default: return (props.clock?.hsi_hz ?? 16_000_000) / 1e6
    }
})

const apbMhz = computed(() => sysclkMhz.value / apbPrescaler.value)
const tickHz = computed(() => tickFreq.value)

/* ---- Constraint warnings ---- */
const pllWarnings = computed<string[]>(() => {
    const w: string[] = []
    if (pllVcoInMhz.value < PLL_VCO_IN_MIN) w.push(`VCO input ${pllVcoInMhz.value.toFixed(2)} MHz below min ${PLL_VCO_IN_MIN} MHz`)
    if (pllVcoInMhz.value > PLL_VCO_IN_MAX) w.push(`VCO input ${pllVcoInMhz.value.toFixed(2)} MHz above max ${PLL_VCO_IN_MAX} MHz`)
    if (pllVcoOutMhz.value < PLL_VCO_OUT_MIN) w.push(`VCO output ${pllVcoOutMhz.value.toFixed(1)} MHz below min ${PLL_VCO_OUT_MIN} MHz`)
    if (pllVcoOutMhz.value > PLL_VCO_OUT_MAX) w.push(`VCO output ${pllVcoOutMhz.value.toFixed(1)} MHz above max ${PLL_VCO_OUT_MAX} MHz`)
    if (pllOutMhz.value > MAX_SYSCLK_MHZ) w.push(`PLL output ${pllOutMhz.value.toFixed(1)} MHz exceeds max SYSCLK ${MAX_SYSCLK_MHZ} MHz`)
    return w
})

const sysclkWarnings = computed<string[]>(() => {
    if (sysclkMhz.value > MAX_SYSCLK_MHZ) return [`SYSCLK ${sysclkMhz.value.toFixed(1)} MHz exceeds max ${MAX_SYSCLK_MHZ} MHz`]
    if (sysclkSource.value === 'HSE' && !props.clock?.hse?.present) return ['HSE not fitted on board']
    return []
})

/* ---- Helpers ---- */
function fmtHz(hz: number): string {
    if (hz >= 1e6) return (hz / 1e6).toFixed(3) + ' MHz'
    if (hz >= 1e3) return (hz / 1e3).toFixed(3) + ' kHz'
    return hz + ' Hz'
}

function fmtMhz(v: number): string { return v.toFixed(2) + ' MHz' }

/* ---- SVG visualization (simplified, auto-updating) ---- */
const W = 580, H = 220

interface VBox { x: number; y: number; w: number; h: number; label: string; sub: string; fill: string; stroke: string }
const svgBoxes = computed<VBox[]>(() => {
    const c = props.clock
    if (!c) return []

    const boxes: VBox[] = []
    const active = '#4ade80', inactive = '#64748b'
    const activeBg = 'rgba(74,222,128,0.12)', inactiveBg = 'rgba(148,163,184,0.08)'

    // HSI
    boxes.push({ x: 8, y: 10, w: 72, h: 38, label: 'HSI', sub: fmtHz(c.hsi_hz), fill: inactiveBg, stroke: inactive })
    // HSE
    const hseOk = c.hse.present
    boxes.push({ x: 8, y: 58, w: 72, h: 38, label: 'HSE', sub: fmtHz(c.hse.frequency_hz), fill: hseOk ? activeBg : inactiveBg, stroke: hseOk ? active : inactive })
    // LSI
    boxes.push({ x: 8, y: 114, w: 72, h: 30, label: 'LSI', sub: fmtHz(c.lsi_hz), fill: inactiveBg, stroke: inactive })
    // LSE
    const lseOk = c.lse.present
    boxes.push({ x: 8, y: 152, w: 72, h: 30, label: 'LSE', sub: fmtHz(c.lse.frequency_hz), fill: lseOk ? activeBg : inactiveBg, stroke: lseOk ? active : inactive })

    // PLL
    const pllAct = sysclkSource.value === 'PLL' || pllSource.value !== ''
    boxes.push({ x: 140, y: 30, w: 100, h: 50, label: 'PLL', sub: `×${pllN.value}/R${pllR.value}`, fill: pllAct ? 'rgba(59,130,246,0.12)' : inactiveBg, stroke: pllAct ? '#3b82f6' : inactive })

    // SYSCLK Mux
    boxes.push({ x: 300, y: 34, w: 100, h: 42, label: 'SYSCLK', sub: fmtMhz(sysclkMhz.value), fill: 'rgba(239,68,68,0.1)', stroke: '#ef4444' })

    // APB
    boxes.push({ x: 300, y: 95, w: 100, h: 30, label: 'APB /' + apbPrescaler.value, sub: fmtMhz(apbMhz.value), fill: 'rgba(245,158,11,0.1)', stroke: '#f59e0b' })

    // FreeRTOS Tick
    boxes.push({ x: 450, y: 95, w: 110, h: 30, label: 'RTOS Tick', sub: fmtHz(tickHz.value), fill: 'rgba(168,85,247,0.1)', stroke: '#a855f7' })

    // IWDG
    boxes.push({ x: 140, y: 114, w: 90, h: 28, label: 'IWDG (LSI)', sub: '', fill: inactiveBg, stroke: inactive })
    // RTC
    const rtcSrc = c.lse.present ? 'LSE' : 'LSI'
    boxes.push({ x: 140, y: 150, w: 90, h: 28, label: 'RTC', sub: rtcSrc, fill: lseOk ? activeBg : inactiveBg, stroke: lseOk ? active : inactive })

    return boxes
})

const svgContent = computed(() => {
    const boxes = svgBoxes.value
    let html = ''

    // Draw boxes
    for (const b of boxes) {
        html += `<rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="4" fill="${b.fill}" stroke="${b.stroke}" stroke-width="1.5"/>`
        const cx = b.x + b.w / 2
        html += `<text x="${cx}" y="${b.y + 14}" fill="#e2e8f0" font-size="9" font-family="monospace" text-anchor="middle" font-weight="600">${b.label}</text>`
        if (b.sub) {
            html += `<text x="${cx}" y="${b.y + b.h - 6}" fill="#94a3b8" font-size="7" font-family="monospace" text-anchor="middle">${b.sub}</text>`
        }
    }

    // Connections
    const c = props.clock
    if (!c) return html

    function conn(x1: number, y1: number, x2: number, y2: number, color: string) {
        const mid = (x1 + x2) / 2
        html += `<path d="M${x1},${y1} L${mid},${y1} L${mid},${y2} L${x2},${y2}" stroke="${color}" stroke-width="1.2" fill="none"/>`
    }

    const pllAct = '#3b82f6', dim = '#475569'
    if (pllSource.value === 'HSE') conn(80, 77, 140, 55, c.hse.present ? pllAct : dim)
    if (pllSource.value === 'HSI') conn(80, 29, 140, 55, pllAct)
    conn(240, 55, 300, 55, pllAct)
    conn(350, 76, 350, 95, '#f59e0b')
    conn(350, 76, 300, 55, '#f59e0b')
    conn(400, 110, 450, 110, '#a855f7')
    conn(80, 129, 140, 128, dim)
    if (c.lse.present) conn(80, 167, 140, 164, pllAct)

    return html
})
</script>

<template>
    <div class="clock-editor" v-if="clock">
        <!-- SVG Tree -->
        <div class="clock-tree-panel">
            <svg :viewBox="`0 0 ${W} ${H}`" class="clock-svg" v-html="svgContent"></svg>
        </div>

        <!-- Configuration Sections -->
        <div class="clock-config">

            <!-- SYSCLK Mux -->
            <section class="cfg-section">
                <div class="cfg-section-head">
                    <span class="cfg-section-icon">SYSCLK</span>
                    <span class="cfg-section-val" :class="{ 'cfg-warn': sysclkWarnings.length }">
                        {{ fmtMhz(sysclkMhz) }}
                    </span>
                </div>
                <div class="cfg-row">
                    <label class="cfg-label">
                        <span>Clock Source</span>
                        <select v-model="sysclkSource" class="cfg-select">
                            <option v-for="s in SYSCLK_SOURCES" :key="s" :value="s">{{ s }}</option>
                        </select>
                    </label>
                </div>
                <div v-if="sysclkWarnings.length" class="cfg-warnings">
                    <div v-for="w in sysclkWarnings" :key="w">{{ w }}</div>
                </div>
            </section>

            <!-- PLL Configuration -->
            <section class="cfg-section">
                <div class="cfg-section-head">
                    <span class="cfg-section-icon pll">PLL</span>
                    <span class="cfg-section-val" :class="{ 'cfg-warn': pllWarnings.length }">
                        {{ fmtMhz(pllOutMhz) }}
                    </span>
                </div>

                <div class="cfg-row">
                    <label class="cfg-label">
                        <span>PLL Source</span>
                        <select v-model="pllSource" class="cfg-select">
                            <option v-for="s in PLL_SOURCES" :key="s" :value="s">{{ s }}</option>
                        </select>
                    </label>
                </div>

                <div class="cfg-row cfg-row-triple">
                    <label class="cfg-label cfg-label-sm">
                        <span>/M</span>
                        <select v-model.number="pllM" class="cfg-select cfg-select-sm">
                            <option v-for="v in PLL_M_VALUES" :key="v" :value="v">{{ v }}</option>
                        </select>
                    </label>
                    <label class="cfg-label cfg-label-sm">
                        <span>×N</span>
                        <input
                            type="number"
                            :value="pllN"
                            @input="pllN = ($event.target as HTMLInputElement).value"
                            :min="PLL_N_MIN" :max="PLL_N_MAX"
                            class="cfg-select cfg-select-sm"
                        />
                    </label>
                    <label class="cfg-label cfg-label-sm">
                        <span>/R</span>
                        <select v-model.number="pllR" class="cfg-select cfg-select-sm">
                            <option v-for="v in PLL_R_VALUES" :key="v" :value="v">{{ v }}</option>
                        </select>
                    </label>
                </div>

                <div class="cfg-freq-chain">
                    <span>{{ fmtMhz(pllSourceFreqMhz) }}</span>
                    <span class="cfg-chain-arrow">/{{ pllM }}→</span>
                    <span :class="{ 'cfg-warn': pllVcoInMhz < PLL_VCO_IN_MIN || pllVcoInMhz > PLL_VCO_IN_MAX }">{{ fmtMhz(pllVcoInMhz) }}</span>
                    <span class="cfg-chain-arrow">×{{ pllN }}→</span>
                    <span :class="{ 'cfg-warn': pllVcoOutMhz < PLL_VCO_OUT_MIN || pllVcoOutMhz > PLL_VCO_OUT_MAX }">{{ fmtMhz(pllVcoOutMhz) }}</span>
                    <span class="cfg-chain-arrow">/{{ pllR }}→</span>
                    <strong :class="{ 'cfg-warn': pllOutMhz > MAX_SYSCLK_MHZ }">{{ fmtMhz(pllOutMhz) }}</strong>
                </div>

                <div v-if="pllWarnings.length" class="cfg-warnings">
                    <div v-for="w in pllWarnings" :key="w">{{ w }}</div>
                </div>
            </section>

            <!-- APB Prescaler -->
            <section class="cfg-section">
                <div class="cfg-section-head">
                    <span class="cfg-section-icon apb">APB</span>
                    <span class="cfg-section-val">{{ fmtMhz(apbMhz) }}</span>
                </div>
                <div class="cfg-row">
                    <label class="cfg-label">
                        <span>Prescaler</span>
                        <select v-model.number="apbPrescaler" class="cfg-select">
                            <option v-for="v in APB_PRESCALERS" :key="v" :value="v">/{{ v }} — {{ fmtMhz(sysclkMhz / v) }}</option>
                        </select>
                    </label>
                </div>
            </section>

            <!-- FreeRTOS Tick -->
            <section class="cfg-section">
                <div class="cfg-section-head">
                    <span class="cfg-section-icon tick">RTOS</span>
                    <span class="cfg-section-val">{{ tickHz }} Hz</span>
                </div>
                <div class="cfg-row">
                    <label class="cfg-label">
                        <span>Timer Source</span>
                        <select v-model="tickSource" class="cfg-select">
                            <option v-for="s in TICK_SOURCES" :key="s" :value="s">{{ s }}</option>
                        </select>
                    </label>
                </div>
                <div class="cfg-row">
                    <label class="cfg-label">
                        <span>Tick Frequency (Hz)</span>
                        <input
                            type="number"
                            :value="tickFreq"
                            @input="tickFreq = ($event.target as HTMLInputElement).value"
                            min="1" max="100000"
                            class="cfg-select"
                        />
                    </label>
                </div>
            </section>

            <!-- Sources status -->
            <section class="cfg-section">
                <div class="cfg-section-head">
                    <span class="cfg-section-icon">Sources</span>
                </div>
                <div class="cfg-source-grid">
                    <div class="cfg-source-item" :class="{ active: clock.hse.present }">
                        <span class="cfg-source-dot" :style="{ background: clock.hse.present ? '#4ade80' : '#64748b' }"></span>
                        <span>HSE</span>
                        <code>{{ clock.hse.present ? fmtHz(clock.hse.frequency_hz) : 'not fitted' }}</code>
                    </div>
                    <div class="cfg-source-item" :class="{ active: clock.lse.present }">
                        <span class="cfg-source-dot" :style="{ background: clock.lse.present ? '#4ade80' : '#64748b' }"></span>
                        <span>LSE</span>
                        <code>{{ clock.lse.present ? fmtHz(clock.lse.frequency_hz) : 'not fitted' }}</code>
                    </div>
                    <div class="cfg-source-item active">
                        <span class="cfg-source-dot" style="background:#94a3b8"></span>
                        <span>HSI</span>
                        <code>{{ fmtHz(clock.hsi_hz) }}</code>
                    </div>
                    <div class="cfg-source-item active">
                        <span class="cfg-source-dot" style="background:#94a3b8"></span>
                        <span>LSI</span>
                        <code>{{ fmtHz(clock.lsi_hz) }}</code>
                    </div>
                </div>
            </section>

        </div>
    </div>

    <div v-else class="clock-empty">
        <p>No clock configuration available. Parse a netlist first.</p>
    </div>
</template>

<style scoped>
.clock-editor {
    display: flex;
    flex-direction: column;
    gap: 1rem;
}

/* SVG Tree */
.clock-tree-panel {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 0.5rem;
}
.clock-svg {
    width: 100%;
    height: auto;
    display: block;
}

/* Config sections */
.clock-config {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
}

.cfg-section {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 0.6rem 0.75rem;
}

.cfg-section-head {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
}

.cfg-section-icon {
    font-size: 0.65rem;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 3px;
    background: rgba(239,68,68,0.12);
    color: #f87171;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.cfg-section-icon.pll { background: rgba(59,130,246,0.12); color: #60a5fa; }
.cfg-section-icon.apb { background: rgba(245,158,11,0.12); color: #fbbf24; }
.cfg-section-icon.tick { background: rgba(168,85,247,0.12); color: #c084fc; }

.cfg-section-val {
    font-size: 0.85rem;
    font-weight: 700;
    color: var(--accent);
    font-family: monospace;
}
.cfg-section-val.cfg-warn { color: #fbbf24; }

.cfg-row {
    display: flex;
    gap: 0.5rem;
    align-items: flex-end;
}
.cfg-row + .cfg-row { margin-top: 0.4rem; }
.cfg-row-triple { gap: 0.35rem; }

.cfg-label {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    flex: 1;
}
.cfg-label > span {
    font-size: 0.65rem;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.4px;
}
.cfg-label-sm { flex: 1; min-width: 0; }

.cfg-select {
    padding: 5px 8px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg-input);
    color: var(--text);
    font-size: 0.78rem;
    font-family: monospace;
}
.cfg-select:focus { outline: none; border-color: var(--accent); }
.cfg-select-sm { font-size: 0.72rem; padding: 4px 6px; }

/* PLL frequency chain */
.cfg-freq-chain {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    margin-top: 0.4rem;
    padding: 0.35rem 0.5rem;
    background: var(--bg-input);
    border-radius: 4px;
    font-size: 0.7rem;
    font-family: monospace;
    color: var(--text-dim);
    flex-wrap: wrap;
}
.cfg-chain-arrow {
    color: var(--border);
    font-size: 0.6rem;
}
.cfg-freq-chain strong {
    color: var(--accent);
    font-size: 0.78rem;
}
.cfg-freq-chain .cfg-warn { color: #fbbf24; }

/* Warnings */
.cfg-warnings {
    margin-top: 0.35rem;
    padding: 0.3rem 0.5rem;
    background: rgba(245,158,11,0.08);
    border: 1px solid rgba(245,158,11,0.3);
    border-radius: 4px;
    font-size: 0.6rem;
    color: #fbbf24;
    line-height: 1.4;
}

/* Source grid */
.cfg-source-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.35rem;
}
.cfg-source-item {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.3rem 0.5rem;
    background: var(--bg-input);
    border-radius: 4px;
    font-size: 0.7rem;
    opacity: 0.6;
}
.cfg-source-item.active { opacity: 1; }
.cfg-source-dot {
    width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
}
.cfg-source-item code {
    font-size: 0.6rem;
    color: var(--text-dim);
    margin-left: auto;
}

.clock-empty {
    text-align: center;
    padding: 2rem;
    color: var(--text-dim);
    font-size: 0.85rem;
}
</style>
