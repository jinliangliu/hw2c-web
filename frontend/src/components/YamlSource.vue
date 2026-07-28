<script setup lang="ts">
defineProps<{ yaml: string }>()
</script>

<template>
    <div class="panel yaml-viewer">
        <div class="panel-title">Generated YAML</div>
        <pre v-if="yaml"><code>{{ yaml }}</code></pre>
        <p v-else class="empty">Parse a netlist to see the generated YAML</p>
    </div>
</template>

<style scoped>
.yaml-viewer { max-height: 400px; overflow: auto; }
pre {
    font-family: 'Cascadia Code', 'Fira Code', 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-all;
}
code { color: var(--text); }
.empty { color: var(--text-dim); font-size: 0.8rem; text-align: center; padding: 1rem; }
</style>
