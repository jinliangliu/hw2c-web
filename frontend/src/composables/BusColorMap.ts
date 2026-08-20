/**
 * BusColorMap — unified bus type → color mapping used across all components.
 *
 * Colors match the CSS variables defined in style.css tag-* classes.
 */

import { POWER_PINS, RESERVED_PINS } from './Lqfp64Pinout'

export { POWER_PINS, RESERVED_PINS }

export const BUS_COLOR: Record<string, string> = {
    I2C:   '#3b82f6',
    SPI:   '#10b981',
    UART:  '#f59e0b',
    USART: '#f59e0b',
    GPIO:  '#8b5cf6',
    POWER: '#ef4444',
    SWD:   '#6b7280',
}

/** CSS class name for a bus type tag (matches style.css .tag-*) */
export function busTagClass(busType: string): string {
    return `tag-${busType.toLowerCase()}`
}

/** Extract bus family from a bus name string, e.g. "SPI1" → "SPI", "USART2" → "UART" */
export function extractBusType(raw: string | null | undefined): string {
    if (!raw) return 'GPIO'
    const upper = raw.toUpperCase()
    if (upper.startsWith('I2C'))   return 'I2C'
    if (upper.startsWith('SPI'))   return 'SPI'
    if (upper.startsWith('USART')) return 'UART'
    if (upper.startsWith('UART'))  return 'UART'
    if (upper.startsWith('SWD'))   return 'SWD'
    return 'GPIO'
}

/** Extract bus index number, e.g. "SPI2" → 2 */
export function extractBusIndex(raw: string | null | undefined): number {
    if (!raw) return 0
    const m = raw.match(/(\d+)$/)
    return m ? parseInt(m[1], 10) : 0
}

/** Get color for a pin based on its function string */
export function pinBusColor(func: string | null | undefined): string {
    if (!func) return BUS_COLOR.GPIO
    const upper = func.toUpperCase()
    if (upper.includes('SWD') || upper.includes('SWCLK') || upper.includes('SWDIO'))
        return BUS_COLOR.SWD
    if (upper.startsWith('I2C'))   return BUS_COLOR.I2C
    if (upper.startsWith('SPI'))   return BUS_COLOR.SPI
    if (upper.startsWith('USART')) return BUS_COLOR.UART
    if (upper.startsWith('UART'))  return BUS_COLOR.UART
    if (upper.startsWith('GPIO'))  return BUS_COLOR.GPIO
    return BUS_COLOR.GPIO
}

/** Check for pin function conflicts: two pins sharing the same bus+signal pair */
export interface PinConflict {
    signal: string
    pinA: string
    pinB: string
}

export function detectConflicts(pins: { id: string; function: string }[]): PinConflict[] {
    const conflicts: PinConflict[] = []
    const seen = new Map<string, string>()
    for (const pin of pins) {
        if (pin.function && pin.function !== 'GPIO_INPUT' && pin.function !== 'GPIO_OUTPUT') {
            const key = pin.function
            if (seen.has(key)) {
                conflicts.push({ signal: key, pinA: seen.get(key)!, pinB: pin.id })
            } else {
                seen.set(key, pin.id)
            }
        }
    }
    return conflicts
}
