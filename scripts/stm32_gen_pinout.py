#!/usr/bin/env python3
"""
Convert stm32-data-generated chip JSON to TypeScript pinout definitions.

Usage:
    python scripts/stm32_gen_pinout.py STM32G0B1RE.json > ../src/composables/Lqfp64Pinout.ts

Input:  A chip JSON file from embassy-rs/stm32-data-generated (data/chips/STM32G0B1RE.json)
Output: TypeScript module with PhysicalPin[] and AF mapping data ready for PinChip.vue
"""

import json
import sys
from pathlib import Path
from typing import Any

# ---- Constants ----

POWER_PIN_IDS = {
    "VDD", "VSS", "VDDA", "VSSA", "VBAT", "VREF+", "VREF-",
    "NRST", "BOOT0",
}

HEADER = """\
/**
 * Lqfp64Pinout — STM32G0B1RE LQFP-64 physical pin layout.
 *
 * Auto-generated from stm32-data by scripts/stm32_gen_pinout.py.
 * Do not edit by hand.
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
    /** All AF entries this pin supports */
    afs: AfEntry[]
}

/** Side labels for rendering */
export const SIDE_LABELS = ['top', 'right', 'bottom', 'left']
"""


def compute_side(num: int) -> tuple[int, int]:
    """Return (side, idx) for LQFP-64 pin numbering (CCW from pin 1)."""
    if 1 <= num <= 16:
        return 0, num - 1         # top, left→right
    elif 17 <= num <= 32:
        return 1, num - 17        # right, top→bottom
    elif 33 <= num <= 48:
        return 2, 47 - num        # bottom, right→left
    elif 49 <= num <= 64:
        return 3, 63 - num        # left, bottom→top
    raise ValueError(f"Invalid LQFP-64 pin number: {num}")


def ts_esc(s: str) -> str:
    """Escape a string for TypeScript source."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


def generate_pinout(chip_data: dict[str, Any]) -> str:
    """Generate the complete TypeScript file."""
    chip_name = chip_data.get("name", "UNKNOWN")
    packages = chip_data.get("packages", [])

    # Find LQFP-64 package
    lqfp = None
    for pkg in packages:
        if pkg.get("package") == "LQFP64":
            lqfp = pkg
            break

    if not lqfp:
        sys.stderr.write(f"WARNING: No LQFP64 package found for {chip_name}\n")
        # Try first package as fallback
        lqfp = packages[0] if packages else {"pins": []}

    pins = lqfp.get("pins", [])

    # Build AF lookup from chip-level pins data
    af_map: dict[str, list[dict[str, Any]]] = {}
    raw_pins = chip_data.get("pins", [])
    for pin_entry in raw_pins:
        pin_name = pin_entry.get("name", "")
        if not pin_name:
            continue
        signals = pin_entry.get("signals", [])
        afs: list[dict[str, Any]] = []
        for sig in signals:
            afs.append({
                "af": sig.get("af", 0),
                "function": sig.get("function", ""),
            })
        af_map[pin_name] = afs

    # Generate TypeScript
    lines: list[str] = []
    lines.append(f"// Chip: {chip_name}")
    lines.append(HEADER)
    lines.append(f"\n/** LQFP-64 pinout for {chip_name} */")
    lines.append("export const LQFP64_PINS: PhysicalPin[] = [")

    ts_entries: list[str] = []

    for pin_entry in pins:
        position = int(pin_entry["position"])
        signals = pin_entry.get("signals", [])
        # Use first signal as primary pin ID
        pin_id = signals[0] if signals else "???"

        side, idx = compute_side(position)
        is_power = pin_id in POWER_PIN_IDS

        # Get AF entries for this pin
        afs = af_map.get(pin_id, [])

        if afs:
            af_lines = ", ".join(
                f'{{ af: {a["af"]}, function: "{ts_esc(a["function"])}" }}'
                for a in afs
            )
            af_str = f"[{af_lines}]"
        else:
            af_str = "[]"

        ts_entries.append(
            f'    {{ num: {position:2d}, id: "{pin_id:6s}", side: {side}, idx: {idx:2d},'
            f' isPower: {"true " if is_power else "false"}, afs: {af_str} }},'
        )

    lines.extend(ts_entries)
    lines.append("]")
    lines.append("")
    lines.append("/** Map from pin ID (e.g. \"PA0\") => PhysicalPin */")
    lines.append("export const LQFP64_MAP: Map<string, PhysicalPin> = new Map(")
    lines.append("    LQFP64_PINS.map(p => [p.id, p])")
    lines.append(")")
    lines.append("")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} path/to/STM32G0B1RE.json", file=sys.stderr)
        sys.exit(1)

    json_path = Path(sys.argv[1])
    if not json_path.exists():
        print(f"Error: file not found: {json_path}", file=sys.stderr)
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        chip_data = json.load(f)

    output = generate_pinout(chip_data)
    print(output)


if __name__ == "__main__":
    main()
