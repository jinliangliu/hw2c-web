<script setup lang="ts">
import { ref, computed } from 'vue'
import type { ParseResponse } from './api'
import { uploadNetlist, generateFirmware } from './api'
import { useHardwareModel } from './composables/useHardwareModel'

import FileUpload from './components/FileUpload.vue'
import TopologyGraph from './components/TopologyGraph.vue'
import PinTable from './components/PinTable.vue'
import PeripheralList from './components/PeripheralList.vue'
import PeripheralConfig from './components/PeripheralConfig.vue'
import YamlEditor from './components/YamlEditor.vue'

// ---- Reactive state ----
const results    = ref<ParseResponse | null>(null)
const loading   = ref(false)
const error     = ref('')
const yamlRef   = ref('')
const selectedPeriIdx = ref(-1)
const generating = ref(false)
const genError = ref('')

const { model, writePin, addPin, removePin, writePeripheral, addPeripheral, removePeripheral, writeTask, addTask, removeTask, loadFromApi } = useHardwareModel(yamlRef)

// Derived view models (read from reactive model for live-updating UI)
const viewPins = computed(() => model.pins)
const viewPeripherals = computed(() => model.peripherals)

// Selected peripheral (null if none selected)
const selectedPeripheral = computed(() => {
    if (selectedPeriIdx.value < 0 || selectedPeriIdx.value >= model.peripherals.length) return null
    return model.peripherals[selectedPeriIdx.value]
})

// ---- Handlers ----
async function handleParse(netlistFile: File, bomFile?: File) {
    loading.value = true
    error.value = ''
    selectedPeriIdx.value = -1
    try {
        const data = await uploadNetlist(netlistFile, bomFile)
        results.value = data
        loadFromApi(data.yaml)
    } catch (e: any) {
        error.value = e.message || 'Unknown error'
        results.value = null
        yamlRef.value = ''
    } finally {
        loading.value = false
    }
}

function handleSelectPeripheral(index: number) {
    selectedPeriIdx.value = selectedPeriIdx.value === index ? -1 : index
}

function handleRemovePeripheral(index: number) {
    removePeripheral(index)
    if (selectedPeriIdx.value >= model.peripherals.length) {
        selectedPeriIdx.value = -1
    }
}

function handlePeripheralUpdate(field: string, value: unknown) {
    writePeripheral(selectedPeriIdx.value, field as any, value)
}

function handlePinUpdate(pinIndex: number, field: string, value: unknown) {
    writePin(pinIndex, field as any, value)
}

async function handleGenerate() {
    if (!yamlRef.value) return
    generating.value = true
    genError.value = ''
    try {
        const blob = await generateFirmware(yamlRef.value)
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'hw2c_firmware.zip'
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
    } catch (e: any) {
        genError.value = e.message || 'Generation failed'
    } finally {
        generating.value = false
    }
}
</script>

<template>
    <div class="app-shell">
        <!-- Header -->
        <header class="header">
            <h1>hw2c web</h1>
            <span class="badge">BETA</span>
            <span class="header-sub">Hardware-to-Code Visual Parser</span>
        </header>

        <!-- Main: three-column layout -->
        <main class="main">
            <!-- LEFT: upload + peripherals + resource tree -->
            <aside class="col-left">
                <FileUpload
                    :results="results"
                    :loading="loading"
                    @parse="handleParse"
                />

                <div v-if="error" class="panel error-box">{{ error }}</div>

                <!-- MCU card -->
                <div v-if="model.mcu.part" class="panel mcu-card">
                    <div class="panel-title">MCU</div>
                    <div class="mcu-chip">
                        <code>{{ model.mcu.part }}</code>
                        <span class="tag tag-spi">{{ model.mcu.core_clock_mhz }} MHz</span>
                    </div>
                </div>

                <!-- Peripheral list -->
                <PeripheralList
                    v-if="viewPeripherals.length"
                    :peripherals="viewPeripherals"
                    :selected-index="selectedPeriIdx"
                    @select="handleSelectPeripheral"
                    @remove="handleRemovePeripheral"
                />

                <!-- Peripheral config (shown when a peripheral is selected) -->
                <PeripheralConfig
                    v-if="selectedPeripheral"
                    :peripheral="selectedPeripheral"
                    :pins="viewPins"
                    :index="selectedPeriIdx"
                    @update-peripheral="handlePeripheralUpdate"
                    @update-pin="handlePinUpdate"
                />

                <!-- Bus hints -->
                <div v-if="results?.annotations.bus_hints.length" class="panel">
                    <div class="panel-title">Bus Hints</div>
                    <div class="hint-chips">
                        <span
                            v-for="hint in results.annotations.bus_hints"
                            :key="hint.bus_name"
                            class="chip"
                        >
                            <span class="tag tag-spi" v-if="hint.bus_type === 'SPI'">SPI</span>
                            <span class="tag tag-i2c" v-else-if="hint.bus_type === 'I2C'">I2C</span>
                            <span class="tag tag-uart" v-else>{{ hint.bus_type }}</span>
                            {{ hint.bus_name }}
                        </span>
                    </div>
                </div>
            </aside>

            <!-- CENTER: topology + pin table -->
            <section class="col-center" v-if="results">
                <TopologyGraph
                    :connections="results.connections"
                    :peripherals="viewPeripherals"
                />

                <PinTable
                    :pins="viewPins"
                    @edit-pin="(idx, field, val) => writePin(idx, field, val)"
                />
            </section>

            <!-- RIGHT: YAML editor -->
            <aside class="col-right" v-if="results">
                <div class="gen-bar">
                    <button
                        class="btn btn-primary btn-gen"
                        :disabled="generating || !yamlRef"
                        @click="handleGenerate"
                    >
                        {{ generating ? 'Generating...' : 'Generate Firmware' }}
                    </button>
                </div>
                <div v-if="genError" class="gen-error">{{ genError }}</div>
                <YamlEditor v-model="yamlRef" />
            </aside>

            <!-- Empty state -->
            <div class="empty-state" v-if="!results && !loading">
                <div class="empty-state-inner">
                    <h2>Welcome to hw2c web</h2>
                    <p>Drop your EasyEDA Pro netlist (<code>.enet</code>) and BOM (<code>.csv</code>)</p>
                    <p class="dim">Parse → Edit YAML → Generate firmware</p>
                </div>
            </div>
        </main>
    </div>
</template>

<style scoped>
.app-shell { display: flex; flex-direction: column; min-height: 100vh; }
.header-sub { font-size: 0.8rem; color: var(--text-dim); }

.main {
    flex: 1;
    display: grid;
    grid-template-columns: 280px 1fr 420px;
    gap: 1rem;
    padding: 1rem;
}

.main:has(.empty-state) {
    grid-template-columns: 1fr;
    place-items: center;
}

.col-left   { display: flex; flex-direction: column; gap: 1rem; }
.col-center { display: flex; flex-direction: column; gap: 1rem; overflow: hidden; }
.col-right  { display: flex; flex-direction: column; gap: 0.5rem; }

.gen-bar { display: flex; }
.btn-gen { flex: 1; text-align: center; justify-content: center; font-weight: 600; }
.gen-error {
    color: var(--red); font-size: 0.75rem; padding: 0.5rem;
    background: rgba(239,68,68,0.1); border: 1px solid var(--red); border-radius: var(--radius);
}

.error-box { color: var(--red); font-size: 0.8rem; border-color: var(--red); }

.mcu-card { text-align: center; }
.mcu-chip { display: flex; align-items: center; justify-content: center; gap: 0.5rem; }
.mcu-chip code { font-size: 1rem; font-weight: 700; }

.hint-chips { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.chip {
    display: inline-flex; align-items: center; gap: 0.3rem;
    padding: 3px 8px; background: var(--bg-input); border-radius: 99px; font-size: 0.75rem;
}

.empty-state { display: flex; align-items: center; justify-content: center; min-height: 60vh; }
.empty-state-inner { text-align: center; color: var(--text-dim); }
.empty-state-inner h2 { font-size: 1.5rem; color: var(--text); margin-bottom: 0.5rem; }
.empty-state-inner p { margin-bottom: 0.25rem; }
.empty-state-inner code { background: var(--bg-input); padding: 1px 4px; border-radius: 3px; }
.dim { font-size: 0.8rem; }
</style>
