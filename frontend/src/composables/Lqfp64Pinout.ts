/**
 * Lqfp64Pinout — Generic MCU pinout loader (LQFP-64 package).
 *
 * Derives physical pin layout, AF lookup table, power-pin set, and
 * reserved-pin set from a stm32-data-generated chip JSON.
 *
 * To support a different MCU, replace the import below with the
 * corresponding JSON file in src/data/mcu/.
 *
 * Data source: embassy-rs/stm32-data (chip JSON).
 */

import chipData from '../data/mcu/STM32G0B1RE.json'

// ---------------------------------------------------------------------------
// JSON shape (subset used by this module)
// ---------------------------------------------------------------------------

interface JsonPkgPin {
    position: string
    signals: string[]
}

interface JsonPackage {
    name: string
    package: string
    pins: JsonPkgPin[]
}

interface JsonPeriPin {
    pin: string
    signal: string
    af?: number
}

interface JsonPeripheral {
    name: string
    pins?: JsonPeriPin[]
}

interface JsonCore {
    name: string
    peripherals: JsonPeripheral[]
}

interface JsonChip {
    name: string
    packages: JsonPackage[]
    cores: JsonCore[]
}

const chip = chipData as unknown as JsonChip

// ---------------------------------------------------------------------------
// Public interfaces
// ---------------------------------------------------------------------------

/** AF assignment for a single pin signal */
export interface AfEntry {
    /** AF number (0-15) */
    af: number
    /** Peripheral signal name, e.g. "I2C1_SCL" */
    function: string
}

export interface PhysicalPin {
    /** Physical pin number (1-64) */
    num: number
    /** Pin ID, e.g. "PA0" or "VDD" */
    id: string
    /** Side: 0=top, 1=right, 2=bottom, 3=left */
    side: number
    /** Index on side (0-15) */
    idx: number
    /** True for power/ground/reset/boot pins (non-configurable) */
    isPower: boolean
    /** All AF entries this pin supports (from datasheet) */
    afs: AfEntry[]
}

/** Side labels for rendering */
export const SIDE_LABELS = ['top', 'right', 'bottom', 'left']

// ---------------------------------------------------------------------------
// AF table builder: invert peripheral→pin mapping to pin→[{af, function}]
// ---------------------------------------------------------------------------

/** Recognised power-pin IDs (V-prefixed or system pins). */
const V_PREFIX = /^V/

/** System pins reserved by SWD or oscillator blocks. */
const SYSTEM_PIN_IDS = new Set([
    'PA13', 'PA14',             // SWDIO, SWCLK
    'PF0',  'PF1',              // HSE OSC_IN, OSC_OUT
    'PC13', 'PC14', 'PC15',     // LSE OSC32
    'NRST', 'BOOT0',
])

function buildAfTable(): Record<string, AfEntry[]> {
    const table: Record<string, AfEntry[]> = {}

    for (const core of chip.cores) {
        for (const peri of core.peripherals) {
            if (!peri.pins) continue
            for (const pp of peri.pins) {
                if (pp.af === undefined) continue       // analog / no-AF signals
                if (!table[pp.pin]) table[pp.pin] = []

                const fn = `${peri.name}_${pp.signal}`
                const dup = table[pp.pin].some(e => e.af === pp.af && e.function === fn)
                if (!dup) {
                    table[pp.pin].push({ af: pp.af!, function: fn })
                }
            }
        }
    }

    // Sort each pin's AF list by AF number for consistent rendering
    for (const key of Object.keys(table)) {
        table[key].sort((a, b) => a.af - b.af || a.function.localeCompare(b.function))
    }

    return table
}

const AF_TABLE: Record<string, AfEntry[]> = buildAfTable()

// ---------------------------------------------------------------------------
// Package pinout builder
// ---------------------------------------------------------------------------

/**
 * Find the first LQFP64 package entry in chip JSON.
 * Falls back to the first package if no LQFP64 entry exists.
 */
function findLqfp64Package(): JsonPackage | null {
    const lqfp = chip.packages.find(p => p.package === 'LQFP64')
    if (lqfp) return lqfp
    // Fallback: try prefix match (e.g. "LQFP-64")
    const alt = chip.packages.find(p => p.package.toUpperCase().includes('LQFP'))
    return alt ?? chip.packages[0] ?? null
}

function buildLqfp64Pins(): PhysicalPin[] {
    const pkg = findLqfp64Package()
    if (!pkg) return []

    const raw = pkg.pins
    const count = raw.length
    const perSide = Math.floor(count / 4)

    const pins: PhysicalPin[] = []

    for (let i = 0; i < count; i++) {
        const signals = raw[i].signals
        // Primary signal is the first in the array; secondary signals
        // (e.g. UCPD remap) share the same physical pad.
        const pinId = signals[0]
        const isPower = V_PREFIX.test(pinId) || pinId === 'NRST' || pinId === 'BOOT0'

        // side: 0=top, 1=right, 2=bottom, 3=left (counter-clockwise)
        const side = Math.floor(i / perSide) % 4
        const offset = i % perSide

        // Bottom and Left edges run in reverse direction
        let idx: number
        if (side === 0 || side === 1) {
            idx = offset                       // top: L→R, right: T→B
        } else {
            idx = perSide - 1 - offset         // bottom: R→L, left: B→T
        }

        pins.push({
            num: i + 1,
            id: pinId,
            side,
            idx,
            isPower,
            afs: AF_TABLE[pinId] ?? [],
        })

        // Secondary signals share the same physical pad.
        // They get their own AF list from the global AF_TABLE.
        for (let s = 1; s < signals.length; s++) {
            pins.push({
                num: i + 1,
                id: signals[s],
                side,
                idx,
                isPower,
                afs: AF_TABLE[signals[s]] ?? [],
            })
        }
    }

    return pins
}

// ---------------------------------------------------------------------------
// Power / reserved pin detection
// ---------------------------------------------------------------------------

function detectPowerPins(pins: PhysicalPin[]): Set<string> {
    const s = new Set<string>()
    for (const p of pins) {
        if (p.isPower) s.add(p.id)
    }
    // Always include NRST and BOOT0 (may not appear in package data)
    s.add('NRST')
    s.add('BOOT0')
    return s
}

function detectReservedPins(pins: PhysicalPin[]): Set<string> {
    const s = new Set<string>()
    for (const p of pins) {
        if (SYSTEM_PIN_IDS.has(p.id)) s.add(p.id)
    }
    // Ensure SWD / OSC pins are reserved even if they share a pad
    for (const id of SYSTEM_PIN_IDS) {
        if (id === 'NRST' || id === 'BOOT0') continue   // handled separately
        s.add(id)
    }
    return s
}

// ---------------------------------------------------------------------------
// Exports (computed once at module load)
// ---------------------------------------------------------------------------

/** Complete LQFP-64 pinout array (includes alias entries for shared pads). */
export const LQFP64_PINS: PhysicalPin[] = buildLqfp64Pins()

/** Lookup map: pin ID → PhysicalPin (primary position only). */
export const LQFP64_MAP: Map<string, PhysicalPin> = (() => {
    const m = new Map<string, PhysicalPin>()
    for (const p of LQFP64_PINS) {
        if (!m.has(p.id)) m.set(p.id, p)        // keep first (primary) occurrence
    }
    return m
})()

/** Non-configurable power / ground / system pins. */
export const POWER_PINS: Set<string> = detectPowerPins(LQFP64_PINS)

/** Debug / oscillator / boot pins reserved from user assignment. */
export const RESERVED_PINS: Set<string> = detectReservedPins(LQFP64_PINS)
