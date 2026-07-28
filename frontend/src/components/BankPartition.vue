<script setup lang="ts">
/**
 * BankPartition.vue — Flash bank partition editor.
 *
 * Visualises BANK1/BANK2 for dual-bank MCUs (or single bank).
 * Allows the user to define named partitions (BOOT, APP, etc.)
 * with start offset and size, rendered as a proportional bar chart.
 * STM32 flash base: 0x0800 0000.
 */
import { computed, ref, reactive, watch } from 'vue'

/* ---- Partition data model ---- */
interface FlashPartition {
    name: string
    bank: number
    offset_kb: number
    size_kb: number
}

const props = defineProps<{
    flashKb: number
    dualBank: boolean
    partitions: FlashPartition[]
}>()

const emit = defineEmits<{
    (e: 'update-partitions', partitions: FlashPartition[]): void
}>()

/* ---- Derived constants ---- */
const FLASH_BASE = 0x08000000
const bankCount = computed(() => props.dualBank ? 2 : 1)
const bankSizeKb = computed(() => Math.floor(props.flashKb / bankCount.value))
const bankSizeBytes = computed(() => bankSizeKb.value * 1024)

/* ---- Bank info ---- */
interface BankInfo {
    index: number
    label: string
    baseAddr: number
    endAddr: number
    sizeKb: number
}
const banks = computed<BankInfo[]>(() => {
    const list: BankInfo[] = []
    for (let i = 0; i < bankCount.value; i++) {
        list.push({
            index: i + 1,
            label: `BANK ${i + 1}`,
            baseAddr: FLASH_BASE + i * bankSizeBytes.value,
            endAddr: FLASH_BASE + (i + 1) * bankSizeBytes.value - 1,
            sizeKb: bankSizeKb.value,
        })
    }
    return list
})

/* ---- Get partitions by bank ---- */
function bankPartitions(bank: number): FlashPartition[] {
    return props.partitions.filter(p => p.bank === bank)
}

function usedKb(bank: number): number {
    return bankPartitions(bank).reduce((sum, p) => sum + p.size_kb, 0)
}

function freeKb(bank: number): number {
    return bankSizeKb.value - usedKb(bank)
}

/* ---- Auto-default partitions on first load ---- */
let defaultsSeeded = false

watch(
    () => props.flashKb,
    (kb) => {
        if (kb <= 0 || defaultsSeeded || props.partitions.length > 0) return
        defaultsSeeded = true

        const b1Size = Math.floor(kb / (props.dualBank ? 2 : 1))
        const bootSizeKb = 8  // 8 KB for BOOT partitions

        const defaults: FlashPartition[] = [
            { name: 'BOOT1', bank: 1, offset_kb: 0, size_kb: bootSizeKb },
            { name: 'APP',   bank: 1, offset_kb: bootSizeKb, size_kb: b1Size - bootSizeKb },
        ]

        if (props.dualBank) {
            defaults.push(
                { name: 'BOOT2', bank: 2, offset_kb: 0, size_kb: bootSizeKb },
            )
        }

        emit('update-partitions', defaults)
    },
    { immediate: true }
)

/* ---- Color palette ---- */
const PART_COLORS = [
    { bg: '#3b82f6', text: '#bfdbfe' },   // blue
    { bg: '#22c55e', text: '#bbf7d0' },   // green
    { bg: '#f59e0b', text: '#fde68a' },   // amber
    { bg: '#ef4444', text: '#fecaca' },   // red
    { bg: '#a855f7', text: '#e9d5ff' },   // purple
    { bg: '#06b6d4', text: '#a5f3fc' },   // cyan
]
const partColors = reactive<Record<string, typeof PART_COLORS[number]>>({})

function colorFor(name: string, idx: number) {
    if (!partColors[name]) {
        partColors[name] = PART_COLORS[idx % PART_COLORS.length]
    }
    return partColors[name]
}

/* ---- Add / remove partitions ---- */
const showAddForm = ref(false)
const newPartName = ref('')
const newPartBank = ref(1)
const newPartOffsetKb = ref(0)
const newPartSizeKb = ref(32)

function openAddForm(bank: number) {
    showAddForm.value = true
    newPartBank.value = bank
    newPartName.value = ''
    newPartOffsetKb.value = usedKb(bank)
    newPartSizeKb.value = Math.min(64, freeKb(bank))
}

function addPartition() {
    if (!newPartName.value.trim() || newPartSizeKb.value <= 0) return
    if (newPartOffsetKb.value + newPartSizeKb.value > bankSizeKb.value) return
    const updated = [...props.partitions, {
        name: newPartName.value.trim(),
        bank: newPartBank.value,
        offset_kb: newPartOffsetKb.value,
        size_kb: newPartSizeKb.value,
    }]
    emit('update-partitions', updated)
    showAddForm.value = false
}

function removePartition(index: number) {
    const updated = [...props.partitions]
    updated.splice(
        updated.findIndex((_, i) => i === index),
        1
    )
    // Actually, the index passed is global. Let me use filter approach.
    emit('update-partitions', props.partitions.filter((_, i) => i !== index))
}

/* ---- Format helpers ---- */
function fmtHex(addr: number): string {
    return '0x' + addr.toString(16).toUpperCase().padStart(8, '0')
}
function fmtKb(kb: number): string {
    return kb >= 1 ? kb.toFixed(0) + ' KB' : (kb * 1024).toFixed(0) + ' B'
}

/* ---- Partition width as % of bar ---- */
function partWidthPct(sizeKb: number): number {
    return Math.max(1, (sizeKb / bankSizeKb.value) * 100)
}
function partOffsetPct(offsetKb: number): number {
    return (offsetKb / bankSizeKb.value) * 100
}
</script>

<template>
    <div class="bank-editor">
        <!-- Dual bank notice -->
        <div v-if="dualBank" class="dual-notice">
            Dual Bank: {{ bankSizeKb }} KB / bank
        </div>

        <!-- Bank columns -->
        <div class="bank-columns" :class="{ single: !dualBank }">
            <div v-for="bank in banks" :key="bank.index" class="bank-col">
                <!-- Bank header -->
                <div class="bank-header">
                    <span class="bank-label">{{ bank.label }}</span>
                    <code class="bank-addr">{{ fmtHex(bank.baseAddr) }} – {{ fmtHex(bank.endAddr) }}</code>
                    <span class="bank-free" :class="{ warn: freeKb(bank.index) < 16 }">
                        {{ freeKb(bank.index) }} KB free
                    </span>
                </div>

                <!-- Partition bar -->
                <div class="bank-bar">
                    <!-- Free space background -->
                    <div
                        v-if="freeKb(bank.index) > 0"
                        class="bank-free-bg"
                        :style="{ left: partOffsetPct(usedKb(bank.index)) + '%', width: partWidthPct(freeKb(bank.index)) + '%' }"
                    />

                    <!-- Partition blocks -->
                    <div
                        v-for="(p, pi) in bankPartitions(bank.index)"
                        :key="p.name + pi"
                        class="bank-part"
                        :style="{
                            left: partOffsetPct(p.offset_kb) + '%',
                            width: partWidthPct(p.size_kb) + '%',
                            background: colorFor(p.name, pi).bg,
                        }"
                        :title="`${p.name}: ${fmtKb(p.size_kb)} @ offset ${p.offset_kb} KB`"
                    >
                        <span :style="{ color: colorFor(p.name, pi).text }">{{ p.name }}</span>
                        <span class="bank-part-size" :style="{ color: colorFor(p.name, pi).text }">
                            {{ fmtKb(p.size_kb) }}
                        </span>
                    </div>
                </div>

                <!-- Partition table -->
                <div class="bank-table" v-if="bankPartitions(bank.index).length">
                    <div
                        v-for="(p, pi) in bankPartitions(bank.index)"
                        :key="p.name + pi"
                        class="bank-table-row"
                    >
                        <span class="bt-name">
                            <span class="bt-dot" :style="{ background: colorFor(p.name, pi).bg }"></span>
                            {{ p.name }}
                        </span>
                        <code class="bt-offset">{{ fmtHex(bank.baseAddr + p.offset_kb * 1024) }}</code>
                        <span class="bt-size">{{ fmtKb(p.size_kb) }}</span>
                        <button
                            class="bt-remove"
                            @click="removePartition(props.partitions.indexOf(p))"
                            title="Remove"
                        >x</button>
                    </div>
                </div>

                <!-- Add partition button -->
                <button
                    class="bank-add-btn"
                    @click="openAddForm(bank.index)"
                    :disabled="freeKb(bank.index) <= 0"
                >
                    + Add Partition
                </button>
            </div>
        </div>

        <!-- Add form (floating) -->
        <div v-if="showAddForm" class="add-overlay" @click.self="showAddForm = false">
            <div class="add-card">
                <div class="add-card-head">Add Partition to BANK {{ newPartBank }}</div>

                <label class="add-field">
                    <span>Name</span>
                    <input v-model="newPartName" placeholder="e.g. BOOT1, APP" class="input" @keydown.enter="addPartition" />
                </label>

                <label class="add-field">
                    <span>Offset (KB from bank start)</span>
                    <input v-model.number="newPartOffsetKb" type="number" min="0" :max="bankSizeKb" class="input" />
                </label>

                <label class="add-field">
                    <span>Size (KB)</span>
                    <input v-model.number="newPartSizeKb" type="number" min="1" :max="freeKb(newPartBank)" class="input" />
                </label>

                <div class="add-actions">
                    <button class="btn btn-sm btn-ghost" @click="showAddForm = false">Cancel</button>
                    <button class="btn btn-sm btn-primary" @click="addPartition">Add</button>
                </div>
            </div>
        </div>

        <!-- Empty state -->
        <div v-if="!partitions.length && !showAddForm" class="bank-empty">
            <p v-if="dualBank">
                Dual Bank detected ({{ flashKb }} KB total).<br />
                Define BOOT and APP partitions for each bank to plan your firmware layout.
            </p>
            <p v-else>
                {{ flashKb }} KB single-bank flash.<br />
                Add partitions to define your firmware memory layout.
            </p>
        </div>
    </div>
</template>

<style scoped>
.bank-editor {
    display: flex;
    flex-direction: column;
    gap: 1rem;
}

/* Dual bank notice */
.dual-notice {
    text-align: center;
    font-size: 0.65rem;
    font-weight: 600;
    color: #06b6d4;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 0.3rem;
    background: rgba(6,182,212,0.08);
    border-radius: 4px;
    border: 1px solid rgba(6,182,212,0.2);
}

/* Bank columns */
.bank-columns {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
}
.bank-columns.single {
    grid-template-columns: 1fr;
    max-width: 500px;
}

.bank-col {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
}

/* Bank header */
.bank-header {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.4rem;
}
.bank-label {
    font-size: 0.8rem;
    font-weight: 700;
    color: var(--text);
    letter-spacing: 0.5px;
}
.bank-addr {
    font-size: 0.6rem;
    color: var(--text-dim);
    background: var(--bg-input);
    padding: 1px 5px;
    border-radius: 3px;
}
.bank-free {
    font-size: 0.6rem;
    color: #22c55e;
    margin-left: auto;
}
.bank-free.warn {
    color: #f59e0b;
}

/* Partition bar */
.bank-bar {
    position: relative;
    height: 28px;
    background: var(--bg-input);
    border-radius: 4px;
    overflow: hidden;
    border: 1px solid var(--border);
}

.bank-free-bg {
    position: absolute;
    top: 0; bottom: 0;
    background: repeating-linear-gradient(
        -45deg,
        transparent,
        transparent 4px,
        rgba(148,163,184,0.06) 4px,
        rgba(148,163,184,0.06) 8px
    );
    border-radius: 2px;
}

.bank-part {
    position: absolute;
    top: 0; bottom: 0;
    border-radius: 2px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-direction: column;
    cursor: default;
    overflow: hidden;
    min-width: 0;
    font-size: 0.55rem;
    font-weight: 700;
    letter-spacing: 0.3px;
    text-transform: uppercase;
}
.bank-part-size {
    font-size: 0.45rem;
    font-weight: 400;
    opacity: 0.8;
}

/* Partition table */
.bank-table {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
}
.bank-table-row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.25rem 0.4rem;
    background: var(--bg-input);
    border-radius: 4px;
    font-size: 0.65rem;
}
.bt-name {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    font-weight: 600;
    min-width: 60px;
}
.bt-dot {
    width: 7px; height: 7px;
    border-radius: 2px;
    flex-shrink: 0;
}
.bt-offset {
    font-size: 0.6rem;
    color: var(--text-dim);
}
.bt-size {
    font-size: 0.6rem;
    color: var(--text-dim);
    margin-left: auto;
}
.bt-remove {
    border: none;
    background: none;
    color: #ef4444;
    cursor: pointer;
    font-weight: 700;
    font-size: 0.7rem;
    padding: 0 3px;
    line-height: 1;
}
.bt-remove:hover { color: #f87171; }

/* Add button */
.bank-add-btn {
    padding: 0.35rem;
    border: 1px dashed var(--border);
    border-radius: 4px;
    background: transparent;
    color: var(--text-dim);
    font-size: 0.65rem;
    cursor: pointer;
    transition: border-color 0.2s;
}
.bank-add-btn:hover:not(:disabled) {
    border-color: var(--accent);
    color: var(--accent);
}
.bank-add-btn:disabled {
    opacity: 0.3;
    cursor: not-allowed;
}

/* Add form overlay */
.add-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
}
.add-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1rem;
    width: 320px;
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    box-shadow: 0 8px 24px rgba(0,0,0,0.3);
}
.add-card-head {
    font-size: 0.8rem;
    font-weight: 700;
    color: var(--text);
    margin-bottom: 0.2rem;
}
.add-field {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    font-size: 0.65rem;
    color: var(--text-dim);
}
.input {
    padding: 5px 8px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg-input);
    color: var(--text);
    font-size: 0.78rem;
    font-family: monospace;
}
.input:focus { outline: none; border-color: var(--accent); }
.add-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.4rem;
    margin-top: 0.3rem;
}

.bank-empty {
    text-align: center;
    padding: 2rem 1rem;
    color: var(--text-dim);
    font-size: 0.75rem;
    line-height: 1.6;
}
</style>
