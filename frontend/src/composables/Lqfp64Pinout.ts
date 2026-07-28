/**
 * Lqfp64Pinout — STM32G0B1RE LQFP-64 physical pin layout.
 *
 * Pinout data source: embassy-rs/stm32-data-generated (chip JSON).
 * AF mappings sourced from STM32G0B1 datasheet DS13560.
 *
 * Re-generate with: python scripts/stm32_gen_pinout.py path/to/STM32G0B1RE.json
 */

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

/**
 * STM32G0B1RE common AF lookup table.
 * Key: pin ID (e.g. "PA0"), Value: list of AF entries.
 * This is a curated subset of the full AF table — the most commonly
 * used peripheral functions. Full AF table can be generated from
 * stm32-data JSON via `scripts/stm32_gen_pinout.py`.
 */
const AF_TABLE: Record<string, AfEntry[]> = {
    /* ---- Port A ---- */
    PA0: [
        { af: 1, function: 'USART2_CTS' }, { af: 2, function: 'TIM2_CH1' },
        { af: 3, function: 'I2C3_SCL' },
    ],
    PA1: [
        { af: 1, function: 'USART2_RTS_DE' }, { af: 2, function: 'TIM2_CH2' },
        { af: 3, function: 'I2C3_SMBA' },
    ],
    PA2: [
        { af: 1, function: 'USART2_TX' }, { af: 2, function: 'TIM2_CH3' },
    ],
    PA3: [
        { af: 1, function: 'USART2_RX' }, { af: 2, function: 'TIM2_CH4' },
    ],
    PA4: [
        { af: 0, function: 'SPI1_NSS' }, { af: 2, function: 'TIM14_CH1' },
        { af: 6, function: 'LPUART1_TX' },
    ],
    PA5: [
        { af: 0, function: 'SPI1_SCK' },
    ],
    PA6: [
        { af: 0, function: 'SPI1_MISO' }, { af: 2, function: 'TIM3_CH1' },
        { af: 6, function: 'LPUART1_CTS' },
    ],
    PA7: [
        { af: 0, function: 'SPI1_MOSI' }, { af: 2, function: 'TIM3_CH2' },
    ],
    PA8: [
        { af: 2, function: 'TIM1_CH1' },
    ],
    PA9: [
        { af: 1, function: 'USART1_TX' }, { af: 2, function: 'TIM1_CH2' },
        { af: 4, function: 'I2C2_SCL' },
    ],
    PA10: [
        { af: 1, function: 'USART1_RX' }, { af: 2, function: 'TIM1_CH3' },
        { af: 4, function: 'I2C2_SDA' },
    ],
    PA11: [
        { af: 1, function: 'USART1_CTS' }, { af: 2, function: 'TIM1_CH4' },
    ],
    PA12: [
        { af: 1, function: 'USART1_RTS_DE' },
    ],
    PA13: [
        // SWDIO — reserved, no user AF
    ],
    PA14: [
        // SWCLK — reserved, no user AF
    ],
    PA15: [
        { af: 0, function: 'SPI1_NSS' }, { af: 2, function: 'TIM2_CH1' },
    ],

    /* ---- Port B ---- */
    PB0: [
        { af: 2, function: 'TIM3_CH3' },
    ],
    PB1: [
        { af: 2, function: 'TIM3_CH4' },
    ],
    PB2: [
        { af: 1, function: 'I2C3_SMBA' },
    ],
    PB3: [
        { af: 0, function: 'SPI1_SCK' }, { af: 1, function: 'USART1_RTS_DE' },
        { af: 2, function: 'TIM2_CH2' },
    ],
    PB4: [
        { af: 0, function: 'SPI1_MISO' }, { af: 1, function: 'USART1_CTS' },
        { af: 2, function: 'TIM3_CH1' },
    ],
    PB5: [
        { af: 0, function: 'SPI1_MOSI' }, { af: 2, function: 'TIM3_CH2' },
    ],
    PB6: [
        { af: 0, function: 'USART1_TX' }, { af: 1, function: 'I2C1_SCL' },
    ],
    PB7: [
        { af: 0, function: 'USART1_RX' }, { af: 1, function: 'I2C1_SDA' },
    ],
    PB8: [
        { af: 1, function: 'I2C1_SCL' }, { af: 2, function: 'TIM16_CH1' },
    ],
    PB9: [
        { af: 1, function: 'I2C1_SDA' }, { af: 2, function: 'TIM17_CH1' },
    ],
    PB10: [
        { af: 1, function: 'I2C2_SCL' }, { af: 2, function: 'TIM2_CH3' },
    ],
    PB11: [
        { af: 1, function: 'I2C2_SDA' }, { af: 2, function: 'TIM2_CH4' },
    ],
    PB12: [
        { af: 0, function: 'SPI2_NSS' },
    ],
    PB13: [
        { af: 0, function: 'SPI2_SCK' }, { af: 1, function: 'I2C2_SCL' },
    ],
    PB14: [
        { af: 0, function: 'SPI2_MISO' }, { af: 1, function: 'I2C2_SDA' },
    ],
    PB15: [
        { af: 0, function: 'SPI2_MOSI' },
    ],

    /* ---- Port C ---- */
    PC0: [
        { af: 1, function: 'LPUART1_RX' },
    ],
    PC1: [
        { af: 1, function: 'LPUART1_TX' },
    ],
    PC4: [
        { af: 1, function: 'LPUART1_TX' },
    ],
    PC5: [
        { af: 1, function: 'LPUART1_RX' },
    ],
    PC6: [
        { af: 1, function: 'USART2_TX' },
    ],
    PC7: [
        { af: 1, function: 'USART2_RX' },
    ],
    PC10: [
        { af: 1, function: 'SPI3_SCK' },
    ],
    PC11: [
        { af: 1, function: 'SPI3_MISO' },
    ],
    PC12: [
        { af: 1, function: 'SPI3_MOSI' },
    ],
    PC13: [
        // LSE/RTC — typically reserved
    ],
    PC14: [
        // LSE/RTC — typically reserved
    ],
    PC15: [
        // LSE/RTC — typically reserved
    ],

    /* ---- Port D ---- */
    PD0: [
        { af: 0, function: 'SPI2_NSS' },
    ],
    PD1: [
        { af: 0, function: 'SPI2_SCK' },
    ],
    PD2: [
        { af: 0, function: 'SPI2_MISO' },
    ],
    PD3: [
        { af: 0, function: 'SPI2_MOSI' },
    ],
    PD4: [
        { af: 0, function: 'USART2_CTS' },
    ],
    PD5: [
        { af: 0, function: 'USART2_TX' },
    ],
    PD6: [
        { af: 0, function: 'USART2_RX' },
    ],

    /* ---- Port F ---- */
    PF0: [
        // HSE OSC_IN — typically reserved
    ],
    PF1: [
        // HSE OSC_OUT — typically reserved
    ],
}

/** Power/ground/reset/boot pins (non-configurable) */
export const POWER_PINS = new Set([
    'VDD', 'VSS', 'VDDA', 'VSSA', 'VBAT', 'VREF+',
    'NRST', 'BOOT0',
])

/** Reserved system pins (SWD + LSE/HSE) */
export const RESERVED_PINS = new Set([
    'PA13', 'PA14',     // SWDIO, SWCLK
    'PF0',  'PF1',      // HSE OSC
    'PC13', 'PC14', 'PC15', // LSE OSC
    'NRST', 'BOOT0',
])

/**
 * LQFP-64 pinout for STM32G0B1RE.
 * Pin numbering: counter-clockwise from pin 1 (top-left dot).
 *
 * Layout:
 *   Top:    1..16   (left → right)
 *   Right:  17..32  (top → bottom)
 *   Bottom: 33..48  (right → left)
 *   Left:   49..64  (bottom → top)
 */
export const LQFP64_PINS: PhysicalPin[] = [
    // ---- Top edge : pins 1-16 ----
    { num:  1, id: 'PC11',    side: 0, idx:  0, isPower: false, afs: AF_TABLE.PC11 ?? [] },
    { num:  2, id: 'PC12',    side: 0, idx:  1, isPower: false, afs: AF_TABLE.PC12 ?? [] },
    { num:  3, id: 'PC13',    side: 0, idx:  2, isPower: false, afs: AF_TABLE.PC13 ?? [] },
    { num:  4, id: 'PC14',    side: 0, idx:  3, isPower: false, afs: AF_TABLE.PC14 ?? [] },
    { num:  5, id: 'PC15',    side: 0, idx:  4, isPower: false, afs: AF_TABLE.PC15 ?? [] },
    { num:  6, id: 'VBAT',    side: 0, idx:  5, isPower: true,  afs: [] },
    { num:  7, id: 'VREF+',   side: 0, idx:  6, isPower: true,  afs: [] },
    { num:  8, id: 'VDD',     side: 0, idx:  7, isPower: true,  afs: [] },
    { num:  9, id: 'VSS',     side: 0, idx:  8, isPower: true,  afs: [] },
    { num: 10, id: 'PF0',     side: 0, idx:  9, isPower: false, afs: AF_TABLE.PF0 ?? [] },
    { num: 11, id: 'PF1',     side: 0, idx: 10, isPower: false, afs: AF_TABLE.PF1 ?? [] },
    { num: 12, id: 'PF2',     side: 0, idx: 11, isPower: false, afs: [] },
    { num: 13, id: 'PC0',     side: 0, idx: 12, isPower: false, afs: AF_TABLE.PC0 ?? [] },
    { num: 14, id: 'PC1',     side: 0, idx: 13, isPower: false, afs: AF_TABLE.PC1 ?? [] },
    { num: 15, id: 'PC2',     side: 0, idx: 14, isPower: false, afs: [] },
    { num: 16, id: 'PC3',     side: 0, idx: 15, isPower: false, afs: [] },

    // ---- Right edge : pins 17-32 ----
    { num: 17, id: 'PA0',     side: 1, idx:  0, isPower: false, afs: AF_TABLE.PA0 ?? [] },
    { num: 18, id: 'PA1',     side: 1, idx:  1, isPower: false, afs: AF_TABLE.PA1 ?? [] },
    { num: 19, id: 'PA2',     side: 1, idx:  2, isPower: false, afs: AF_TABLE.PA2 ?? [] },
    { num: 20, id: 'PA3',     side: 1, idx:  3, isPower: false, afs: AF_TABLE.PA3 ?? [] },
    { num: 21, id: 'PA4',     side: 1, idx:  4, isPower: false, afs: AF_TABLE.PA4 ?? [] },
    { num: 22, id: 'PA5',     side: 1, idx:  5, isPower: false, afs: AF_TABLE.PA5 ?? [] },
    { num: 23, id: 'PA6',     side: 1, idx:  6, isPower: false, afs: AF_TABLE.PA6 ?? [] },
    { num: 24, id: 'PA7',     side: 1, idx:  7, isPower: false, afs: AF_TABLE.PA7 ?? [] },
    { num: 25, id: 'PC4',     side: 1, idx:  8, isPower: false, afs: AF_TABLE.PC4 ?? [] },
    { num: 26, id: 'PC5',     side: 1, idx:  9, isPower: false, afs: AF_TABLE.PC5 ?? [] },
    { num: 27, id: 'PB0',     side: 1, idx: 10, isPower: false, afs: AF_TABLE.PB0 ?? [] },
    { num: 28, id: 'PB1',     side: 1, idx: 11, isPower: false, afs: AF_TABLE.PB1 ?? [] },
    { num: 29, id: 'PB2',     side: 1, idx: 12, isPower: false, afs: AF_TABLE.PB2 ?? [] },
    { num: 30, id: 'PB10',    side: 1, idx: 13, isPower: false, afs: AF_TABLE.PB10 ?? [] },
    { num: 31, id: 'PB11',    side: 1, idx: 14, isPower: false, afs: AF_TABLE.PB11 ?? [] },
    { num: 32, id: 'PB12',    side: 1, idx: 15, isPower: false, afs: AF_TABLE.PB12 ?? [] },

    // ---- Bottom edge : pins 33-48 ----
    { num: 33, id: 'PB13',    side: 2, idx: 15, isPower: false, afs: AF_TABLE.PB13 ?? [] },
    { num: 34, id: 'PB14',    side: 2, idx: 14, isPower: false, afs: AF_TABLE.PB14 ?? [] },
    { num: 35, id: 'PB15',    side: 2, idx: 13, isPower: false, afs: AF_TABLE.PB15 ?? [] },
    { num: 36, id: 'PA8',     side: 2, idx: 12, isPower: false, afs: AF_TABLE.PA8 ?? [] },
    { num: 37, id: 'PA9',     side: 2, idx: 11, isPower: false, afs: AF_TABLE.PA9 ?? [] },
    { num: 38, id: 'PC6',     side: 2, idx: 10, isPower: false, afs: AF_TABLE.PC6 ?? [] },
    { num: 39, id: 'PC7',     side: 2, idx:  9, isPower: false, afs: AF_TABLE.PC7 ?? [] },
    { num: 40, id: 'PD8',     side: 2, idx:  8, isPower: false, afs: [] },
    { num: 41, id: 'PD9',     side: 2, idx:  7, isPower: false, afs: [] },
    { num: 42, id: 'PA10',    side: 2, idx:  6, isPower: false, afs: AF_TABLE.PA10 ?? [] },
    { num: 43, id: 'PA11',    side: 2, idx:  5, isPower: false, afs: AF_TABLE.PA11 ?? [] },
    { num: 44, id: 'PA12',    side: 2, idx:  4, isPower: false, afs: AF_TABLE.PA12 ?? [] },
    { num: 45, id: 'PA13',    side: 2, idx:  3, isPower: false, afs: AF_TABLE.PA13 ?? [] },
    { num: 46, id: 'PA14',    side: 2, idx:  2, isPower: false, afs: AF_TABLE.PA14 ?? [] },
    { num: 47, id: 'PA15',    side: 2, idx:  1, isPower: false, afs: AF_TABLE.PA15 ?? [] },
    { num: 48, id: 'PC8',     side: 2, idx:  0, isPower: false, afs: [] },

    // ---- Left edge : pins 49-64 ----
    { num: 49, id: 'PC9',     side: 3, idx: 15, isPower: false, afs: [] },
    { num: 50, id: 'PD0',     side: 3, idx: 14, isPower: false, afs: AF_TABLE.PD0 ?? [] },
    { num: 51, id: 'PD1',     side: 3, idx: 13, isPower: false, afs: AF_TABLE.PD1 ?? [] },
    { num: 52, id: 'PD2',     side: 3, idx: 12, isPower: false, afs: AF_TABLE.PD2 ?? [] },
    { num: 53, id: 'PD3',     side: 3, idx: 11, isPower: false, afs: AF_TABLE.PD3 ?? [] },
    { num: 54, id: 'PD4',     side: 3, idx: 10, isPower: false, afs: AF_TABLE.PD4 ?? [] },
    { num: 55, id: 'PD5',     side: 3, idx:  9, isPower: false, afs: AF_TABLE.PD5 ?? [] },
    { num: 56, id: 'PD6',     side: 3, idx:  8, isPower: false, afs: AF_TABLE.PD6 ?? [] },
    { num: 57, id: 'PB3',     side: 3, idx:  7, isPower: false, afs: AF_TABLE.PB3 ?? [] },
    { num: 58, id: 'PB4',     side: 3, idx:  6, isPower: false, afs: AF_TABLE.PB4 ?? [] },
    { num: 59, id: 'PB5',     side: 3, idx:  5, isPower: false, afs: AF_TABLE.PB5 ?? [] },
    { num: 60, id: 'PB6',     side: 3, idx:  4, isPower: false, afs: AF_TABLE.PB6 ?? [] },
    { num: 61, id: 'PB7',     side: 3, idx:  3, isPower: false, afs: AF_TABLE.PB7 ?? [] },
    { num: 62, id: 'PB8',     side: 3, idx:  2, isPower: false, afs: AF_TABLE.PB8 ?? [] },
    { num: 63, id: 'PB9',     side: 3, idx:  1, isPower: false, afs: AF_TABLE.PB9 ?? [] },
    { num: 64, id: 'PC10',    side: 3, idx:  0, isPower: false, afs: AF_TABLE.PC10 ?? [] },
]

/** Map from pin ID (e.g. "PA0") → PhysicalPin */
export const LQFP64_MAP: Map<string, PhysicalPin> = new Map(
    LQFP64_PINS.map(p => [p.id, p])
)
