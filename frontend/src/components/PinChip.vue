<script setup lang="ts">
/**
 * PinChip.vue — LQFP-64 MCU package visualizer (SVG).
 *
 * Renders the MCU package outline with 64 pins color-coded by bus type.
 * Highlights assigned pins with their function, dims power/unused pins.
 */
import { computed, ref } from 'vue'
import type { PinModel } from '../composables/useHardwareModel'
import { LQFP64_PINS, type PhysicalPin } from '../composables/Lqfp64Pinout'
import { pinBusColor } from '../composables/BusColorMap'

const props = defineProps<{
    pins: PinModel[]
}>()

const emit = defineEmits<{
    (e: 'select-pin', pinId: string): void
}>()

/* ---- Layout constants ---- */
const CHIP_X = 100
const CHIP_Y = 100
const CHIP_W = 320
const PAD_GAP = CHIP_W / 16        // 20px per pin
const PAD_HALF = 6                  // half-width of pad rect
const PAD_LEN = 16                  // pad length (outward from chip)
const PAD_INSET = 3                 // pad goes 3px into chip body
const PIN1_SIZE = 16                // pin-1 marker dot size
const VIEW_W = 520
const VIEW_H = 520

/* ---- Lookup: pin ID → user-assigned PinModel ---- */
const pinLookup = computed(() => {
    const m = new Map<string, PinModel>()
    for (const p of props.pins) {
        m.set(p.id, p)
    }
    return m
})

/* ---- Compute pad rectangles per physical pin ---- */
interface PinPad {
    pp: PhysicalPin
    /** Assigned pin model (if any) */
    assigned: PinModel | undefined
    x: number
    y: number
    w: number
    h: number
    /** Label position (outside pad) */
    labelX: number
    labelY: number
    /** Text anchor for label */
    anchor: 'start' | 'middle' | 'end'
    /** Pin number position (inside pad, center) */
    numX: number
    numY: number
}

const pinPads = computed<PinPad[]>(() =>
    LQFP64_PINS.map(pp => {
        const idx = pp.idx
        const seg = PAD_GAP
        const half = PAD_HALF
        const len = PAD_LEN
        const inset = PAD_INSET

        let x: number, y: number, w: number, h: number
        let labelX: number, labelY: number, anchor: 'start' | 'middle' | 'end'
        let numX: number, numY: number

        switch (pp.side) {
            case 0: // top: horizontal, left→right
                x = CHIP_X + idx * seg + seg / 2 - half
                y = CHIP_Y - inset - len
                w = half * 2
                h = len + inset
                labelX = CHIP_X + idx * seg + seg / 2
                labelY = CHIP_Y - len - inset - 6
                anchor = 'middle'
                numX = x + w / 2
                numY = y + h / 2
                break
            case 1: // right: vertical, top→bottom
                x = CHIP_X + CHIP_W + inset
                y = CHIP_Y + idx * seg + seg / 2 - half
                w = len + inset
                h = half * 2
                labelX = CHIP_X + CHIP_W + len + inset + 6
                labelY = CHIP_Y + idx * seg + seg / 2 + 4
                anchor = 'start'
                numX = x + w / 2
                numY = y + h / 2
                break
            case 2: // bottom: horizontal, right→left
                x = CHIP_X + (15 - idx) * seg + seg / 2 - half
                y = CHIP_Y + CHIP_W + inset
                w = half * 2
                h = len + inset
                labelX = CHIP_X + (15 - idx) * seg + seg / 2
                labelY = CHIP_Y + CHIP_W + len + inset + 6
                anchor = 'middle'
                numX = x + w / 2
                numY = y + h / 2
                break
            case 3: // left: vertical, bottom→top
                x = CHIP_X - inset - len
                y = CHIP_Y + (15 - idx) * seg + seg / 2 - half
                w = len + inset
                h = half * 2
                labelX = CHIP_X - len - inset - 6
                labelY = CHIP_Y + (15 - idx) * seg + seg / 2 + 4
                anchor = 'end'
                numX = x + w / 2
                numY = y + h / 2
                break
        }

        const assigned = pinLookup.value.get(pp.id)
        return { pp, assigned, x: x!, y: y!, w: w!, h: h!, labelX: labelX!, labelY: labelY!, anchor: anchor!, numX: numX!, numY: numY! }
    })
)

/* ---- Colors ---- */
function padFill(pad: PinPad): string {
    if (pad.pp.isPower) return '#1a1a2e'
    if (!pad.assigned?.function) return '#1e2430'
    return pinBusColor(pad.assigned.function)
}

function padStroke(pad: PinPad): string {
    return '#c9a84c'  // gold pin outline
}

function padOpacity(pad: PinPad): number {
    if (pad.pp.isPower) return 0.4
    if (!pad.assigned?.function) return 0.5
    return 1
}

function labelText(pad: PinPad): string {
    if (pad.pp.isPower) return pad.pp.id
    if (pad.assigned?.function) {
        const fn = pad.assigned.function
        const idx = fn.indexOf('_')
        return idx >= 0 ? fn.slice(idx + 1) : fn
    }
    return pad.pp.id  // show pin ID for unassigned
}

function isHighlighted(pad: PinPad): boolean {
    return !!pad.assigned?.function && !pad.pp.isPower
}

/* ---- Hover tooltip state ---- */
const tooltipPin = ref<PhysicalPin | null>(null)
const tooltipX = ref(0)
const tooltipY = ref(0)

const tooltipWidth = computed(() => {
    if (!tooltipPin.value) return 120
    const text = `Pin ${tooltipPin.value.num}: ${tooltipPin.value.id}`
    return Math.max(120, text.length * 7 + 20)
})

const tooltipHeight = computed(() => {
    if (!tooltipPin.value) return 36
    return tooltipPin.value.afs.length > 0 ? 44 : 30
})

function showTooltip(pad: PinPad, e: MouseEvent) {
    tooltipPin.value = pad.pp
    tooltipX.value = e.offsetX
    tooltipY.value = e.offsetY
}

function hideTooltip() {
    tooltipPin.value = null
}

/* ---- Stats ---- */
const stats = computed(() => {
    const total = LQFP64_PINS.length
    const power = LQFP64_PINS.filter(p => p.isPower).length
    const assigned = pinPads.value.filter(p => isHighlighted(p)).length
    return { total, power, assigned, unused: total - power - assigned }
})
</script>

<template>
    <div class="panel chip-panel">
        <div class="panel-title-row">
            <span class="panel-title">MCU Package (LQFP-64)</span>
            <span class="pin-stats">
                <span class="stat">{{ stats.total }} pins</span>
                <span class="stat stat-active" v-if="stats.assigned">{{ stats.assigned }} used</span>
                <span class="stat stat-unused" v-if="stats.unused">{{ stats.unused }} free</span>
            </span>
        </div>

        <div class="chip-svg-wrap">
            <svg
                viewBox="0 0 520 520"
                class="chip-svg"
            >
                <!-- Chip body shadow -->
                <rect
                    :x="CHIP_X - 2" :y="CHIP_Y - 2"
                    :width="CHIP_W + 4" :height="CHIP_W + 4"
                    rx="6" fill="rgba(0,0,0,0.3)"
                />

                <!-- Chip body -->
                <rect
                    :x="CHIP_X" :y="CHIP_Y"
                    :width="CHIP_W" :height="CHIP_W"
                    rx="4"
                    fill="#4a4f58"
                    stroke="#5f646d"
                    stroke-width="1.5"
                />

                <!-- MCU label -->
                <text
                    :x="CHIP_X + CHIP_W / 2"
                    :y="CHIP_Y + CHIP_W / 2 - 8"
                    text-anchor="middle"
                    fill="#e2e8f0"
                    font-size="16"
                    font-weight="700"
                >STM32G0B1</text>
                <text
                    :x="CHIP_X + CHIP_W / 2"
                    :y="CHIP_Y + CHIP_W / 2 + 14"
                    text-anchor="middle"
                    fill="#8899aa"
                    font-size="11"
                >Cortex-M0+ 64MHz</text>

                <!-- Pin 1 marker -->
                <circle
                    :cx="CHIP_X - 8"
                    :cy="CHIP_Y - 8"
                    :r="PIN1_SIZE / 2"
                    fill="#f59e0b"
                />

                <!-- Pin pads -->
                <g
                    v-for="pad in pinPads"
                    :key="pad.pp.num"
                    class="pin-group"
                    @mouseenter="showTooltip(pad, $event)"
                    @mouseleave="hideTooltip"
                    @click="!pad.pp.isPower && emit('select-pin', pad.pp.id)"
                    :style="{ cursor: pad.pp.isPower ? 'default' : 'pointer' }"
                >
                    <!-- Pad body -->
                    <rect
                        :x="pad.x" :y="pad.y"
                        :width="pad.w" :height="pad.h"
                        :rx="pad.w < pad.h ? 2 : 2"
                        :fill="padFill(pad)"
                        :stroke="padStroke(pad)"
                        :stroke-width="isHighlighted(pad) ? 1.5 : 0.8"
                        :opacity="padOpacity(pad)"
                        class="pad-rect"
                    />

                    <!-- Pin number -->
                    <text
                        :x="pad.numX"
                        :y="pad.numY"
                        text-anchor="middle"
                        dominant-baseline="central"
                        fill="#e2e8f0"
                        font-size="7"
                        font-weight="700"
                    >{{ pad.pp.num }}</text>
                </g>

                <!-- Pin function labels (only for assigned pins) -->
                <g v-for="pad in pinPads" :key="'lbl-' + pad.pp.num">
                    <text
                        v-if="isHighlighted(pad)"
                        :x="pad.labelX"
                        :y="pad.labelY"
                        :text-anchor="pad.anchor"
                        :fill="padFill(pad)"
                        font-size="8"
                        font-weight="600"
                    >{{ labelText(pad) }}</text>
                </g>

                <!-- Tooltip -->
                <g v-if="tooltipPin" class="tooltip-g">
                    <rect
                        :x="tooltipX + 12"
                        :y="tooltipY - 28"
                        :width="tooltipWidth"
                        :height="tooltipHeight"
                        rx="4"
                        fill="#1a1f2e"
                        stroke="#3b82f6"
                        stroke-width="1"
                        opacity="0.95"
                    />
                    <text
                        :x="tooltipX + 22"
                        :y="tooltipY - 10"
                        fill="#e2e8f0"
                        font-size="10"
                        font-weight="600"
                    >Pin {{ tooltipPin.num }}: {{ tooltipPin.id }}</text>
                    <text
                        v-if="tooltipPin.afs.length"
                        :x="tooltipX + 22"
                        :y="tooltipY + 4"
                        fill="#8899aa"
                        font-size="8"
                    >AF: {{ tooltipPin.afs.map(a => `AF${a.af}=${a.function}`).join(', ') }}</text>
                </g>
            </svg>
        </div>

        <!-- Legend -->
        <div class="legend">
            <div class="legend-item">
                <span class="legend-dot" style="background: #3b82f6"></span> I2C
            </div>
            <div class="legend-item">
                <span class="legend-dot" style="background: #10b981"></span> SPI
            </div>
            <div class="legend-item">
                <span class="legend-dot" style="background: #f59e0b"></span> UART
            </div>
            <div class="legend-item">
                <span class="legend-dot" style="background: #8b5cf6"></span> GPIO
            </div>
            <div class="legend-item">
                <span class="legend-dot" style="background: #2d3748"></span> Power
            </div>
            <div class="legend-item">
                <span class="legend-dot" style="background: #6b7280"></span> SWD
            </div>
        </div>
    </div>
</template>

<style scoped>
.chip-panel {
    display: flex;
    flex-direction: column;
}

.panel-title-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
}
.panel-title-row .panel-title { margin-bottom: 0; }

.pin-stats {
    display: flex;
    gap: 0.4rem;
    font-size: 0.65rem;
}
.stat {
    padding: 1px 6px;
    border-radius: 99px;
    background: rgba(107,114,128,0.15);
    color: #9ca3af;
}
.stat-active {
    background: rgba(16,185,129,0.15);
    color: #34d399;
}
.stat-unused {
    background: rgba(59,130,246,0.12);
    color: #60a5fa;
}

.chip-svg-wrap {
    display: flex;
    justify-content: center;
}

.chip-svg {
    width: 100%;
    max-width: 520px;
    height: auto;
}

.pad-rect {
    transition: opacity 0.15s, stroke-width 0.15s;
}
.pin-group:hover .pad-rect {
    stroke-width: 2.5 !important;
    opacity: 1 !important;
}

.tooltip-g {
    pointer-events: none;
}

/* Legend */
.legend {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    justify-content: center;
    margin-top: 0.5rem;
    padding-top: 0.5rem;
    border-top: 1px solid var(--border);
}
.legend-item {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    font-size: 0.65rem;
    color: var(--text-dim);
}
.legend-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 2px;
}
</style>
