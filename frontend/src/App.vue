<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import type { ParseResponse } from './api'
import { uploadNetlist, generateFirmware } from './api'
import { useHardwareModel } from './composables/useHardwareModel'
import { useTaskModel } from './composables/useTaskModel'
import type { AppTaskModel } from './composables/useTaskModel'
import { useBindModel } from './composables/useBindModel'

import FileUpload from './components/FileUpload.vue'
import TopologyGraph from './components/TopologyGraph.vue'
import PinChip from './components/PinChip.vue'
import PeripheralList from './components/PeripheralList.vue'
import PeripheralConfig from './components/PeripheralConfig.vue'
import TaskAllocator from './components/TaskAllocator.vue'
import BindGraph from './components/BindGraph.vue'
import ClockTree from './components/ClockTree.vue'
import BankPartition from './components/BankPartition.vue'
import PinAfSelector from './components/PinAfSelector.vue'
import StateMachineEditor from './components/StateMachineEditor.vue'
import SleepConfig from './components/SleepConfig.vue'
import YamlEditor from './components/YamlEditor.vue'
import PdfViewer from './components/PdfViewer.vue'
import { validate, type PinAssignment } from './composables/ConstraintEngine'
import { getMcuDocUrls } from './composables/useMcudoc'

// ---- Reactive state ----
const results       = ref<ParseResponse | null>(null)
const loading       = ref(false)
const error         = ref('')
const hardwareYamlRef = ref('')
const taskYamlRef     = ref('')
const componentsYamlRef = ref('')
const bindYamlRef     = ref('')
const paramsYamlRef     = ref('')
const pubsubYamlRef     = ref('')
const selectedPeriIdx = ref(-1)
const generating    = ref(false)
const genError      = ref('')

/** Active tab: 0=Hardware, 1=Tasks, 2=Bind, 3=Behavior, 4=YAML */
const activeTab = ref<'chip' | 'clock' | 'bank' | 'tasks' | 'bind' | 'behavior' | 'yaml'>('chip')

// ---- Six-layer YAML: three layers have structured models; components/params/pubsub are raw YAML for now ----
const {
    model: hwModel,
    writePin, addPin, removePin,
    writePeripheral, addPeripheral, removePeripheral,
    writeSleep, writeClock, writeFlashPartitions,
    loadFromApi: loadHw,
} = useHardwareModel(hardwareYamlRef)

const {
    model: taskModel,
    writeTask, addTask, removeTask, setBehavior, writeHeapSize, writeEventTask, writeProject,
    loadFromApi: loadTask,
} = useTaskModel(taskYamlRef)

const {
    model: bindModel,
    addInterrupt, removeInterrupt,
    addPeripheralAssign, removePeripheralAssign,
    addRouting, removeRouting, writeRouting,
    loadFromApi: loadBind,
} = useBindModel(bindYamlRef)

// ---- Derived view models ----
const viewPins         = computed(() => hwModel.pins)
const viewPeripherals  = computed(() => hwModel.peripherals)
const viewTasks        = computed(() => taskModel.app_tasks)

const selectedPeripheral = computed(() => {
    if (selectedPeriIdx.value < 0 || selectedPeriIdx.value >= hwModel.peripherals.length) return null
    return hwModel.peripherals[selectedPeriIdx.value]
})

/** Peripheral names for task auto-suggestion */
const peripheralNames = computed(() =>
    viewPeripherals.value.map(p => p.name).filter(Boolean)
)

/** Whether RTC peripheral is present */
const hasRtc = computed(() =>
    viewPeripherals.value.some(p => p.type === 'Internal_RTC')
)

/** Selected pin for AF assignment popup */
const selectedPin = ref<string | null>(null)

/** Datasheet PDF viewer */
const showDatasheet = ref(false)
const dsUrls = ref<{ datasheet_url: string | null; reference_manual_url: string | null }>({
    datasheet_url: null,
    reference_manual_url: null,
})

function openDatasheet() {
    const part = hwModel.mcu.part
    if (!part) return
    dsUrls.value = getMcuDocUrls(part)
    showDatasheet.value = true
}

/** Real-time pin constraint validation */
const validationResult = computed(() => {
    const assignments: PinAssignment[] = viewPins.value.map(p => ({
        pinId: p.id,
        function: p.function,
        af: p.af,
    }))
    return validate(assignments)
})

const conflictPins = computed(() =>
    new Set(validationResult.value.issues
        .filter(i => i.severity === 'error')
        .flatMap(i => i.pins))
)

const warningPins = computed(() =>
    new Set(validationResult.value.issues
        .filter(i => i.severity === 'warning')
        .flatMap(i => i.pins))
)

/** Count of constraint issues by severity */
const validationBadge = computed(() => ({
    errors: conflictPins.value.size,
    warnings: warningPins.value.size,
}))

/** EXTI-capable pins for BindGraph */
const extiPins = computed(() =>
    viewPins.value
        .filter(p => p.exti || p.function === 'GPIO_Input' || p.function === 'GPIO_EXTI')
        .map(p => ({ id: p.id, label: p.label }))
)

// ---- Keyboard shortcuts ----
function onKeydown(e: KeyboardEvent) {
    const mod = e.ctrlKey || e.metaKey
    if (!mod) return

    if (e.key === 's' && hardwareYamlRef.value) {
        e.preventDefault()
        downloadYaml()
    }

    if (e.key === 'g' && hardwareYamlRef.value && !generating.value) {
        e.preventDefault()
        handleGenerate()
    }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))

// ---- Handlers ----
async function handleParse(netlistFile: File, bomFile?: File) {
    loading.value = true
    error.value = ''
    selectedPeriIdx.value = -1
    genError.value = ''
    try {
        const data = await uploadNetlist(netlistFile, bomFile)
        results.value = data
        results.value.clock = data.clock ?? undefined

        // Load three-layer YAML into respective models
        loadHw(data.hardware_yaml || data.yaml)
        if (data.task_yaml) {
            loadTask(data.task_yaml)
        }
        componentsYamlRef.value = data.components_yaml || ''
        paramsYamlRef.value = data.params_yaml || ''
        pubsubYamlRef.value = data.pubsub_yaml || ''
        if (data.bind_yaml) {
            loadBind(data.bind_yaml)
        } else if (data.bind) {
            // Generate empty bind from backend BindInfo
            loadBind('')
        }
    } catch (e: any) {
        error.value = e.message || 'Unknown error'
        results.value = null
        hardwareYamlRef.value = ''
        taskYamlRef.value = ''
        componentsYamlRef.value = ''
        bindYamlRef.value = ''
        paramsYamlRef.value = ''
        pubsubYamlRef.value = ''
    } finally {
        loading.value = false
    }
}

function handleSelectPeripheral(index: number) {
    selectedPeriIdx.value = selectedPeriIdx.value === index ? -1 : index
}

function handleRemovePeripheral(index: number) {
    removePeripheral(index)
    if (selectedPeriIdx.value >= hwModel.peripherals.length) {
        selectedPeriIdx.value = -1
    }
}

function handlePeripheralUpdate(field: string, value: unknown) {
    writePeripheral(selectedPeriIdx.value, field as any, value)
}

async function handleGenerate() {
    if (!hardwareYamlRef.value) return
    generating.value = true
    genError.value = ''
    try {
        const blob = await generateFirmware(
            hardwareYamlRef.value,
            taskYamlRef.value,
            componentsYamlRef.value,
            bindYamlRef.value,
            paramsYamlRef.value,
            pubsubYamlRef.value,
        )
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

function downloadYaml() {
    if (!hardwareYamlRef.value) return
    const blob = new Blob([hardwareYamlRef.value], { type: 'application/x-yaml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'hardware.yaml'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
}

// ---- Task handlers ----
function handleAddTask(task: AppTaskModel) {
    addTask(task)
}

function handleUpdateTask(index: number, field: string, value: unknown) {
    writeTask(index, field as any, value)
}

function handleRemoveTask(index: number) {
    removeTask(index)
}

function handleUpdateHeap(size: number) {
    writeHeapSize(size)
}

function handleUpdateEventTask(partial: Record<string, unknown>) {
    writeEventTask(partial as any)
}

/* ---- Project rename ---- */
const editingProject = ref(false)
const editProjectName = ref('')
const projectNameInput = ref<HTMLInputElement | null>(null)

function startProjectRename() {
    editProjectName.value = taskModel.project.name
    editingProject.value = true
    /* Focus after Vue renders the input */
    setTimeout(() => { projectNameInput.value?.focus(); projectNameInput.value?.select() }, 50)
}

function commitProjectRename() {
    editingProject.value = false
    const name = editProjectName.value.trim()
    if (name && name !== taskModel.project.name) {
        writeProject({ name })
    }
}

// ---- Bind handlers ----
function handleAddInterrupt(binding: { pin: string; task: string; event: string }) {
    addInterrupt(binding)
}

function handleRemoveInterrupt(index: number) {
    removeInterrupt(index)
}

function handleAddPeripheralAssign(binding: { peripheral: string; task: string; role: string }) {
    addPeripheralAssign(binding)
}

function handleRemovePeripheralAssign(index: number) {
    removePeripheralAssign(index)
}

function handleAddRouting(binding: { from: string; to: string; signal: string; condition?: string }) {
    addRouting(binding)
}

function handleRemoveRouting(index: number) {
    removeRouting(index)
}

function handleUpdateRouting(index: number, field: string, value: unknown) {
    writeRouting(index, field as any, value)
}

/** Update behavior (state machine) */
function handleUpdateBehavior(newBehavior: Record<string, unknown>) {
    taskModel.behavior = newBehavior as any
    setBehavior(newBehavior as any)
}

/** Pin selection for AF assignment */
function handlePinSelect(pinId: string) {
    selectedPin.value = selectedPin.value === pinId ? null : pinId
}

/** Assign a pin to a new AF function */
function handleAssignFunction(pinId: string, afFunction: string, af: number) {
    const idx = viewPins.value.findIndex(p => p.id === pinId)
    if (idx < 0) return
    writePin(idx, 'function', afFunction)
    writePin(idx, 'af', af)
    selectedPin.value = null
}

/** Update GPIO config from PinAfSelector */
function handleUpdateGpio(pinId: string, field: string, value: unknown) {
    const idx = viewPins.value.findIndex(p => p.id === pinId)
    if (idx < 0) return
    writePin(idx, field as any, value)
}

/** Update sleep / low-power configuration */
function handleUpdateSleep(sleep: import('./composables/useHardwareModel').SleepModel) {
    writeSleep(sleep)
}

function handleUpdateClock(partial: Record<string, unknown>) {
    writeClock(partial as any)
}

function handleUpdateFlashPartitions(partitions: import('./composables/useHardwareModel').FlashPartition[]) {
    writeFlashPartitions(partitions)
}
</script>

<template>
    <div class="app-shell">
        <!-- Header -->
        <header class="header">
            <h1>hw2c web</h1>
            <span class="badge">BETA</span>
            <span class="header-sub">Hardware-to-Code Visual Parser</span>
            <span class="header-spacer"></span>
            <span class="shortcuts-hint">Ctrl+S YAML &middot; Ctrl+G Generate</span>
        </header>

        <!-- Main: two-column layout -->
        <main class="main">
            <!-- LEFT: upload + MCU + topology + peripherals -->
            <aside class="col-left">
                <FileUpload
                    :results="results"
                    :loading="loading"
                    @parse="handleParse"
                />

                <div v-if="error" class="panel error-box">{{ error }}</div>

                <!-- MCU card -->
                <div v-if="hwModel.mcu.part" class="panel mcu-card">
                    <div class="panel-title">MCU</div>
                    <div class="mcu-chip" @click="openDatasheet">
                        <code>{{ hwModel.mcu.part }}</code>
                        <span class="datasheet-icon" title="View Datasheet">&#128196;</span>
                        <span class="tag tag-mcu">{{ hwModel.mcu.core_clock_mhz }} MHz</span>
                    </div>
                    <div v-if="hwModel.mcu.core" class="mcu-core-info">
                        Core: <strong>{{ hwModel.mcu.core }}</strong>
                    </div>
                    <div class="mcu-resources">
                        <div class="mcu-res">
                            <span class="mcu-res-icon">&#9641;</span>
                            <span>Flash: <strong>{{ hwModel.mcu.flash_kb }}</strong> KB</span>
                            <span v-if="hwModel.mcu.dual_bank" class="tag tag-bank">Dual Bank</span>
                        </div>
                        <div class="mcu-res">
                            <span class="mcu-res-icon">&#9731;</span>
                            <span>RAM: <strong>{{ hwModel.mcu.ram_kb }}</strong> KB</span>
                        </div>
                    </div>
                </div>

                <!-- Project info -->
                <div v-if="results?.project" class="panel project-card">
                    <div class="panel-title">Project</div>
                    <div class="project-name" v-if="editingProject" @click.stop>
                        <input
                            ref="projectNameInput"
                            v-model="editProjectName"
                            class="project-name-input"
                            @keyup.enter="commitProjectRename"
                            @keyup.escape="editingProject = false"
                            @blur="commitProjectRename"
                        />
                    </div>
                    <div
                        v-else
                        class="project-name project-name-editable"
                        @click="startProjectRename"
                        title="Click to rename"
                    >{{ taskModel.project.name }}</div>
                    <div class="project-ver">v{{ taskModel.project.version }}</div>
                </div>

                <!-- Topology graph -->
                <TopologyGraph
                    v-if="results?.connections.length"
                    :connections="results.connections"
                    :peripherals="viewPeripherals"
                />

                <!-- Sleep / low-power -->
                <SleepConfig
                    v-if="results"
                    :sleep="hwModel.sleep"
                    @update-sleep="handleUpdateSleep"
                />

                <!-- Peripheral config -->
                <PeripheralConfig
                    v-if="selectedPeripheral"
                    :peripheral="selectedPeripheral"
                    :pins="viewPins"
                    :index="selectedPeriIdx"
                    @update-peripheral="handlePeripheralUpdate"
                    @update-pin="(idx, field, val) => writePin(idx, field, val)"
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

            <!-- CENTER + RIGHT: tabbed content area -->
            <section class="col-tabs" v-if="results">
                <!-- Tab bar -->
                <nav class="tab-bar">
                    <button
                        :class="['tab-btn', { active: activeTab === 'chip' }]"
                        @click="activeTab = 'chip'"
                    >Chip</button>
                    <button
                        :class="['tab-btn', { active: activeTab === 'clock' }]"
                        @click="activeTab = 'clock'"
                        :disabled="!results"
                    >Clock</button>
                    <button
                        :class="['tab-btn', { active: activeTab === 'bank' }]"
                        @click="activeTab = 'bank'"
                        :disabled="!results"
                    >Bank</button>
                    <button
                        :class="['tab-btn', { active: activeTab === 'tasks' }]"
                        @click="activeTab = 'tasks'"
                    >
                        Tasks
                        <span class="tab-count" v-if="viewTasks.length">{{ viewTasks.length }}</span>
                    </button>
                    <button
                        :class="['tab-btn', { active: activeTab === 'bind' }]"
                        @click="activeTab = 'bind'"
                    >
                        Bind
                        <span class="tab-count" v-if="bindModel.interrupt.length || bindModel.routing.length">
                            {{ bindModel.interrupt.length + bindModel.routing.length }}
                        </span>
                    </button>
                    <button
                        :class="['tab-btn', { active: activeTab === 'behavior' }]"
                        @click="activeTab = 'behavior'"
                    >
                        Behavior
                        <span class="tab-count" v-if="taskModel.behavior?.states?.length">
                            {{ taskModel.behavior.states.length }}
                        </span>
                    </button>
                    <button
                        :class="['tab-btn', { active: activeTab === 'yaml' }]"
                        @click="activeTab = 'yaml'"
                    >YAML</button>
                </nav>

                <!-- Tab: Hardware -->
                <div v-show="activeTab === 'chip'" class="tab-content">
                    <!-- Validation badge -->
                    <div v-if="validationBadge.errors || validationBadge.warnings" class="validation-bar">
                        <span v-if="validationBadge.errors" class="val-badge val-error">
                            {{ validationBadge.errors }} pin conflict(s)
                        </span>
                        <span v-if="validationBadge.warnings" class="val-badge val-warn">
                            {{ validationBadge.warnings }} warning(s)
                        </span>
                    </div>

                    <PinChip
                        :pins="viewPins"
                        :conflicts="conflictPins"
                        :warnings="warningPins"
                        @select-pin="handlePinSelect"
                    />
                    <PeripheralList
                        v-if="viewPeripherals.length"
                        :peripherals="viewPeripherals"
                        :pins="viewPins"
                        :selected-index="selectedPeriIdx"
                        @select="handleSelectPeripheral"
                        @remove="handleRemovePeripheral"
                    />
                </div>

                <!-- Tab: Clock -->
                <div v-show="activeTab === 'clock'" class="tab-content">
                    <ClockTree
                        :clock="hwModel.clock"
                        @update-clock="handleUpdateClock"
                    />
                </div>

                <!-- Tab: Bank -->
                <div v-show="activeTab === 'bank'" class="tab-content">
                    <BankPartition
                        :flash-kb="hwModel.mcu.flash_kb"
                        :dual-bank="hwModel.mcu.dual_bank"
                        :partitions="hwModel.flash_partitions"
                        @update-partitions="handleUpdateFlashPartitions"
                    />
                </div>

                <!-- Tab: Tasks -->
                <div v-show="activeTab === 'tasks'" class="tab-content">
                    <TaskAllocator
                        :tasks="viewTasks"
                        :pins="viewPins"
                        :peripheral-names="peripheralNames"
                        :heap-size="taskModel.project.heap_size"
                        :event-task="taskModel.event_task"
                        @add-task="handleAddTask"
                        @remove-task="handleRemoveTask"
                        @update-task="handleUpdateTask"
                        @update-heap="handleUpdateHeap"
                        @update-event-task="handleUpdateEventTask"
                    />
                </div>

                <!-- Tab: Bind -->
                <div v-show="activeTab === 'bind'" class="tab-content">
                    <BindGraph
                        :exti-pins="extiPins"
                        :peripherals="viewPeripherals.map(p => ({ name: p.name, type: p.type }))"
                        :tasks="viewTasks"
                        :bind-interrupt="bindModel.interrupt"
                        :bind-peripheral-assign="bindModel.peripheral_assign"
                        :bind-routing="bindModel.routing"
                        :has-rtc="hasRtc"
                        @add-interrupt="handleAddInterrupt"
                        @remove-interrupt="handleRemoveInterrupt"
                        @add-peripheral-assign="handleAddPeripheralAssign"
                        @remove-peripheral-assign="handleRemovePeripheralAssign"
                        @add-routing="handleAddRouting"
                        @remove-routing="handleRemoveRouting"
                        @update-routing="handleUpdateRouting"
                    />
                </div>

                <!-- Tab: Behavior -->
                <div v-show="activeTab === 'behavior'" class="tab-content">
                    <StateMachineEditor
                        :behavior="taskModel.behavior"
                        @update-behavior="handleUpdateBehavior"
                    />
                </div>

                <!-- Tab: YAML -->
                <div v-show="activeTab === 'yaml'" class="tab-content tab-yaml">
                    <div class="gen-bar">
                        <button
                            class="btn btn-primary btn-gen"
                            :disabled="generating || !hardwareYamlRef"
                            @click="handleGenerate"
                        >
                            <span v-if="generating" class="spinner"></span>
                            {{ generating ? 'Generating...' : 'Generate Firmware' }}
                        </button>
                        <button
                            class="btn btn-icon"
                            :disabled="!hardwareYamlRef"
                            @click="downloadYaml"
                            title="Download YAML (Ctrl+S)"
                        >
                            YAML
                        </button>
                    </div>
                    <div v-if="genError" class="gen-error">{{ genError }}</div>

                    <!-- Six-pane YAML preview -->
                    <div class="yaml-multi-pane">
                        <div class="yaml-pane">
                            <div class="yaml-pane-title">hardware.yaml</div>
                            <YamlEditor v-model="hardwareYamlRef" />
                        </div>
                        <div class="yaml-pane">
                            <div class="yaml-pane-title">task.yaml</div>
                            <YamlEditor v-model="taskYamlRef" />
                        </div>
                        <div class="yaml-pane">
                            <div class="yaml-pane-title">components.yaml</div>
                            <YamlEditor v-model="componentsYamlRef" />
                        </div>
                        <div class="yaml-pane">
                            <div class="yaml-pane-title">bind.yaml</div>
                            <YamlEditor v-model="bindYamlRef" />
                        </div>
                        <div class="yaml-pane">
                            <div class="yaml-pane-title">params.yaml</div>
                            <YamlEditor v-model="paramsYamlRef" />
                        </div>
                        <div class="yaml-pane">
                            <div class="yaml-pane-title">pubsub.yaml</div>
                            <YamlEditor v-model="pubsubYamlRef" />
                        </div>
                    </div>
                </div>
            </section>

            <!-- Pin AF Selector Popup -->
            <PinAfSelector
                v-if="selectedPin"
                :pin-id="selectedPin"
                :pins="viewPins"
                :conflicts="conflictPins"
                @assign-function="handleAssignFunction"
                @update-gpio="handleUpdateGpio"
                @close="selectedPin = null"
            />

            <!-- Empty state -->
            <div class="empty-state" v-if="!results && !loading">
                <div class="empty-state-inner">
                    <h2>Welcome to hw2c web</h2>
                    <p>Drop your EasyEDA Pro netlist (<code>.enet</code>) and BOM (<code>.csv</code>)</p>
                    <p class="dim">Parse &rarr; Hardware &rarr; Tasks &rarr; Bind &rarr; Generate</p>
                </div>
            </div>

            <!-- Loading overlay -->
            <div v-if="loading" class="loading-overlay">
                <div class="loading-card">
                    <span class="spinner spinner-lg"></span>
                    <p>Parsing netlist...</p>
                </div>
            </div>
        </main>

        <!-- Datasheet PDF viewer -->
        <PdfViewer
            v-if="showDatasheet"
            :part="hwModel.mcu.part"
            :datasheet-url="dsUrls.datasheet_url"
            :reference-manual-url="dsUrls.reference_manual_url"
            @close="showDatasheet = false"
        />
    </div>
</template>

<style scoped>
.app-shell { display: flex; flex-direction: column; min-height: 100vh; }
.header-sub { font-size: 0.8rem; color: var(--text-dim); }
.header-spacer { flex: 1; }

/* ---- MCU chip clickable ---- */
.mcu-chip {
    cursor: pointer;
    position: relative;
}
.mcu-chip:hover {
    opacity: 0.85;
}
.mcu-chip:hover .datasheet-icon {
    opacity: 1;
}
.datasheet-icon {
    font-size: 0.85rem;
    margin-left: 0.15rem;
    opacity: 0.4;
    transition: opacity 0.15s;
    vertical-align: middle;
}
.shortcuts-hint {
    font-size: 0.65rem;
    color: var(--text-dim);
    padding: 2px 8px;
    background: var(--bg-input);
    border-radius: 4px;
}

.main {
    flex: 1;
    display: grid;
    grid-template-columns: 280px 1fr;
    gap: 1rem;
    padding: 1rem;
}

.main:has(.empty-state) {
    grid-template-columns: 1fr;
    place-items: center;
}

.main:has(.loading-overlay) {
    position: relative;
}

.col-left   { display: flex; flex-direction: column; gap: 1rem; }
.col-tabs  { display: flex; flex-direction: column; gap: 0; overflow: hidden; min-width: 0; }

/* ---- Tab bar ---- */
.tab-bar {
    display: flex;
    gap: 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 0;
}
.tab-btn {
    padding: 0.5rem 1rem;
    border: none;
    border-bottom: 2px solid transparent;
    background: transparent;
    color: var(--text-dim);
    font-size: 0.8rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s;
    display: flex;
    align-items: center;
    gap: 0.35rem;
}
.tab-btn:hover { color: var(--text); }
.tab-btn.active {
    color: var(--accent);
    border-bottom-color: var(--accent);
}
.tab-count {
    font-size: 0.6rem;
    background: var(--accent);
    color: #fff;
    border-radius: 99px;
    padding: 0 5px;
    line-height: 1.4;
}

/* ---- Tab content ---- */
.tab-content {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 1rem;
    padding: 1rem 0 0 0;
}

/* Validation bar */
.validation-bar {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
}
.val-badge {
    font-size: 0.65rem;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 99px;
}
.val-error {
    background: rgba(239,68,68,0.15);
    color: #f87171;
    border: 1px solid rgba(239,68,68,0.4);
}
.val-warn {
    background: rgba(245,158,11,0.12);
    color: #fbbf24;
    border: 1px solid rgba(245,158,11,0.35);
}
.tab-yaml {
    padding-top: 0.5rem;
}

.gen-bar { display: flex; gap: 0.4rem; margin-bottom: 0.5rem; }
.btn-gen { flex: 1; text-align: center; justify-content: center; font-weight: 600; }
.btn-icon {
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--bg-input);
    color: var(--text-dim);
    cursor: pointer;
    font-size: 0.75rem;
    font-weight: 600;
    transition: all 0.15s;
}
.btn-icon:hover {
    background: var(--accent-hover);
    border-color: var(--accent);
    color: #fff;
}
.btn-icon:disabled { opacity: 0.4; cursor: default; }

.gen-error {
    color: var(--red); font-size: 0.75rem; padding: 0.5rem;
    background: rgba(239,68,68,0.1); border: 1px solid var(--red); border-radius: var(--radius);
    margin-bottom: 0.5rem;
}

/* Six-pane YAML layout */
.yaml-multi-pane {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    grid-auto-rows: minmax(180px, 1fr);
    gap: 0.5rem;
    flex: 1;
    min-height: 0;
}
.yaml-pane {
    display: flex;
    flex-direction: column;
    min-width: 0;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
}
.yaml-pane-title {
    font-size: 0.7rem;
    font-weight: 700;
    color: var(--text-dim);
    padding: 4px 8px;
    background: var(--bg-input);
    border-bottom: 1px solid var(--border);
    font-family: monospace;
}

.error-box { color: var(--red); font-size: 0.8rem; border-color: var(--red); }

.mcu-card { text-align: center; }
.mcu-chip { display: flex; align-items: center; justify-content: center; gap: 0.5rem; margin-bottom: 0.4rem; }
.mcu-chip code { font-size: 0.95rem; font-weight: 700; }
.mcu-core-info {
    font-size: 0.7rem;
    color: var(--text-dim);
    margin-bottom: 0.4rem;
}
.mcu-core-info strong { color: var(--accent); }
.mcu-resources { display: flex; flex-direction: column; gap: 0.3rem; }
.mcu-res { display: flex; align-items: center; gap: 0.4rem; font-size: 0.75rem; color: var(--text-dim); }
.mcu-res-icon { font-size: 0.65rem; color: var(--blue); }
.mcu-res strong { color: var(--text); }

.project-card { text-align: center; }
.project-name { font-size: 1rem; font-weight: 700; }
.project-name-editable { cursor: pointer; transition: color 0.15s; }
.project-name-editable:hover { color: var(--accent); }
.project-name-input {
    font-size: 1rem; font-weight: 700; text-align: center;
    background: var(--bg-input); color: var(--text);
    border: 1px solid var(--accent); border-radius: 4px;
    padding: 2px 8px; width: 100%; outline: none;
    font-family: inherit;
}
.project-ver { font-size: 0.7rem; color: var(--text-dim); }

.tag-mcu {
    background: var(--bg-input); color: var(--text); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 1px 6px; font-size: 0.65rem; font-weight: 600;
}
.tag-bank {
    background: rgba(59,130,246,0.15); color: var(--blue); border-radius: var(--radius);
    padding: 0 4px; font-size: 0.55rem; font-weight: 600;
}

.hint-chips { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.chip {
    display: inline-flex; align-items: center; gap: 0.3rem;
    padding: 3px 8px; background: var(--bg-input); border-radius: 99px; font-size: 0.75rem;
}

/* Spinner */
.spinner {
    display: inline-block;
    width: 14px; height: 14px;
    border: 2px solid rgba(255,255,255,0.3);
    border-top-color: #fff;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
    margin-right: 0.35rem;
    vertical-align: middle;
}
.spinner-lg { width: 24px; height: 24px; border-width: 3px; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Loading overlay */
.loading-overlay {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(15,20,25,0.8);
    z-index: 10;
}
.loading-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
    padding: 2rem;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
}
.loading-card p {
    font-size: 0.9rem;
    color: var(--text-dim);
}

.empty-state { display: flex; align-items: center; justify-content: center; min-height: 60vh; }
.empty-state-inner { text-align: center; color: var(--text-dim); }
.empty-state-inner h2 { font-size: 1.5rem; color: var(--text); margin-bottom: 0.5rem; }
.empty-state-inner p { margin-bottom: 0.25rem; }
.empty-state-inner code { background: var(--bg-input); padding: 1px 4px; border-radius: 3px; }
.dim { font-size: 0.8rem; }
</style>
