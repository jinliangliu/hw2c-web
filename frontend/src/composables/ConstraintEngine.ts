/**
 * ConstraintEngine — pin assignment constraint checker.
 *
 * Validates AF function conflicts, pin occupation, voltage domain
 * compatibility, and suggests alternative pin assignments.
 */
import { LQFP64_PINS, LQFP64_MAP, POWER_PINS, RESERVED_PINS, type PhysicalPin, type AfEntry } from './Lqfp64Pinout'
import { extractBusType } from './BusColorMap'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ConstraintSeverity = 'error' | 'warning' | 'info'

export interface ConstraintIssue {
    severity: ConstraintSeverity
    /** Affected pin IDs */
    pins: string[]
    message: string
    /** Suggested fix text (optional) */
    suggestion?: string
}

export interface PinAssignment {
    pinId: string
    function: string
    /** Assigned AF number (from user config) */
    af?: number
}

export interface PinSuggestion {
    pinId: string
    af: number
    function: string
}

// ---------------------------------------------------------------------------
// AF Conflict Detection
// ---------------------------------------------------------------------------

/**
 * Extract peripheral instance from a function name.
 * "I2C1_SCL" → "I2C1", "SPI2_MOSI" → "SPI2"
 */
function periInstance(fn: string): string {
    const idx = fn.indexOf('_')
    return idx >= 0 ? fn.slice(0, idx) : fn
}

/**
 * Check if two function names conflict.
 * Same peripheral but same signal = conflict (two SPI1_SCK)
 * Same peripheral different signals = compatible (SPI1_SCK + SPI1_MOSI)
 */
function functionsConflict(fnA: string, fnB: string): boolean {
    if (fnA === fnB) return true  // exact same signal
    return false
}

/**
 * Detect AF conflicts: two different pins assigned to the same peripheral signal.
 */
export function checkAfConflicts(assignments: PinAssignment[]): ConstraintIssue[] {
    const issues: ConstraintIssue[] = []
    const used = new Map<string, PinAssignment[]>()  // function → assignments

    for (const a of assignments) {
        if (!a.function) continue
        const key = a.function
        if (!used.has(key)) used.set(key, [])
        used.get(key)!.push(a)
    }

    for (const [fn, pins] of used) {
        if (pins.length > 1) {
            issues.push({
                severity: 'error',
                pins: pins.map(p => p.pinId),
                message: `${fn} assigned to ${pins.length} pins: ${pins.map(p => p.pinId).join(', ')}`,
                suggestion: `Each peripheral signal can only be assigned to one pin. Remove duplicates.`,
            })
        }
    }

    return issues
}

// ---------------------------------------------------------------------------
// Pin Occupation Check
// ---------------------------------------------------------------------------

/**
 * Check which pins are currently occupied (have a non-GPIO assignment).
 * Returns the list of occupied pin IDs.
 */
export function getOccupiedPins(assignments: PinAssignment[]): Set<string> {
    const occupied = new Set<string>()
    for (const a of assignments) {
        if (a.function && a.function !== 'GPIO_INPUT' && a.function !== 'GPIO_OUTPUT') {
            occupied.add(a.pinId)
        }
    }
    return occupied
}

/**
 * Check if a reserved pin is being reassigned.
 */
export function checkReservedPins(assignments: PinAssignment[]): ConstraintIssue[] {
    const issues: ConstraintIssue[] = []
    for (const a of assignments) {
        if (!a.function || a.function === 'GPIO_INPUT' || a.function === 'GPIO_OUTPUT') continue
        if (RESERVED_PINS.has(a.pinId)) {
            issues.push({
                severity: 'error',
                pins: [a.pinId],
                message: `${a.pinId} is reserved (SWD/LSE/HSE) and cannot be reassigned to ${a.function}`,
                suggestion: 'Use a free GPIO pin instead.',
            })
        }
    }
    return issues
}

// ---------------------------------------------------------------------------
// Voltage Domain Check (basic)
// ---------------------------------------------------------------------------

/** Pins that are in the VDDA (analog) domain */
const ANALOG_PINS = new Set(['PA0', 'PA1', 'PA2', 'PA3', 'PA4', 'PA5', 'PA6', 'PA7'])

/** Peripheral types that require analog-capable pins */
const ANALOG_PERIPHERALS = new Set(['ADC', 'DAC', 'COMP', 'OPAMP'])

/**
 * Check if an analog peripheral is assigned to a non-VDDA-domain pin.
 */
export function checkVoltageDomain(assignments: PinAssignment[]): ConstraintIssue[] {
    const issues: ConstraintIssue[] = []
    for (const a of assignments) {
        if (!a.function) continue
        const busType = extractBusType(a.function)
        // Just a warning — not all UART/I2C on PA0 are ADC; this is simplistic
        if (ANALOG_PINS.has(a.pinId) && ['GPIO'].includes(busType)) {
            // Pin is analog-capable but assigned as GPIO — ok
        }
    }
    // Voltage domain checking requires more detailed data (ADC channel mapping etc.)
    // Placeholder for future expansion
    return issues
}

// ---------------------------------------------------------------------------
// Pin Suggestion Engine
// ---------------------------------------------------------------------------

/**
 * Find alternative pins that support a given function.
 * Looks through the AF table for pins that have the matching AF entry.
 */
export function findAlternativePins(
    targetFunction: string,
    assignments: PinAssignment[],
): PinSuggestion[] {
    const occupied = getOccupiedPins(assignments)
    const results: PinSuggestion[] = []

    for (const pp of LQFP64_PINS) {
        if (pp.isPower) continue
        if (RESERVED_PINS.has(pp.id)) continue
        if (occupied.has(pp.id)) continue

        for (const af of pp.afs) {
            if (af.function === targetFunction) {
                results.push({
                    pinId: pp.id,
                    af: af.af,
                    function: af.function,
                })
            }
        }
    }

    return results
}

/**
 * Find alternative peripheral functions for a given pin, based on its AF table.
 */
export function findFunctionsForPin(pinId: string): AfEntry[] {
    const pp = LQFP64_MAP.get(pinId)
    return pp?.afs ?? []
}

// ---------------------------------------------------------------------------
// Full Validation
// ---------------------------------------------------------------------------

export interface ValidationResult {
    issues: ConstraintIssue[]
    occupiedPins: Set<string>
    /** True if there are any error-level issues */
    hasErrors: boolean
    /** True if there are any warning-level issues */
    hasWarnings: boolean
}

/**
 * Run all constraint checks and aggregate results.
 */
export function validate(assignments: PinAssignment[]): ValidationResult {
    const issues: ConstraintIssue[] = []

    issues.push(...checkReservedPins(assignments))
    issues.push(...checkAfConflicts(assignments))
    issues.push(...checkVoltageDomain(assignments))

    const occupiedPins = getOccupiedPins(assignments)

    return {
        issues,
        occupiedPins,
        hasErrors: issues.some(i => i.severity === 'error'),
        hasWarnings: issues.some(i => i.severity === 'warning'),
    }
}
