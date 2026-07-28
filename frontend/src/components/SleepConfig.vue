<script setup lang="ts">
/**
 * SleepConfig.vue — Low-power strategy configuration panel.
 *
 * Simplified three-level abstraction:
 *   - Low Power Run: reduced clock + regulator VOS
 *   - Sleep: CPU stopped, peripherals alive (SLEEP mode)
 *   - STOP: deep sleep with configurable wakeup sources
 */
import { ref, computed } from 'vue'
import type { SleepModel } from '../composables/useHardwareModel'

/* ---- Wakeup source types ---- */
interface WakeupSource {
    type: 'gpio' | 'rtc_alarm' | 'rtc_wakeup' | 'lpuart' | 'iwdg'
    pin?: string
    edge?: 'rising' | 'falling' | 'both'
    period_s?: number
}

const props = defineProps<{
    sleep: SleepModel | null
}>()

const emit = defineEmits<{
    (e: 'update-sleep', sleep: SleepModel): void
}>()

/* ---- Local reactive form state ---- */
const enabled = ref(props.sleep?.enabled ?? false)
const mode = ref<string>(
    props.sleep?.mode === 'LowPowerRun' || props.sleep?.mode === 'SLEEP' || props.sleep?.mode === 'STOP'
        ? props.sleep.mode
        : 'SLEEP'
)
const enterOnExit = ref(props.sleep?.enter_on_exit ?? false)
const regulatorVos = ref<number>(props.sleep?.regulator_voltage_scale ?? 2)
const flashPowerDown = ref(props.sleep?.flash_power_down ?? false)
const wakeupSources = ref<WakeupSource[]>(props.sleep?.wakeup_sources ?? [])

/* ---- Wakeup source form ---- */
const showAddWakeup = ref(false)
const newWuType = ref<WakeupSource['type']>('gpio')
const newWuPin = ref('')
const newWuEdge = ref<WakeupSource['edge']>('rising')
const newWuPeriodS = ref(60)

/* ---- STM32G0B1 WKUP pins ---- */
const WKUP_PINS = ['PA0', 'PC13', 'PE6']

/* ---- Mode description ---- */
const modeDescription = computed(() => {
    switch (mode.value) {
        case 'LowPowerRun': return 'Reduced core clock + regulator VOS Range 2. Peripherals keep running with limited speed.'
        case 'SLEEP':       return 'CPU stopped. All peripherals and clocks remain active. Fastest wake-up.'
        case 'STOP':        return 'HSI/HSE stopped, LSI/LSE kept. GPIO / RTC / LPUART wakeup. ~3 µs exit latency.'
        default:            return ''
    }
})

/* ---- Only show wakeup config for STOP ---- */
const showWakeupConfig = computed(() => mode.value === 'STOP')

/* ---- Only show regulator / flash for Low Power Run ---- */
const showLowPowerRunConfig = computed(() => mode.value === 'LowPowerRun')

/* ---- Emit change ---- */
function emitChange() {
    emit('update-sleep', {
        enabled: enabled.value,
        mode: mode.value,
        enter_on_exit: enterOnExit.value,
        regulator_voltage_scale: regulatorVos.value,
        flash_power_down: flashPowerDown.value,
        wakeup_sources: [...wakeupSources.value],
    })
}

function addWakeup() {
    const src: WakeupSource = { type: newWuType.value }
    if (newWuType.value === 'gpio') {
        src.pin = newWuPin.value || 'PA0'
        src.edge = newWuEdge.value
    }
    if (newWuType.value === 'rtc_wakeup') {
        src.period_s = newWuPeriodS.value
    }
    wakeupSources.value.push(src)
    showAddWakeup.value = false
    emitChange()
}

function removeWakeup(index: number) {
    wakeupSources.value.splice(index, 1)
    emitChange()
}

const MODE_LABELS: Record<string, string> = {
    'LowPowerRun': 'Low Power Run',
    SLEEP: 'Sleep',
    STOP: 'STOP',
}

const WU_TYPE_LABELS: Record<string, string> = {
    gpio: 'GPIO (WKUP pin)',
    rtc_alarm: 'RTC Alarm',
    rtc_wakeup: 'RTC Wakeup Timer',
    lpuart: 'LPUART RX',
    iwdg: 'IWDG Reset',
}
</script>

<template>
    <div class="panel config-panel">
        <div class="panel-title">Low-Power Configuration</div>

        <!-- Enable -->
        <label class="cfg-row toggle-row">
            <span class="cfg-label">Enable Sleep</span>
            <input type="checkbox" v-model="enabled" @change="emitChange" />
        </label>

        <template v-if="enabled">
            <!-- Mode selector -->
            <label class="cfg-label" style="margin-bottom: 0.35rem;">
                <span>Sleep Level</span>
                <select v-model="mode" class="cfg-select" @change="emitChange">
                    <option v-for="(label, key) in MODE_LABELS" :key="key" :value="key">{{ label }}</option>
                </select>
            </label>

            <p class="cfg-hint" v-if="modeDescription">{{ modeDescription }}</p>

            <!-- Low Power Run config -->
            <template v-if="showLowPowerRunConfig">
                <label class="cfg-label">
                    <span>Regulator Voltage Scale (VOS)</span>
                    <select v-model.number="regulatorVos" class="cfg-select" @change="emitChange">
                        <option :value="2">Range 2 (16 MHz, low power)</option>
                        <option :value="3">Range 3 (8 MHz, lowest power)</option>
                    </select>
                </label>
            </template>

            <!-- STOP wakeup config -->
            <template v-if="showWakeupConfig">
                <!-- WFI / Enter on Exit -->
                <label class="cfg-row toggle-row">
                    <span class="cfg-label">Enter Stop on ISR Exit (WFI)</span>
                    <input type="checkbox" v-model="enterOnExit" @change="emitChange" />
                </label>

                <!-- Flash Power Down -->
                <label class="cfg-row toggle-row">
                    <span class="cfg-label">Flash Power-Down in Stop</span>
                    <input type="checkbox" v-model="flashPowerDown" @change="emitChange" />
                </label>

                <!-- Wakeup Sources -->
                <div class="cfg-section-title">
                    Wakeup Sources
                    <button class="btn-add-sm" @click="showAddWakeup = !showAddWakeup">
                        {{ showAddWakeup ? 'Cancel' : '+ Add' }}
                    </button>
                </div>

                <!-- Add wakeup form -->
                <div v-if="showAddWakeup" class="wu-add-form">
                    <select v-model="newWuType" class="cfg-select">
                        <option v-for="(label, key) in WU_TYPE_LABELS" :key="key" :value="key">{{ label }}</option>
                    </select>

                    <template v-if="newWuType === 'gpio'">
                        <select v-model="newWuPin" class="cfg-select">
                            <option v-for="pin in WKUP_PINS" :key="pin" :value="pin">{{ pin }}</option>
                        </select>
                        <select v-model="newWuEdge" class="cfg-select">
                            <option value="rising">Rising Edge</option>
                            <option value="falling">Falling Edge</option>
                            <option value="both">Both Edges</option>
                        </select>
                    </template>

                    <template v-if="newWuType === 'rtc_wakeup'">
                        <label class="cfg-label">
                            <span>Wakeup Period (s)</span>
                            <input v-model.number="newWuPeriodS" type="number" min="1" max="86400" class="cfg-select" />
                        </label>
                    </template>

                    <button class="btn btn-sm btn-primary" @click="addWakeup">Add</button>
                </div>

                <!-- Wakeup source list -->
                <div v-if="wakeupSources.length" class="wu-list">
                    <div v-for="(src, idx) in wakeupSources" :key="idx" class="wu-item">
                        <span class="wu-type-tag">{{ WU_TYPE_LABELS[src.type] ?? src.type }}</span>
                        <span v-if="src.pin" class="wu-detail">Pin {{ src.pin }} ({{ src.edge }})</span>
                        <span v-if="src.period_s" class="wu-detail">every {{ src.period_s }}s</span>
                        <button class="btn-mini btn-remove" @click="removeWakeup(idx)">Remove</button>
                    </div>
                </div>

                <p v-if="!wakeupSources.length && !showAddWakeup" class="wu-empty">
                    No wakeup sources. Add GPIO, RTC, LPUART, or IWDG wakeup.
                </p>
            </template>
        </template>

        <p v-else class="wu-empty">
            Sleep disabled. The MCU will use the default Run mode.
        </p>
    </div>
</template>

<style scoped>
.config-panel {
    background: var(--bg-card);
    border-left: 2px solid #06b6d4;
}

.cfg-label {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    font-size: 0.75rem;
    color: var(--text-dim);
}

.cfg-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.3rem 0;
}
.cfg-row .cfg-label { color: var(--text); }

.toggle-row input[type="checkbox"] { accent-color: var(--accent); }

.cfg-select {
    padding: 5px 8px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg-input);
    color: var(--text);
    font-size: 0.75rem;
    width: 100%;
}
.cfg-select:focus { outline: none; border-color: #06b6d4; }

.cfg-section-title {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.7rem;
    font-weight: 700;
    color: #06b6d4;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding-top: 0.5rem;
    margin-top: 0.25rem;
    border-top: 1px solid var(--border);
}

.btn-add-sm {
    padding: 1px 8px;
    border: 1px solid #06b6d4;
    border-radius: 3px;
    background: transparent;
    color: #06b6d4;
    font-size: 0.6rem;
    font-weight: 600;
    cursor: pointer;
}
.btn-add-sm:hover { background: rgba(6,182,212,0.1); }

.wu-add-form {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    padding: 0.5rem;
    background: var(--bg-input);
    border-radius: 4px;
}
.wu-add-form .cfg-select { width: auto; flex: 1; min-width: 80px; }

.wu-list {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
}
.wu-item {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.25rem 0.4rem;
    background: var(--bg-input);
    border-radius: 4px;
    font-size: 0.65rem;
}
.wu-type-tag {
    font-weight: 600;
    color: #06b6d4;
    background: rgba(6,182,212,0.1);
    padding: 1px 5px;
    border-radius: 2px;
}
.wu-detail {
    color: var(--text-dim);
    font-size: 0.6rem;
}

.btn-mini {
    padding: 1px 6px;
    border: 1px solid var(--border);
    border-radius: 3px;
    background: var(--bg-card);
    color: var(--text-dim);
    cursor: pointer;
    font-size: 0.55rem;
    font-weight: 600;
    margin-left: auto;
}
.btn-mini:hover { border-color: var(--text-dim); color: var(--text); }
.btn-remove { color: #ef4444; border-color: rgba(239,68,68,0.3); }
.btn-remove:hover { background: rgba(239,68,68,0.1); color: #f87171; }

.wu-empty {
    color: var(--text-dim);
    font-size: 0.65rem;
    text-align: center;
    padding: 0.5rem;
}
</style>
