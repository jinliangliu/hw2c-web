<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
    results: import('../api').ParseResponse | null
    loading: boolean
}>()

const emit = defineEmits<{
    (e: 'parse', netlist: File, bom?: File): void
}>()

const hint = computed(() => {
    if (props.results) return `${props.results.pins.length} pins, ${props.results.peripherals.length} peripherals`
    return 'Drop .enet + .csv files here, or click to browse'
})

type DropState = 'idle' | 'drag' | 'loading' | 'done'
</script>

<template>
    <label
        class="dropzone panel"
        :class="{ 'dropzone-drag': false, 'dropzone-done': results }"
        @dragover.prevent
        @drop.prevent="(e: DragEvent) => {
            const files = e.dataTransfer?.files
            if (!files?.length) return
            const netlist = [...files].find(f => f.name.endsWith('.enet') || f.name.endsWith('.net'))
            const bom = [...files].find(f => f.name.endsWith('.csv'))
            if (netlist) emit('parse', netlist, bom)
        }"
    >
        <input
            type="file"
            accept=".enet,.net,.csv"
            multiple
            hidden
            @change="(e: Event) => {
                const files = (e.target as HTMLInputElement).files
                if (!files?.length) return
                const arr = [...files]
                const netlist = arr.find(f => f.name.endsWith('.enet') || f.name.endsWith('.net'))
                const bom = arr.find(f => f.name.endsWith('.csv'))
                if (netlist) emit('parse', netlist, bom)
            }"
            ref="fileInput"
        />
        <div class="dropzone-content">
            <div class="dropzone-icon">
                <template v-if="results">&#10003;</template>
                <template v-else-if="loading">&#8987;</template>
                <template v-else>&#8682;</template>
            </div>
            <p class="dropzone-hint">{{ hint }}</p>
            <p class="dropzone-sub" v-if="!results">
                Supported: EasyEDA Pro .enet, KiCad .net
            </p>
        </div>
    </label>
</template>

<style scoped>
.dropzone {
    border: 2px dashed var(--border);
    border-radius: var(--radius);
    padding: 2.5rem 1.5rem;
    text-align: center;
    cursor: pointer;
    transition: border-color 0.2s, background 0.2s;
    min-height: 160px;
    display: flex;
    align-items: center;
    justify-content: center;
}
.dropzone:hover {
    border-color: var(--accent);
    background: rgba(59,130,246,0.05);
}
.dropzone-done {
    border-color: var(--green);
    border-style: solid;
}
.dropzone-icon {
    font-size: 2rem;
    margin-bottom: 0.5rem;
    color: var(--text-dim);
}
.dropzone-done .dropzone-icon { color: var(--green); }
.dropzone-hint { font-size: 0.9rem; margin-bottom: 0.25rem; }
.dropzone-sub { font-size: 0.7rem; color: var(--text-dim); }
</style>
