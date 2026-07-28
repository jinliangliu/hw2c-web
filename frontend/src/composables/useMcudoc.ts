/**
 * useMcudoc — Datasheet / reference manual PDF path lookup.
 *
 * PDFs stored in public/docs/ are served as static assets by Vite.
 * To add a new MCU:
 *   1. Drop datasheet + RM PDF into public/docs/
 *   2. Add a new branch in getMcuDocUrls() below
 */
import chipData from '../data/mcu/STM32G0B1RE.json'

export interface McuDocUrls {
    datasheet_url: string | null
    reference_manual_url: string | null
}

/**
 * Resolve local PDF paths for the given MCU part.
 * Files are served from /docs/ (Vite public directory).
 */
export function getMcuDocUrls(part: string): McuDocUrls {
    const name = (chipData as any).name ?? ''
    if (name && part.toUpperCase().startsWith(name.toUpperCase())) {
        return {
            datasheet_url: '/docs/STM32G0B1_datasheet.pdf',
            reference_manual_url: '/docs/STM32G0B1_RM0444.pdf',
        }
    }
    return { datasheet_url: null, reference_manual_url: null }
}
