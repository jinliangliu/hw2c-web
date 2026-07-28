<script setup lang="ts">
/**
 * ClockTree — SVG clock tree visualization for STM32G0B1.
 *
 * Shows clock sources (HSI/HSE/LSI/LSE), PLL path, SYSCLK output,
 * APB prescaler, and FreeRTOS tick timer.
 * Highlights external vs internal sources based on BOM detection.
 */
import { computed } from 'vue'
import type { ClockConfig } from '../api'

const props = defineProps<{
    clock: ClockConfig
}>()

const emit = defineEmits<{
    (e: 'update', key: string, value: any): void
}>()

/* ---------- helpers ---------- */
function fmtHz(hz: number): string {
    if (hz >= 1e6) return (hz / 1e6).toFixed(0) + ' MHz'
    if (hz >= 1e3) return (hz / 1e3).toFixed(3) + ' kHz'
    return hz + ' Hz'
}

function fmtPllParams(): string {
    const p = props.clock.pll
    return `/M${p.m} ×N${p.n} /R${p.r}`
}

/* ---------- color helpers ---------- */
function sourceColor(present: boolean): string { return present ? '#4ade80' : '#94a3b8' }
function sourceBg(present: boolean): string { return present ? 'rgba(74,222,128,0.15)' : 'rgba(148,163,184,0.1)' }
function sourceStroke(present: boolean): string { return present ? '#22c55e' : '#64748b' }

/* ---------- layout constants ---------- */
const W = 600, H = 300

// Source boxes positions (left column)
const SRC_X = 10,  SRC_W = 90, SRC_H = 36
const Y_HSI = 30, Y_HSE = 80, Y_LSI = 150, Y_LSE = 200

// PLL box
const PLL_X = 170, PLL_Y = 55, PLL_W = 95, PLL_H = 56

// SYSCLK box
const SYS_X = 340, SYS_Y = 55, SYS_W = 100, SYS_H = 32

// APB box
const APB_X = 340, APB_Y = 110, APB_W = 100, APB_H = 28

// FreeRTOS tick box
const TICK_X = 340, TICK_Y = 170, TICK_W = 100, TICK_H = 28

// IWDG / RTC boxes
const IWDG_X = 170, IWDG_Y = 148, IWDG_W = 95, IWDG_H = 28
const RTC_X  = 170, RTC_Y  = 196, RTC_W  = 95, RTC_H  = 28

// SysTick box
const STK_X = 500, STK_Y = 170, STK_W = 85, STK_H = 28

/* ---------- box drawing helpers ---------- */
function box(x: number, y: number, w: number, h: number, fill: string, stroke: string): string {
    return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="4" fill="${fill}" stroke="${stroke}" stroke-width="1.5"/>`
}

function text(x: number, y: number, s: string, cls: string): string {
    const sizes: Record<string, number> = { title: 10, label: 8, small: 7 }
    const sz = sizes[cls] || 9
    return `<text x="${x}" y="${y}" fill="#e2e8f0" font-size="${sz}" font-family="monospace" text-anchor="middle">${s}</text>`
}

function line(x1: number, y1: number, x2: number, y2: number, color: string): string {
    const mid = (x1 + x2) / 2
    return `<path d="M${x1},${y1} L${mid},${y1} L${mid},${y2} L${x2},${y2}" stroke="${color}" stroke-width="1.5" fill="none"/>`
}

/* ---------- computed SVG ---------- */
const svgContent = computed(() => {
    const c = props.clock
    const parts: string[] = []

    // ---- Sources ----
    // HSI
    parts.push(box(SRC_X, Y_HSI, SRC_W, SRC_H, 'rgba(148,163,184,0.1)', '#64748b'))
    parts.push(text(SRC_X + SRC_W / 2, Y_HSI + 16, 'HSI', 'title'))
    parts.push(text(SRC_X + SRC_W / 2, Y_HSI + 28, fmtHz(c.hsi_hz), 'small'))

    // HSE
    const hseFill = sourceBg(c.hse.present)
    const hseStroke = sourceStroke(c.hse.present)
    parts.push(box(SRC_X, Y_HSE, SRC_W, SRC_H, hseFill, hseStroke))
    parts.push(text(SRC_X + SRC_W / 2, Y_HSE + 12, 'HSE', 'title'))
    parts.push(text(SRC_X + SRC_W / 2, Y_HSE + 24, fmtHz(c.hse.frequency_hz), 'small'))
    if (!c.hse.present) parts.push(text(SRC_X + SRC_W / 2, Y_HSE + 34, '(not fitted)', 'small'))

    // HSE → PLL line
    if (c.pll.source === 'HSE') {
        const color = c.hse.present ? '#4ade80' : '#94a3b8'
        parts.push(line(SRC_X + SRC_W, Y_HSE + SRC_H / 2, PLL_X, PLL_Y + 14, color))
    }

    // HSI → PLL line
    if (c.pll.source === 'HSI') {
        parts.push(line(SRC_X + SRC_W, Y_HSI + SRC_H / 2, PLL_X, PLL_Y + 14, '#94a3b8'))
    }

    // ---- LSI / LSE ----
    // LSI
    parts.push(box(SRC_X, Y_LSI, SRC_W, SRC_H, 'rgba(148,163,184,0.1)', '#64748b'))
    parts.push(text(SRC_X + SRC_W / 2, Y_LSI + 16, 'LSI', 'title'))
    parts.push(text(SRC_X + SRC_W / 2, Y_LSI + 28, fmtHz(c.lsi_hz), 'small'))

    // LSE
    const lseFill = sourceBg(c.lse.present)
    const lseStroke = sourceStroke(c.lse.present)
    parts.push(box(SRC_X, Y_LSE, SRC_W, SRC_H, lseFill, lseStroke))
    parts.push(text(SRC_X + SRC_W / 2, Y_LSE + 12, 'LSE', 'title'))
    parts.push(text(SRC_X + SRC_W / 2, Y_LSE + 24, fmtHz(c.lse.frequency_hz), 'small'))
    if (!c.lse.present) parts.push(text(SRC_X + SRC_W / 2, Y_LSE + 34, '(not fitted)', 'small'))

    // ---- PLL block ----
    parts.push(box(PLL_X, PLL_Y, PLL_W, PLL_H, 'rgba(59,130,246,0.1)', '#3b82f6'))
    parts.push(text(PLL_X + PLL_W / 2, PLL_Y + 16, 'PLL', 'title'))
    parts.push(text(PLL_X + PLL_W / 2, PLL_Y + 30, c.pll.source + ' ' + fmtPllParams(), 'small'))
    parts.push(text(PLL_X + PLL_W / 2, PLL_Y + 44, fmtHz(c.sysclk.frequency_hz), 'small'))

    // PLL → SYSCLK
    parts.push(line(PLL_X + PLL_W, PLL_Y + PLL_H / 2, SYS_X, SYS_Y + SYS_H / 2, '#3b82f6'))

    // ---- SYSCLK ----
    parts.push(box(SYS_X, SYS_Y, SYS_W, SYS_H, 'rgba(239,68,68,0.12)', '#ef4444'))
    parts.push(text(SYS_X + SYS_W / 2, SYS_Y + 12, 'SYSCLK', 'title'))
    parts.push(text(SYS_X + SYS_W / 2, SYS_Y + 24, fmtHz(c.sysclk.frequency_hz), 'small'))

    // ---- APB ----
    parts.push(box(APB_X, APB_Y, APB_W, APB_H, 'rgba(245,158,11,0.12)', '#f59e0b'))
    const apbHz = c.sysclk.frequency_hz / c.apb.prescaler
    parts.push(text(APB_X + APB_W / 2, APB_Y + 12, 'APB /' + c.apb.prescaler, 'title'))
    parts.push(text(APB_X + APB_W / 2, APB_Y + 22, fmtHz(apbHz), 'small'))

    // SYSCLK → APB
    parts.push(line(SYS_X + SYS_W, SYS_Y + SYS_H / 2 - 5, APB_X, APB_Y + APB_H / 2, '#f59e0b'))

    // ---- FreeRTOS Tick via SysTick ----
    parts.push(box(STK_X, STK_Y, STK_W, STK_H, 'rgba(168,85,247,0.12)', '#a855f7'))
    parts.push(text(STK_X + STK_W / 2, STK_Y + 12, 'SysTick', 'title'))
    parts.push(text(STK_X + STK_W / 2, STK_Y + 22, fmtHz(c.freertos_tick.frequency_hz), 'small'))

    // APB → SysTick
    parts.push(line(APB_X + APB_W, APB_Y + APB_H / 2, STK_X, STK_Y + STK_H / 2, '#a855f7'))

    // ---- IWDG (always from LSI) ----
    parts.push(box(IWDG_X, IWDG_Y, IWDG_W, IWDG_H, 'rgba(148,163,184,0.08)', '#64748b'))
    parts.push(text(IWDG_X + IWDG_W / 2, IWDG_Y + 18, 'IWDG (LSI)', 'small'))

    // LSI → IWDG
    parts.push(line(SRC_X + SRC_W, Y_LSI + SRC_H / 2, IWDG_X, IWDG_Y + IWDG_H / 2, '#64748b'))

    // ---- RTC (LSE or LSI) ----
    const rtcSrc = c.lse.present ? 'LSE' : 'LSI'
    const rtcFill = c.lse.present ? 'rgba(74,222,128,0.1)' : 'rgba(148,163,184,0.08)'
    const rtcStroke = c.lse.present ? '#4ade80' : '#64748b'
    parts.push(box(RTC_X, RTC_Y, RTC_W, RTC_H, rtcFill, rtcStroke))
    parts.push(text(RTC_X + RTC_W / 2, RTC_Y + 18, 'RTC (' + rtcSrc + ')', 'small'))

    // LSE/LSI → RTC
    if (c.lse.present) {
        parts.push(line(SRC_X + SRC_W, Y_LSE + SRC_H / 2, RTC_X, RTC_Y + RTC_H / 2, '#4ade80'))
    }

    return parts.join('')
})
</script>

<template>
    <div class="clock-tree">
        <div class="panel-title">Clock Tree</div>
        <svg
            :viewBox="`0 0 ${W} ${H}`"
            class="clock-svg"
            v-html="svgContent"
        ></svg>
        <div class="clock-legend">
            <span class="legend-item"><span class="legend-dot" style="background:#4ade80"></span> External fitted</span>
            <span class="legend-item"><span class="legend-dot" style="background:#94a3b8"></span> Internal / not fitted</span>
        </div>
    </div>
</template>

<style scoped>
.clock-tree {
    overflow: hidden;
}
.clock-svg {
    width: 100%;
    height: auto;
    display: block;
}
.clock-legend {
    display: flex; gap: 1rem; padding: 0.3rem 0.4rem; font-size: 0.6rem; color: var(--text-dim);
}
.legend-item { display: inline-flex; align-items: center; gap: 0.25rem; }
.legend-dot { width: 8px; height: 8px; border-radius: 2px; }
</style>
